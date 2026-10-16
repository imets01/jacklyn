from enum import StrEnum


class AccountType(StrEnum):
    STANDARD = "standard"
    SWISS = "swiss"
    TBSZ = "tbsz"  # Hungarian long-term investment account, tracked by vintage (collection) year
    PENSION = "pension"
    SAVINGS = "savings"
    CRYPTO = "crypto"
    OTHER = "other"


class TransactionType(StrEnum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    FEE = "fee"
    TAX = "tax"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    FX_CONVERSION = "fx_conversion"  # one leg of a currency exchange; amount is signed
    TRANSFER_IN = "transfer_in"  # securities or cash moved in from another institution
    TRANSFER_OUT = "transfer_out"


TRADE_TYPES = frozenset({TransactionType.BUY, TransactionType.SELL})
SECURITY_TYPES = frozenset(
    {TransactionType.BUY, TransactionType.SELL, TransactionType.TRANSFER_IN, TransactionType.TRANSFER_OUT}
)


class AssetClass(StrEnum):
    STOCK = "stock"
    ETF = "etf"
    FUND = "fund"
    BOND = "bond"
    CRYPTO = "crypto"
    COMMODITY = "commodity"
    CASH = "cash"
    OTHER = "other"


class ImportSource(StrEnum):
    FILE = "file"
    API_SYNC = "api_sync"
    SEED = "seed"
    MANUAL = "manual"
    WEBHOOK = "webhook"


class ImportStatus(StrEnum):
    COMMITTED = "committed"
    FAILED = "failed"


class PriceSource(StrEnum):
    SEED = "seed"  # synthetic demo history
    YFINANCE = "yfinance"
    IMPORT = "import"
