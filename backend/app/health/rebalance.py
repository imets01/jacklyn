"""Rebalancing math: contribution-only plans, orders in real shares, months back to target, full rebalance.

All pure functions over Decimals in the base currency, so every number on the page can be unit-tested.
"""

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from app.health.rules import band

ZERO = Decimal(0)
CENT = Decimal("0.01")
FRACTION_STEP = Decimal("0.0001")
MAX_MONTHS = 240


@dataclass(frozen=True)
class Instrument:
    """A holding that can receive new money."""

    asset_id: int
    symbol: str
    name: str | None
    category: str
    currency: str
    price: Decimal | None  # in `currency`
    local_per_base: Decimal  # units of `currency` per unit of base currency
    value: Decimal  # current holding value, base currency
    ter: Decimal | None
    logo_url: str | None = None
    asset_class: str = "etf"


@dataclass(frozen=True)
class Order:
    category: str
    amount: Decimal  # base currency
    instrument: Instrument | None  # None: you hold nothing in this category yet
    quantity: Decimal | None
    local_amount: Decimal | None


@dataclass(frozen=True)
class Plan:
    amount: Decimal
    split: dict[str, Decimal]
    orders: list[Order]
    unspent: Decimal
    before: dict[str, Decimal]  # shares of the investable total
    after: dict[str, Decimal]
    in_band_before: bool
    in_band_after: bool
    months_to_band: int | None  # at this monthly amount; None = not within MAX_MONTHS (or nothing to add)


def shares(values: dict[str, Decimal]) -> dict[str, Decimal]:
    total = sum(values.values(), ZERO)
    return {key: (value / total if total else ZERO) for key, value in values.items()}


def within_band(values: dict[str, Decimal], targets: dict[str, Decimal], absolute: Decimal, relative: Decimal) -> bool:
    current = shares(values)
    return all(
        abs(current.get(key, ZERO) - targets.get(key, ZERO)) <= band(targets.get(key, ZERO), absolute, relative)
        for key in set(current) | set(targets)
    )


def contribution_split(values: dict[str, Decimal], targets: dict[str, Decimal], amount: Decimal) -> dict[str, Decimal]:
    """Divide new money without selling: fill each category's shortfall versus its target after the deposit.

    If the shortfalls exceed the deposit they are filled proportionally; any money left after closing every
    shortfall is spread by target weight. The result always sums to `amount`.
    """
    if amount <= 0:
        return {}
    total_after = sum(values.values(), ZERO) + amount
    shortfalls = {
        key: max(ZERO, weight * total_after - values.get(key, ZERO)) for key, weight in targets.items() if weight > 0
    }
    needed = sum(shortfalls.values(), ZERO)
    if needed == 0:
        split = {key: amount * weight for key, weight in targets.items() if weight > 0}
    elif needed >= amount:
        split = {key: amount * gap / needed for key, gap in shortfalls.items() if gap > 0}
    else:
        rest = amount - needed
        split = {key: gap + rest * targets[key] for key, gap in shortfalls.items()}
    return {key: value for key, value in split.items() if value > 0}


def choose_instrument(candidates: list[Instrument]) -> Instrument | None:
    """Cheapest fund first (unknown TER last), then the largest existing position."""
    if not candidates:
        return None
    return min(candidates, key=lambda i: (i.ter is None, i.ter or ZERO, -i.value))


def build_orders(
    split: dict[str, Decimal],
    instruments: list[Instrument],
    *,
    fractional: bool,
    min_order: Decimal,
) -> tuple[list[Order], Decimal]:
    """Turn category amounts into orders. Money that can't buy a share (or a minimum order) rolls on to the
    next category; whatever is left at the end is returned as unspent."""
    orders: list[Order] = []
    carry = ZERO
    for category, planned in sorted(split.items(), key=lambda item: item[1], reverse=True):
        budget = planned + carry
        carry = ZERO
        instrument = choose_instrument([i for i in instruments if i.category == category])
        if instrument is None:
            orders.append(Order(category, budget.quantize(CENT), None, None, None))
            continue
        if instrument.price is None or instrument.price <= 0:
            carry = budget
            continue
        local_budget = budget * instrument.local_per_base
        step = FRACTION_STEP if fractional else Decimal(1)
        quantity = (local_budget / instrument.price).quantize(step, rounding=ROUND_DOWN)
        local_cost = quantity * instrument.price
        cost = local_cost / instrument.local_per_base
        if quantity <= 0 or cost < min_order:
            carry = budget
            continue
        orders.append(Order(category, cost.quantize(CENT), instrument, quantity, local_cost.quantize(CENT)))
        carry = budget - cost
    return orders, carry.quantize(CENT)


def months_to_band(
    values: dict[str, Decimal],
    targets: dict[str, Decimal],
    monthly: Decimal,
    absolute: Decimal,
    relative: Decimal,
) -> int | None:
    """Months of contribution-only investing (prices unchanged) until every category is within its band."""
    current = dict(values)
    for month in range(MAX_MONTHS + 1):
        if within_band(current, targets, absolute, relative):
            return month
        if monthly <= 0:
            return None
        for key, amount in contribution_split(current, targets, monthly).items():
            current[key] = current.get(key, ZERO) + amount
    return None


def plan_contribution(
    values: dict[str, Decimal],
    targets: dict[str, Decimal],
    amount: Decimal,
    instruments: list[Instrument],
    *,
    monthly: Decimal,
    absolute: Decimal,
    relative: Decimal,
    fractional: bool = True,
    min_order: Decimal = ZERO,
) -> Plan:
    split = contribution_split(values, targets, amount)
    orders, unspent = build_orders(split, instruments, fractional=fractional, min_order=min_order)
    after = dict(values)
    for order in orders:
        after[order.category] = after.get(order.category, ZERO) + order.amount
    return Plan(
        amount=amount,
        split={key: value.quantize(CENT) for key, value in split.items()},
        orders=orders,
        unspent=unspent,
        before=shares(values),
        after=shares(after),
        in_band_before=within_band(values, targets, absolute, relative),
        in_band_after=within_band(after, targets, absolute, relative),
        months_to_band=months_to_band(values, targets, monthly, absolute, relative),
    )


def full_rebalance(values: dict[str, Decimal], targets: dict[str, Decimal]) -> dict[str, Decimal]:
    """Buy (+) or sell (−) per category to hit the targets exactly with today's money."""
    total = sum(values.values(), ZERO)
    keys = set(values) | set(targets)
    return {
        key: (targets.get(key, ZERO) * total - values.get(key, ZERO)).quantize(CENT)
        for key in keys
        if (targets.get(key, ZERO) * total - values.get(key, ZERO)).quantize(CENT) != 0
    }
