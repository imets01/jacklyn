from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import Account, User
from app.services.market_data import MarketDataService

DbSession = Annotated[Session, Depends(get_session)]


def get_current_user(session: DbSession) -> User:
    """Phase 1 has no login: every request acts as the seeded default user.

    All queries are still scoped by this user's id, so adding authentication later only
    means replacing this dependency.
    """
    user = session.scalar(select(User).where(User.email == get_settings().default_user_email))
    if user is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Default user is not initialized yet.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_market_service(request: Request) -> MarketDataService:
    service: MarketDataService = request.app.state.market
    return service


MarketService = Annotated[MarketDataService, Depends(get_market_service)]


def base_currency(user: CurrentUser, base: Annotated[str | None, Query(pattern=r"^[A-Za-z]{3}$")] = None) -> str:
    return (base or user.base_currency).upper()


BaseCurrency = Annotated[str, Depends(base_currency)]


def get_owned_account(session: Session, user: User, account_id: int) -> Account:
    account = session.get(Account, account_id)
    if account is None or account.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return account
