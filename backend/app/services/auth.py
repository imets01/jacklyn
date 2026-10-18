"""Accounts, sessions, login protection, invite/reset links and first-run setup."""

import datetime as dt
import hmac
import logging
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AuthToken, AuthTokenPurpose, User, UserSession
from app.models._common import utcnow
from app.security import passwords, totp
from app.security.secrets import hash_token, new_token, write_private_file
from app.security.throttle import LoginThrottle

logger = logging.getLogger(__name__)
SESSION_TOUCH_INTERVAL = dt.timedelta(minutes=5)


def normalize_email(email: str) -> str:
    return email.strip().lower()


# ------------------------------------------------------------------ sessions


def create_session(db: Session, user: User, *, ip: str | None, user_agent: str | None) -> str:
    token = new_token()
    now = utcnow()
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            created_at=now,
            last_seen_at=now,
            expires_at=now + dt.timedelta(days=get_settings().session_days),
            ip_address=(ip or "")[:64] or None,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    user.last_login_at = now
    db.commit()
    return token


def resolve_session(db: Session, token: str | None) -> tuple[UserSession, User] | None:
    if not token or len(token) > 200:
        return None
    row = db.execute(
        select(UserSession, User)
        .join(User, User.id == UserSession.user_id)
        .where(UserSession.token_hash == hash_token(token))
    ).first()
    if row is None:
        return None
    user_session, user = row
    now = utcnow()
    if user_session.expires_at <= now or not user.is_active or user.password_hash is None:
        db.delete(user_session)
        db.commit()
        return None
    if now - user_session.last_seen_at > SESSION_TOUCH_INTERVAL:
        user_session.last_seen_at = now
        db.commit()
    return user_session, user


def revoke_sessions(db: Session, user_id: int, *, keep_session_id: int | None = None) -> int:
    query = delete(UserSession).where(UserSession.user_id == user_id)
    if keep_session_id is not None:
        query = query.where(UserSession.id != keep_session_id)
    result = db.execute(query)
    db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def purge_expired_sessions(db: Session) -> None:
    db.execute(delete(UserSession).where(UserSession.expires_at <= utcnow()))
    db.commit()


# ------------------------------------------------------------------ login


class LoginOutcome(StrEnum):
    OK = "ok"
    INVALID = "invalid"
    TOTP_REQUIRED = "totp_required"
    LOCKED = "locked"
    THROTTLED = "throttled"


@dataclass
class LoginResult:
    outcome: LoginOutcome
    user: User | None = None
    retry_after: int = 0


def authenticate(
    db: Session, throttle: LoginThrottle, *, email: str, password: str, totp_code: str | None, ip: str
) -> LoginResult:
    settings = get_settings()
    if wait := throttle.retry_after(ip):
        return LoginResult(LoginOutcome.THROTTLED, retry_after=wait)

    user = db.scalar(select(User).where(User.email == normalize_email(email)))
    now = utcnow()
    if user is not None and user.locked_until is not None and user.locked_until > now:
        throttle.record_failure(ip)
        return LoginResult(LoginOutcome.LOCKED, retry_after=int((user.locked_until - now).total_seconds()) + 1)

    # Always run the hash check (against a dummy hash for unknown emails) so timing doesn't reveal accounts.
    password_ok = passwords.verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok or not user.is_active:
        throttle.record_failure(ip)
        if user is not None and user.password_hash is not None:
            user.failed_logins += 1
            if user.failed_logins >= settings.lockout_threshold:
                user.locked_until = now + dt.timedelta(minutes=settings.lockout_minutes)
                user.failed_logins = 0
                logger.warning("Locked account %s after repeated failed logins", user.id)
            db.commit()
        return LoginResult(LoginOutcome.INVALID)

    if user.totp_enabled:
        if not totp_code:
            return LoginResult(LoginOutcome.TOTP_REQUIRED)
        # An unreadable secret (changed secret key) fails closed: only an admin reset link gets back in.
        step = totp.verify(user.totp_secret, totp_code, user.totp_last_step) if user.totp_secret else None
        if step is None:
            throttle.record_failure(ip)
            user.failed_logins += 1
            if user.failed_logins >= settings.lockout_threshold:
                user.locked_until = now + dt.timedelta(minutes=settings.lockout_minutes)
                user.failed_logins = 0
            db.commit()
            return LoginResult(LoginOutcome.TOTP_REQUIRED)
        user.totp_last_step = step

    user.failed_logins = 0
    user.locked_until = None
    if user.password_hash and passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    db.commit()
    return LoginResult(LoginOutcome.OK, user=user)


