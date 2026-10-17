"""Look-through exposure of a portfolio: asset class, country, sector, currency, issuer and fund overlap.

Pure functions over plain inputs, so the math is testable without a database. All values are in the
investor's base currency. Approximations are recorded as notes and shown on the page.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import combinations

from app.enums import AssetClass
from app.health.config import Benchmark

ZERO = Decimal(0)
UNCLASSIFIED = "Unclassified"
BENCHMARK_OTHER = "Other (benchmark mix)"
FUND_CLASSES = (AssetClass.ETF, AssetClass.FUND)
_BOND_NAME = re.compile(r"\b(bond|treasury|treasuries|govt|government|aggregate|corporate|gilt|t-bill)", re.I)
_CLASS_CATEGORY = {"stock": "equity", "bond": "bonds", "cash": "cash", "other": "other"}
_ASSET_CATEGORY = {
    AssetClass.STOCK: "equity",
    AssetClass.BOND: "bonds",
    AssetClass.COMMODITY: "commodities",
    AssetClass.CRYPTO: "crypto",
    AssetClass.CASH: "cash",
    AssetClass.OTHER: "other",
}


@dataclass
class PositionInput:
    asset_id: int
    symbol: str
    name: str | None
    asset_class: AssetClass
    currency: str
    value: Decimal  # base currency
    value_local: Decimal  # asset currency
    price: Decimal | None  # asset currency
    quantity: Decimal
    ter: Decimal | None = None
    provider: str | None = None
    country: str | None = None
    sector: str | None = None  # single stocks: Yahoo sector name
    sector_weights: dict[str, Decimal] | None = None
    class_weights: dict[str, Decimal] | None = None
    top_holdings: dict[str, Decimal] | None = None
    country_weights: dict[str, Decimal] | None = None  # reported by a data provider (Eulerpool)
    holdings: dict[str, Decimal] | None = None  # full holdings by ISIN (Eulerpool)
    logo_url: str | None = None

    @property
    def is_fund(self) -> bool:
        return self.asset_class in FUND_CLASSES


@dataclass
class Overlap:
    first: str
    second: str
    shared: Decimal
    complete: bool  # True: from full holdings; False: top-10 only, so a lower bound


@dataclass
class Exposure:
    total: Decimal  # holdings + cash
    invested: Decimal  # holdings only
    cash: Decimal
    categories: dict[str, Decimal]
    countries: dict[str, Decimal]  # equity only
    sectors: dict[str, Decimal]  # equity only, benchmark (GICS) names
    currencies: dict[str, Decimal]
    issuers: dict[str, Decimal]  # funds by provider
    broad_fund_value: Decimal
    single_stocks: list[PositionInput]
    positions: list[PositionInput]
    ter_value: Decimal  # value of funds with a known TER
    ter_cost: Decimal  # sum(value * TER)
    unknown_ter_value: Decimal
    overlaps: list[Overlap]
    # Equity value by how its country is known: reported (stock HQ or provider data), estimated, unknown.
    country_quality: dict[str, Decimal] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def equity(self) -> Decimal:
        return self.categories.get("equity", ZERO)

    def share(self, values: dict[str, Decimal], key: str, *, exclude: tuple[str, ...] = ()) -> Decimal | None:
        denominator = sum((v for k, v in values.items() if k not in exclude), ZERO)
        return values.get(key, ZERO) / denominator if denominator else None


def category_split(position: PositionInput) -> tuple[dict[str, Decimal], bool]:
    """How a position's value divides across allocation categories; True when approximated."""
    if not position.is_fund:
        return {_ASSET_CATEGORY.get(position.asset_class, "other"): Decimal(1)}, False
    if position.class_weights:
        split: dict[str, Decimal] = defaultdict(Decimal)
        for key, weight in position.class_weights.items():
            split[_CLASS_CATEGORY.get(key, "other")] += weight
        total = sum(split.values(), ZERO)
        if total:
            return {key: weight / total for key, weight in split.items()}, False
    category = "bonds" if _BOND_NAME.search(position.name or "") else "equity"
    return {category: Decimal(1)}, True


def _normalize_sector(raw: str, benchmark: Benchmark) -> str:
    key = raw.strip().lower().replace(" ", "_").replace("-", "_")
    return benchmark.sector_names.get(key, UNCLASSIFIED)


def _countries(position: PositionInput, benchmark: Benchmark) -> tuple[dict[str, Decimal], str, str | None]:
    """Country weights of a position's equity part, how they are known, and a note when estimated."""
    if not position.is_fund:
        if position.country:
            return {position.country: Decimal(1)}, "reported", None
        return {UNCLASSIFIED: Decimal(1)}, "unknown", None
    if position.country_weights:
        # The provider's own unspecified remainder stays unclassified rather than guessed.
        weights = {(UNCLASSIFIED if k == "Other" else k): v for k, v in position.country_weights.items()}
        return weights, "reported", None
    mapping = benchmark.index_for(position.name)
    if mapping is None:
        return {UNCLASSIFIED: Decimal(1)}, "unknown", f"{position.symbol}: country mix unknown"
    note = f"{position.symbol}: countries approximated from its index ({mapping.label})"
    if mapping.countries is None:
        spread = {(BENCHMARK_OTHER if k == "Other" else k): v for k, v in benchmark.countries.items()}
        return spread, "estimated", note
    return mapping.countries, "estimated", note


