"""Test configuration. Environment is set before any `app` import so the engine binds to a temp DB."""

import os
import tempfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

_TMP = Path(tempfile.mkdtemp(prefix="jacklyn-tests-"))
os.environ["JACKLYN_DATABASE_URL"] = f"sqlite:///{(_TMP / 'api.db').as_posix()}"
os.environ["JACKLYN_DATA_DIR"] = str(_TMP / "data")
os.environ["JACKLYN_LIVE_MARKET_DATA"] = "false"
os.environ["JACKLYN_AUTO_BACKUPS"] = "false"
os.environ["JACKLYN_SEED_DEMO_DATA"] = "true"
os.environ["JACKLYN_SETUP_TOKEN"] = "test-setup-token"
os.environ["JACKLYN_SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["JACKLYN_LOGIN_IP_MAX_FAILURES"] = "1000"  # individual tests install a strict throttle when needed

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.db.migrate import upgrade_to_head  # noqa: E402
from app.db.session import build_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Account, User  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct horse battery staple"
CSRF = {"X-Jacklyn-Request": "1"}


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def new_client() -> TestClient:
    """A separate browser: its own cookie jar, sending the UI's CSRF header like the real frontend."""
    return TestClient(app, headers=CSRF)


@pytest.fixture(scope="session")
def bootstrap() -> Iterator[dict[str, Any]]:
    """Start the app on a fresh database and record what the API does before setup is completed."""
    with TestClient(app, headers=CSRF) as raw:
        good = {
            "setup_token": "test-setup-token",
            "email": ADMIN_EMAIL,
            "display_name": "Admin",
            "password": ADMIN_PASSWORD,
            "keep_demo_data": True,
        }
        events: dict[str, Any] = {
            "status_before": raw.get("/api/auth/session").json(),
            "data_before": raw.get("/api/portfolio/summary").status_code,
            "no_csrf_header": TestClient(app).post("/api/auth/setup", json=good).status_code,
            "wrong_token": raw.post("/api/auth/setup", json={**good, "setup_token": "nope"}).status_code,
            "weak_password": raw.post("/api/auth/setup", json={**good, "password": "short"}).status_code,
        }
        setup = raw.post("/api/auth/setup", json=good)
        events["setup"] = setup
        events["second_setup"] = new_client().post("/api/auth/setup", json=good).status_code
        events["client"] = raw
        yield events


@pytest.fixture(scope="session")
def client(bootstrap: dict[str, Any]) -> TestClient:
    """The admin's browser, signed in, with the demo portfolio."""
    test_client: TestClient = bootstrap["client"]
    return test_client


@pytest.fixture(scope="session")
def make_user(client: TestClient) -> Callable[..., TestClient]:
    """Invite and register a friend; returns that friend's signed-in browser."""
    counter = {"n": 0}

    def factory(password: str = "a very long friend password", *, admin: bool = False) -> TestClient:
        counter["n"] += 1
        invite = client.post("/api/admin/invites", json={"label": f"Friend {counter['n']}", "grants_admin": admin})
        assert invite.status_code == 201, invite.text
        token = invite.json()["path"].rsplit("/", 1)[-1]
        friend = new_client()
        response = friend.post(
            "/api/auth/register",
            json={
                "token": token,
                "email": f"friend{counter['n']}@example.com",
                "display_name": f"Friend {counter['n']}",
                "password": password,
            },
        )
        assert response.status_code == 200, response.text
        friend.email = f"friend{counter['n']}@example.com"
        return friend

    return factory


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    """An isolated, migrated, empty database per test."""
    url = f"sqlite:///{(tmp_path / 'unit.db').as_posix()}"
    upgrade_to_head(url)
    engine = build_engine(url)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def user(db: Session) -> User:
    owner = User(email="test@jacklyn.local", display_name="Test", base_currency="CHF")
    db.add(owner)
    db.commit()
    return owner


@pytest.fixture
def account(db: Session, user: User) -> Account:
    acc = Account(user_id=user.id, name="Test IBKR", broker="Interactive Brokers", currency="CHF")
    db.add(acc)
    db.commit()
    return acc
