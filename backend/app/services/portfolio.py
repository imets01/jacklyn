"""Valuation engine: replays the ledger into positions, cash, P&L and history in any base currency.

All arithmetic is Decimal. Cost basis uses the average-cost method, converted to the base
currency at each transaction's own date, so P&L includes currency effects on positions.
"""

import datetime as dt
import math
from collections import defaultdict
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import AccountType, AssetClass, PriceSource, TransactionType
from app.models import Account, Asset, AssetLogo, AssetPrice, AssetProfile, AssetSplit, Transaction
from app.schemas.portfolio import (
    AccountReturn,
    AccountSummary,
    Allocations,
    AllocationSlice,
    AssetOut,
    AssetProfileOut,
    CashBalance,
    HistoryPoint,
    HistoryRange,
    HistoryResponse,
    Holding,
    HoldingAccount,
    HoldingActivity,
    HoldingDetail,
    HoldingsResponse,
    MarketStatus,
    PerformanceResponse,
    PeriodReturn,
    PortfolioSummary,
    ReturnPeriod,
)
from app.schemas.standard import cash_flow
from app.services.asset_info import shared_logo_urls
from app.services.market_data import LiveStatus
from app.services.market_tables import FxTable, PriceTable
from app.services.returns import Snapshot, over_period, per_year, time_weighted, xirr
from app.services.tbsz import reduced_rate_from, tax_free_from

ZERO = Decimal(0)
CENT = Decimal("0.01")
BASIS_POINT = Decimal("0.0001")
ASSET_CLASS_LABELS = {
    AssetClass.STOCK: "Stocks",
    AssetClass.ETF: "ETFs",
    AssetClass.FUND: "Funds",
    AssetClass.BOND: "Bonds",
    AssetClass.CRYPTO: "Crypto",
    AssetClass.COMMODITY: "Commodities",
    AssetClass.CASH: "Cash",
    AssetClass.OTHER: "Other",
}


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_EVEN)


def ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator).quantize(BASIS_POINT, rounding=ROUND_HALF_EVEN)


@dataclass
class Position:
    quantity: Decimal = ZERO
    cost_base: Decimal = ZERO  # average-cost basis in base currency, fees included
    cost_local: Decimal = ZERO  # the same basis in the asset's own currency, for an average buy price


@dataclass
class Ledger:
    positions: dict[int, Position] = field(default_factory=lambda: defaultdict(Position))
    cash: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    realized: Decimal = ZERO
    income: Decimal = ZERO  # dividends + interest, net of withholding
    costs: Decimal = ZERO  # standalone fees and taxes
    contributions: Decimal = ZERO  # net money put in, at historical FX
    transaction_count: int = 0
    last_date: dt.date | None = None


@dataclass
class Valuation:
    holdings_value: Decimal = ZERO
    cash_value: Decimal = ZERO
    cost_basis: Decimal = ZERO
    day_change: Decimal = ZERO

    @property
    def total(self) -> Decimal:
        return self.holdings_value + self.cash_value


