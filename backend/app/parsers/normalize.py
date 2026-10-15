"""Turn loosely-typed broker cells into a clean :class:`ParsedTransaction`."""

import re
from datetime import date
from decimal import Decimal
from typing import Literal

from app.core.money import ZERO
from app.models.enums import CASH_DIRECTION, AssetClass, TransactionType
from app.parsers.base import ParsedTransaction
from app.parsers.csv_utils import normalise_header

AmountSign = Literal["infer", "as_is"]

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

# Normalised words -> transaction type. Covers EN / DE / HU broker vocabularies.
TYPE_SYNONYMS: dict[TransactionType, tuple[str, ...]] = {
    TransactionType.BUY: (
        "buy",
        "bought",
        "purchase",
        "market buy",
        "limit buy",
        "kauf",
        "vetel",
        "b",
    ),
    TransactionType.SELL: (
        "sell",
        "sold",
        "sale",
        "market sell",
        "limit sell",
        "verkauf",
        "eladas",
        "s",
    ),
    TransactionType.DIVIDEND: (
        "dividend",
        "dividends",
        "distribution",
        "cash dividend",
        "dividende",
        "osztalek",
        "hozamfizetes",
    ),
    TransactionType.INTEREST: ("interest", "zins", "zinsen", "kamat", "kamatjovairas", "reward"),
    TransactionType.DEPOSIT: (
        "deposit",
        "top up",
        "topup",
        "cash in",
        "einzahlung",
        "befizetes",
        "jovairas",
    ),
    TransactionType.WITHDRAWAL: (
        "withdrawal",
        "withdraw",
        "cash out",
        "auszahlung",
        "kifizetes",
        "kivet",
        "terheles",
    ),
    TransactionType.FEE: ("fee", "fees", "commission", "gebuhr", "jutalek", "dij", "kezelesi dij"),
    TransactionType.TAX: (
        "tax",
        "withholding tax",
        "wht",
        "steuer",
        "quellensteuer",
        "ado",
        "szja",
    ),
    TransactionType.FX: (
        "fx",
        "conversion",
        "currency exchange",
        "exchange",
        "devizavaltas",
        "konverzio",
        "forex",
    ),
    TransactionType.TRANSFER_IN: ("transfer in", "security transfer in", "transzfer be"),
    TransactionType.TRANSFER_OUT: ("transfer out", "security transfer out", "transzfer ki"),
}

_TYPE_LOOKUP: dict[str, TransactionType] = {
    word: ttype for ttype, words in TYPE_SYNONYMS.items() for word in words
}


def guess_transaction_type(value: str) -> TransactionType | None:
    norm = normalise_header(value)
    if not norm:
        return None
    if norm in _TYPE_LOOKUP:
        return _TYPE_LOOKUP[norm]
    try:
        return TransactionType(norm.replace(" ", "_"))
    except ValueError:
        pass
    # Longest synonym contained in the value ("Market buy - AAPL" -> buy).
    for word in sorted(_TYPE_LOOKUP, key=len, reverse=True):
        if len(word) > 2 and re.search(rf"\b{re.escape(word)}\b", norm):
            return _TYPE_LOOKUP[word]
    return None


def clean_currency(value: str | None) -> str:
    code = (value or "").strip().upper()
    if not _CURRENCY_RE.match(code):
        raise ValueError(f"Invalid currency code: {value!r}")
    return code


def clean_isin(value: str | None) -> str | None:
    code = (value or "").strip().upper()
    return code if _ISIN_RE.match(code) else None


def build_transaction(
    *,
    row_number: int,
    ttype: TransactionType,
    trade_date: date,
    currency: str,
    amount: Decimal | None,
    quantity: Decimal | None = None,
    price: Decimal | None = None,
    fee: Decimal | None = None,
    amount_sign: AmountSign = "infer",
    symbol: str | None = None,
    isin: str | None = None,
    asset_name: str | None = None,
    asset_class: AssetClass | None = None,
    description: str | None = None,
    external_id: str | None = None,
    settle_date: date | None = None,
) -> ParsedTransaction:
    """Validate and normalise one transaction.

    * ``fee`` is stored as a positive magnitude.
    * ``quantity`` is stored as a positive magnitude; the type gives direction.
    * ``amount`` is derived from ``quantity * price ± fee`` when missing, and
      its sign is forced from the type when ``amount_sign == "infer"``.
    """
    fee_abs = abs(fee) if fee is not None else ZERO
    qty_abs = abs(quantity) if quantity is not None else None

    if ttype in (TransactionType.BUY, TransactionType.SELL) and not qty_abs:
        raise ValueError(f"{ttype.value} row needs a non-zero quantity")

    if amount is None:
        if qty_abs is None or price is None:
            raise ValueError("Row has no amount and no quantity × price to derive it from")
        gross = qty_abs * abs(price)
        amount = -(gross + fee_abs) if ttype is TransactionType.BUY else gross - fee_abs

    direction = CASH_DIRECTION[ttype]
    if amount_sign == "infer" and direction is not None:
        amount = abs(amount) * direction

    symbol_clean = (symbol or "").strip().upper() or None
    return ParsedTransaction(
        row_number=row_number,
        type=ttype,
        trade_date=trade_date,
        amount=amount,
        currency=clean_currency(currency),
        quantity=qty_abs,
        price=abs(price) if price is not None else None,
        fee=fee_abs,
        symbol=symbol_clean,
        isin=clean_isin(isin),
        asset_name=(asset_name or "").strip() or None,
        asset_class=asset_class,
        description=(description or "").strip()[:500] or None,
        external_id=(external_id or "").strip()[:128] or None,
        settle_date=settle_date,
    )
