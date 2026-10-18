"""Authentication, authorization and - above all - isolation between users."""

import time
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import unquote

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import SessionLocal
from app.main import app
from app.models import BrokerCredential, User
from app.security import passwords, totp
from app.security.throttle import LoginThrottle
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, fixture_bytes, new_client

MakeUser = Callable[..., TestClient]


def _login(client: TestClient, email: str, password: str, code: str | None = None) -> Any:
    return client.post("/api/auth/login", json={"email": email, "password": password, "totp_code": code})


@pytest.fixture
def strict_throttle() -> Iterator[LoginThrottle]:
    original = app.state.login_throttle
    app.state.login_throttle = LoginThrottle(max_failures=3)
    try:
        yield app.state.login_throttle
    finally:
        app.state.login_throttle = original


# ------------------------------------------------------------------ first run


def test_first_run_setup_is_guarded(bootstrap: dict[str, Any]) -> None:
    assert bootstrap["status_before"] == {"authenticated": False, "needs_setup": True, "user": None}
    assert bootstrap["data_before"] == 401  # nothing is readable before an admin exists
    assert bootstrap["no_csrf_header"] == 403
    assert bootstrap["wrong_token"] == 403
    assert bootstrap["weak_password"] == 422
    assert bootstrap["setup"].status_code == 200
    assert bootstrap["setup"].json()["is_admin"] is True
    assert bootstrap["second_setup"] == 409  # the instance can be claimed exactly once


def test_setup_claims_the_seeded_owner_with_demo_data(client: TestClient) -> None:
    status = client.get("/api/auth/session").json()
    assert status["authenticated"] is True
    assert status["needs_setup"] is False
    assert status["user"]["email"] == ADMIN_EMAIL
    assert len(client.get("/api/accounts").json()) >= 4


# ------------------------------------------------------------------ sign in / out


def test_login_logout_and_cookie_flags() -> None:
    browser = new_client()
    assert _login(browser, ADMIN_EMAIL, "wrong password!!").status_code == 401
    response = _login(browser, ADMIN_EMAIL.upper(), ADMIN_PASSWORD)  # email is case-insensitive
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "jacklyn_session=" in cookie
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert browser.get("/api/me").status_code == 200
    assert browser.post("/api/auth/logout").status_code == 204
    assert browser.get("/api/me").status_code == 401


def test_unknown_email_and_wrong_password_look_the_same() -> None:
    browser = new_client()
    unknown = _login(browser, "nobody@example.com", "whatever password")
    wrong = _login(browser, ADMIN_EMAIL, "whatever password")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


@pytest.mark.parametrize(
    "path",
    [
        "/api/me",
        "/api/portfolio/summary",
        "/api/portfolio/history",
        "/api/accounts",
        "/api/import/logs",
        "/api/mappings",
    ],
)
def test_data_requires_a_session(path: str) -> None:
    assert new_client().get(path).status_code == 401


def test_csrf_protection(client: TestClient) -> None:
    body = {"name": "CSRF probe", "broker": "X", "currency": "CHF"}
    no_header = client.post("/api/accounts", json=body, headers={"X-Jacklyn-Request": ""})
    assert no_header.status_code == 403
    cross_site = client.post("/api/accounts", json=body, headers={"Origin": "https://evil.example"})
    assert cross_site.status_code == 403
    same_site = client.post("/api/accounts", json=body, headers={"Origin": "http://testserver"})
    assert same_site.status_code == 201


def test_security_headers_and_no_caching(client: TestClient) -> None:
    response = client.get("/api/portfolio/summary")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"


# ------------------------------------------------------------------ brute force


def test_account_lockout(make_user: MakeUser) -> None:
    friend = make_user("friend lockout password")
    email = friend.email
    attacker = new_client()
    for _ in range(5):
        assert _login(attacker, email, "guessing password").status_code == 401
    locked = _login(attacker, email, "friend lockout password")
    assert locked.status_code == 429  # even the right password waits out the lock
    assert "Retry-After" in locked.headers


def test_ip_throttle(strict_throttle: LoginThrottle) -> None:
    attacker = new_client()
    for i in range(3):
        _login(attacker, f"spray{i}@example.com", "guessing password")
    assert _login(attacker, ADMIN_EMAIL, ADMIN_PASSWORD).status_code == 429


# ------------------------------------------------------------------ invites


