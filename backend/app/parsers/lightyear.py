"""Lightyear account statement CSV.

Expected header (Lightyear "Account statement" export)::

    Date,Reference,Ticker,ISIN,Type,Quantity,CCY,Price/share,Gross Amount,
    FX Rate,Fee,Net Amt.,Tax Amt.

Built on :class:`GenericCSVParser` with a preset mapping. Marked as a stub
until verified against a broad set of real exports (conversions in particular).
"""

from app.models.enums import Institution, TransactionType
from app.parsers.base import BaseBrokerParser, FileSample, ParseResult
from app.parsers.generic_csv import ColumnMapping, GenericCSVParser

_SIGNATURE = {"date", "reference", "ticker", "isin", "type", "ccy", "net amt."}

LIGHTYEAR_MAPPING = ColumnMapping(
    columns={
        "trade_date": "Date",
        "external_id": "Reference",
        "symbol": "Ticker",
        "isin": "ISIN",
        "type": "Type",
        "quantity": "Quantity",
        "currency": "CCY",
        "price": "Price/share",
        "fee": "Fee",
        "amount": "Net Amt.",
    },
    decimal_separator=".",
    thousands_separator=",",
    type_map={
        "Buy": TransactionType.BUY,
        "Sell": TransactionType.SELL,
        "Deposit": TransactionType.DEPOSIT,
        "Withdrawal": TransactionType.WITHDRAWAL,
        "Dividend": TransactionType.DIVIDEND,
        "Distribution": TransactionType.DIVIDEND,
        "Interest": TransactionType.INTEREST,
        "Reward": TransactionType.INTEREST,
        "Conversion": TransactionType.FX,
        "Tax": TransactionType.TAX,
        "Fee": TransactionType.FEE,
    },
)


class LightyearParser(BaseBrokerParser):
    key = "lightyear"
    label = "Lightyear – Account statement"
    institution = Institution.LIGHTYEAR
    is_stub = True

    @classmethod
    def detect(cls, sample: FileSample) -> float:
        overlap = len(_SIGNATURE & sample.header_set)
        if overlap >= 6:
            return 0.95
        if "lightyear" in sample.filename.lower() and overlap >= 3:
            return 0.7
        return 0.0

    def parse(self, text: str) -> ParseResult:
        result = GenericCSVParser(LIGHTYEAR_MAPPING).parse(text)
        result.parser_key = self.key
        return result
