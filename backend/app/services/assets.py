import re

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.enums import SECURITY_TYPES, AssetClass
from app.models import Asset
from app.parsers.ibkr import yahoo_ticker
from app.schemas.standard import StandardTransaction

_FUND_HINTS = re.compile(
    r"\b(ETF|UCITS|ISHARES|VANGUARD|XTRACKERS|SPDR|AMUNDI|INVESCO|LYXOR|WISDOMTREE|INDEX FUND|ETC)\b", re.I
)
# Where a bare symbol in a given currency most likely trades on Yahoo Finance.
_CURRENCY_SUFFIX = {"USD": "", "CHF": ".SW", "HUF": ".BD", "GBP": ".L"}


def guess_asset_class(transaction: StandardTransaction) -> AssetClass:
    if transaction.asset_class:
        return transaction.asset_class
    return AssetClass.ETF if transaction.name and _FUND_HINTS.search(transaction.name) else AssetClass.STOCK


def guess_yf_ticker(symbol: str | None, currency: str, exchange: str | None) -> str | None:
    if not symbol or not re.fullmatch(r"[A-Z0-9.\-]{1,12}", symbol):
        return None
    if exchange and (ticker := yahoo_ticker(symbol, exchange)):
        return ticker
    suffix = _CURRENCY_SUFFIX.get(currency)
    return None if suffix is None else f"{symbol}{suffix}"


class AssetResolver:
    """Finds or creates the shared Asset row for a transaction, caching lookups for one import batch."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._cache: dict[tuple[str, str, str], Asset | None] = {}

    def resolve(self, transaction: StandardTransaction) -> Asset | None:
        if not (transaction.symbol or transaction.isin):
            return None
        key = (transaction.isin or "", transaction.symbol or "", transaction.currency)
        if key in self._cache:
            return self._cache[key]

        asset = self._find(transaction)
        if asset is None and transaction.type in SECURITY_TYPES:
            asset = Asset(
                symbol=transaction.symbol or transaction.isin or "",
                isin=transaction.isin,
                name=transaction.name,
                asset_class=guess_asset_class(transaction),
                currency=transaction.currency,
                exchange=transaction.exchange,
                yf_ticker=guess_yf_ticker(transaction.symbol, transaction.currency, transaction.exchange),
            )
            self.session.add(asset)
            self.session.flush()
        elif asset is not None:
            asset.isin = asset.isin or transaction.isin
            asset.name = asset.name or transaction.name
            asset.exchange = asset.exchange or transaction.exchange
        self._cache[key] = asset
        return asset

    def _find(self, transaction: StandardTransaction) -> Asset | None:
        if transaction.type in SECURITY_TYPES:
            # Trades bind to a listing: (symbol, currency), falling back to ISIN in the trade currency
            # for brokers that use a different symbol for the same line.
            if transaction.symbol and (found := self._first(Asset.symbol == transaction.symbol, transaction.currency)):
                return found
            if transaction.isin:
                return self._first(Asset.isin == transaction.isin, transaction.currency)
            return None
        # Income lines (dividends, withholding) may be paid in another currency than the listing.
        if transaction.isin and (found := self._first(Asset.isin == transaction.isin)):
            return found
        if transaction.symbol:
            return self._first(Asset.symbol == transaction.symbol)
        return None

    def _first(self, condition: ColumnElement[bool], currency: str | None = None) -> Asset | None:
        query = select(Asset).where(condition)
        if currency is not None:
            query = query.where(Asset.currency == currency)
        return self.session.scalars(query.order_by(Asset.id)).first()