def test_invite_is_single_use_and_creates_a_regular_user(client: TestClient) -> None:
    invite = client.post("/api/admin/invites", json={"label": "Anna"}).json()
    token = invite["path"].rsplit("/", 1)[-1]
    info = new_client().get(f"/api/auth/links/{token}", params={"purpose": "invite"})
    assert info.status_code == 200
    assert info.json()["label"] == "Anna"

    anna = new_client()
    body = {"token": token, "email": "anna@example.com", "display_name": "Anna", "password": "short"}
    assert anna.post("/api/auth/register", json=body).status_code == 422
    body["password"] = "anna has a long password"
    registered = anna.post("/api/auth/register", json=body)
    assert registered.status_code == 200
    assert registered.json()["is_admin"] is False
    assert anna.get("/api/accounts").json() == []  # friends start empty, never with the owner's data

    again = new_client().post("/api/auth/register", json={**body, "email": "anna2@example.com"})
    assert again.status_code == 404
    states = {i["label"]: i for i in client.get("/api/admin/invites").json()}
    assert states["Anna"]["state"] == "used"
    assert states["Anna"]["used_by"] == "Anna"


def test_registration_requires_a_valid_invite() -> None:
    body = {"token": "x" * 43, "email": "sneaky@example.com", "display_name": "Sneaky", "password": "a long password!"}
    assert new_client().post("/api/auth/register", json=body).status_code == 404


def test_revoked_invite_cannot_be_used(client: TestClient) -> None:
    invite = client.post("/api/admin/invites", json={"label": "Revoked"}).json()
    invite_id = next(i["id"] for i in client.get("/api/admin/invites").json() if i["label"] == "Revoked")
    assert client.delete(f"/api/admin/invites/{invite_id}").status_code == 204
    token = invite["path"].rsplit("/", 1)[-1]
    assert new_client().get(f"/api/auth/links/{token}", params={"purpose": "invite"}).status_code == 404


def test_admin_endpoints_are_admin_only(make_user: MakeUser) -> None:
    friend = make_user()
    assert friend.get("/api/admin/users").status_code == 403
    assert friend.post("/api/admin/invites", json={}).status_code == 403
    assert friend.patch("/api/admin/users/1", json={"is_active": False}).status_code == 403


def test_admin_cannot_lock_themselves_out(client: TestClient) -> None:
    me = client.get("/api/auth/session").json()["user"]
    assert client.patch(f"/api/admin/users/{me['id']}", json={"is_active": False}).status_code == 400
    assert client.patch(f"/api/admin/users/{me['id']}", json={"is_admin": False}).status_code == 400


# ------------------------------------------------------------------ isolation between users


def test_users_cannot_see_or_touch_each_others_data(client: TestClient, make_user: MakeUser) -> None:
    admin_accounts = client.get("/api/accounts").json()
    target = admin_accounts[0]["id"]
    mapping = client.post(
        "/api/mappings",
        json={"name": "Admin preset", "header_signature": "a" * 64, "config": {"columns": {"date": "Date"}}},
    ).json()

    friend = make_user()
    assert friend.get(f"/api/accounts/{target}").status_code == 404
    assert friend.get("/api/transactions", params={"account_id": target}).json()["items"] == []
    assert friend.patch(f"/api/accounts/{target}", json={"name": "Mine now"}).status_code == 404
    assert friend.get("/api/portfolio/holdings", params={"account_id": target}).json()["holdings"] == []
    assert friend.get("/api/portfolio/history", params={"account_id": target}).json()["points"] == []
    assert friend.get("/api/portfolio/summary").json()["accounts"] == []
    assert friend.get("/api/mappings").json() == []
    assert friend.delete(f"/api/mappings/{mapping['id']}").status_code == 404
    assert friend.get("/api/import/logs").json() == []
    preview = friend.post(
        "/api/import/preview",
        files={"file": ("s.csv", fixture_bytes("ibkr_activity.csv"))},
        data={"account_id": str(target)},
    )
    assert preview.status_code == 404
    commit = friend.post(
        "/api/import/commit",
        json={
            "account_id": target,
            "transactions": [{"date": "2025-01-01", "type": "deposit", "amount": "1", "currency": "CHF"}],
        },
    )
    assert commit.status_code == 404

    # ...and the friend's own data stays invisible to the admin's data endpoints.
    own = friend.post("/api/accounts", json={"name": "Friend savings", "broker": "Revolut", "currency": "EUR"})
    assert own.status_code == 201
    assert own.json()["id"] not in {a["id"] for a in client.get("/api/accounts").json()}
    assert client.get(f"/api/accounts/{own.json()['id']}").status_code == 404
    # Untouched after all the attempts above.
    assert client.get(f"/api/accounts/{target}").json()["name"] == admin_accounts[0]["name"]
    assert client.get("/api/mappings").json()[0]["name"] == "Admin preset"


