from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import Account, User, UserSession
from app.security.throttle import LoginThrottle
from app.services.auth import SetupGuard, resolve_session
from app.services.market_data import MarketDataService
from app.services.sync import SyncService

DbSession = Annotated[Session, Depends(get_session)]
SESSION_COOKIE = "jacklyn_session"


def client_ip(request: Request) -> str:
    # uvicorn --proxy-headers resolves this from X-Forwarded-For set by our nginx.
    return request.client.host if request.client else "unknown"


def cookie_secure(request: Request) -> bool:
    mode = get_settings().cookie_secure
    if mode == "auto":
        return request.url.scheme == "https"
    return mode == "true"


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=get_settings().session_days * 86_400,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=cookie_secure(request), httponly=True, samesite="lax")


def get_auth(request: Request, db: DbSession) -> tuple[UserSession, User]:
    resolved = resolve_session(db, request.cookies.get(SESSION_COOKIE))
    if resolved is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    return resolved


Auth = Annotated[tuple[UserSession, User], Depends(get_auth)]


def get_current_user(auth: Auth) -> User:
    """Every data endpoint depends on this; all queries are scoped to the returned user's id."""
    return auth[1]


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only.")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_market_service(request: Request) -> MarketDataService:
    service: MarketDataService = request.app.state.market
    return service


MarketService = Annotated[MarketDataService, Depends(get_market_service)]


def get_sync_service(request: Request) -> SyncService:
    service: SyncService = request.app.state.sync
    return service


SyncSvc = Annotated[SyncService, Depends(get_sync_service)]


def get_throttle(request: Request) -> LoginThrottle:
    throttle: LoginThrottle = request.app.state.login_throttle
    return throttle


Throttle = Annotated[LoginThrottle, Depends(get_throttle)]


def get_setup_guard(request: Request) -> SetupGuard:
    guard: SetupGuard = request.app.state.setup_guard
    return guard


Guard = Annotated[SetupGuard, Depends(get_setup_guard)]


def base_currency(user: CurrentUser, base: Annotated[str | None, Query(pattern=r"^[A-Za-z]{3}$")] = None) -> str:
    return (base or user.base_currency).upper()


BaseCurrency = Annotated[str, Depends(base_currency)]


def get_owned_account(session: Session, user: User, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account