# ------------------------------------------------------------------ invite & reset links


class LinkError(ValueError):
    pass


def create_link(
    db: Session,
    *,
    purpose: AuthTokenPurpose,
    created_by: User | None,
    days: int,
    user: User | None = None,
    label: str | None = None,
    grants_admin: bool = False,
) -> tuple[AuthToken, str]:
    token = new_token()
    if purpose is AuthTokenPurpose.PASSWORD_RESET and user is not None:
        # Only the newest reset link for an account stays valid.
        for old in db.scalars(
            select(AuthToken).where(
                AuthToken.purpose == AuthTokenPurpose.PASSWORD_RESET,
                AuthToken.user_id == user.id,
                AuthToken.used_at.is_(None),
                AuthToken.revoked_at.is_(None),
            )
        ):
            old.revoked_at = utcnow()
    link = AuthToken(
        purpose=purpose,
        token_hash=hash_token(token),
        created_by_id=created_by.id if created_by else None,
        user_id=user.id if user else None,
        label=label,
        grants_admin=grants_admin,
        expires_at=utcnow() + dt.timedelta(days=days),
    )
    db.add(link)
    db.commit()
    return link, token


def find_link(db: Session, token: str, purpose: AuthTokenPurpose) -> AuthToken:
    link = db.scalar(select(AuthToken).where(AuthToken.token_hash == hash_token(token), AuthToken.purpose == purpose))
    if link is None or link.revoked_at is not None:
        raise LinkError("This link isn't valid.")
    if link.used_at is not None:
        raise LinkError("This link has already been used.")
    if link.expires_at <= utcnow():
        raise LinkError("This link has expired. Ask for a new one.")
    return link


def link_state(link: AuthToken) -> str:
    if link.used_at is not None:
        return "used"
    if link.revoked_at is not None:
        return "revoked"
    if link.expires_at <= utcnow():
        return "expired"
    return "pending"


# ------------------------------------------------------------------ first-run setup


def needs_setup(db: Session) -> bool:
    """True until an admin account has a password."""
    return db.scalar(select(User.id).where(User.is_admin.is_(True), User.password_hash.is_not(None)).limit(1)) is None


class SetupGuard:
    """One-time token that must accompany the first-run setup, so nobody else can claim the instance.

    It is printed to the server log and written to <data_dir>/setup-token.txt.
    """

    def __init__(self) -> None:
        self._token: str | None = None

    def arm(self) -> str:
        settings = get_settings()
        token = settings.setup_token or new_token(18)
        self._token = token
        path = settings.data_dir / "setup-token.txt"
        if not settings.setup_token:
            write_private_file(path, token + "\n")
        banner = "=" * 72
        logger.warning(
            "\n%s\nJacklyn needs first-run setup. Open the app and enter this setup token:\n\n    %s\n\n"
            "(also saved to %s)\n%s",
            banner,
            token,
            path,
            banner,
        )
        return token

    def check(self, token: str) -> bool:
        return self._token is not None and hmac.compare_digest(self._token, token.strip())

    def disarm(self) -> None:
        self._token = None
        path = get_settings().data_dir / "setup-token.txt"
        path.unlink(missing_ok=True)
