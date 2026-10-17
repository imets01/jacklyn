"""Builds the Portfolio Health report from the database: holdings, profiles, rules and rebalancing."""

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.health.allocation import (
    CATEGORY_LABELS,
    effective_horizon,
    parse_overrides,
    suggested_equity,
    suggested_targets,
)
from app.health.config import Citation, load_benchmark, load_rules
from app.health.exposure import BENCHMARK_OTHER, UNCLASSIFIED, Exposure, PositionInput, build_exposure, category_split
from app.health.rebalance import Instrument, full_rebalance, plan_contribution
from app.health.rules import HealthContext, band, evaluate
from app.models import AssetProfile, InvestorProfile
from app.schemas.health import (
    Breakdown,
    CategoryRow,
    CitationOut,
    FindingOut,
    HealthReport,
    InvestorProfileOut,
    OrderOut,
    OverlapOut,
    PositionWeight,
    RebalanceOut,
    RuleOut,
    ScoreLineOut,
    Slice,
    SourceOut,
    TerSummary,
)
from app.services.portfolio import PortfolioEngine

ZERO = Decimal(0)
WEIGHT = Decimal("0.0001")


def _decimal_map(raw: dict[str, str] | None) -> dict[str, Decimal] | None:
    if not raw:
        return None
    return {key: Decimal(str(value)) for key, value in raw.items()}


def _citation(citation: Citation) -> CitationOut:
    return CitationOut(
        title=citation.title, publisher=citation.publisher, year=citation.year, url=citation.url, note=citation.note
    )


def load_positions(session: Session, engine: PortfolioEngine) -> tuple[list[PositionInput], dict[str, Decimal]]:
    """Holdings combined across accounts, with their profile data, plus cash per currency in base currency."""
    holdings = engine.holdings()
    by_asset: dict[int, PositionInput] = {}
    for holding in holdings.holdings:
        existing = by_asset.get(holding.asset_id)
        if existing:
            existing.value += holding.value
            existing.value_local += holding.value_local
            existing.quantity += holding.quantity
            continue
        by_asset[holding.asset_id] = PositionInput(
            asset_id=holding.asset_id,
            symbol=holding.symbol,
            name=holding.name,
            asset_class=holding.asset_class,
            currency=holding.currency,
            value=holding.value,
            value_local=holding.value_local,
            price=holding.price,
            quantity=holding.quantity,
            logo_url=holding.logo_url,
        )
    if by_asset:
        for profile in session.scalars(select(AssetProfile).where(AssetProfile.asset_id.in_(by_asset))):
            position = by_asset[profile.asset_id]
            position.ter = profile.expense_ratio
            position.provider = profile.provider
            position.country = profile.country
            position.sector = profile.sector
            position.name = position.name or profile.long_name
            position.sector_weights = _decimal_map(profile.sector_weights)
            position.class_weights = _decimal_map(profile.class_weights)
            position.top_holdings = _decimal_map(profile.top_holdings)
            position.country_weights = _decimal_map(profile.country_weights)
            position.holdings = _decimal_map(profile.holdings)
    cash: dict[str, Decimal] = defaultdict(Decimal)
    for balance in holdings.cash:
        cash[balance.currency] += balance.value
    return [p for p in by_asset.values() if p.value > 0], dict(cash)


def _breakdown(
    title: str,
    values: dict[str, Decimal],
    compare: dict[str, Decimal] | None,
    compare_label: str | None,
    note: str | None = None,
    labels: dict[str, str] | None = None,
    *,
    classified_only: bool = False,
) -> Breakdown:
    """Slices with weights; `classified_only` measures weights over classified values, as the rules do."""
    unclassified = values.get(UNCLASSIFIED, ZERO)
    if classified_only and unclassified:
        everything = sum(values.values(), ZERO)
        values = {k: v for k, v in values.items() if k != UNCLASSIFIED}
        share = f"{unclassified / everything * 100:.1f}%" if everything else "0%"
        note = (
            f"{note} {share} of stocks has no data and is left out."
            if note
            else f"{share} has no data and is left out."
        )
    total = sum(values.values(), ZERO)
    keys = sorted(
        set(values) | set(compare or {}),
        key=lambda k: (k in (UNCLASSIFIED, BENCHMARK_OTHER, "Other"), -values.get(k, ZERO)),
    )
    slices = [
        Slice(
            key=key,
            label=(labels or {}).get(key, key),
            value=values.get(key, ZERO).quantize(Decimal("0.01")),
            weight=(values.get(key, ZERO) / total).quantize(WEIGHT) if total else ZERO,
            compare=(compare.get(key) if compare is not None else None),
        )
        for key in keys
        if values.get(key, ZERO) > 0 or (compare and compare.get(key))
    ]
    return Breakdown(title=title, compare_label=compare_label, slices=slices, note=note)


