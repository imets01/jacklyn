from fastapi import APIRouter

from app.api.deps import CurrentUser, MarketService
from app.schemas.api import MarketRefreshResult

router = APIRouter(prefix="/api/market", tags=["market"])


@router.post("/refresh", response_model=MarketRefreshResult)
def refresh_market(market: MarketService, _user: CurrentUser) -> MarketRefreshResult:
    """Force a background refresh of quotes and FX rates (ignores the cache TTL)."""
    return MarketRefreshResult(started=market.refresh_in_background(force=True), **market.status())
