"""Database backups: snapshots, pruning, checks on uploaded files, a restore round trip, and admin-only access."""

import datetime as dt
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from app.db.migrate import upgrade_to_head
from app.db.session import build_engine
from app.services import backups as backups_module
from app.services.backups import BackupError, BackupService


@pytest.fixture
def live(tmp_path: Path) -> Iterator[tuple[Engine, BackupService]]:
    url = f"sqlite:///{(tmp_path / 'live.db').as_posix()}"
    upgrade_to_head(url)
    engine = build_engine(url)
    try:
        yield engine, BackupService(engine, tmp_path / "data")
    finally:
        engine.dispose()


def _users(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return list(connection.scalars(text("SELECT email FROM users ORDER BY email")))


def _add_user(engine: Engine, email: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (email, display_name, base_currency, is_admin, is_active, totp_enabled,"
                " failed_logins, created_at) VALUES (:email, 'x', 'CHF', 0, 1, 0, 0, '2026-01-01 00:00:00')"
            ),
            {"email": email},
        )


def test_snapshot_restore_round_trip(live: tuple[Engine, BackupService]) -> None:
    engine, service = live
    _add_user(engine, "before@example.com")
    backup = service.create("manual")
    assert [b.name for b in service.list()] == [backup.name]
    assert backup.kind == "manual"
    assert backup.size > 0

    _add_user(engine, "after@example.com")  # a change the restore should undo
    safety = service.restore(service.path(backup.name))
    assert _users(engine) == ["before@example.com"]
    assert safety.kind == "before-restore"
    # The safety copy holds what was there just before.
    with closing(sqlite3.connect(service.path(safety.name))) as copy:
        emails = sorted(row[0] for row in copy.execute("SELECT email FROM users"))
    assert emails == ["after@example.com", "before@example.com"]


def test_uploads_that_are_not_jacklyn_backups_are_refused(live: tuple[Engine, BackupService], tmp_path: Path) -> None:
    _, service = live
    junk = tmp_path / "notes.db"
    junk.write_bytes(b"hello, not a database")
    with pytest.raises(BackupError, match="not an SQLite database"):
        service.check(junk)

    other = tmp_path / "other.db"
    with closing(sqlite3.connect(other)) as connection:
        connection.execute("CREATE TABLE things (id INTEGER)")
    with pytest.raises(BackupError, match="isn't a Jacklyn backup"):
        service.check(other)

    newer = service.path(service.create().name)
    with closing(sqlite3.connect(newer)) as connection:
        connection.execute("UPDATE alembic_version SET version_num = '9999'")
        connection.commit()
    with pytest.raises(BackupError, match="newer Jacklyn version"):
        service.check(newer)


def test_daily_snapshots_and_pruning(live: tuple[Engine, BackupService], monkeypatch: pytest.MonkeyPatch) -> None:
    _, service = live
    first = service.backup_if_due()
    assert first is not None
    assert first.kind == "daily"
    assert service.backup_if_due() is None  # not yet a day old
    # A day later (the newest daily one is from yesterday): due again.
    yesterday = (first.created_at - dt.timedelta(days=1, minutes=1)).strftime("%Y%m%d-%H%M%S")
    service.path(first.name).rename(service.folder / f"jacklyn-{yesterday}-daily.db")
    again = service.backup_if_due()
    assert again is not None
    assert again.kind == "daily"

    monkeypatch.setattr(backups_module, "KEEP_AUTOMATIC", 2)
    service.folder.joinpath("jacklyn-20200101-000000-daily.db").write_bytes(b"old")
    service.folder.joinpath("jacklyn-20200102-000000-daily.db").write_bytes(b"old")
    service.folder.joinpath("jacklyn-20190101-000000-manual.db").write_bytes(b"kept")
    service._prune()
    names = [b.name for b in service.list()]
    assert "jacklyn-20200101-000000-daily.db" not in names  # oldest automatic one goes
    assert "jacklyn-20190101-000000-manual.db" in names  # manual ones stay until deleted


def test_names_from_requests_cannot_escape_the_folder(live: tuple[Engine, BackupService]) -> None:
    _, service = live
    for name in ("../live.db", "jacklyn-20260101-000000-manual.db/../../live.db", "live.db"):
        with pytest.raises(BackupError):
            service.path(name)


def test_postgres_is_pointed_to_pg_dump(tmp_path: Path) -> None:
    engine = build_engine("postgresql+psycopg://u:p@localhost/jacklyn")
    service = BackupService(engine, tmp_path)
    assert service.supported is False
    with pytest.raises(BackupError, match="pg_dump"):
        service.create()


def test_backup_api_is_admin_only(client: TestClient, make_user: Callable[..., TestClient]) -> None:
    listing = client.get("/api/admin/backups")
    assert listing.status_code == 200, listing.text
    assert listing.json()["supported"] is True

    created = client.post("/api/admin/backups")
    assert created.status_code == 201, created.text
    name = created.json()["name"]
    download = client.get(f"/api/admin/backups/{name}")
    assert download.status_code == 200
    assert download.content.startswith(b"SQLite format 3\x00")
    assert "attachment" in download.headers["content-disposition"]

    friend = make_user()
    assert friend.get("/api/admin/backups").status_code == 403
    assert friend.get(f"/api/admin/backups/{name}").status_code == 403
    assert friend.post("/api/admin/backups").status_code == 403

    unconfirmed = client.post(
        "/api/admin/backups/restore", files={"file": ("b.db", download.content)}, data={"confirm": "yes"}
    )
    assert unconfirmed.status_code == 400
    junk = client.post("/api/admin/backups/restore", files={"file": ("b.db", b"nope")}, data={"confirm": "RESTORE"})
    assert junk.status_code == 400
    assert "SQLite" in junk.json()["detail"]

    # Restoring the snapshot just taken: same data, and the app keeps working afterwards.
    restored = client.post(
        "/api/admin/backups/restore", files={"file": ("b.db", download.content)}, data={"confirm": "RESTORE"}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["safety_backup"]["kind"] == "before-restore"
    assert client.get("/api/portfolio/summary").status_code == 200

    assert client.delete(f"/api/admin/backups/{name}").status_code == 204
    assert client.get(f"/api/admin/backups/{name}").status_code == 404
