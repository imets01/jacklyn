import os
from collections.abc import Iterator
from pathlib import Path

# Must be set before the app (and its engine) is imported.
os.environ["JACKLYN_DATABASE_URL"] = "sqlite://"
os.environ["JACKLYN_SEED_ON_STARTUP"] = "true"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.main import app
from app.models import Base

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _fresh_db() -> Iterator[None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:  # runs lifespan -> seeds demo data
        yield c


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()