def _country_note(exposure: Exposure) -> str:
    estimated = exposure.country_quality.get("estimated", ZERO)
    if not estimated:
        return "Countries as reported: company headquarters for stocks, fund holdings data for funds."
    return "Some funds' countries are estimated from the index they track; see the data notes."


def _breakdowns(exposure: Exposure, ctx: HealthContext) -> dict[str, Breakdown]:
    benchmark = ctx.benchmark
    allocation = ctx.allocation()
    target_compare = dict(ctx.targets) if ctx.targets else None
    countries = dict(exposure.countries)
    bench_countries = {(BENCHMARK_OTHER if k == "Other" else k): v for k, v in benchmark.countries.items()}
    return {
        "asset_class": _breakdown(
            "Asset class",
            allocation,
            target_compare,
            "Target" if target_compare else None,
            note="Cash counts only beyond your emergency fund.",
            labels=CATEGORY_LABELS,
        ),
        "country": _breakdown(
            "Country (stocks)",
            countries,
            bench_countries,
            benchmark.name,
            note=_country_note(exposure),
            classified_only=True,
        ),
        "sector": _breakdown(
            "Sector (stocks)",
            exposure.sectors,
            benchmark.sectors,
            benchmark.name,
            note="Morningstar sectors (Yahoo) mapped to GICS (MSCI): approximate.",
            classified_only=True,
        ),
        "currency": _breakdown(
            "Currency exposure",
            exposure.currencies,
            None,
            None,
            note="By where the businesses are, not the currency a fund trades in. Information only.",
        ),
        "issuer": _breakdown("Fund providers", exposure.issuers, None, None),
    }


def _instruments(positions: list[PositionInput]) -> list[Instrument]:
    instruments = []
    for position in positions:
        split, _ = category_split(position)
        category = max(split.items(), key=lambda item: item[1])[0]
        if not position.value or not position.value_local:
            continue
        instruments.append(
            Instrument(
                asset_id=position.asset_id,
                symbol=position.symbol,
                name=position.name,
                category=category,
                currency=position.currency,
                price=position.price,
                local_per_base=position.value_local / position.value,
                value=position.value,
                ter=position.ter,
                logo_url=position.logo_url,
                asset_class=position.asset_class.value,
            )
        )
    return instruments


def _rebalance(
    ctx: HealthContext,
    positions: list[PositionInput],
    profile: InvestorProfile | None,
    amount: Decimal | None,
    include_idle_cash: bool,
) -> RebalanceOut | None:
    targets = ctx.targets
    if not targets:
        return None
    monthly = (profile.monthly_contribution if profile else None) or ZERO
    fractional = profile.fractional_shares if profile else True
    min_order = profile.min_order if profile else ZERO
    values = ctx.allocation()
    idle = values.get("cash", ZERO)
    budget = monthly if amount is None else amount
    if include_idle_cash and idle:
        budget += idle
        values = {k: v for k, v in values.items() if k != "cash"}
    plan = plan_contribution(
        values,
        targets,
        budget,
        _instruments(positions),
        monthly=monthly,
        absolute=ctx.absolute_band,
        relative=ctx.relative_band,
        fractional=fractional,
        min_order=min_order,
    )
    full = full_rebalance(ctx.allocation(), targets)
    bought: dict[str, Decimal] = defaultdict(Decimal)
    for order in plan.orders:
        bought[order.category] += order.amount
    keys = sorted(set(values) | set(targets) | set(full), key=lambda k: -targets.get(k, ZERO))
    rows = [
        CategoryRow(
            category=key,
            label=CATEGORY_LABELS.get(key, key),
            value=values.get(key, ZERO).quantize(Decimal("0.01")),
            before=plan.before.get(key, ZERO).quantize(WEIGHT),
            after=plan.after.get(key, ZERO).quantize(WEIGHT),
            target=targets.get(key, ZERO),
            band=band(targets.get(key, ZERO), ctx.absolute_band, ctx.relative_band),
            buy=bought.get(key, ZERO),
            full_rebalance=full.get(key, ZERO),
        )
        for key in keys
    ]
    orders = [
        OrderOut(
            category=order.category,
            category_label=CATEGORY_LABELS.get(order.category, order.category),
            amount=order.amount,
            asset_id=order.instrument.asset_id if order.instrument else None,
            symbol=order.instrument.symbol if order.instrument else None,
            name=order.instrument.name if order.instrument else None,
            asset_class=order.instrument.asset_class if order.instrument else None,
            logo_url=order.instrument.logo_url if order.instrument else None,
            currency=order.instrument.currency if order.instrument else None,
            quantity=order.quantity,
            local_amount=order.local_amount,
        )
        for order in plan.orders
    ]
    return RebalanceOut(
        amount=budget.quantize(Decimal("0.01")),
        monthly_contribution=monthly,
        idle_cash=idle.quantize(Decimal("0.01")),
        include_idle_cash=include_idle_cash,
        fractional_shares=fractional,
        min_order=min_order,
        rows=rows,
        orders=orders,
        unspent=plan.unspent,
        in_band_before=plan.in_band_before,
        in_band_after=plan.in_band_after,
        months_to_band=plan.months_to_band,
    )


