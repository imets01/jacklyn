"""Sign-in, first-run setup, invites, password resets, sessions and two-factor authentication."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, select

from app.api.deps import (
    SESSION_COOKIE,
    Auth,
    CurrentUser,
    DbSession,
    Guard,
    Throttle,
    clear_session_cookie,
    client_ip,
    set_session_cookie,
)
from app.config import get_settings
from app.models import Account, AuthTokenPurpose, CustomCSVMapping, ImportLog, User, UserSession
from app.models._common import utcnow
from app.schemas.auth import (
    LinkInfo,
    LoginIn,
    MeOut,
    PasswordChangeIn,
    RegisterIn,
    ResetIn,
    SessionOut,
    SessionStatus,
    SetupIn,
    TotpCodeIn,
    TotpDisableIn,
    TotpSetupOut,
)
from app.security import passwords, totp
from app.services import auth as auth_service
from app.services.auth import LinkError, LoginOutcome

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _start_session(db: DbSession, request: Request, response: Response, user: User) -> MeOut:
    token = auth_service.create_session(db, user, ip=client_ip(request), user_agent=request.headers.get("user-agent"))
    set_session_cookie(response, request, token)
    return MeOut.model_validate(user)


def _policy(password: str, email: str) -> None:
    try:
        passwords.check_policy(password, email=email)
    except passwords.WeakPasswordError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


def _email_taken(db: DbSession, email: str, except_user_id: int | None = None) -> bool:
    query = select(User.id).where(User.email == email)
    if except_user_id is not None:
        query = query.where(User.id != except_user_id)
    return db.scalar(query) is not None


@router.get("/session", response_model=SessionStatus)
def session_status(request: Request, db: DbSession) -> SessionStatus:
    settings = get_settings()
    resolved = auth_service.resolve_session(db, request.cookies.get(SESSION_COOKIE))
    return SessionStatus(
        authenticated=resolved is not None,
        needs_setup=auth_service.needs_setup(db),
        user=MeOut.model_validate(resolved[1]) if resolved else None,
        demo=settings.demo_mode,
        demo_source_url=settings.demo_source_url if settings.demo_mode else None,
    )


@router.post("/demo", response_model=MeOut)
def demo_login(request: Request, response: Response, db: DbSession) -> MeOut:
    """Sign in to a public demo with no credentials. Only exists while `JACKLYN_DEMO_MODE` is on."""
    if not get_settings().demo_mode:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    user = auth_service.demo_user(db)
    if user is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "This demo has no account to sign in to.")
    return _start_session(db, request, response, user)


@router.post("/login", response_model=MeOut)
def login(payload: LoginIn, request: Request, response: Response, db: DbSession, throttle: Throttle) -> MeOut:
    result = auth_service.authenticate(
        db,
        throttle,
        email=payload.email,
        password=payload.password,
        totp_code=payload.totp_code,
        ip=client_ip(request),
    )
    if result.outcome is LoginOutcome.OK and result.user is not None:
        return _start_session(db, request, response, result.user)
    if result.outcome in (LoginOutcome.THROTTLED, LoginOutcome.LOCKED):
        minutes = max(1, round(result.retry_after / 60))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many attempts. Try again in about {minutes} minute{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(result.retry_after)},
        )
    if result.outcome is LoginOutcome.TOTP_REQUIRED:
        message = (
            "Enter the 6-digit code from your authenticator app." if not payload.totp_code else "That code didn't work."
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, {"code": "totp_required", "message": message})
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password.")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: DbSession) -> Response:
    resolved = auth_service.resolve_session(db, request.cookies.get(SESSION_COOKIE))
    if resolved is not None:
        db.delete(resolved[0])
        db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, request)
    return response


@router.post("/setup", response_model=MeOut)
def first_run_setup(
    payload: SetupIn, request: Request, response: Response, db: DbSession, guard: Guard, throttle: Throttle
) -> MeOut:
    """Claim the instance: create the admin account. Requires the one-time token from the server log."""
    if not auth_service.needs_setup(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "Setup is already complete.")
    ip = client_ip(request)
    if throttle.retry_after(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
    if not guard.check(payload.setup_token):
        throttle.record_failure(ip)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That setup token isn't right. Check the server log.")
    _policy(payload.password, payload.email)

    # Claim the seeded owner (who holds the demo portfolio) rather than creating a second user.
    owner = db.scalar(select(User).where(User.is_admin.is_(True), User.password_hash.is_(None)).order_by(User.id))
    if owner is None:
        owner = User(
            email=payload.email, display_name=payload.display_name, base_currency=get_settings().default_base_currency
        )
        db.add(owner)
    if _email_taken(db, payload.email, owner.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already used by another account.")
    owner.email = payload.email
    owner.display_name = payload.display_name
    owner.is_admin = True
    owner.is_active = True
    owner.password_hash = passwords.hash_password(payload.password)
    db.flush()
    if not payload.keep_demo_data:
        db.execute(delete(ImportLog).where(ImportLog.user_id == owner.id))
        db.execute(delete(CustomCSVMapping).where(CustomCSVMapping.user_id == owner.id))
        db.execute(delete(Account).where(Account.user_id == owner.id))  # transactions cascade
    db.commit()
    guard.disarm()
    return _start_session(db, request, response, owner)


@router.get("/links/{token}", response_model=LinkInfo)
def link_info(
    token: str,
    purpose: Annotated[Literal["invite", "password_reset"], Query()],
    request: Request,
    db: DbSession,
    throttle: Throttle,
) -> LinkInfo:
    ip = client_ip(request)
    if throttle.retry_after(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
    try:
        link = auth_service.find_link(db, token, AuthTokenPurpose(purpose))
    except LinkError as exc:
        throttle.record_failure(ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    target = db.get(User, link.user_id) if link.purpose is AuthTokenPurpose.PASSWORD_RESET and link.user_id else None
    return LinkInfo(
        purpose=purpose, label=link.label, email=target.email if target else None, expires_at=link.expires_at
    )


@router.post("/register", response_model=MeOut)
def register(payload: RegisterIn, request: Request, response: Response, db: DbSession, throttle: Throttle) -> MeOut:
    ip = client_ip(request)
    if throttle.retry_after(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
    try:
        link = auth_service.find_link(db, payload.token, AuthTokenPurpose.INVITE)
    except LinkError as exc:
        throttle.record_failure(ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    _policy(payload.password, payload.email)
    if _email_taken(db, payload.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        base_currency=get_settings().default_base_currency,
        password_hash=passwords.hash_password(payload.password),
        is_admin=link.grants_admin,
    )
    db.add(user)
    db.flush()
    link.used_at = utcnow()
    link.user_id = user.id
    db.commit()
    return _start_session(db, request, response, user)


@router.post("/reset", response_model=MeOut)
def reset_password(payload: ResetIn, request: Request, response: Response, db: DbSession, throttle: Throttle) -> MeOut:
    """Set a new password from an admin-issued reset link. Also clears 2FA (lost-phone recovery)."""
    ip = client_ip(request)
    if throttle.retry_after(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
    try:
        link = auth_service.find_link(db, payload.token, AuthTokenPurpose.PASSWORD_RESET)
    except LinkError as exc:
        throttle.record_failure(ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    user = db.get(User, link.user_id) if link.user_id else None
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This link isn't valid.")
    _policy(payload.password, user.email)
    user.password_hash = passwords.hash_password(payload.password)
    user.failed_logins = 0
    user.locked_until = None
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_last_step = None
    link.used_at = utcnow()
    db.commit()
    auth_service.revoke_sessions(db, user.id)
    return _start_session(db, request, response, user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: PasswordChangeIn, auth: Auth, db: DbSession) -> Response:
    current_session, user = auth
    if not passwords.verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is wrong.")
    _policy(payload.new_password, user.email)
    user.password_hash = passwords.hash_password(payload.new_password)
    db.commit()
    auth_service.revoke_sessions(db, user.id, keep_session_id=current_session.id)  # sign out everywhere else
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(auth: Auth, db: DbSession) -> list[SessionOut]:
    current_session, user = auth
    rows = db.scalars(
        select(UserSession).where(UserSession.user_id == user.id).order_by(UserSession.last_seen_at.desc())
    )
    return [
        SessionOut(
            id=row.id,
            created_at=row.created_at,
            last_seen_at=row.last_seen_at,
            expires_at=row.expires_at,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            current=row.id == current_session.id,
        )
        for row in rows
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(session_id: int, auth: Auth, db: DbSession) -> Response:
    _, user = auth
    row = db.get(UserSession, session_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(auth: Auth, db: DbSession) -> Response:
    current_session, user = auth
    auth_service.revoke_sessions(db, user.id, keep_session_id=current_session.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/totp/setup", response_model=TotpSetupOut)
def totp_setup(user: CurrentUser, db: DbSession) -> TotpSetupOut:
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-factor authentication is already on.")
    secret = totp.new_secret()
    user.totp_secret = secret
    user.totp_last_step = None
    db.commit()
    uri = totp.provisioning_uri(secret, user.email)
    return TotpSetupOut(secret=secret, otpauth_uri=uri, qr_data_url=totp.qr_svg_data_url(uri))


@router.post("/totp/enable", response_model=MeOut)
def totp_enable(payload: TotpCodeIn, user: CurrentUser, db: DbSession) -> MeOut:
    if user.totp_enabled or not user.totp_secret:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start two-factor setup first.")
    step = totp.verify(user.totp_secret, payload.code, user.totp_last_step)
    if step is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "That code didn't work. Check your phone's clock and try again."
        )
    user.totp_enabled = True
    user.totp_last_step = step
    db.commit()
    return MeOut.model_validate(user)


@router.post("/totp/disable", response_model=MeOut)
def totp_disable(payload: TotpDisableIn, user: CurrentUser, db: DbSession) -> MeOut:
    if not passwords.verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your password is wrong.")
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_last_step = None
    db.commit()
    return MeOut.model_validate(user)