class PortfolioEngine:
    def __init__(
        self,
        session: Session,
        *,
        user_id: int,
        base_currency: str,
        account_ids: Sequence[int] | None = None,
        as_of: dt.date | None = None,
        include_archived: bool = False,
    ) -> None:
        self.base = base_currency.upper()
        self.as_of = as_of or dt.date.today()
        query = select(Account).where(Account.user_id == user_id).order_by(Account.id)
        if account_ids is not None:
            query = query.where(Account.id.in_(account_ids))
        if not include_archived:
            query = query.where(Account.is_archived.is_(False))
        self.accounts: list[Account] = list(session.scalars(query))
        self.account_by_id = {account.id: account for account in self.accounts}

        self.transactions: list[Transaction] = (
            list(
                session.scalars(
                    select(Transaction)
                    .where(
                        Transaction.user_id == user_id,
                        Transaction.account_id.in_(list(self.account_by_id)),
                        Transaction.trade_date <= self.as_of,
                    )
                    .order_by(Transaction.trade_date, Transaction.id)
                )
            )
            if self.accounts
            else []
        )
        asset_ids = {t.asset_id for t in self.transactions if t.asset_id is not None}
        self.assets: dict[int, Asset] = (
            {asset.id: asset for asset in session.scalars(select(Asset).where(Asset.id.in_(asset_ids)))}
            if asset_ids
            else {}
        )
        self.prices = PriceTable.load(session, asset_ids)
        self.unpriced_assets = 0
        for asset_id in asset_ids:
            if not self.prices.has(asset_id):
                self.unpriced_assets += 1
                for t in self.transactions:
                    if (
                        t.asset_id == asset_id
                        and t.unit_price
                        and t.type in (TransactionType.BUY, TransactionType.SELL)
                    ):
                        self.prices.add_fallback(asset_id, t.trade_date, t.unit_price)
        self.synthetic_assets = (
            len(
                set(
                    session.scalars(
                        select(AssetPrice.asset_id)
                        .where(AssetPrice.asset_id.in_(asset_ids), AssetPrice.source == PriceSource.SEED)
                        .distinct()
                    )
                )
            )
            if asset_ids
            else 0
        )
        self.fx = FxTable.load(session)
        self.split_factors = self._split_factors(session)
        self.warnings: set[str] = set()
        self.session = session

    def _split_factors(self, session: Session) -> dict[int, Decimal]:
        """Transaction id -> share multiplier for trades booked before a stock split.

        Brokers' statements rarely record splits (Lightyear lists NVDA's 2024 buy at 1 183.80 USD and the
        later sale in post-split shares) while Yahoo's closes are split-adjusted, so older trades are restated
        in today's shares; cost and proceeds stay the same. A trade whose price already matches the adjusted
        close was restated by the broker and is left alone.
        """
        held = {t.asset_id for t in self.transactions if t.asset_id is not None and t.quantity}
        if not held:
            return {}
        splits: dict[int, list[tuple[dt.date, Decimal]]] = defaultdict(list)
        for asset_id, day, ratio in session.execute(
            select(AssetSplit.asset_id, AssetSplit.split_date, AssetSplit.ratio).where(
                AssetSplit.asset_id.in_(held), AssetSplit.split_date <= self.as_of
            )
        ):
            splits[asset_id].append((day, ratio))
        factors: dict[int, Decimal] = {}
        for tx in self.transactions:
            if tx.asset_id is None or tx.asset_id not in splits or not tx.quantity:
                continue
            factor = math.prod((ratio for day, ratio in splits[tx.asset_id] if day > tx.trade_date), start=Decimal(1))
            if factor != 1 and not self._already_split_adjusted(tx, factor):
                factors[tx.id] = factor
        return factors

    def _already_split_adjusted(self, tx: Transaction, factor: Decimal) -> bool:
        """Is the trade price nearer the split-adjusted close than the unadjusted one (close x factor)?"""
        point = self.prices.at(tx.asset_id, tx.trade_date) if tx.asset_id is not None else None
        if not tx.unit_price or point is None or point[1] <= 0:
            return False
        distance = math.log(float(tx.unit_price / point[1]))
        return abs(distance) < abs(distance - math.log(float(factor)))

    # ------------------------------------------------------------------ ledger replay

    def _to_base(self, amount: Decimal, currency: str, on: dt.date) -> Decimal:
        converted = self.fx.convert(amount, currency, self.base, on)
        if converted is None:
            self.warnings.add(f"No FX rate for {currency}→{self.base}; {currency} amounts are excluded.")
            return ZERO
        return converted

    def _convert(self, amount: Decimal, currency: str, target: str, on: dt.date) -> Decimal:
        if currency == target:
            return amount
        return self.fx.convert(amount, currency, target, on) or ZERO

    def _apply(self, ledger: Ledger, account: Account, tx: Transaction) -> None:
        on, currency = tx.trade_date, tx.currency
        amount, fee, tax = tx.amount or ZERO, tx.fee, tx.tax
        quantity = (tx.quantity or ZERO) * self.split_factors.get(tx.id, Decimal(1))  # in today's shares
        ledger.transaction_count += 1
        ledger.last_date = on
        if account.track_cash:
            ledger.cash[currency] += cash_flow(tx.type, tx.amount, fee, tax, has_asset=tx.asset_id is not None)

        position = ledger.positions[tx.asset_id] if tx.asset_id is not None else None
        asset_currency = self.assets[tx.asset_id].currency if tx.asset_id is not None else currency
        match tx.type:
            case TransactionType.BUY if position is not None:
                cost = self._to_base(amount + fee + tax, currency, on)
                position.quantity += quantity
                position.cost_base += cost
                position.cost_local += self._convert(amount + fee + tax, currency, asset_currency, on)
                if not account.track_cash:
                    ledger.contributions += cost
            case TransactionType.SELL if position is not None:
                proceeds = self._to_base(amount - fee - tax, currency, on)
                basis = self._release_basis(position, quantity)
                ledger.realized += proceeds - basis
                if not account.track_cash:
                    ledger.contributions -= proceeds
            case TransactionType.TRANSFER_IN if position is not None:
                gross = (tx.quantity or ZERO) * (tx.unit_price or ZERO)  # as booked, before any split
                value = self._to_base(gross, currency, on)
                position.quantity += quantity
                position.cost_base += value
                position.cost_local += self._convert(gross, currency, asset_currency, on)
                ledger.contributions += value
                ledger.costs += self._to_base(fee + tax, currency, on)
            case TransactionType.TRANSFER_OUT if position is not None:
                ledger.contributions -= self._release_basis(position, quantity)
                ledger.costs += self._to_base(fee + tax, currency, on)
            case TransactionType.DEPOSIT | TransactionType.TRANSFER_IN:
                if account.track_cash:
                    ledger.contributions += self._to_base(amount, currency, on)
                ledger.costs += self._to_base(fee + tax, currency, on)
            case TransactionType.WITHDRAWAL | TransactionType.TRANSFER_OUT:
                if account.track_cash:
                    ledger.contributions -= self._to_base(amount, currency, on)
                ledger.costs += self._to_base(fee + tax, currency, on)
            case TransactionType.DIVIDEND | TransactionType.INTEREST:
                ledger.income += self._to_base(amount - fee - tax, currency, on)
            case TransactionType.FEE | TransactionType.TAX:
                ledger.costs += self._to_base(amount + fee + tax, currency, on)
            case TransactionType.FX_CONVERSION:
                ledger.costs += self._to_base(fee + tax, currency, on)
            case _:
                self.warnings.add(f"Ignored {tx.type.value} transaction without an asset (id {tx.id}).")

    @staticmethod
    def _release_basis(position: Position, quantity: Decimal) -> Decimal:
        """Remove `quantity` at average cost; selling more than held carries a zero basis."""
        if position.quantity <= 0:
            position.quantity -= quantity
            return ZERO
        covered = min(quantity, position.quantity)
        basis = position.cost_base * covered / position.quantity
        position.cost_local -= position.cost_local * covered / position.quantity
        position.cost_base -= basis
        position.quantity -= quantity
        if position.quantity <= 0:
            position.cost_base = position.cost_local = ZERO
        return basis

    def replay(self) -> dict[int, Ledger]:
        ledgers = {account.id: Ledger() for account in self.accounts}
        for tx in self.transactions:
            self._apply(ledgers[tx.account_id], self.account_by_id[tx.account_id], tx)
        return ledgers

    def _replay_through(self, dates: Sequence[dt.date]) -> Iterator[tuple[dt.date, dict[int, Ledger]]]:
        ledgers = {account.id: Ledger() for account in self.accounts}
        index = 0
        for day in dates:
            while index < len(self.transactions) and self.transactions[index].trade_date <= day:
                tx = self.transactions[index]
                self._apply(ledgers[tx.account_id], self.account_by_id[tx.account_id], tx)
                index += 1
            yield day, ledgers

    # ------------------------------------------------------------------ valuation

    def _value(self, account: Account, ledger: Ledger, on: dt.date, *, with_day_change: bool = False) -> Valuation:
        valuation = Valuation()
        for asset_id, position in ledger.positions.items():
            if position.quantity == 0:
                continue
            asset = self.assets[asset_id]
            point = self.prices.at(asset_id, on)
            if point is None:
                continue
            price_date, price = point
            value = self._to_base(position.quantity * price, asset.currency, on)
            valuation.holdings_value += value
            valuation.cost_basis += position.cost_base
            if with_day_change:
                previous = self.prices.before(asset_id, price_date)
                previous_price = previous[1] if previous else price
                previous_value = self._to_base(
                    position.quantity * previous_price, asset.currency, price_date - dt.timedelta(days=1)
                )
                valuation.day_change += value - previous_value
        if account.track_cash:
            fx_day = min(self.fx.last_date or on, on)
            for currency, amount in ledger.cash.items():
                if amount == 0:
                    continue
                value = self._to_base(amount, currency, on)
                valuation.cash_value += value
                if with_day_change:
                    valuation.day_change += value - self._to_base(amount, currency, fx_day - dt.timedelta(days=1))
        return valuation

    def summary(self, market_status: LiveStatus | None = None) -> PortfolioSummary:
        ledgers = self.replay()
        accounts: list[AccountSummary] = []
        totals = Valuation()
        realized = income = costs = contributions = ZERO
        by_class: dict[str, Decimal] = defaultdict(Decimal)
        by_currency: dict[str, Decimal] = defaultdict(Decimal)
        by_broker: dict[str, Decimal] = defaultdict(Decimal)
        by_wrapper: dict[str, tuple[str, Decimal]] = {}
        by_account: dict[str, tuple[str, Decimal]] = {}

        for account in self.accounts:
            ledger = ledgers[account.id]
            valuation = self._value(account, ledger, self.as_of, with_day_change=True)
            pnl = valuation.holdings_value - valuation.cost_basis + ledger.realized + ledger.income - ledger.costs
            totals.holdings_value += valuation.holdings_value
            totals.cash_value += valuation.cash_value
            totals.cost_basis += valuation.cost_basis
            totals.day_change += valuation.day_change
            realized += ledger.realized
            income += ledger.income
            costs += ledger.costs
            contributions += ledger.contributions

            for asset_id, position in ledger.positions.items():
                if position.quantity == 0 or (point := self.prices.at(asset_id, self.as_of)) is None:
                    continue
                asset = self.assets[asset_id]
                value = self._to_base(position.quantity * point[1], asset.currency, self.as_of)
                by_class[asset.asset_class.value] += value
                by_currency[asset.currency] += value
            if account.track_cash:
                for currency, amount in ledger.cash.items():
                    value = self._to_base(amount, currency, self.as_of)
                    by_class[AssetClass.CASH.value] += value
                    by_currency[currency] += value
            by_broker[account.broker] += valuation.total
            if account.account_type is AccountType.TBSZ:
                key, label = f"tbsz-{account.tbsz_year}", f"TBSZ {account.tbsz_year}"
            else:
                key, label = "regular", "Regular"
            by_wrapper[key] = (label, by_wrapper.get(key, (label, ZERO))[1] + valuation.total)
            by_account[str(account.id)] = (account.name, valuation.total)
            accounts.append(self._account_summary(account, ledger, valuation, pnl))

        net_worth = totals.total
        unrealized = totals.holdings_value - totals.cost_basis
        total_pnl = unrealized + realized + income - costs
        return PortfolioSummary(
            base_currency=self.base,
            as_of=self.as_of,
            net_worth=money(net_worth),
            holdings_value=money(totals.holdings_value),
            cash=money(totals.cash_value),
            day_change=money(totals.day_change),
            day_change_pct=ratio(totals.day_change, net_worth - totals.day_change),
            total_pnl=money(total_pnl),
            total_pnl_pct=ratio(total_pnl, net_worth - total_pnl),
            unrealized_pnl=money(unrealized),
            realized_pnl=money(realized),
            income=money(income),
            costs=money(costs),
            net_contributions=money(contributions),
            allocations=Allocations(
                asset_class=_slices({k: (ASSET_CLASS_LABELS[AssetClass(k)], v) for k, v in by_class.items()}),
                currency=_slices({k: (k, v) for k, v in by_currency.items()}),
                broker=_slices({k: (k, v) for k, v in by_broker.items()}),
                wrapper=_slices(by_wrapper),
                account=_slices(by_account),
            ),
            accounts=accounts,
            market=MarketStatus.model_validate(
                {
                    **(market_status or {}),
                    "prices_as_of": max(
                        (s.last_date for s in self.prices.series.values() if s.last_date), default=None
                    ),
                    "fx_as_of": self.fx.last_date,
                    "synthetic_price_assets": self.synthetic_assets,
                    "unpriced_assets": self.unpriced_assets,
                }
            ),
            warnings=sorted(self.warnings),
        )

    def _account_summary(self, account: Account, ledger: Ledger, valuation: Valuation, pnl: Decimal) -> AccountSummary:
        in_account_currency = self.fx.convert(valuation.total, self.base, account.currency, self.as_of)
        is_tbsz = account.account_type is AccountType.TBSZ and account.tbsz_year is not None
        return AccountSummary(
            id=account.id,
            name=account.name,
            broker=account.broker,
            account_type=account.account_type,
            tbsz_year=account.tbsz_year,
            tbsz_reduced_rate_from=reduced_rate_from(account.tbsz_year) if is_tbsz and account.tbsz_year else None,
            tbsz_tax_free_from=tax_free_from(account.tbsz_year) if is_tbsz and account.tbsz_year else None,
            currency=account.currency,
            external_account_id=account.external_account_id,
            track_cash=account.track_cash,
            is_archived=account.is_archived,
            value=money(valuation.total),
            value_account_currency=money(in_account_currency) if in_account_currency is not None else None,
            cash=money(valuation.cash_value),
            day_change=money(valuation.day_change),
            total_pnl=money(pnl),
            net_contributions=money(ledger.contributions),
            holdings_count=sum(1 for p in ledger.positions.values() if p.quantity != 0),
            transaction_count=ledger.transaction_count,
            last_transaction_date=ledger.last_date,
        )

    def logo_urls(self, asset_ids: Iterable[int]) -> dict[int, str]:
        """Cache-busting URLs for assets whose logo has been downloaded."""
        ids = list(asset_ids)
        if not ids:
            return {}
        rows = self.session.execute(
            select(AssetProfile.asset_id, AssetLogo.fetched_at)
            .join(AssetLogo, AssetLogo.key == AssetProfile.logo_key)
            .where(AssetProfile.asset_id.in_(ids), AssetLogo.data.is_not(None))
        ).all()
        return {asset_id: f"/api/assets/{asset_id}/logo?v={int(fetched.timestamp())}" for asset_id, fetched in rows}

    def currency_logo_urls(self) -> dict[str, str]:
        urls = shared_logo_urls(self.session, AssetLogo.key.like("currency:%"))
        return {key.removeprefix("currency:"): url for key, url in urls.items()}

    def holdings(self) -> HoldingsResponse:
        ledgers = self.replay()
        logos = self.logo_urls(self.assets)
        currency_logos = self.currency_logo_urls()
        holdings: list[Holding] = []
        cash: list[CashBalance] = []
        for account in self.accounts:
            ledger = ledgers[account.id]
            for asset_id, position in ledger.positions.items():
                if position.quantity == 0:
                    continue
                asset = self.assets[asset_id]
                point = self.prices.at(asset_id, self.as_of)
                price_date, price = point if point else (None, None)
                value_local = position.quantity * price if price is not None else ZERO
                value = self._to_base(value_local, asset.currency, self.as_of)
                day_change = ZERO
                if point is not None and price is not None and price_date is not None:
                    previous = self.prices.before(asset_id, price_date)
                    previous_value = self._to_base(
                        position.quantity * (previous[1] if previous else price),
                        asset.currency,
                        price_date - dt.timedelta(days=1),
                    )
                    day_change = value - previous_value
                unrealized = value - position.cost_base
                holdings.append(
                    Holding(
                        account_id=account.id,
                        account_name=account.name,
                        asset_id=asset_id,
                        symbol=asset.symbol,
                        name=asset.name,
                        isin=asset.isin,
                        asset_class=asset.asset_class,
                        currency=asset.currency,
                        quantity=position.quantity.normalize(),
                        price=price,
                        price_date=price_date,
                        value_local=money(value_local),
                        value=money(value),
                        cost_basis=money(position.cost_base),
                        unrealized_pnl=money(unrealized),
                        unrealized_pnl_pct=ratio(unrealized, position.cost_base),
                        day_change=money(day_change),
                        weight=ZERO,
                        avg_cost=_avg_cost(position),
                        logo_url=logos.get(asset_id),
                    )
                )
            if account.track_cash:
                for currency, amount in sorted(ledger.cash.items()):
                    if amount == 0:
                        continue
                    cash.append(
                        CashBalance(
                            account_id=account.id,
                            account_name=account.name,
                            currency=currency,
                            amount=money(amount),
                            value=money(self._to_base(amount, currency, self.as_of)),
                            logo_url=currency_logos.get(currency),
                        )
                    )
        total = sum((h.value for h in holdings), ZERO) + sum((c.value for c in cash), ZERO)
        for holding in holdings:
            holding.weight = ratio(holding.value, total) or ZERO
        holdings.sort(key=lambda h: h.value, reverse=True)
        return HoldingsResponse(base_currency=self.base, as_of=self.as_of, holdings=holdings, cash=cash)

    def holding_detail(self, asset_id: int) -> HoldingDetail | None:
        """One asset across every account; None when the user never transacted in it."""
        asset = self.assets.get(asset_id)
        if asset is None:
            return None
        ledgers = self.replay()
        point = self.prices.at(asset_id, self.as_of)
        price_date, price = point if point else (None, None)
        previous = self.prices.before(asset_id, price_date) if price_date else None
        previous_close = previous[1] if previous else None

        combined = Position()
        accounts: list[HoldingAccount] = []
        value = day_change = portfolio_total = ZERO
        for account in self.accounts:
            ledger = ledgers[account.id]
            portfolio_total += self._value(account, ledger, self.as_of).total
            position = ledger.positions.get(asset_id)
            if position is None or position.quantity == 0:
                continue
            combined.quantity += position.quantity
            combined.cost_base += position.cost_base
            combined.cost_local += position.cost_local
            account_value = self._to_base(position.quantity * price, asset.currency, self.as_of) if price else ZERO
            value += account_value
            if price is not None and price_date is not None:
                before = self._to_base(
                    position.quantity * (previous_close or price), asset.currency, price_date - dt.timedelta(days=1)
                )
                day_change += account_value - before
            unrealized = account_value - position.cost_base
            accounts.append(
                HoldingAccount(
                    account_id=account.id,
                    account_name=account.name,
                    broker=account.broker,
                    quantity=position.quantity.normalize(),
                    value=money(account_value),
                    cost_basis=money(position.cost_base),
                    unrealized_pnl=money(unrealized),
                    unrealized_pnl_pct=ratio(unrealized, position.cost_base),
                )
            )
        accounts.sort(key=lambda a: a.value, reverse=True)
        unrealized = value - combined.cost_base
        profile = self.session.get(AssetProfile, asset_id)
        activity = [
            HoldingActivity(
                id=tx.id,
                account_id=tx.account_id,
                account_name=self.account_by_id[tx.account_id].name,
                date=tx.trade_date,
                type=tx.type,
                quantity=tx.quantity,
                unit_price=tx.unit_price,
                amount=tx.amount,
                fee=tx.fee,
                tax=tx.tax,
                currency=tx.currency,
            )
            for tx in reversed(self.transactions)
            if tx.asset_id == asset_id
        ]
        return HoldingDetail(
            base_currency=self.base,
            as_of=self.as_of,
            asset=AssetOut(
                id=asset.id,
                symbol=asset.symbol,
                name=asset.name,
                isin=asset.isin,
                asset_class=asset.asset_class,
                currency=asset.currency,
                exchange=asset.exchange,
                yf_ticker=asset.yf_ticker,
                logo_url=self.logo_urls([asset_id]).get(asset_id),
            ),
            profile=AssetProfileOut.model_validate(profile, from_attributes=True) if profile else None,
            price=price,
            price_date=price_date,
            previous_close=previous_close,
            price_change_pct=ratio(price - previous_close, previous_close) if price and previous_close else None,
            quantity=combined.quantity.normalize(),
            avg_cost=_avg_cost(combined),
            value_local=money(combined.quantity * price) if price else ZERO,
            value=money(value),
            cost_basis=money(combined.cost_base),
            unrealized_pnl=money(unrealized),
            unrealized_pnl_pct=ratio(unrealized, combined.cost_base),
            day_change=money(day_change),
            weight=ratio(value, portfolio_total) or ZERO,
            accounts=accounts,
            activity=activity,
        )

    def history(self, range_key: HistoryRange) -> HistoryResponse:
        if not self.transactions:
            return HistoryResponse(base_currency=self.base, range=range_key, points=[], change=ZERO, change_pct=None)
        first = self.transactions[0].trade_date
        end = self.as_of
        start = {
            "1W": end - dt.timedelta(days=7),
            "1M": end - dt.timedelta(days=30),
            "3M": end - dt.timedelta(days=91),
            "YTD": dt.date(end.year, 1, 1),
            "1Y": end - dt.timedelta(days=365),
            "ALL": first,
        }[range_key]
        start = max(start, first)
        span = (end - start).days
        step = max(1, math.ceil(span / 365))
        dates = [start + dt.timedelta(days=offset) for offset in range(0, span + 1, step)]
        if not dates or dates[-1] != end:
            dates.append(end)

        points: list[HistoryPoint] = []
        for day, ledgers in self._replay_through(dates):
            value = invested = ZERO
            for account in self.accounts:
                ledger = ledgers[account.id]
                value += self._value(account, ledger, day).total
                invested += ledger.contributions
            points.append(HistoryPoint(date=day, value=money(value), invested=money(invested)))

        first_point, last_point = points[0], points[-1]
        # Performance over the window, net of money moved in or out during it.
        flows = last_point.invested - first_point.invested
        change = last_point.value - first_point.value - flows
        return HistoryResponse(
            base_currency=self.base,
            range=range_key,
            points=points,
            change=money(change),
            change_pct=ratio(change, first_point.value + max(flows, ZERO)) if first_point.value or flows else None,
        )

    # ------------------------------------------------------------------ performance

    @staticmethod
    def _net_flows(account: Account, ledger: Ledger) -> Decimal:
        """Money put into the account minus money taken out, at the FX of each day.

        Without cash tracking, buys are the money put in (already in `contributions`), and dividends or fees
        paid outside the account count as money taken out or put in, since the account's value never holds them.
        """
        if account.track_cash:
            return ledger.contributions
        return ledger.contributions - ledger.income + ledger.costs

    def performance(self, period: ReturnPeriod) -> PerformanceResponse:
        """Money- and time-weighted returns over the period, overall and per account.

        Accounts are valued on the evening before the period and on every day money moved in or out,
        which is all both rates need.
        """
        empty = PerformanceResponse(base_currency=self.base, period=period, total=None, accounts=[])
        if not self.transactions:
            return empty
        end = self.as_of
        first = self.transactions[0].trade_date
        start = {
            "YTD": dt.date(end.year, 1, 1),
            "1Y": _years_before(end, 1),
            "3Y": _years_before(end, 3),
            "5Y": _years_before(end, 5),
            "ALL": first,
        }[period]
        opening = max(start, first) - dt.timedelta(days=1)
        if opening >= end:
            return empty
        days = sorted({opening, end, *(t.trade_date for t in self.transactions if opening < t.trade_date < end)})

        series: dict[int, list[Snapshot]] = {account.id: [] for account in self.accounts}
        previous: dict[int, Decimal] | None = None
        for day, ledgers in self._replay_through(days):
            flows = {account.id: self._net_flows(account, ledgers[account.id]) for account in self.accounts}
            if day not in (opening, end) and flows == previous:
                continue  # trades inside the accounts only: nothing for the rates to account for
            previous = flows
            for account in self.accounts:
                value = self._value(account, ledgers[account.id], day).total
                series[account.id].append(Snapshot(day, value, flows[account.id]))

        accounts = [
            AccountReturn(account_id=account_id, **figures.model_dump())
            for account_id, snapshots in series.items()
            if (figures := _period_return(snapshots)) is not None
        ]
        combined = [
            Snapshot(
                day=snapshots[0].day,
                value=sum((s.value for s in snapshots), ZERO),
                net_flows=sum((s.net_flows for s in snapshots), ZERO),
            )
            for snapshots in zip(*series.values(), strict=True)
        ]
        return PerformanceResponse(
            base_currency=self.base, period=period, total=_period_return(combined), accounts=accounts
        )


