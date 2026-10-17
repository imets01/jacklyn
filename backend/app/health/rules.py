"""Deterministic rules engine: named metrics computed from the exposure, compared with rules.toml thresholds."""

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from app.health.allocation import CATEGORY_LABELS
from app.health.config import Benchmark, Citation, Rule, RuleSet, Severity, ValueFormat
from app.health.exposure import BENCHMARK_OTHER, UNCLASSIFIED, Exposure

ZERO = Decimal(0)
EUROPE_UNSPLIT = "Europe (broad, not split)"
EUROPEAN = {"United Kingdom", "France", "Germany", "Switzerland"}


def pct(value: Decimal, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def fmt(value: Decimal, kind: ValueFormat) -> str:
    match kind:
        case "percent":
            return pct(value, 2 if abs(value) < Decimal("0.01") else 1)
        case "points":
            return f"{value * 100:.1f} points"
        case "multiple":
            return f"{value:.1f}×"
        case _:
            return f"{value:.0f}"


def money(value: Decimal, currency: str) -> str:
    return f"{currency} {value:,.0f}"


def band(target: Decimal, absolute: Decimal, relative: Decimal) -> Decimal:
    """Tolerance around a target: the smaller of the absolute and relative bands (absolute for a 0 target)."""
    return min(absolute, relative * target) if target > 0 else absolute


@dataclass
class HealthContext:
    exposure: Exposure
    benchmark: Benchmark
    base_currency: str
    home_country: str
    emergency_fund: Decimal
    targets: dict[str, Decimal] | None
    suggested_equity: Decimal | None
    absolute_band: Decimal
    relative_band: Decimal

    @property
    def excess_cash(self) -> Decimal:
        return max(ZERO, self.exposure.categories.get("cash", ZERO) - self.emergency_fund)

    def allocation(self) -> dict[str, Decimal]:
        """Values per category for allocation purposes: cash counts only beyond the emergency fund."""
        values = {key: value for key, value in self.exposure.categories.items() if key != "cash"}
        if self.excess_cash:
            values["cash"] = self.excess_cash
        return values

    @property
    def investable(self) -> Decimal:
        return sum(self.allocation().values(), ZERO)

    def equity_countries(self) -> dict[str, Decimal]:
        return {k: v for k, v in self.exposure.countries.items() if k != UNCLASSIFIED}

    def equity_sectors(self) -> dict[str, Decimal]:
        return {k: v for k, v in self.exposure.sectors.items() if k != UNCLASSIFIED}


@dataclass
class MetricResult:
    value: Decimal
    context: dict[str, str] = field(default_factory=dict)


MetricFn = Callable[[HealthContext], MetricResult | None]
METRICS: dict[str, MetricFn] = {}


def metric(name: str) -> Callable[[MetricFn], MetricFn]:
    def register(fn: MetricFn) -> MetricFn:
        METRICS[name] = fn
        return fn

    return register


@metric("max_single_stock_weight")
def _max_single_stock(ctx: HealthContext) -> MetricResult | None:
    if not ctx.exposure.single_stocks or not ctx.exposure.total:
        return None
    largest = max(ctx.exposure.single_stocks, key=lambda p: p.value)
    return MetricResult(largest.value / ctx.exposure.total, {"asset": largest.name or largest.symbol})


@metric("single_stock_count_without_broad_fund")
def _stock_count(ctx: HealthContext) -> MetricResult | None:
    if ctx.exposure.broad_fund_value > 0 or not ctx.exposure.single_stocks:
        return None
    return MetricResult(Decimal(len(ctx.exposure.single_stocks)))


@metric("home_equity_multiple")
def _home_bias(ctx: HealthContext) -> MetricResult | None:
    bench = ctx.benchmark.countries.get(ctx.home_country)
    countries = ctx.equity_countries()
    share = ctx.exposure.share(countries, ctx.home_country) if countries else None
    if not bench or share is None:
        return None
    return MetricResult(
        share / bench, {"home": ctx.home_country, "home_share": pct(share), "benchmark_share": pct(bench)}
    )


@metric("max_country_deviation")
def _country_deviation(ctx: HealthContext) -> MetricResult | None:
    countries = ctx.equity_countries()
    if not countries:
        return None
    # A broad-Europe fund hides its UK/French/German/Swiss split, so those countries can't be compared fairly.
    skip = EUROPEAN if countries.get(EUROPE_UNSPLIT) else set()
    worst: tuple[Decimal, str, Decimal, Decimal] | None = None
    for country, bench in ctx.benchmark.countries.items():
        if country == "Other" or country in skip:
            continue
        share = ctx.exposure.share(countries, country) or ZERO
        gap = abs(share - bench)
        if worst is None or gap > worst[0]:
            worst = (gap, country, share, bench)
    if worst is None:
        return None
    gap, country, share, bench = worst
    return MetricResult(gap, {"country": country, "share": pct(share), "benchmark_share": pct(bench)})


@metric("max_sector_overweight")
def _sector_overweight(ctx: HealthContext) -> MetricResult | None:
    sectors = ctx.equity_sectors()
    if not sectors:
        return None
    gaps = [((ctx.exposure.share(sectors, s) or ZERO) - b, s, b) for s, b in ctx.benchmark.sectors.items()]
    gap, sector, bench = max(gaps)
    share = ctx.exposure.share(sectors, sector) or ZERO
    return MetricResult(gap, {"sector": sector, "share": pct(share), "benchmark_share": pct(bench)})


@metric("weighted_ter")
def _weighted_ter(ctx: HealthContext) -> MetricResult | None:
    if not ctx.exposure.ter_value:
        return None
    return MetricResult(ctx.exposure.ter_cost / ctx.exposure.ter_value)


@metric("max_allocation_drift")
def _drift(ctx: HealthContext) -> MetricResult | None:
    if not ctx.targets or not ctx.investable:
        return None
    allocation = ctx.allocation()
    worst: tuple[Decimal, str, Decimal, Decimal, Decimal] | None = None
    for category in set(ctx.targets) | set(allocation):
        target = ctx.targets.get(category, ZERO)
        actual = allocation.get(category, ZERO) / ctx.investable
        tolerance = band(target, ctx.absolute_band, ctx.relative_band)
        ratio = abs(actual - target) / tolerance
        if worst is None or ratio > worst[0]:
            worst = (ratio, category, actual, target, tolerance)
    if worst is None:
        return None
    ratio, category, actual, target, tolerance = worst
    return MetricResult(
        ratio,
        {
            "category": CATEGORY_LABELS.get(category, category),
            "actual": pct(actual),
            "target": pct(target),
            "band": f"{tolerance * 100:.1f} points",
        },
    )


@metric("equity_profile_gap")
def _equity_gap(ctx: HealthContext) -> MetricResult | None:
    if ctx.suggested_equity is None or not ctx.investable:
        return None
    actual = ctx.allocation().get("equity", ZERO) / ctx.investable
    return MetricResult(
        abs(actual - ctx.suggested_equity), {"actual": pct(actual), "suggested": pct(ctx.suggested_equity)}
    )


@metric("excess_cash_share")
def _excess_cash(ctx: HealthContext) -> MetricResult | None:
    if not ctx.exposure.total:
        return None
    excess = ctx.excess_cash
    return MetricResult(excess / ctx.exposure.total, {"excess": money(excess, ctx.base_currency)})


@metric("broad_fund_share")
def _broad_share(ctx: HealthContext) -> MetricResult | None:
    if not ctx.exposure.invested:
        return None
    return MetricResult(ctx.exposure.broad_fund_value / ctx.exposure.invested)


@dataclass
class Finding:
    rule_id: str
    title: str
    severity: Severity
    message: str
    value: str
    threshold: str
    explanation: str
    threshold_note: str
    citations: tuple[Citation, ...]


@dataclass
class ScoreLine:
    rule_id: str
    title: str
    severity: Severity
    points: int


@dataclass
class HealthResult:
    findings: list[Finding]
    score: int
    score_lines: list[ScoreLine]
    skipped: list[str]  # rule ids that didn't apply (no data, no profile)


def _finding(rule: Rule, result: MetricResult) -> Finding | None:
    issue_levels = [level for level in rule.levels if level.severity != "good"]
    matched = next((level for level in rule.levels if level.matches(result.value)), None)
    severity: Severity
    if matched is not None and matched.severity != "good":
        severity, template, threshold = matched.severity, rule.message, matched.threshold
    elif matched is not None:
        severity, template, threshold = "good", rule.good_message or rule.pass_message or "", matched.threshold
    elif rule.pass_message and issue_levels:
        severity, template, threshold = "good", rule.pass_message, issue_levels[-1].threshold
    else:
        return None
    value, limit = fmt(result.value, rule.format), fmt(threshold, rule.format)
    return Finding(
        rule_id=rule.id,
        title=rule.title,
        severity=severity,
        message=template.format(value=value, threshold=limit, **result.context),
        value=value,
        threshold=limit,
        explanation=rule.explanation,
        threshold_note=rule.threshold_note,
        citations=rule.citations,
    )


def evaluate(ruleset: RuleSet, ctx: HealthContext) -> HealthResult:
    findings: list[Finding] = []
    skipped: list[str] = []
    for rule in ruleset.rules:
        result = METRICS[rule.metric](ctx)
        if result is None:
            skipped.append(rule.id)
            continue
        if (finding := _finding(rule, result)) is not None:
            findings.append(finding)
    lines = [
        ScoreLine(f.rule_id, f.title, f.severity, -ruleset.penalties.get(f.severity, 0))
        for f in findings
        if ruleset.penalties.get(f.severity, 0)
    ]
    score = max(0, ruleset.score_start + sum(line.points for line in lines))
    order = {"problem": 0, "warning": 1, "info": 2, "good": 3}
    findings.sort(key=lambda f: order[f.severity])
    return HealthResult(findings=findings, score=score, score_lines=lines, skipped=skipped)


__all__ = ["BENCHMARK_OTHER", "METRICS", "Finding", "HealthContext", "HealthResult", "band", "evaluate"]
