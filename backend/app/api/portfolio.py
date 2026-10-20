from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import BaseCurrency, CurrentUser, DbSession, MarketService
from app.schemas.portfolio import (
    HistoryRange,
    HistoryResponse,
    HoldingsResponse,
    IncomeResponse,
    PerformanceResponse,
    PortfolioSummary,
    ReturnPeriod,
)
from app.services.income import income_report
from app.services.portfolio import PortfolioEngine

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])
AccountFilter = Annotated[list[int] | None, Query(alias="account_id")]


@router.get("/summary", response_model=PortfolioSummary)
def portfolio_summary(
    session: DbSession, user: CurrentUser, base: BaseCurrency, market: MarketService
) -> PortfolioSummary:
    # Serve from the cache immediately; refresh quotes in the background when the TTL has expired.
    market.refresh_in_background()
    engine = PortfolioEngine(session, user_id=user.id, base_currency=base)
    return engine.summary(market.status())


@router.get("/history", response_model=HistoryResponse)
def portfolio_history(
    session: DbSession,
    user: CurrentUser,
    base: BaseCurrency,
    range: HistoryRange = "1Y",  # noqa: A002 - public query parameter name
    account_ids: AccountFilter = None,
) -> HistoryResponse:
    engine = PortfolioEngine(session, user_id=user.id, base_currency=base, account_ids=account_ids)
    return engine.history(range)


@router.get("/holdings", response_model=HoldingsResponse)
def portfolio_holdings(
    session: DbSession, user: CurrentUser, base: BaseCurrency, account_ids: AccountFilter = None
) -> HoldingsResponse:
    engine = PortfolioEngine(session, user_id=user.id, base_currency=base, account_ids=account_ids)
    return engine.holdings()


@router.get("/performance", response_model=PerformanceResponse)
def portfolio_performance(
    session: DbSession, user: CurrentUser, base: BaseCurrency, period: ReturnPeriod = "ALL"
) -> PerformanceResponse:
    """Money- and time-weighted returns, overall and per account."""
    engine = PortfolioEngine(session, user_id=user.id, base_currency=base)
    return engine.performance(period)


@router.get("/income", response_model=IncomeResponse)
def portfolio_income(session: DbSession, user: CurrentUser, base: BaseCurrency) -> IncomeResponse:
    """Dividends and interest: by month, by holding, and what is likely to come."""
    return income_report(PortfolioEngine(session, user_id=user.id, base_currency=base))
