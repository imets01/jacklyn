import datetime as dt
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.enums import AccountType, AssetClass

HistoryRange = Literal["1W", "1M", "3M", "YTD", "1Y", "ALL"]


class AllocationSlice(BaseModel):
    key: str
    label: str
    value: Decimal
    weight: Decimal


class Allocations(BaseModel):
    asset_class: list[AllocationSlice]
    currency: list[AllocationSlice]
    broker: list[AllocationSlice]
    wrapper: list[AllocationSlice]
    account: list[AllocationSlice]


class AccountSummary(BaseModel):
    id: int
    name: str
    broker: str
    account_type: AccountType
    tbsz_year: int | None
    tbsz_reduced_rate_from: dt.date | None
    tbsz_tax_free_from: dt.date | None
    currency: str
    external_account_id: str | None
    track_cash: bool
    is_archived: bool
    value: Decimal
    value_account_currency: Decimal | None
    cash: Decimal
    day_change: Decimal
    total_pnl: Decimal
    net_contributions: Decimal
    holdings_count: int
    transaction_count: int
    last_transaction_date: dt.date | None


class MarketStatus(BaseModel):
    live_enabled: bool = False
    refreshing: bool = False
    last_refresh_at: dt.datetime | None = None
    last_refresh_error: str | None = None
    prices_as_of: dt.date | None
    fx_as_of: dt.date | None
    synthetic_price_assets: int
    unpriced_assets: int


class PortfolioSummary(BaseModel):
    base_currency: str
    as_of: dt.date
    net_worth: Decimal
    holdings_value: Decimal
    cash: Decimal
    day_change: Decimal
    day_change_pct: Decimal | None
    total_pnl: Decimal
    total_pnl_pct: Decimal | None
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    income: Decimal
    costs: Decimal
    net_contributions: Decimal
    allocations: Allocations
    accounts: list[AccountSummary]
    market: MarketStatus
    warnings: list[str]


class Holding(BaseModel):
    account_id: int
    account_name: str
    asset_id: int
    symbol: str
    name: str | None
    isin: str | None
    asset_class: AssetClass
    currency: str
    quantity: Decimal
    price: Decimal | None
    price_date: dt.date | None
    value_local: Decimal
    value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal | None
    day_change: Decimal
    weight: Decimal


class CashBalance(BaseModel):
    account_id: int
    account_name: str
    currency: str
    amount: Decimal
    value: Decimal


class HoldingsResponse(BaseModel):
    base_currency: str
    as_of: dt.date
    holdings: list[Holding]
    cash: list[CashBalance]


class HistoryPoint(BaseModel):
    date: dt.date
    value: Decimal
    invested: Decimal


class HistoryResponse(BaseModel):
    base_currency: str
    range: HistoryRange
    points: list[HistoryPoint]
    change: Decimal
    change_pct: Decimal | None
