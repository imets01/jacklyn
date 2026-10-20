"""Database backups: consistent snapshots of the SQLite file, kept in `data_dir/backups`, and restores.

A snapshot uses SQLite's online backup API, so it is consistent while the app keeps running (WAL included). The
backup holds every user's data but not `secret.key`, which encrypts 2FA secrets and broker tokens: restoring on
the same server needs nothing else, a new server needs that key too. PostgreSQL deployments use `pg_dump`.
"""

import datetime as dt
import logging
import re
import sqlite3
import threading
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import Engine
from sqlalchemy.engine.url import make_url

from app.db.migrate import alembic_config, upgrade_to_head

logger = logging.getLogger(__name__)

AUTO_EVERY = dt.timedelta(days=1)
KEEP_AUTOMATIC = 14  # daily and before-restore snapshots; manual ones stay until deleted
CHECK_EVERY_SECONDS = 3600
NAME_RE = re.compile(r"^jacklyn-\d{8}-\d{6}-(manual|daily|before-restore)\.db$")
REQUIRED_TABLES = {"alembic_version", "users", "accounts", "transactions"}


class BackupError(ValueError):
    """A backup that can't be made, found or restored; the message is safe to show."""


@dataclass(frozen=True)
class BackupFile:
    name: str
    kind: str  # manual | daily | before-restore
    size: int
    created_at: dt.datetime


class BackupService:
    def __init__(self, engine: Engine, data_dir: Path) -> None:
        self.engine = engine
        url = make_url(str(engine.url))
        database = url.database if url.get_backend_name() == "sqlite" else None
        self.database = Path(database) if database and database != ":memory:" else None
        self.folder = data_dir / "backups"
        self._lock = threading.Lock()  # one snapshot or restore at a time
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def supported(self) -> bool:
        return self.database is not None

    # ------------------------------------------------------------------ snapshots

    def list(self) -> list[BackupFile]:
        if not self.folder.is_dir():
            return []
        files = [self._describe(path) for path in self.folder.iterdir() if NAME_RE.match(path.name)]
        return sorted(files, key=lambda f: f.name, reverse=True)

    def path(self, name: str) -> Path:
        """The file for a backup name from a request; refuses anything that isn't one of ours."""
        path = self.folder / name
        if not NAME_RE.match(name) or not path.is_file():
            raise BackupError("No such backup.")
        return path

    def create(self, kind: str = "manual") -> BackupFile:
        database = self._require_sqlite()
        self.folder.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        target = self.folder / f"jacklyn-{stamp}-{kind}.db"
        if target.exists():
            raise BackupError("A backup was made a moment ago; try again in a second.")
        with self._lock:
            partial = target.with_suffix(".partial")
            with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(partial)) as copy:
                source.backup(copy)
            # Close before renaming (Windows), then the file appears whole or not at all.
            partial.replace(target)
        self._prune()
        return self._describe(target)

    def delete(self, name: str) -> None:
        self.path(name).unlink()

    def _prune(self) -> None:
        automatic = [f for f in self.list() if f.kind != "manual"]
        for old in automatic[KEEP_AUTOMATIC:]:
            (self.folder / old.name).unlink(missing_ok=True)

    def _describe(self, path: Path) -> BackupFile:
        match = NAME_RE.match(path.name)
        assert match is not None
        stamp = dt.datetime.strptime(path.name[8:23], "%Y%m%d-%H%M%S").replace(tzinfo=dt.UTC)
        return BackupFile(name=path.name, kind=match[1], size=path.stat().st_size, created_at=stamp)

    # ------------------------------------------------------------------ restore

    def restore(self, upload: Path) -> BackupFile:
        """Replace the live database with `upload` after checking it; returns the safety snapshot taken first.

        The copy goes through the backup API into the open database, so other connections see either the old
        or the new data; migrations then bring an older backup up to date.
        """
        database = self._require_sqlite()
        self.check(upload)
        safety = self.create("before-restore")
        with self._lock:
            self.engine.dispose()
            with closing(sqlite3.connect(upload)) as source, closing(sqlite3.connect(database)) as live:
                source.backup(live)
            self.engine.dispose()
        upgrade_to_head(self.engine.url.render_as_string(hide_password=False))
        logger.warning("Database restored from an uploaded backup; the previous data is in %s.", safety.name)
        return safety

    def check(self, path: Path) -> None:
        """Refuse files that aren't a healthy Jacklyn database this version can migrate."""
        try:
            with path.open("rb") as handle:
                if handle.read(16) != b"SQLite format 3\x00":
                    raise BackupError("That file isn't a Jacklyn backup (not an SQLite database).")
            connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
            try:
                if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise BackupError("The backup is damaged (SQLite integrity check failed).")
                tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not REQUIRED_TABLES.issubset(tables):
                    raise BackupError("That database isn't a Jacklyn backup.")
                revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
            finally:
                connection.close()
        except sqlite3.DatabaseError as exc:
            raise BackupError("That file isn't a readable SQLite database.") from exc
        known = {
            script.revision for script in ScriptDirectory.from_config(alembic_config("sqlite://")).walk_revisions()
        }
        if revision is None or revision[0] not in known:
            raise BackupError("The backup comes from a newer Jacklyn version. Update Jacklyn first, then restore.")

    def _require_sqlite(self) -> Path:
        if self.database is None:
            raise BackupError("Backups from the app work with SQLite. For PostgreSQL, use pg_dump.")
        return self.database

    # ------------------------------------------------------------------ daily

    def start_scheduler(self) -> None:
        if not self.supported or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="daily-backups", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.backup_if_due()
            self._stop.wait(CHECK_EVERY_SECONDS)

    def backup_if_due(self, now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC)) -> BackupFile | None:
        latest = next((f for f in self.list() if f.kind == "daily"), None)
        if latest is not None and now() - latest.created_at < AUTO_EVERY:
            return None
        try:
            return self.create("daily")
        except Exception:
            logger.exception("Daily backup failed")
            return None