def _sectors(position: PositionInput, benchmark: Benchmark) -> dict[str, Decimal]:
    if not position.is_fund:
        return (
            {_normalize_sector(position.sector, benchmark): Decimal(1)}
            if position.sector
            else {UNCLASSIFIED: Decimal(1)}
        )
    if not position.sector_weights:
        return {UNCLASSIFIED: Decimal(1)}
    sectors: dict[str, Decimal] = defaultdict(Decimal)
    for raw, weight in position.sector_weights.items():
        sectors[_normalize_sector(raw, benchmark)] += weight
    total = sum(sectors.values(), ZERO)
    return {key: weight / total for key, weight in sectors.items()} if total else {UNCLASSIFIED: Decimal(1)}


def _shared(first: dict[str, Decimal], second: dict[str, Decimal]) -> Decimal:
    return sum((min(first[key], second[key]) for key in set(first) & set(second)), ZERO)


def overlaps(funds: list[PositionInput]) -> list[Overlap]:
    """Portfolio weight two funds have in common: exact from full holdings (matched by ISIN) when both have
    them, otherwise a lower bound from their top-10 lists (matched by symbol)."""
    found = []
    for first, second in combinations(funds, 2):
        if first.holdings and second.holdings:
            # Exact only when both lists cover (nearly) the whole fund.
            covered = min(sum(first.holdings.values(), ZERO), sum(second.holdings.values(), ZERO))
            shared, complete = _shared(first.holdings, second.holdings), covered >= Decimal("0.95")
        elif first.top_holdings and second.top_holdings:
            shared, complete = _shared(first.top_holdings, second.top_holdings), False
        else:
            continue
        if shared > 0:
            found.append(Overlap(first.symbol, second.symbol, shared, complete))
    return sorted(found, key=lambda overlap: overlap.shared, reverse=True)


def build_exposure(positions: list[PositionInput], cash: dict[str, Decimal], benchmark: Benchmark) -> Exposure:
    categories: dict[str, Decimal] = defaultdict(Decimal)
    countries: dict[str, Decimal] = defaultdict(Decimal)
    sectors: dict[str, Decimal] = defaultdict(Decimal)
    currencies: dict[str, Decimal] = defaultdict(Decimal)
    issuers: dict[str, Decimal] = defaultdict(Decimal)
    notes: list[str] = []
    quality: dict[str, Decimal] = defaultdict(Decimal)
    broad = ter_value = ter_cost = unknown_ter = ZERO

    for position in positions:
        split, approximated = category_split(position)
        if approximated:
            notes.append(f"{position.symbol}: asset class guessed from its name")
        for category, weight in split.items():
            categories[category] += position.value * weight
        equity_value = position.value * split.get("equity", ZERO)
        if equity_value:
            country_weights, known, note = _countries(position, benchmark)
            quality[known] += equity_value
            if note:
                notes.append(note)
            for country, weight in country_weights.items():
                countries[country] += equity_value * weight
                currencies[benchmark.region_currencies.get(country, "Other")] += equity_value * weight
            for sector, weight in _sectors(position, benchmark).items():
                sectors[sector] += equity_value * weight
        non_equity = position.value - equity_value
        if non_equity:
            # Bond and commodity prices are set in their trading currency (gold in USD); an approximation for funds.
            currency = "USD" if position.asset_class is AssetClass.COMMODITY else position.currency
            currencies[currency] += non_equity
        if position.is_fund or position.asset_class is AssetClass.COMMODITY:
            issuers[position.provider or "Unknown provider"] += position.value
            if position.ter is not None:
                ter_value += position.value
                ter_cost += position.value * position.ter
            else:
                unknown_ter += position.value
        if position.is_fund and (mapping := benchmark.index_for(position.name)) and mapping.broad:
            broad += position.value

    cash_total = sum(cash.values(), ZERO)
    if cash_total:
        categories["cash"] += cash_total
        for currency, value in cash.items():
            currencies[currency] += value
    invested = sum((p.value for p in positions), ZERO)
    funds = [p for p in positions if p.is_fund]
    return Exposure(
        total=invested + cash_total,
        invested=invested,
        cash=cash_total,
        categories=dict(categories),
        countries=dict(countries),
        sectors=dict(sectors),
        currencies=dict(currencies),
        issuers=dict(issuers),
        broad_fund_value=broad,
        single_stocks=[p for p in positions if p.asset_class is AssetClass.STOCK],
        positions=sorted(positions, key=lambda p: p.value, reverse=True),
        ter_value=ter_value,
        ter_cost=ter_cost,
        unknown_ter_value=unknown_ter,
        overlaps=overlaps(funds),
        country_quality=dict(quality),
        notes=sorted(set(notes)),
    )
