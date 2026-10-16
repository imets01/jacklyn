"""Lightyear account statement (CSV export from the app's Statements screen)."""

from decimal import Decimal
from typing import ClassVar

from app.enums import TransactionType
from app.parsers.base import AccountHint, ParseResult, RawStatement
from app.parsers.generic import MappingField
from app.parsers.presets import PresetTableParser
from app.parsers.text import NumberFormatError, parse_decimal
from app.schemas.standard import StandardTransaction


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
        net_by_row = {record.row: record.fields.get("Net Amt.", "") for record in statement.records}
        for parsed in result.rows:
            parsed.transaction = _settle_fees(parsed.transaction, net_by_row.get(parsed.row, ""))
        return result


def _settle_fees(tx: StandardTransaction, raw_net: str) -> StandardTransaction:
    """Lightyear's "Gross Amount" already contains the fee on buys and conversions.

    Re-express each line so Jacklyn's cash flow (amount +/- fee) equals Lightyear's "Net Amt.":
    buys pay net + fee, conversion legs move net and pay the fee on top, sells keep gross - fee.
    """
    try:
        net = parse_decimal(raw_net, ".")
    except NumberFormatError:
        net = None
    if net is None:
        return tx
    if tx.type is TransactionType.BUY:
        return tx.model_copy(update={"amount": abs(net)})
    if tx.type is TransactionType.FX_CONVERSION:
        return tx.model_copy(update={"amount": net})
    if (
        tx.type in (TransactionType.DEPOSIT, TransactionType.WITHDRAWAL)
        and tx.amount is not None
        and abs(net) == tx.amount
    ):
        # Card top-up fees are shown but not taken from the credited amount.
        return tx.model_copy(update={"fee": Decimal(0)})
    return tx
