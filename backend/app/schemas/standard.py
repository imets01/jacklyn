"""The unified StandardTransaction schema every ingestion source normalizes into."""

import datetime as dt
import re
from decimal import Decimal
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import TRADE_TYPES, AssetClass, TransactionType

ZERO = Decimal(0)
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")


def currency_code(value: str) -> str:
    """Normalized ISO 4217 code ("chf " -> "CHF"); raises ValueError for anything else."""
    code = value.strip().upper()
    if not CURRENCY_RE.match(code):
        raise ValueError(f"'{value}' is not an ISO 4217 currency code")
    return code


# Income legs can legitimately be negative (dividend reversal, charged interest);
# FX legs carry their direction in the sign. Everything else is a magnitude.
SIGNED_AMOUNT_TYPES = frozenset({TransactionType.FX_CONVERSION, TransactionType.DIVIDEND, TransactionType.INTEREST})
CASH_IN_TYPES = frozenset({TransactionType.DEPOSIT, TransactionType.DIVIDEND, TransactionType.INTEREST})
CASH_OUT_TYPES = frozenset({TransactionType.WITHDRAWAL, TransactionType.FEE, TransactionType.TAX})


class StandardTransaction(BaseModel):
    """One normalized ledger line.

    * ``quantity``, ``unit_price``, ``fee`` and ``tax`` are always non-negative.
    * ``amount`` is the gross cash value in ``currency``. It is a magnitude whose direction is
      implied by ``type``, except for ``SIGNED_AMOUNT_TYPES``.
    * For BUY/SELL the missing one of ``amount`` / ``unit_price`` is derived from the other.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    date: dt.date
    type: TransactionType
    symbol: str | None = Field(default=None, max_length=32)
    isin: str | None = None
    name: str | None = Field(default=None, max_length=200)
    asset_class: AssetClass | None = None
    exchange: str | None = Field(default=None, max_length=32)
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    fee: Decimal = ZERO
    tax: Decimal = ZERO
    currency: str
    external_id: str | None = Field(default=None, max_length=128)
    description: str | None = None

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str) -> str:
        return currency_code(value)

    @field_validator("symbol", "exchange")
    @classmethod
    def _upper_or_none(cls, value: str | None) -> str | None:
        return value.strip().upper() or None if value else None

    @field_validator("isin")
    @classmethod
    def _isin(cls, value: str | None) -> str | None:
        if not value:
            return None
        code = value.strip().upper()
        if not ISIN_RE.match(code):
            raise ValueError(f"'{value}' is not a valid ISIN")
        return code

    @field_validator("name", "description", "external_id")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None

    @model_validator(mode="after")
    def _normalize(self) -> Self:
        for field in ("quantity", "unit_price"):
            value = getattr(self, field)
            if value is not None:
                setattr(self, field, abs(value))
        self.fee = abs(self.fee)
        self.tax = abs(self.tax)
        if self.amount is not None and self.type not in SIGNED_AMOUNT_TYPES:
            self.amount = abs(self.amount)

        if self.type in TRADE_TYPES:
            if self.symbol is None and self.isin is None:
                raise ValueError(f"{self.type.value} requires a symbol or ISIN")
            self._derive_trade_values()
        elif self.type in (TransactionType.TRANSFER_IN, TransactionType.TRANSFER_OUT):
            if self.symbol or self.isin:
                if not self.quantity:
                    raise ValueError("a security transfer requires a quantity")
            elif self.amount is None:
                raise ValueError("a cash transfer requires an amount")
        elif self.type in (TransactionType.FEE, TransactionType.TAX):
            # Allow a fee/tax line expressed only through the fee/tax column.
            if self.amount is None:
                self.amount, self.fee, self.tax = self.fee + self.tax, ZERO, ZERO
            if self.amount == ZERO:
                raise ValueError(f"{self.type.value} amount must not be zero")
        else:
            if self.amount is None:
                raise ValueError(f"{self.type.value} requires an amount")
            if self.type is TransactionType.FX_CONVERSION and self.amount == ZERO:
                raise ValueError("fx_conversion amount must not be zero")
        return self

    def _derive_trade_values(self) -> None:
        if not self.quantity:
            raise ValueError(f"{self.type.value} requires a non-zero quantity")
        if self.amount is None and self.unit_price is None:
            raise ValueError(f"{self.type.value} requires a unit price or an amount")
        if self.amount is None:
            assert self.unit_price is not None
            self.amount = self.quantity * self.unit_price
        elif self.unit_price is None:
            self.unit_price = self.amount / self.quantity

    def cash_flow(self) -> Decimal:
        """Signed effect on the account's cash balance in ``currency``."""
        return cash_flow(self.type, self.amount, self.fee, self.tax, has_asset=bool(self.symbol or self.isin))


def cash_flow(
    tx_type: TransactionType, amount: Decimal | None, fee: Decimal, tax: Decimal, *, has_asset: bool
) -> Decimal:
    gross = amount or ZERO
    costs = fee + tax
    if tx_type is TransactionType.BUY:
        return -gross - costs
    if tx_type is TransactionType.SELL:
        return gross - costs
    if tx_type in (TransactionType.TRANSFER_IN, TransactionType.TRANSFER_OUT):
        if has_asset:
            return -costs
        return (gross if tx_type is TransactionType.TRANSFER_IN else -gross) - costs
    if tx_type in CASH_IN_TYPES or tx_type is TransactionType.FX_CONVERSION:
        return gross - costs
    if tx_type in CASH_OUT_TYPES:
        return -gross - costs
    raise ValueError(f"Unhandled transaction type {tx_type}")
