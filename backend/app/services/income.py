"""Dividend and interest income: monthly totals, per-holding yields and cadence, and what's likely to come.

Amounts are in the base currency at each payment's own FX rate. Withholding tax counts against income wherever
the broker put it: in a dividend row's tax column (Lightyear) or as a separate tax row for the holding (IBKR,
Revolut). Expectations assume each holding keeps paying what it paid per share over the last 12 months.
"""

import datetime as dt
import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import pairwise

from app.enums import TransactionType
from app.models import Transaction
from app.schemas.portfolio import (
    IncomeHolding,
    IncomeMonth,
    IncomeResponse,
    IncomeTotals,
    UpcomingPayment,
)
from app.services.portfolio import PortfolioEngine, money, ratio

ZERO = Decimal(0)
MONTHS_SHOWN = 24
UPCOMING_DAYS = 90
OVERDUE_DAYS = 14  # a payment a little late still shows as coming
# Typical gaps between payments (days) and what to call them.
CADENCES = ((45, "monthly"), (110, "quarterly"), (220, "twice a year"), (400, "yearly"))


@dataclass
class Payment:
    """One holding's dividend into one account on one day, with any withholding booked for it."""

    day: dt.date
    gross: Decimal = ZERO  # base currency
    withheld: Decimal = ZERO
    shares: Decimal = ZERO  # held in that account at the end of the day

    @property
    def net(self) -> Decimal:
        return self.gross - self.withheld

    @property
    def per_share(self) -> Decimal | None:
        return self.net / self.shares if self.gross > 0 and self.shares > 0 else None


@dataclass
class AssetIncome:
    """Payments per account: each account receives every dividend once, whatever day its broker books it."""

    accounts: dict[int, dict[dt.date, Payment]] = field(default_factory=lambda: defaultdict(dict))

    def on(self, account_id: int, day: dt.date) -> Payment:
        return self.accounts[account_id].setdefault(day, Payment(day))

    def all(self) -> list[Payment]:
        return [payment for payments in self.accounts.values() for payment in payments.values()]


def _month(day: dt.date) -> dt.date:
    return day.replace(day=1)


def _months_back(day: dt.date, months: int) -> dt.date:
    index = day.year * 12 + day.month - 1 - months
    return dt.date(index // 12, index % 12 + 1, 1)


def _gap(days: Iterable[dt.date]) -> int | None:
    """The typical gap in days between one account's payments."""
    ordered = sorted(set(days))
    if len(ordered) < 2:
        return None
    return int(statistics.median((b - a).days for a, b in pairwise(ordered)))


def income_report(engine: PortfolioEngine) -> IncomeResponse:
    today = engine.as_of
    year_ago = today - dt.timedelta(days=365)
    two_years_ago = today - dt.timedelta(days=730)

    income_txs = [
        t
        for t in engine.transactions
        if t.type in (TransactionType.DIVIDEND, TransactionType.INTEREST)
        or (t.type is TransactionType.TAX and t.asset_id is not None)
    ]
    shares_on = _shares_on_payment_days(engine, income_txs)

    by_asset: dict[int, AssetIncome] = defaultdict(AssetIncome)
    months: dict[dt.date, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO, ZERO])  # dividends, interest, withheld
    for tx in income_txs:
        amount = engine._to_base(tx.amount or ZERO, tx.currency, tx.trade_date)
        costs = engine._to_base(tx.fee + tx.tax, tx.currency, tx.trade_date)
        bucket = months[_month(tx.trade_date)]
        if tx.type is TransactionType.INTEREST:
            bucket[1] += amount - costs
            continue
        if tx.type is TransactionType.TAX:
            withheld = amount + costs  # withholding on a holding's dividend, booked on its own row
            bucket[2] += withheld
            if tx.asset_id is not None:
                by_asset[tx.asset_id].on(tx.account_id, tx.trade_date).withheld += withheld
            continue
        bucket[0] += amount
        bucket[2] += costs
        if tx.asset_id is not None:
            payment = by_asset[tx.asset_id].on(tx.account_id, tx.trade_date)
            payment.gross += amount
            payment.withheld += costs
            payment.shares = shares_on.get((tx.account_id, tx.asset_id, tx.trade_date), ZERO)

    holdings, current_values = _holdings(engine, by_asset, today, year_ago)
    upcoming = sorted(
        (
            UpcomingPayment(
                asset_id=h.asset_id,
                symbol=h.symbol,
                name=h.name,
                logo_url=h.logo_url,
                expected_on=h.next_expected,
                estimate=h.next_estimate,
            )
            for h in holdings
            if h.next_expected is not None
            and h.next_estimate is not None
            and today - dt.timedelta(days=OVERDUE_DAYS) <= h.next_expected <= today + dt.timedelta(days=UPCOMING_DAYS)
        ),
        key=lambda p: p.expected_on,
    )

    def net_between(start: dt.date, end: dt.date) -> Decimal:
        return sum((d - w + i for month, (d, i, w) in months.items() if start <= month <= end), ZERO)

    def net_since(start: dt.date, end: dt.date = today) -> Decimal:
        total = ZERO
        for tx in income_txs:
            if not start < tx.trade_date <= end:
                continue
            amount = engine._to_base(tx.amount or ZERO, tx.currency, tx.trade_date)
            costs = engine._to_base(tx.fee + tx.tax, tx.currency, tx.trade_date)
            total += -(amount + costs) if tx.type is TransactionType.TAX else amount - costs
        return total

    trailing = net_since(year_ago)
    holdings_value = sum(current_values.values(), ZERO)
    expected = sum((h.expected_12m for h in holdings), ZERO)
    totals = IncomeTotals(
        trailing_12m=money(trailing),
        previous_12m=money(net_since(two_years_ago, year_ago)),
        this_year=money(net_since(dt.date(today.year, 1, 1) - dt.timedelta(days=1))),
        all_time=money(net_between(dt.date.min, today)),
        withheld_12m=money(sum((p.withheld for a in by_asset.values() for p in a.all() if p.day > year_ago), ZERO)),
        expected_12m=money(expected),
        portfolio_yield=ratio(trailing, holdings_value) if holdings_value > 0 else None,
    )
    return IncomeResponse(
        base_currency=engine.base,
        as_of=today,
        totals=totals,
        months=[
            IncomeMonth(
                month=month,
                dividends=money(months[month][0] - months[month][2]),
                interest=money(months[month][1]),
                withheld=money(months[month][2]),
            )
            for month in (_months_back(today, back) for back in range(MONTHS_SHOWN - 1, -1, -1))
        ],
        holdings=sorted(holdings, key=lambda h: h.trailing_12m, reverse=True),
        upcoming=upcoming,
    )


