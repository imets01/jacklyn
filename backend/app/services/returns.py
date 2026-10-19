"""Rates of return that ignore how much money was added or withdrawn along the way.

* Money-weighted (XIRR): the yearly rate that makes all money in, all money out and the value at the end
  balance out. Each deposit counts for as long as it was invested, so it reflects your timing too.
* Time-weighted (TWR): the investments' own growth between deposits and withdrawals, chained together.
  Timing and size of deposits don't affect it, which makes it fair to compare accounts or an index.

Both run in Decimal. Periods under a year are reported as the total over the period, not per year: a yearly
rate from a few weeks of data exaggerates.
"""

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from itertools import pairwise

ZERO = Decimal(0)
ONE = Decimal(1)
YEAR = Decimal(365)
# One basis point is plenty for a rate shown with one decimal place.
_TOLERANCE = Decimal("0.00001")
_LOWEST, _HIGHEST = Decimal("-0.9999"), Decimal(100)


@dataclass(frozen=True)
class Snapshot:
    """An account (or several) at the end of a day: market value, and all money put in so far minus taken out."""

    day: dt.date
    value: Decimal
    net_flows: Decimal


def _growth(rate: Decimal, years: Decimal) -> Decimal:
    return (ONE + rate) ** years


def xirr(flows: Sequence[tuple[dt.date, Decimal]]) -> Decimal | None:
    """Yearly rate r with sum(amount / (1 + r) ** years_since_first) == 0.

    Flows are from the investor's side: money put in is negative, money taken out (and the value at the end)
    positive. None when there is no answer, e.g. money only went one way.
    """
    if not any(amount < 0 for _, amount in flows) or not any(amount > 0 for _, amount in flows):
        return None
    first = min(day for day, _ in flows)
    timed = [(Decimal((day - first).days) / YEAR, amount) for day, amount in flows]

    def npv(rate: Decimal) -> Decimal:
        return sum((amount / _growth(rate, years) for years, amount in timed), ZERO)

    with localcontext() as context:
        context.prec = 28
        try:
            low, high = _LOWEST, _HIGHEST
            npv_low, npv_high = npv(low), npv(high)
            if (npv_low > 0) == (npv_high > 0):
                return None
            # Bisection: slower than Newton's method but always converges once the root is bracketed.
            while high - low > _TOLERANCE:
                middle = (low + high) / 2
                npv_middle = npv(middle)
                if (npv_middle > 0) == (npv_low > 0):
                    low, npv_low = middle, npv_middle
                else:
                    high = middle
        except (InvalidOperation, OverflowError, ZeroDivisionError):
            return None
    return (low + high) / 2


def time_weighted(snapshots: Sequence[Snapshot]) -> Decimal | None:
    """Total growth over the snapshots, chaining the return of each stretch between two of them.

    Money moved in or out on a day is assumed to arrive at its end, so that day's market move belongs to the
    money already there. Stretches that start with nothing invested are skipped (the first deposit).
    """
    total = ONE
    measured = False
    for previous, current in pairwise(snapshots):
        if previous.value <= 0:
            continue
        flow = current.net_flows - previous.net_flows
        total *= (current.value - flow) / previous.value
        measured = True
    return total - ONE if measured else None


def per_year(total: Decimal, days: int) -> Decimal:
    """A total return over `days` as a yearly rate."""
    if total <= -1:
        return Decimal(-1)
    return _growth(total, YEAR / Decimal(days)) - ONE


def over_period(yearly: Decimal, days: int) -> Decimal:
    """A yearly rate as the total over `days`."""
    return _growth(yearly, Decimal(days) / YEAR) - ONE
