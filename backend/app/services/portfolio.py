"""Portfolio valuation: replay a user's transaction ledger into positions & cash.

All arithmetic is Decimal. Values are converted into the requested base
currency with :class:`~app.services.fx.FxConverter` at the very end, so a
position is always valued in its own currency first.
"""

from bisect import bisect_right
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import StrEnum

from sqlalchemy.orm import Session, selectinload

from app.core.money import ZERO, quantize_money, safe_ratio
from app.models import Account, Asset, Transaction
from app.models.enums import (
    CONTRIBUTION_TYPES,
    QUANTITY_DIRECTION,
    AssetClass,
    TransactionType,
)
from app.services.fx import FxConverter, default_fx
from app.services.tenancy import owned

CASH_BUCKET = "cash"
ASSET_CLASS_LABELS: dict[AssetClass, str] = {
    AssetClass.EQUITY: "Stocks",
    AssetClass.ETF: "ETFs",
    AssetClass.BOND: "Bonds",
    AssetClass.FUND: "Funds",
    AssetClass.CRYPTO: "Crypto",
    AssetClass.COMMODITY: "Commodities",
    AssetClass.OTHER: "Other",
}


@dataclass(slots=True)
class Position:
    quantity: Decimal = ZERO
    cost: Decimal = ZERO  # total cost basis in the trade currency (average-cost method)


