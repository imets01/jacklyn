"""Portfolio Health API models."""

import datetime as dt
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.health.allocation import CATEGORIES, RISK_LEVELS, parse_overrides

Severity = Literal["good", "info", "warning", "problem"]


class InvestorProfileIn(BaseModel):
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    horizon_years: int | None = Field(default=None, ge=-40, le=80)
    risk_tolerance: str = "balanced"
    goal: str | None = Field(default=None, max_length=40)
    home_country: str = Field(default="Switzerland", min_length=2, max_length=64)
    currency: str = Field(default="CHF", pattern=r"^[A-Z]{3}$")  # of the money amounts below
    emergency_fund: Decimal | None = Field(default=None, ge=0)
    monthly_contribution: Decimal | None = Field(default=None, ge=0)
    min_order: Decimal = Field(default=Decimal(0), ge=0)
    fractional_shares: bool = True
    target_overrides: dict[str, Decimal] | None = None

    @field_validator("risk_tolerance")
    @classmethod
    def _risk(cls, value: str) -> str:
        if value not in RISK_LEVELS:
            raise ValueError(f"Choose one of: {', '.join(RISK_LEVELS)}")
        return value

    @model_validator(mode="after")
    def _targets(self) -> Self:
        if self.target_overrides:
            parse_overrides(dict(self.target_overrides))  # raises a readable ValueError
        return self


class InvestorProfileOut(InvestorProfileIn):
    model_config = ConfigDict(from_attributes=True)

    updated_at: dt.datetime


class CitationOut(BaseModel):
    title: str
    publisher: str
    year: int
    url: str
    note: str | None


class FindingOut(BaseModel):
    rule_id: str
    title: str
    severity: Severity
    message: str
    value: str
    threshold: str
    explanation: str
    threshold_note: str
    citations: list[CitationOut]


class ScoreLineOut(BaseModel):
    rule_id: str
    title: str
    severity: Severity
    points: int


class RuleOut(BaseModel):
    id: str
    title: str
    levels: list[str]
    threshold_note: str
    citations: list[CitationOut]


class Slice(BaseModel):
    key: str
    label: str
    value: Decimal
    weight: Decimal
    compare: Decimal | None = None  # benchmark or target weight


class Breakdown(BaseModel):
    title: str
    compare_label: str | None
    slices: list[Slice]
    note: str | None = None


class PositionWeight(BaseModel):
    asset_id: int
    symbol: str
    name: str | None
    asset_class: str
    logo_url: str | None
    value: Decimal
    weight: Decimal
    ter: Decimal | None


class OverlapOut(BaseModel):
    first: str
    second: str
    shared: Decimal
    complete: bool  # full holdings (exact) vs. top-10 only (lower bound)


class SourceOut(BaseModel):
    title: str
    publisher: str
    url: str
    as_of: str


class OrderOut(BaseModel):
    category: str
    category_label: str
    amount: Decimal
    asset_id: int | None
    symbol: str | None
    name: str | None
    asset_class: str | None
    logo_url: str | None
    currency: str | None
    quantity: Decimal | None
    local_amount: Decimal | None


class CategoryRow(BaseModel):
    category: str
    label: str
    value: Decimal
    before: Decimal
    after: Decimal
    target: Decimal
    band: Decimal
    buy: Decimal  # contribution plan
    full_rebalance: Decimal  # +buy / −sell to hit the target today


class RebalanceOut(BaseModel):
    amount: Decimal
    monthly_contribution: Decimal
    idle_cash: Decimal
    include_idle_cash: bool
    fractional_shares: bool
    min_order: Decimal
    rows: list[CategoryRow]
    orders: list[OrderOut]
    unspent: Decimal
    in_band_before: bool
    in_band_after: bool
    months_to_band: int | None


class TerSummary(BaseModel):
    weighted: Decimal | None
    covered_value: Decimal
    uncovered_value: Decimal


class HealthReport(BaseModel):
    base_currency: str
    as_of: dt.date
    has_holdings: bool
    profile: InvestorProfileOut | None
    horizon_years: int | None
    suggested_equity: Decimal | None
    targets: dict[str, Decimal] | None
    targets_source: Literal["profile", "manual"] | None
    glide_citation: CitationOut
    total: Decimal
    invested: Decimal
    cash: Decimal
    score: int
    score_start: int
    score_penalties: dict[str, int]
    score_lines: list[ScoreLineOut]
    findings: list[FindingOut]
    skipped_rules: list[str]
    breakdowns: dict[str, Breakdown]
    positions: list[PositionWeight]
    ter: TerSummary
    overlaps: list[OverlapOut]
    country_quality: dict[str, Decimal]  # share of stock value whose country is reported / estimated / unknown
    look_through_provider: str | None
    notes: list[str]
    benchmark_name: str
    benchmark_sources: list[SourceOut]
    rebalance: RebalanceOut | None
    rules: list[RuleOut]


__all__ = ["CATEGORIES", "HealthReport", "InvestorProfileIn", "InvestorProfileOut"]