def _shares_on_payment_days(engine: PortfolioEngine, txs: list[Transaction]) -> dict[tuple[int, int, dt.date], Decimal]:
    """Shares of each paying asset in each account at the end of each payment day."""
    days = sorted({t.trade_date for t in txs if t.asset_id is not None})
    held: dict[tuple[int, int, dt.date], Decimal] = {}
    for day, ledgers in engine._replay_through(days):
        for account_id, ledger in ledgers.items():
            for asset_id, position in ledger.positions.items():
                held[(account_id, asset_id, day)] = position.quantity
    return held


def _holdings(
    engine: PortfolioEngine, by_asset: dict[int, AssetIncome], today: dt.date, year_ago: dt.date
) -> tuple[list[IncomeHolding], dict[int, Decimal]]:
    ledgers = engine.replay()
    logos = engine.logo_urls(by_asset)
    shares_now: dict[tuple[int, int], Decimal] = {}  # (account, asset)
    held: dict[int, Decimal] = defaultdict(Decimal)
    cost_now: dict[int, Decimal] = defaultdict(Decimal)
    for account_id, ledger in ledgers.items():
        for asset_id, position in ledger.positions.items():
            if position.quantity > 0:
                shares_now[(account_id, asset_id)] = position.quantity
                held[asset_id] += position.quantity
                cost_now[asset_id] += position.cost_base
    values: dict[int, Decimal] = {}
    for asset_id, quantity in held.items():
        point = engine.prices.at(asset_id, today)
        if point is not None:
            values[asset_id] = engine._to_base(quantity * point[1], engine.assets[asset_id].currency, today)

    holdings: list[IncomeHolding] = []
    for asset_id, income in by_asset.items():
        asset = engine.assets.get(asset_id)
        if asset is None:
            continue
        payments = income.all()
        recent = [p for p in payments if p.day > year_ago]
        expected = ZERO  # each account: last 12 months' income per share x the shares it holds now
        next_estimate = ZERO  # each account: its last dividend per share x the shares it holds now
        next_dates: list[dt.date] = []
        gaps: list[int] = []
        events_12m = 0
        for account_id, by_day in income.accounts.items():
            received = sorted((p for p in by_day.values() if p.gross > 0), key=lambda p: p.day)
            events_12m = max(events_12m, sum(1 for p in received if p.day > year_ago))
            gap = _gap(p.day for p in received)
            if gap is not None:
                gaps.append(gap)
            now = shares_now.get((account_id, asset_id), ZERO)
            if now <= 0 or not received:
                continue
            expected += sum((p.per_share or ZERO for p in received if p.day > year_ago), ZERO) * now
            last = received[-1]
            if gap is not None and last.per_share is not None and last.per_share > 0:
                next_dates.append(last.day + dt.timedelta(days=gap))
                next_estimate += last.per_share * now
        gap = int(statistics.median(gaps)) if gaps else None
        cadence = next((label for limit, label in CADENCES if gap <= limit), "irregular") if gap else None
        trailing = sum((p.net for p in recent), ZERO)
        is_held = held.get(asset_id, ZERO) > 0
        value = values.get(asset_id)
        holdings.append(
            IncomeHolding(
                asset_id=asset_id,
                symbol=asset.symbol,
                name=asset.name,
                logo_url=logos.get(asset_id),
                held=is_held,
                trailing_12m=money(trailing),
                all_time=money(sum((p.net for p in payments), ZERO)),
                payments_12m=events_12m,
                cadence=cadence,
                last_paid=max((p.day for p in payments if p.gross > 0), default=None),
                next_expected=min(next_dates) if next_dates else None,
                next_estimate=money(next_estimate) if next_dates else None,
                expected_12m=money(expected),
                value=money(value) if value is not None else None,
                yield_pct=ratio(trailing, value) if value and is_held else None,
                yield_on_cost=ratio(trailing, cost_now[asset_id]) if is_held and cost_now[asset_id] > 0 else None,
            )
        )
    return holdings, values
