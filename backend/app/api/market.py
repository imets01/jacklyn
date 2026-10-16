from fastapi import APIRouter

from app.api.deps import CurrentUser, MarketService
from app.schemas.api import MarketRefreshResult

router = APIRouter(prefix="/api/market", tags=["market"])


def _result(market: MarketService, started: bool) -> MarketRefreshResult:
    return MarketRefreshResult(started=started, **market.status())


@router.get("/status", response_model=MarketRefreshResult)
def market_status(market: MarketService, _user: CurrentUser) -> MarketRefreshResult:
    return _result(market, started=False)


@router.post("/refresh", response_model=MarketRefreshResult)
def refresh_market(market: MarketService, _user: CurrentUser) -> MarketRefreshResult:
    """Force a background refresh of quotes and FX rates (ignores the cache TTL)."""
    return _result(market, started=market.refresh_in_background(force=True))
