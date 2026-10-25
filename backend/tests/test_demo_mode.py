"""The public demo: one click in, and only when the instance is deliberately set up as one."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User
from app.seed import open_for_demo
from app.services.auth import demo_user, needs_setup
from tests.conftest import ADMIN_EMAIL, new_client


@pytest.fixture
def demo_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "demo_mode", True)
    monkeypatch.setattr(get_settings(), "demo_source_url", "https://example.com/jacklyn")


def test_demo_sign_in_does_not_exist_on_a_private_instance(client: TestClient) -> None:
    status = client.get("/api/auth/session").json()
    assert status["demo"] is False
    assert status["demo_source_url"] is None
    assert new_client().post("/api/auth/demo").status_code == 404


@pytest.mark.usefixtures("demo_instance")
def test_demo_sign_in_needs_no_credentials(client: TestClient) -> None:
    visitor = new_client()
    before = visitor.get("/api/auth/session").json()
    assert before["authenticated"] is False
    assert (before["demo"], before["demo_source_url"]) == (True, "https://example.com/jacklyn")

    me = visitor.post("/api/auth/demo")
    assert me.status_code == 200, me.text
    assert me.json()["email"] == ADMIN_EMAIL  # the instance's admin, who holds the demo portfolio
    assert visitor.get("/api/auth/session").json()["authenticated"] is True
    assert visitor.get("/api/portfolio/summary", params={"base": "CHF"}).status_code == 200
    assert visitor.post("/api/auth/logout").status_code == 204
    assert visitor.get("/api/auth/session").json()["authenticated"] is False


@pytest.mark.usefixtures("demo_instance")
def test_demo_sign_in_still_needs_our_own_ui(client: TestClient) -> None:
    """Nothing about the demo relaxes the cross-site protection."""
    assert TestClient(client.app).post("/api/auth/demo").status_code == 403


def test_opening_an_instance_for_demo_claims_the_owner(db: Session) -> None:
    db.add(User(email="owner@jacklyn.local", display_name="Owner", base_currency="CHF", is_admin=True))
    db.commit()
    assert needs_setup(db) is True
    assert demo_user(db) is None

    open_for_demo(db)

    assert needs_setup(db) is False  # no setup token to find, no setup screen to pass
    signed_in = demo_user(db)
    assert signed_in is not None
    assert signed_in.email == "owner@jacklyn.local"


def test_opening_an_instance_for_demo_leaves_a_claimed_owner_alone(db: Session) -> None:
    owner = User(
        email="real@example.com", display_name="Owner", base_currency="CHF", is_admin=True, password_hash="kept"
    )
    db.add(owner)
    db.commit()

    open_for_demo(db)

    assert owner.password_hash == "kept"
