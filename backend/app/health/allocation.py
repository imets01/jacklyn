"""Suggested target allocation from the investor profile: a target-date glide path shifted by risk tolerance."""

import datetime as dt
from decimal import Decimal

from app.health.config import ProfileConfig

ZERO = Decimal(0)
ONE = Decimal(1)
# Allocation categories used for targets, drift and rebalancing.
CATEGORIES = ("equity", "bonds", "commodities", "crypto", "other", "cash")
CATEGORY_LABELS = {
    "equity": "Stocks",
    "bonds": "Bonds",
    "commodities": "Gold & commodities",
    "crypto": "Crypto",
    "other": "Other",
    "cash": "Cash (beyond emergency fund)",
}
RISK_LEVELS = ("conservative", "balanced", "growth", "aggressive")
DEFAULT_RETIREMENT_AGE = 65


def effective_horizon(horizon_years: int | None, birth_year: int | None, today: dt.date) -> int | None:
    """The explicit horizon, else years until 65 from the birth year."""
    if horizon_years is not None:
        return horizon_years
    if birth_year is not None:
        return DEFAULT_RETIREMENT_AGE - (today.year - birth_year)
    return None


def glide_path_equity(horizon_years: int, config: ProfileConfig) -> Decimal:
    """Equity share on a linear version of the glide path; negative horizons are years past the target date."""
    if horizon_years >= config.glide_years:
        return config.glide_start_equity
    if horizon_years >= 0:
        span = config.glide_start_equity - config.glide_target_equity
        return config.glide_target_equity + span * Decimal(horizon_years) / Decimal(config.glide_years)
    past = min(-horizon_years, config.glide_floor_years)
    span = config.glide_target_equity - config.glide_floor_equity
    return config.glide_target_equity - span * Decimal(past) / Decimal(config.glide_floor_years)


def suggested_equity(horizon_years: int, risk_tolerance: str, config: ProfileConfig) -> Decimal:
    shifted = glide_path_equity(horizon_years, config) + config.risk_adjustments.get(risk_tolerance, ZERO)
    return min(ONE, max(ZERO, shifted)).quantize(Decimal("0.01"))


def suggested_targets(equity: Decimal) -> dict[str, Decimal]:
    return {"equity": equity, "bonds": ONE - equity}


def parse_overrides(raw: dict[str, object] | None) -> dict[str, Decimal] | None:
    """Validated manual targets: known categories, each 0..1, summing to 1 (±0.001)."""
    if not raw:
        return None
    targets: dict[str, Decimal] = {}
    for key, value in raw.items():
        if key not in CATEGORIES:
            raise ValueError(f"Unknown category '{key}'.")
        weight = Decimal(str(value))
        if not ZERO <= weight <= ONE:
            raise ValueError(f"Target for {key} must be between 0 and 1.")
        if weight:
            targets[key] = weight
    if abs(sum(targets.values(), ZERO) - ONE) > Decimal("0.001"):
        raise ValueError("Targets must add up to 100%.")
    return targets
