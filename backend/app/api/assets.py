import datetime as dt
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Response, status
from sqlalchemy import select

from app.api.deps import BaseCurrency, CurrentUser, DbSession, MarketService
from app.health.composition import fund_composition
from app.models import Asset, AssetLogo, AssetProfile, Transaction, User
from app.schemas.portfolio import ChartRange, ChartResponse, HoldingDetail
from app.services.charts import INTRADAY, change, stored_chart, yahoo_chart
from app.services.portfolio import PortfolioEngine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["assets"])
LOGO_CACHE = "private, max-age=604800, immutable"  # URLs carry a version, so a new logo gets a new URL


def get_traded_asset(session: DbSession, user: User, asset_id: int) -> Asset:
    """Assets are shared reference data; a user may only look at the ones they have traded."""
    traded = session.scalar(
        select(Transaction.id).where(Transaction.user_id == user.id, Transaction.asset_id == asset_id).limit(1)
    )
    asset = session.get(Asset, asset_id) if traded else None
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found.")
    return asset


@router.get("/api/portfolio/holdings/{asset_id}", response_model=HoldingDetail)
def holding_detail(asset_id: int, session: DbSession, user: CurrentUser, base: BaseCurrency) -> HoldingDetail:
    detail = PortfolioEngine(session, user_id=user.id, base_currency=base).holding_detail(asset_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found.")
    if (asset := session.get(Asset, asset_id)) is not None:
        detail.composition = fund_composition(session, asset)
    return detail


@router.get("/api/assets/{asset_id}/chart", response_model=ChartResponse)
def asset_chart(
    asset_id: int,
    session: DbSession,
    user: CurrentUser,
    market: MarketService,
    range: ChartRange = "1Y",  # noqa: A002 - public query parameter name
) -> ChartResponse:
    asset = get_traded_asset(session, user, asset_id)
    points = []
    if market.enabled and asset.yf_ticker:
        try:
            points = yahoo_chart(asset.yf_ticker, range)
        except Exception as exc:  # noqa: BLE001 - fall back to stored closes when Yahoo is unreachable
            logger.info("Chart for %s (%s) failed: %s", asset.yf_ticker, range, exc)
    source: Literal["yfinance", "stored"] = "yfinance" if points else "stored"
    if not points:
        points = stored_chart(session, asset.id, range, dt.date.today())
    delta, pct = change(points)
    return ChartResponse(
        asset_id=asset.id,
        range=range,
        currency=asset.currency,
        intraday=source == "yfinance" and range in INTRADAY,
        source=source,
        points=points,
        change=delta,
        change_pct=pct,
    )


def _image(logo: AssetLogo | None) -> Response:
    if logo is None or logo.data is None or logo.content_type is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No logo for this asset.")
    return Response(
        logo.data,
        media_type=logo.content_type,
        headers={"Cache-Control": LOGO_CACHE, "Content-Security-Policy": "default-src 'none'; sandbox"},
    )


@router.get("/api/logos/{key}", responses={200: {"content": {"image/svg+xml": {}}}})
def shared_logo(
    key: Annotated[str, Path(pattern=r"^(country:[A-Z]{2}|currency:[A-Z]{3})$")],
    session: DbSession,
    _user: CurrentUser,
) -> Response:
    """Country flags and currency badges: public reference images any signed-in user may load, from the
    cache only."""
    return _image(session.get(AssetLogo, key))


@router.get("/api/assets/{asset_id}/logo", responses={200: {"content": {"image/png": {}}}})
def asset_logo(asset_id: int, session: DbSession, user: CurrentUser) -> Response:
    get_traded_asset(session, user, asset_id)
    logo = session.scalars(
        select(AssetLogo)
        .join(AssetProfile, AssetProfile.logo_key == AssetLogo.key)
        .where(AssetProfile.asset_id == asset_id, AssetLogo.data.is_not(None))
    ).first()
    return _image(logo)
