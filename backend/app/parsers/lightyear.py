"""Lightyear account statement (CSV export from the app's Statements screen)."""

from typing import ClassVar

from app.enums import TransactionType
from app.parsers.base import AccountHint, ParseResult, RawStatement
from app.parsers.generic import MappingField
from app.parsers.presets import PresetTableParser


class LightyearCSVParser(PresetTableParser):
    key: ClassVar[str] = "lightyear_csv"
    label: ClassVar[str] = "Lightyear statement"
    broker: ClassVar[str | None] = "Lightyear"

    # Date,Reference,Ticker,ISIN,Type,Quantity,CCY,Price/share,Gross Amount,FX Rate,Fee,Net Amt.,Tax Amt.
    signature_headers: ClassVar[tuple[str, ...]] = ("Reference", "Ticker", "ISIN", "CCY", "Price/share", "Net Amt.")
    column_aliases: ClassVar[dict[MappingField, tuple[str, ...]]] = {
        MappingField.DATE: ("Date",),
        MappingField.TYPE: ("Type",),
        MappingField.SYMBOL: ("Ticker",),
        MappingField.ISIN: ("ISIN",),
        MappingField.QUANTITY: ("Quantity",),
        MappingField.UNIT_PRICE: ("Price/share",),
        # Gross amount keeps the sign on Conversion legs (negative = currency sold).
        MappingField.AMOUNT: ("Gross Amount",),
        MappingField.FEE: ("Fee",),
        MappingField.TAX: ("Tax Amt.",),
        MappingField.CURRENCY: ("CCY",),
        MappingField.EXTERNAL_ID: ("Reference",),
    }
    required_fields: ClassVar[frozenset[MappingField]] = frozenset(
        {MappingField.DATE, MappingField.TYPE, MappingField.CURRENCY, MappingField.EXTERNAL_ID}
    )
    decimal_separator = "."
    type_map: ClassVar[dict[str, TransactionType]] = {
        "Buy": TransactionType.BUY,
        "Sell": TransactionType.SELL,
        "Deposit": TransactionType.DEPOSIT,
        "Withdrawal": TransactionType.WITHDRAWAL,
        "Dividend": TransactionType.DIVIDEND,
        "Distribution": TransactionType.DIVIDEND,
        "Interest": TransactionType.INTEREST,
        "Reward": TransactionType.INTEREST,
        "Conversion": TransactionType.FX_CONVERSION,
        "Fee": TransactionType.FEE,
        "Custody fee": TransactionType.FEE,
        "Tax": TransactionType.TAX,
    }

    def normalize(self, statement: RawStatement) -> ParseResult:
        result = super().normalize(statement)
        result.account_hint = AccountHint(broker=self.broker)
        return result
