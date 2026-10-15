from enum import StrEnum


class Institution(StrEnum):
    IBKR = "ibkr"
    LIGHTYEAR = "lightyear"
    ERSTE = "erste"
    OTHER = "other"


class AccountType(StrEnum):
    """Account subtype. Drives tax treatment and UI badges."""

    STANDARD = "standard"
    SWISS = "swiss"  # Swiss-domiciled / Swiss tax reporting
    TBSZ = "tbsz"  # Hungarian tartós befektetési számla; requires ``tbsz_year``


class AssetClass(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    BOND = "bond"
    FUND = "fund"
    CRYPTO = "crypto"
    COMMODITY = "commodity"
    OTHER = "other"


class TransactionType(StrEnum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FEE = "fee"
    TAX = "tax"
    FX = "fx"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"


# Cash direction implied by each type. ``None`` = sign comes from the source.
CASH_DIRECTION: dict[TransactionType, int | None] = {
    TransactionType.BUY: -1,
    TransactionType.SELL: 1,
    TransactionType.DIVIDEND: 1,
    TransactionType.INTEREST: 1,
    TransactionType.DEPOSIT: 1,
    TransactionType.WITHDRAWAL: -1,
    TransactionType.FEE: -1,
    TransactionType.TAX: -1,
    TransactionType.FX: None,
    TransactionType.TRANSFER_IN: 1,
    TransactionType.TRANSFER_OUT: -1,
}

# Types that move units of an asset in (+1) or out (-1) of a position.
QUANTITY_DIRECTION: dict[TransactionType, int] = {
    TransactionType.BUY: 1,
    TransactionType.SELL: -1,
    TransactionType.TRANSFER_IN: 1,
    TransactionType.TRANSFER_OUT: -1,
}

# Types counted as money the user put in (or took out) of the portfolio.
CONTRIBUTION_TYPES = frozenset({TransactionType.DEPOSIT, TransactionType.WITHDRAWAL})


class ImportStatus(StrEnum):
    COMMITTED = "committed"
    FAILED = "failed"