# ------------------------------------------------------------------ account lifecycle


def test_deactivating_a_user_signs_them_out(client: TestClient, make_user: MakeUser) -> None:
    friend = make_user("deactivated friend password")
    friend_id = friend.get("/api/auth/session").json()["user"]["id"]
    assert client.patch(f"/api/admin/users/{friend_id}", json={"is_active": False}).status_code == 200
    assert friend.get("/api/me").status_code == 401
    assert _login(new_client(), friend.email, "deactivated friend password").status_code == 401


def test_password_change_signs_out_other_sessions(make_user: MakeUser) -> None:
    laptop = make_user("original friend password")
    email = laptop.email
    phone = new_client()
    assert _login(phone, email, "original friend password").status_code == 200
    assert len(laptop.get("/api/auth/sessions").json()) == 2

    wrong = laptop.post("/api/auth/password", json={"current_password": "nope", "new_password": "x" * 20})
    assert wrong.status_code == 400
    change = {"current_password": "original friend password", "new_password": "brand new friend password"}
    assert laptop.post("/api/auth/password", json=change).status_code == 204
    assert laptop.get("/api/me").status_code == 200
    assert phone.get("/api/me").status_code == 401
    assert _login(new_client(), email, "original friend password").status_code == 401
    assert _login(new_client(), email, "brand new friend password").status_code == 200


def test_sessions_can_be_listed_and_revoked(make_user: MakeUser) -> None:
    laptop = make_user("session friend password")
    phone = new_client()
    _login(phone, laptop.email, "session friend password")
    sessions = laptop.get("/api/auth/sessions").json()
    other = next(s for s in sessions if not s["current"])
    assert laptop.delete(f"/api/auth/sessions/{other['id']}").status_code == 204
    assert phone.get("/api/me").status_code == 401
    assert laptop.get("/api/me").status_code == 200


# ------------------------------------------------------------------ two-factor & reset links


def test_two_factor_login_and_replay_protection(make_user: MakeUser) -> None:
    friend = make_user("two factor friend password")
    email = friend.email
    setup = friend.post("/api/auth/totp/setup").json()
    assert setup["qr_data_url"].startswith("data:image/svg+xml")
    assert "xmlns" in unquote(setup["qr_data_url"])  # without it browsers won't render the <img>
    generator = pyotp.TOTP(setup["secret"])
    step = int(time.time()) // 30
    used_code = generator.at(step * 30)
    assert friend.post("/api/auth/totp/enable", json={"code": "000000"}).status_code == 400
    assert friend.post("/api/auth/totp/enable", json={"code": used_code}).status_code == 200

    browser = new_client()
    first = _login(browser, email, "two factor friend password")
    assert first.status_code == 401
    assert first.json()["detail"]["code"] == "totp_required"
    # The code used to enable 2FA can't be replayed; the next time step's code works (clock drift window).
    replay = _login(browser, email, "two factor friend password", used_code)
    assert replay.status_code == 401
    next_code = generator.at((step + 1) * 30)
    assert _login(browser, email, "two factor friend password", next_code).status_code == 200
    assert _login(new_client(), email, "two factor friend password", next_code).status_code == 401  # used once

    assert friend.post("/api/auth/totp/disable", json={"password": "wrong"}).status_code == 400
    assert friend.post("/api/auth/totp/disable", json={"password": "two factor friend password"}).status_code == 200
    assert _login(new_client(), email, "two factor friend password").status_code == 200


def test_reset_link_restores_access_and_clears_two_factor(client: TestClient, make_user: MakeUser) -> None:
    friend = make_user("forgotten friend password")
    email = friend.email
    friend_id = friend.get("/api/auth/session").json()["user"]["id"]
    secret = friend.post("/api/auth/totp/setup").json()["secret"]
    friend.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(secret).now()})

    link = client.post(f"/api/admin/users/{friend_id}/reset-link").json()
    token = link["path"].rsplit("/", 1)[-1]
    info = new_client().get(f"/api/auth/links/{token}", params={"purpose": "password_reset"}).json()
    assert info["email"] == email

    rescued = new_client()
    assert rescued.post("/api/auth/reset", json={"token": token, "password": "recovered password!"}).status_code == 200
    assert rescued.get("/api/auth/session").json()["user"]["totp_enabled"] is False
    assert friend.get("/api/me").status_code == 401  # every old session is gone
    assert (
        new_client().post("/api/auth/reset", json={"token": token, "password": "another password!!"}).status_code == 404
    )
    assert _login(new_client(), email, "recovered password!").status_code == 200


