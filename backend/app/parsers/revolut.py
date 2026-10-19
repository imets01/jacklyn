"""Revolut trading account statement (CSV from the app: Invest → ... → Documents → Account statement).

Columns: Date, Ticker, Type, Quantity, Price per share, Total Amount, Currency, FX Rate. Money cells carry the
currency ("USD 695.01", "$830.40", "USD -0.02"). Two kinds of rows are skipped on purpose:

* STOCK SPLIT: the shares a split added. Jacklyn applies splits itself from market data (and restates the
  trades before them), so importing these too would count each split twice.
* TRANSFER FROM REVOLUT ... TO REVOLUT ...: Revolut moving EU accounts between its own companies (Revolut Trading
  Ltd → Revolut Securities Europe UAB, 2023). Holdings and cash stayed in the account.
"""

import re
from collections.abc import Callable
from decimal import Decimal
from typing import ClassVar

from pydantic import ValidationError

from app.enums import TransactionType
from app.parsers.base import AccountHint, BaseBrokerParser, ParsedRow, ParseResult, RawRecord, RawStatement, RowError
from app.parsers.source import SourceFile, UnsupportedFileError
from app.parsers.text import NumberFormatError, parse_date, parse_decimal
from app.schemas.standard import StandardTransaction

HEADERS = ("Date", "Ticker", "Type", "Quantity", "Price per share", "Total Amount", "Currency", "FX Rate")
INTERNAL_TRANSFER = re.compile(r"^TRANSFER FROM REVOLUT .+ TO REVOLUT ", re.IGNORECASE)
SPLIT_NOTE = "Stock split rows are skipped: Jacklyn applies splits itself from market data."
TRANSFER_NOTE = (
    "Revolut's transfers between its own companies (e.g. to Revolut Securities Europe UAB) are skipped: "
    "holdings and cash stayed in the account."
)


def _money(raw: str) -> Decimal | None:
    return parse_decimal(raw, ".")


class RevolutTradingParser(BaseBrokerParser):
    key: ClassVar[str] = "revolut_trading"
    label: ClassVar[str] = "Revolut trading statement"
    broker: ClassVar[str | None] = "Revolut"

    def detect(self, source: SourceFile) -> float:
        try:
            if source.kind != "csv":
                return 0.0
            headers = [header.strip() for header in source.table.headers()]
        except (UnsupportedFileError, ValueError):
            return 0.0
        except Exception:  # noqa: BLE001 - detection must never raise
            return 0.0
        return 0.9 if tuple(headers[: len(HEADERS)]) == HEADERS else 0.0

    def parse(self, source: SourceFile) -> RawStatement:
        table = source.table
        headers = table.headers()
        records = [
            RawRecord(row=number, fields=dict(zip(headers, cells, strict=False))) for number, cells in table.data_rows()
        ]
        return RawStatement(records=records)

    def normalize(self, statement: RawStatement) -> ParseResult:
        result = self._result()
        result.account_hint = AccountHint(broker=self.broker)
        for record in statement.records:
            fields = {key.strip(): (value or "").strip() for key, value in record.fields.items()}
            kind = fields.get("Type", "").upper()
            if kind == "STOCK SPLIT":
                if SPLIT_NOTE not in result.warnings:
                    result.warnings.append(SPLIT_NOTE)
                continue
            if INTERNAL_TRANSFER.match(kind):
                if TRANSFER_NOTE not in result.warnings:
                    result.warnings.append(TRANSFER_NOTE)
                continue
            try:
                transaction = self._transaction(kind, fields)
            except (ValueError, ValidationError, NumberFormatError) as exc:
                message = (
                    "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in exc.errors())
                    if isinstance(exc, ValidationError)
                    else str(exc)
                )
                result.errors.append(RowError(row=record.row, message=message, raw=fields))
                continue
            result.rows.append(ParsedRow(row=record.row, transaction=transaction))
        return result

    def _transaction(self, kind: str, fields: dict[str, str]) -> StandardTransaction:
        date = parse_date(fields.get("Date", "")[:10])
        if date is None:
            raise ValueError("Missing date")
        amount = _money(fields.get("Total Amount", ""))
        builder = self._builder(kind, amount)
        if builder is None:
            raise ValueError(f"Unknown Revolut transaction type '{fields.get('Type', '')}'")
        tx_type, description = builder
        return StandardTransaction(
            date=date,
            type=tx_type,
            symbol=fields.get("Ticker") or None,
            quantity=_money(fields.get("Quantity", "")),
            unit_price=_money(fields.get("Price per share", "")),
            amount=amount,
            currency=fields.get("Currency", ""),
            description=description(fields) if description else None,
        )

    @staticmethod
    def _builder(
        kind: str, amount: Decimal | None
    ) -> tuple[TransactionType, Callable[[dict[str, str]], str] | None] | None:
        """(type, optional description) for a Revolut row type; the sign of the amount decides corrections."""
        negative = amount is not None and amount < 0
        if kind.startswith("BUY"):
            return TransactionType.BUY, None
        if kind.startswith("SELL"):
            return TransactionType.SELL, None
        if kind == "CASH TOP-UP":
            return TransactionType.DEPOSIT, None
        if kind == "CASH WITHDRAWAL":
            return TransactionType.WITHDRAWAL, None
        if kind == "DIVIDEND":
            return TransactionType.DIVIDEND, None
        if kind.startswith("DIVIDEND TAX"):
            # Withholding is negative; a positive line reverses an earlier one.
            if negative:
                return TransactionType.TAX, lambda f: f"Dividend tax {f.get('Ticker', '')}".strip()
            return TransactionType.DIVIDEND, lambda f: f"Dividend tax refund {f.get('Ticker', '')}".strip()
        if kind in ("CUSTODY FEE", "FEE") or kind.endswith(" FEE"):
            if negative:
                return TransactionType.FEE, lambda f: f.get("Type", "").title()
            return TransactionType.INTEREST, lambda f: f"{f.get('Type', '').title()} refund"
        if kind == "POSITION CLOSURE":
            # Revolut closes a position it never listed as bought (e.g. GameStop warrants given to holders)
            # and pays out the value: income, like a dividend.
            return TransactionType.DIVIDEND, lambda f: f"Position closure {f.get('Ticker', '')}".strip()
        if kind == "INTEREST":
            return TransactionType.INTEREST, None
        return None