@dataclass(slots=True)
class Ledger:
    """Running state while replaying transactions in date order."""

    positions: dict[tuple[int, int], Position] = field(
        default_factory=lambda: defaultdict(Position)
    )
    cash: dict[tuple[int, str], Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    contributions: dict[tuple[int, str], Decimal] = field(
        default_factory=lambda: defaultdict(lambda: ZERO)
    )

    def apply(self, tx: Transaction) -> None:
        self.cash[(tx.account_id, tx.currency)] += tx.amount
        if tx.type in CONTRIBUTION_TYPES:
            self.contributions[(tx.account_id, tx.currency)] += tx.amount

        direction = QUANTITY_DIRECTION.get(tx.type)
        if direction is None or tx.asset_id is None or not tx.quantity:
            return
        pos = self.positions[(tx.account_id, tx.asset_id)]
        if direction > 0:
            if tx.type is TransactionType.BUY:
                pos.cost += -tx.amount
            elif tx.price is not None:
                pos.cost += tx.quantity * tx.price
            pos.quantity += tx.quantity
        else:
            if pos.quantity > ZERO:
                sold = min(tx.quantity, pos.quantity)
                pos.cost -= pos.cost * sold / pos.quantity
            pos.quantity -= tx.quantity
            if pos.quantity <= ZERO:
                pos.quantity, pos.cost = ZERO, ZERO


class PriceBook:
    """Asset prices over time: trade prices + the latest quote, linearly interpolated."""

    def __init__(self, assets: Iterable[Asset], transactions: Iterable[Transaction], today: date):
        obs: dict[int, dict[date, Decimal]] = defaultdict(dict)
        for tx in transactions:
            if tx.asset_id is not None and tx.price and tx.type in QUANTITY_DIRECTION:
                obs[tx.asset_id][tx.trade_date] = tx.price
        for asset in assets:
            if asset.last_price is not None:
                when = asset.last_price_at.date() if asset.last_price_at else today
                obs[asset.id][when] = asset.last_price
        self._series = {
            asset_id: (sorted(points), [points[d] for d in sorted(points)])
            for asset_id, points in obs.items()
        }

    def latest(self, asset_id: int) -> Decimal | None:
        series = self._series.get(asset_id)
        return series[1][-1] if series else None

    def at(self, asset_id: int, when: date) -> Decimal | None:
        series = self._series.get(asset_id)
        if not series:
            return None
        dates, prices = series
        i = bisect_right(dates, when)
        if i == 0:
            return prices[0]
        if i == len(dates):
            return prices[-1]
        d0, d1, p0, p1 = dates[i - 1], dates[i], prices[i - 1], prices[i]
        return p0 + (p1 - p0) * Decimal((when - d0).days) / Decimal((d1 - d0).days)


@dataclass(slots=True)
class PortfolioData:
    accounts: list[Account]
    assets: dict[int, Asset]
    transactions: list[Transaction]


def load_portfolio(db: Session, user_id: int) -> PortfolioData:
    accounts = list(db.scalars(owned(Account, user_id).order_by(Account.id)))
    assets = {a.id: a for a in db.scalars(owned(Asset, user_id))}
    transactions = list(
        db.scalars(
            owned(Transaction, user_id)
            .options(selectinload(Transaction.asset))
            .order_by(Transaction.trade_date, Transaction.id)
        )
    )
    return PortfolioData(accounts, assets, transactions)


# --------------------------------------------------------------------- summary


@dataclass(slots=True)
class Bucket:
    key: str
    label: str
    value: Decimal
    weight: Decimal = ZERO


@dataclass(slots=True)
class HoldingView:
    asset: Asset
    quantity: Decimal
    price: Decimal | None
    value: Decimal  # base currency
    cost: Decimal  # base currency
    weight: Decimal = ZERO


@dataclass(slots=True)
class AccountView:
    account: Account
    value: Decimal  # base currency
    invested: Decimal
    cash: Decimal
    contributions: Decimal
    value_in_account_currency: Decimal
    holdings_count: int
    cash_by_currency: dict[str, Decimal]
    weight: Decimal = ZERO


@dataclass(slots=True)
class PortfolioSummary:
    base_currency: str
    as_of: date
    net_worth: Decimal
    invested: Decimal
    cash: Decimal
    net_contributions: Decimal
    total_gain: Decimal
    total_gain_pct: Decimal
    by_asset_class: list[Bucket]
    by_currency: list[Bucket]
    by_account: list[Bucket]
    accounts: list[AccountView]
    holdings: list[HoldingView]
    fx_rates: dict[str, Decimal]
    warnings: list[str]


def _buckets(
    values: dict[tuple[str, str], Decimal], total: Decimal, q: Callable[[Decimal], Decimal]
) -> list[Bucket]:
    out = [
        Bucket(key=k, label=label, value=q(v), weight=safe_ratio(v, total))
        for (k, label), v in values.items()
        if v != ZERO
    ]
    return sorted(out, key=lambda b: b.value, reverse=True)


def summarize(
    data: PortfolioData, base: str, today: date | None = None, fx: FxConverter = default_fx
) -> PortfolioSummary:
    today = today or date.today()
    ledger = Ledger()
    for tx in data.transactions:
        ledger.apply(tx)
    prices = PriceBook(data.assets.values(), data.transactions, today)
    warnings: set[str] = set()

    def to_base(amount: Decimal, ccy: str) -> Decimal:
        if not fx.supports(ccy):
            warnings.add(f"No FX rate for {ccy}; excluded from totals")
            return ZERO
        return fx.convert(amount, ccy, base)

    by_class: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    by_ccy: dict[tuple[str, str], Decimal] = defaultdict(lambda: ZERO)
    holdings: dict[int, HoldingView] = {}
    acct_invested: dict[int, Decimal] = defaultdict(lambda: ZERO)
    acct_holdings: dict[int, int] = defaultdict(int)

    for (account_id, asset_id), pos in ledger.positions.items():
        if pos.quantity <= ZERO:
            continue
        asset = data.assets[asset_id]
        price = prices.latest(asset_id)
        if price is None:
            warnings.add(f"No price for {asset.symbol}; valued at cost")
            native_value = pos.cost
        else:
            native_value = pos.quantity * price
        value = to_base(native_value, asset.currency)
        cost = to_base(pos.cost, asset.currency)

        by_class[(asset.asset_class.value, ASSET_CLASS_LABELS[asset.asset_class])] += value
        by_ccy[(asset.currency, asset.currency)] += value
        acct_invested[account_id] += value
        acct_holdings[account_id] += 1

        view = holdings.setdefault(
            asset_id, HoldingView(asset=asset, quantity=ZERO, price=price, value=ZERO, cost=ZERO)
        )
        view.quantity += pos.quantity
        view.value += value
        view.cost += cost

    acct_cash: dict[int, Decimal] = defaultdict(lambda: ZERO)
    acct_cash_ccy: dict[int, dict[str, Decimal]] = defaultdict(dict)
    for (account_id, ccy), amount in ledger.cash.items():
        if amount == ZERO:
            continue
        value = to_base(amount, ccy)
        acct_cash[account_id] += value
        acct_cash_ccy[account_id][ccy] = amount
        by_class[(CASH_BUCKET, "Cash")] += value
        by_ccy[(ccy, ccy)] += value

    acct_contrib: dict[int, Decimal] = defaultdict(lambda: ZERO)
    for (account_id, ccy), amount in ledger.contributions.items():
        acct_contrib[account_id] += to_base(amount, ccy)

    def q(value: Decimal) -> Decimal:
        return quantize_money(value, base)

    invested = sum(acct_invested.values(), ZERO)
    cash = sum(acct_cash.values(), ZERO)
    net_worth = invested + cash
    contributions = sum(acct_contrib.values(), ZERO)
    gain = net_worth - contributions

    account_views = []
    for account in data.accounts:
        value = acct_invested[account.id] + acct_cash[account.id]
        account_views.append(
            AccountView(
                account=account,
                value=q(value),
                invested=q(acct_invested[account.id]),
                cash=q(acct_cash[account.id]),
                contributions=q(acct_contrib[account.id]),
                value_in_account_currency=quantize_money(
                    fx.convert(value, base, account.base_currency)
                    if fx.supports(account.base_currency)
                    else value,
                    account.base_currency,
                ),
                holdings_count=acct_holdings[account.id],
                cash_by_currency=acct_cash_ccy[account.id],
                weight=safe_ratio(value, net_worth),
            )
        )

    holding_list = sorted(holdings.values(), key=lambda h: h.value, reverse=True)
    for h in holding_list:
        h.weight = safe_ratio(h.value, net_worth)
        h.value, h.cost = q(h.value), q(h.cost)

    return PortfolioSummary(
        base_currency=base,
        as_of=today,
        net_worth=q(invested) + q(cash),
        invested=q(invested),
        cash=q(cash),
        net_contributions=q(contributions),
        total_gain=q(gain),
        total_gain_pct=safe_ratio(gain, contributions),
        by_asset_class=_buckets(by_class, net_worth, q),
        by_currency=_buckets(by_ccy, net_worth, q),
        by_account=_buckets(
            {(str(v.account.id), v.account.name): v.value for v in account_views}, net_worth, q
        ),
        accounts=account_views,
        holdings=holding_list,
        fx_rates=fx.table(base),
        warnings=sorted(warnings),
    )


# ----------------------------------------------------------------- performance


class PerformanceRange(StrEnum):
    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    YTD = "YTD"
    ONE_YEAR = "1Y"
    ALL = "ALL"


@dataclass(frozen=True, slots=True)
class PerformancePoint:
    date: date
    value: Decimal
    net_contributions: Decimal


@dataclass(frozen=True, slots=True)
class Performance:
    base_currency: str
    range: PerformanceRange
    points: list[PerformancePoint]
    start_value: Decimal
    end_value: Decimal
    change: Decimal  # raw change in value, including deposits
    gain: Decimal  # change minus net deposits over the period = market gain
    gain_pct: Decimal


_TARGET_POINTS = 90


def _range_start(rng: PerformanceRange, today: date, first: date) -> date:
    match rng:
        case PerformanceRange.ONE_MONTH:
            start = today - timedelta(days=30)
        case PerformanceRange.THREE_MONTHS:
            start = today - timedelta(days=91)
        case PerformanceRange.SIX_MONTHS:
            start = today - timedelta(days=182)
        case PerformanceRange.YTD:
            start = date(today.year, 1, 1)
        case PerformanceRange.ONE_YEAR:
            start = today - timedelta(days=365)
        case PerformanceRange.ALL:
            start = first
    return max(start, first)


def _sample_dates(start: date, end: date) -> list[date]:
    span = max((end - start).days, 1)
    step = max(span // _TARGET_POINTS, 1)
    dates = [start + timedelta(days=i) for i in range(0, span, step)]
    if not dates or dates[-1] != end:
        dates.append(end)
    return dates


def performance(
    data: PortfolioData,
    base: str,
    rng: PerformanceRange,
    today: date | None = None,
    fx: FxConverter = default_fx,
) -> Performance:
    today = today or date.today()
    txs: Sequence[Transaction] = data.transactions
    if not txs:
        return Performance(base, rng, [], ZERO, ZERO, ZERO, ZERO, ZERO)

    prices = PriceBook(data.assets.values(), txs, today)
    assets = data.assets
    start = _range_start(rng, today, txs[0].trade_date)

    def to_base(amount: Decimal, ccy: str) -> Decimal:
        return fx.convert(amount, ccy, base) if fx.supports(ccy) else ZERO

    ledger = Ledger()
    i = 0
    points: list[PerformancePoint] = []
    for when in _sample_dates(start, today):
        while i < len(txs) and txs[i].trade_date <= when:
            ledger.apply(txs[i])
            i += 1
        value = sum((to_base(amount, ccy) for (_, ccy), amount in ledger.cash.items()), ZERO)
        for (_, asset_id), pos in ledger.positions.items():
            if pos.quantity <= ZERO:
                continue
            price = prices.at(asset_id, when)
            native = pos.quantity * price if price is not None else pos.cost
            value += to_base(native, assets[asset_id].currency)
        contributions = sum(
            (to_base(amount, ccy) for (_, ccy), amount in ledger.contributions.items()), ZERO
        )
        points.append(
            PerformancePoint(when, quantize_money(value, base), quantize_money(contributions, base))
        )

    first, last = points[0], points[-1]
    change = last.value - first.value
    flows = last.net_contributions - first.net_contributions
    gain = change - flows
    return Performance(
        base_currency=base,
        range=rng,
        points=points,
        start_value=first.value,
        end_value=last.value,
        change=change,
        gain=gain,
        gain_pct=safe_ratio(gain, first.value + flows),
    )