def _years_before(day: dt.date, years: int) -> dt.date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


def _period_return(snapshots: Sequence[Snapshot]) -> PeriodReturn | None:
    """Both rates for one account (or the sum of several) from its snapshots; None if nothing was invested."""
    if len(snapshots) < 2:
        return None
    opening, closing = snapshots[0], snapshots[-1]
    # From the investor's side: money put in is negative, the value at the end counts as taken out.
    flows: list[tuple[dt.date, Decimal]] = []
    if opening.value != 0:
        flows.append((opening.day, -opening.value))
    for before, after in pairwise(snapshots):
        if moved := after.net_flows - before.net_flows:
            flows.append((after.day, -moved))
    if not flows:
        return None
    flows.append((closing.day, closing.value))
    began = flows[0][0]
    days = (closing.day - began).days
    if days <= 0:
        return None

    yearly = days >= 365
    money_weighted = xirr(flows)
    if money_weighted is not None and not yearly:
        money_weighted = over_period(money_weighted, days)
    growth = time_weighted([s for s in snapshots if s.day >= began])
    if growth is not None and yearly:
        growth = per_year(growth, days)
    net_flows = closing.net_flows - opening.net_flows
    return PeriodReturn(
        # The opening snapshot is the evening before the period; a first deposit starts on its own day.
        start=began + dt.timedelta(days=1) if began == opening.day else began,
        end=closing.day,
        days=days,
        per_year=yearly,
        money_weighted=_rate(money_weighted),
        time_weighted=_rate(growth),
        gain=money(closing.value - opening.value - net_flows),
        start_value=money(opening.value),
        end_value=money(closing.value),
        net_flows=money(net_flows),
    )


def _rate(value: Decimal | None) -> Decimal | None:
    return value.quantize(BASIS_POINT, rounding=ROUND_HALF_EVEN) if value is not None else None


def _avg_cost(position: Position) -> Decimal | None:
    if position.quantity <= 0 or position.cost_local <= 0:
        return None
    return (position.cost_local / position.quantity).quantize(Decimal("0.000001"))


def _slices(values: dict[str, tuple[str, Decimal]]) -> list[AllocationSlice]:
    positive = {key: (label, value) for key, (label, value) in values.items() if value > 0}
    total = sum((value for _, value in positive.values()), ZERO)
    slices = [
        AllocationSlice(key=key, label=label, value=money(value), weight=ratio(value, total) or ZERO)
        for key, (label, value) in positive.items()
    ]
    return sorted(slices, key=lambda s: s.value, reverse=True)