def build_report(
    session: Session,
    *,
    user_id: int,
    base_currency: str,
    amount: Decimal | None = None,
    include_idle_cash: bool = False,
    today: dt.date | None = None,
) -> HealthReport:
    today = today or dt.date.today()
    rules, benchmark = load_rules(), load_benchmark()
    engine = PortfolioEngine(session, user_id=user_id, base_currency=base_currency, as_of=today)
    positions, cash = load_positions(session, engine)
    exposure = build_exposure(positions, cash, benchmark)

    profile = session.get(InvestorProfile, user_id)
    horizon = effective_horizon(profile.horizon_years, profile.birth_year, today) if profile else None
    suggested = (
        suggested_equity(horizon, profile.risk_tolerance, rules.profile) if profile and horizon is not None else None
    )
    manual = parse_overrides(profile.target_overrides) if profile else None
    targets = manual or (suggested_targets(suggested) if suggested is not None else None)

    ctx = HealthContext(
        exposure=exposure,
        benchmark=benchmark,
        base_currency=base_currency,
        home_country=profile.home_country if profile else "Switzerland",
        emergency_fund=(profile.emergency_fund or ZERO) if profile else ZERO,
        targets=targets,
        suggested_equity=suggested,
        absolute_band=rules.absolute_band,
        relative_band=rules.relative_band,
    )
    result = evaluate(rules, ctx)
    total = exposure.total
    return HealthReport(
        base_currency=base_currency,
        as_of=today,
        has_holdings=bool(positions or cash),
        profile=InvestorProfileOut.model_validate(profile, from_attributes=True) if profile else None,
        horizon_years=horizon,
        suggested_equity=suggested,
        targets=targets,
        targets_source="manual" if manual else ("profile" if targets else None),
        glide_citation=_citation(rules.profile.citation),
        total=total.quantize(Decimal("0.01")),
        invested=exposure.invested.quantize(Decimal("0.01")),
        cash=exposure.cash.quantize(Decimal("0.01")),
        score=result.score,
        score_start=rules.score_start,
        score_penalties=rules.penalties,
        score_lines=[ScoreLineOut(**vars(line)) for line in result.score_lines],
        findings=[
            FindingOut(
                rule_id=f.rule_id,
                title=f.title,
                severity=f.severity,
                message=f.message,
                value=f.value,
                threshold=f.threshold,
                explanation=f.explanation,
                threshold_note=f.threshold_note,
                citations=[_citation(c) for c in f.citations],
            )
            for f in result.findings
        ],
        skipped_rules=result.skipped,
        breakdowns=_breakdowns(exposure, ctx),
        positions=[
            PositionWeight(
                asset_id=p.asset_id,
                symbol=p.symbol,
                name=p.name,
                asset_class=p.asset_class.value,
                logo_url=p.logo_url,
                value=p.value,
                weight=(p.value / total).quantize(WEIGHT) if total else ZERO,
                ter=p.ter,
            )
            for p in exposure.positions
        ],
        ter=TerSummary(
            weighted=(exposure.ter_cost / exposure.ter_value).quantize(Decimal("0.00001"))
            if exposure.ter_value
            else None,
            covered_value=exposure.ter_value.quantize(Decimal("0.01")),
            uncovered_value=exposure.unknown_ter_value.quantize(Decimal("0.01")),
        ),
        overlaps=[
            OverlapOut(first=o.first, second=o.second, shared=o.shared.quantize(WEIGHT), complete=o.complete)
            for o in exposure.overlaps
        ],
        country_quality={
            key: (value / exposure.equity).quantize(WEIGHT) for key, value in exposure.country_quality.items()
        }
        if exposure.equity
        else {},
        look_through_provider="Eulerpool" if any(p.country_weights or p.holdings for p in positions) else None,
        notes=exposure.notes,
        benchmark_name=benchmark.name,
        benchmark_sources=[
            SourceOut(title=s.title, publisher=s.publisher, url=s.url, as_of=s.as_of)
            for s in (benchmark.sectors_source, benchmark.countries_source)
        ],
        rebalance=_rebalance(ctx, positions, profile, amount, include_idle_cash),
        rules=[
            RuleOut(
                id=rule.id,
                title=rule.title,
                levels=[f"{lv.severity}: {lv.op} {lv.threshold}" for lv in rule.levels],
                threshold_note=rule.threshold_note,
                citations=[_citation(c) for c in rule.citations],
            )
            for rule in rules.rules
        ],
    )
