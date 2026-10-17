"""A single fund's composition for its holding page: countries, sectors, asset classes and largest holdings."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AssetClass
from app.health.config import load_benchmark
from app.health.exposure import UNCLASSIFIED, PositionInput, category_split, position_countries, position_sectors
from app.models import Asset, AssetLogo, AssetProfile
from app.schemas.portfolio import FundComposition, TopHolding, WeightRow
from app.services.eulerpool import COUNTRY_CODES, normalize_country

ZERO = Decimal(0)
WEIGHT = Decimal("0.0001")
TOP_HOLDINGS = 10
CLASS_LABELS = {"equity": "Stocks", "bonds": "Bonds", "cash": "Cash", "other": "Other"}


def _decimals(raw: dict[str, str] | None) -> dict[str, Decimal] | None:
    return {key: Decimal(str(value)) for key, value in raw.items()} if raw else None


def country_logo_key(name: str) -> str | None:
    code = COUNTRY_CODES.get(name)
    return f"country:{code}" if code else None


def composition_logo_keys(profile: AssetProfile) -> set[str]:
    """Flags for every country a fund holds, fetched in the background."""
    keys = {country_logo_key(normalize_country(name)) for name in (profile.country_weights or {})}
    return {key for key in keys if key}


def _logo_urls(session: Session, keys: set[str]) -> dict[str, str]:
    if not keys:
        return {}
    rows = session.execute(
        select(AssetLogo.key, AssetLogo.fetched_at).where(AssetLogo.key.in_(keys), AssetLogo.data.is_not(None))
    ).all()
    return {key: f"/api/logos/{key}?v={int(fetched.timestamp())}" for key, fetched in rows}


def _rows(weights: dict[str, Decimal], logos: dict[str, str] | None = None) -> list[WeightRow]:
    rows = [
        WeightRow(
            key=key,
            label="Not specified" if key == UNCLASSIFIED else key,
            weight=weight.quantize(WEIGHT),
            logo_url=(logos or {}).get(country_logo_key(key) or ""),
        )
        for key, weight in weights.items()
        if weight > 0
    ]
    # Largest first, the unspecified remainder last.
    return sorted(rows, key=lambda row: (row.key == UNCLASSIFIED, -row.weight))


def _countries_source(position: PositionInput, known: str) -> str:
    if known == "reported":
        return "Eulerpool (from the fund's holdings)"
    if known == "estimated" and (mapping := load_benchmark().index_for(position.name)):
        return f"Estimated from the index it tracks: {mapping.label}"
    return "Not available"


def _holding_rows(weights: dict[str, Decimal], names: dict[str, str]) -> list[TopHolding]:
    largest = sorted(weights.items(), key=lambda item: item[1], reverse=True)[:TOP_HOLDINGS]
    return [TopHolding(key=key, name=names.get(key), weight=weight.quantize(WEIGHT)) for key, weight in largest]


def _top_holdings(profile: AssetProfile) -> tuple[list[TopHolding], int | None, str | None]:
    names = profile.holding_names or {}
    if full := _decimals(profile.holdings):
        return _holding_rows(full, names), len(full), "Eulerpool"
    if top := _decimals(profile.top_holdings):
        return _holding_rows(top, names), None, "Yahoo Finance"
    return [], None, None


def fund_composition(session: Session, asset: Asset) -> FundComposition | None:
    if asset.asset_class not in (AssetClass.ETF, AssetClass.FUND):
        return None
    profile = session.get(AssetProfile, asset.id)
    if profile is None:
        return None
    benchmark = load_benchmark()
    countries = _decimals(profile.country_weights)
    position = PositionInput(
        asset_id=asset.id,
        symbol=asset.symbol,
        name=asset.name or profile.long_name,
        asset_class=asset.asset_class,
        currency=asset.currency,
        value=Decimal(1),
        value_local=Decimal(1),
        price=None,
        quantity=Decimal(1),
        sector_weights=_decimals(profile.sector_weights),
        class_weights=_decimals(profile.class_weights),
        country_weights={normalize_country(k): v for k, v in countries.items()} if countries else None,
    )
    country_weights, known, _ = position_countries(position, benchmark)
    split, _ = category_split(position)
    sectors = position_sectors(position, benchmark) if profile.sector_weights else {}
    logos = _logo_urls(session, composition_logo_keys(profile))
    holdings, count, holdings_source = _top_holdings(profile)
    return FundComposition(
        countries=_rows(country_weights, logos) if known != "unknown" else [],
        countries_source=_countries_source(position, known),
        sectors=_rows(sectors),
        sectors_source="Yahoo Finance (Morningstar sectors, shown under MSCI's names)" if sectors else None,
        asset_classes=_rows({CLASS_LABELS.get(k, k): v for k, v in split.items()}) if profile.class_weights else [],
        holdings=holdings,
        holdings_count=count,
        holdings_source=holdings_source,
    )
