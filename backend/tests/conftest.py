"""Test configuration. Environment is set before any `app` import so the engine binds to a temp DB."""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="jacklyn-tests-"))
os.environ["JACKLYN_DATABASE_URL"] = f"sqlite:///{(_TMP / 'api.db').as_posix()}"
os.environ["JACKLYN_LIVE_MARKET_DATA"] = "false"
os.environ["JACKLYN_SEED_DEMO_DATA"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.db.migrate import upgrade_to_head  # noqa: E402
from app.db.session import build_engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Account, User  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    """The full app (migrations + demo seed) against a throwaway SQLite file."""
    with TestClient(app) as test_client:
        yield test_client


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