def test_secrets_are_encrypted_at_rest(make_user: MakeUser) -> None:
    friend = make_user()
    friend_id = friend.get("/api/auth/session").json()["user"]["id"]
    secret = friend.post("/api/auth/totp/setup").json()["secret"]
    with SessionLocal() as db:
        db.add(BrokerCredential(user_id=friend_id, provider="ibkr_flex", token="flex-token-123456"))
        db.commit()
        raw_totp = db.execute(text("SELECT totp_secret FROM users WHERE id = :id"), {"id": friend_id}).scalar_one()
        raw_token = db.execute(
            text("SELECT token FROM broker_credentials WHERE user_id = :id"), {"id": friend_id}
        ).scalar_one()
        assert secret not in raw_totp
        assert "flex-token" not in raw_token
        assert db.get(User, friend_id).totp_secret == secret  # type: ignore[union-attr]
        assert db.query(BrokerCredential).filter_by(user_id=friend_id).one().token == "flex-token-123456"
        raw_hash = db.execute(text("SELECT password_hash FROM users WHERE id = :id"), {"id": friend_id}).scalar_one()
        assert raw_hash.startswith("$argon2id$")


# ------------------------------------------------------------------ unit level


def test_password_policy() -> None:
    with pytest.raises(passwords.WeakPasswordError):
        passwords.check_policy("short")
    with pytest.raises(passwords.WeakPasswordError):
        passwords.check_policy("aaaaaaaaaaaaaaaa")
    with pytest.raises(passwords.WeakPasswordError):
        passwords.check_policy("me@example.com", email="me@example.com")
    passwords.check_policy("plant more alocasias")
    hashed = passwords.hash_password("plant more alocasias")
    assert passwords.verify_password("plant more alocasias", hashed)
    assert not passwords.verify_password("plant more alocasia", hashed)
    assert not passwords.verify_password("anything", None)


def test_throttle_window() -> None:
    throttle = LoginThrottle(max_failures=2, window_seconds=60)
    throttle.record_failure("1.2.3.4")
    assert throttle.retry_after("1.2.3.4") == 0
    throttle.record_failure("1.2.3.4")
    assert throttle.retry_after("1.2.3.4") > 0
    assert throttle.retry_after("5.6.7.8") == 0


def test_totp_rejects_reused_steps() -> None:
    secret = totp.new_secret()
    code = pyotp.TOTP(secret).now()
    step = totp.verify(secret, code, None)
    assert step is not None
    assert totp.verify(secret, code, step) is None
    assert totp.verify(secret, "12345", None) is None


def test_unreadable_two_factor_secret_fails_closed(make_user: MakeUser) -> None:
    """If the secret key changes, 2FA users are kept out (not let in without a code) and nothing crashes."""
    friend = make_user("fail closed friend password")
    email = friend.email
    friend_id = friend.get("/api/auth/session").json()["user"]["id"]
    secret = friend.post("/api/auth/totp/setup").json()["secret"]
    step = int(time.time()) // 30
    friend.post("/api/auth/totp/enable", json={"code": pyotp.TOTP(secret).at(step * 30)})
    with SessionLocal() as db:
        db.execute(text("UPDATE users SET totp_secret = 'not-a-valid-token' WHERE id = :id"), {"id": friend_id})
        db.commit()
    assert friend.get("/api/auth/session").status_code == 200  # still serves requests
    next_code = pyotp.TOTP(secret).at((step + 1) * 30)
    assert _login(new_client(), email, "fail closed friend password").status_code == 401
    assert _login(new_client(), email, "fail closed friend password", next_code).status_code == 401


def test_users_cannot_delete_each_others_accounts(client: TestClient, make_user: MakeUser) -> None:
    target = client.get("/api/accounts").json()[0]
    friend = make_user()
    assert friend.delete(f"/api/accounts/{target['id']}", params={"confirm": target["name"]}).status_code == 404
    assert client.get(f"/api/accounts/{target['id']}").status_code == 200
    blocked = client.delete(
        f"/api/accounts/{target['id']}", params={"confirm": target["name"]}, headers={"X-Jacklyn-Request": ""}
    )
    assert blocked.status_code == 403  # CSRF protection covers deletes too
