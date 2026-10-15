"""Interactive Brokers *Activity Statement* CSV parser.

IBKR statements are multi-section CSVs where every line starts with the
section name and a row kind::

    Trades,Header,DataDiscriminator,Asset Category,Currency,Symbol,Date/Time,Quantity,...
    Trades,Data,Order,Stocks,USD,AAPL,"2025-01-15, 10:30:00",10,185.5,...
    Dividends,Header,Currency,Date,Description,Amount
    Dividends,Data,USD,2025-02-15,AAPL(US0378331005) Cash Dividend ...,2.4

Supported sections: Trades (stocks/ETFs/forex), Dividends, Withholding Tax,
Deposits & Withdrawals, Fees, Interest, Financial Instrument Information.
Flex Query exports are a different layout and are not handled yet.
"""

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

from app.core.money import ZERO, parse_decimal
from app.models.enums import AssetClass, Institution, TransactionType
from app.parsers.base import BaseBrokerParser, FileSample, ParseResult, RowError
from app.parsers.csv_utils import parse_date
from app.parsers.normalize import build_transaction

_KNOWN_SECTIONS = {
    "Statement",
    "Account Information",
    "Trades",
    "Dividends",
    "Withholding Tax",
    "Deposits & Withdrawals",
    "Open Positions",
    "Net Asset Value",
}

_CASH_SECTIONS: dict[str, TransactionType] = {
    "Dividends": TransactionType.DIVIDEND,
    "Withholding Tax": TransactionType.TAX,
    "Deposits & Withdrawals": TransactionType.DEPOSIT,  # sign decides deposit vs withdrawal
    "Fees": TransactionType.FEE,
    "Interest": TransactionType.INTEREST,
}

# "AAPL(US0378331005) Cash Dividend USD 0.24 per Share" -> AAPL, US0378331005
_DIVIDEND_DESC = re.compile(r"^(?P<symbol>[A-Z0-9.\- ]+?)\s*\((?P<isin>[A-Z]{2}[A-Z0-9]{9}\d)\)")


@dataclass(frozen=True, slots=True)
class _InstrumentInfo:
    name: str
    isin: str | None
    asset_class: AssetClass


@dataclass(frozen=True, slots=True)
class _Row:
    line_no: int
    section: str
    cells: dict[str, str]


class IbkrActivityParser(BaseBrokerParser):
    key = "ibkr"
    label = "Interactive Brokers – Activity Statement"
    institution = Institution.IBKR

    @classmethod
    def detect(cls, sample: FileSample) -> float:
        lines = sample.text.splitlines()[:200]
        hits = sum(
            1
            for line in lines
            if line.split(",", 2)[1:2] in (["Header"], ["Data"])
            and line.split(",", 1)[0].strip('"') in _KNOWN_SECTIONS
        )
        if hits >= 3:
            return 0.98
        if "interactive brokers" in sample.text[:4000].lower() and hits:
            return 0.8
        return 0.0

    def parse(self, text: str) -> ParseResult:
        result = ParseResult(parser_key=self.key, headers=[])
        rows = list(self._iter_data_rows(text, result))
        instruments = self._instrument_info(rows)

        for row in rows:
            if row.section == "Trades":
                handler = self._trade
            elif row.section in _CASH_SECTIONS:
                handler = self._cash
            else:
                continue
            if self._is_total(row):
                continue
            result.rows_total += 1
            try:
                handler(row, instruments, result)
            except (ValueError, ArithmeticError, KeyError) as exc:
                result.errors.append(
                    RowError(row_number=row.line_no, message=str(exc), raw=row.cells)
                )
        return result

    # ------------------------------------------------------------------ reading

    @staticmethod
    def _iter_data_rows(text: str, result: ParseResult) -> Iterator[_Row]:
        headers: dict[str, list[str]] = {}
        for line_no, cells in enumerate(csv.reader(io.StringIO(text)), start=1):
            if len(cells) < 2:
                continue
            section, kind, values = cells[0], cells[1], cells[2:]
            if kind == "Header":
                # Sections can repeat with a different header (e.g. Trades for forex).
                headers[section] = values
                if section not in result.headers:
                    result.headers.append(section)
            elif kind == "Data" and section in headers:
                yield _Row(line_no, section, dict(zip(headers[section], values, strict=False)))

    @staticmethod
    def _is_total(row: _Row) -> bool:
        first = next(iter(row.cells.values()), "")
        disc = row.cells.get("DataDiscriminator", "Order")
        return first.startswith("Total") or disc not in ("Order", "Trade", "")

    @staticmethod
    def _instrument_info(rows: list[_Row]) -> dict[str, _InstrumentInfo]:
        info: dict[str, _InstrumentInfo] = {}
        for row in rows:
            if row.section != "Financial Instrument Information":
                continue
            symbol = row.cells.get("Symbol", "").strip()
            kind = row.cells.get("Type", "").upper()
            category = row.cells.get("Asset Category", "")
            asset_class = (
                AssetClass.ETF
                if kind == "ETF"
                else AssetClass.BOND
                if category == "Bonds"
                else AssetClass.EQUITY
            )
            for sym in symbol.split(","):
                info[sym.strip()] = _InstrumentInfo(
                    name=row.cells.get("Description", sym).strip(),
                    isin=row.cells.get("Security ID", "").strip() or None,
                    asset_class=asset_class,
                )
        return info

    # ------------------------------------------------------------------ sections

    @staticmethod
    def _dec(value: str | None) -> Decimal | None:
        return parse_decimal(value or "")

    def _trade(self, row: _Row, instruments: dict[str, _InstrumentInfo], out: ParseResult) -> None:
        c = row.cells
        category = c.get("Asset Category", "")
        trade_date = parse_date(c["Date/Time"].split(",")[0])
        quantity = self._dec(c.get("Quantity")) or ZERO
        proceeds = self._dec(c.get("Proceeds")) or ZERO
        commission = self._dec(c.get("Comm/Fee") or c.get("Comm in USD")) or ZERO
        symbol = c.get("Symbol", "").strip()

        if category == "Forex":
            base, _, quote = symbol.partition(".")
            for ccy, amt in ((base, quantity), (quote, proceeds)):
                out.transactions.append(
                    build_transaction(
                        row_number=row.line_no,
                        ttype=TransactionType.FX,
                        trade_date=trade_date,
                        currency=ccy,
                        amount=amt,
                        description=f"FX {symbol}",
                    )
                )
            if commission:
                out.transactions.append(
                    build_transaction(
                        row_number=row.line_no,
                        ttype=TransactionType.FEE,
                        trade_date=trade_date,
                        currency="USD" if "Comm in USD" in c else c.get("Currency", quote),
                        amount=commission,
                        description=f"FX commission {symbol}",
                    )
                )
            return

        if category not in ("Stocks", "Bonds", "Funds", ""):
            raise ValueError(f"Asset category {category!r} not supported yet")
        meta = instruments.get(symbol)
        out.transactions.append(
            build_transaction(
                row_number=row.line_no,
                ttype=TransactionType.BUY if quantity > 0 else TransactionType.SELL,
                trade_date=trade_date,
                currency=c.get("Currency", ""),
                amount=proceeds + commission,  # commission is reported negative
                quantity=quantity,
                price=self._dec(c.get("T. Price")),
                fee=commission,
                symbol=symbol,
                isin=meta.isin if meta else None,
                asset_name=meta.name if meta else None,
                asset_class=meta.asset_class if meta else AssetClass.EQUITY,
                amount_sign="as_is",
            )
        )

    def _cash(self, row: _Row, instruments: dict[str, _InstrumentInfo], out: ParseResult) -> None:
        c = row.cells
        amount = self._dec(c.get("Amount"))
        if amount is None:
            raise ValueError("Amount: empty")
        ttype = _CASH_SECTIONS[row.section]
        if row.section == "Deposits & Withdrawals" and amount < 0:
            ttype = TransactionType.WITHDRAWAL

        description = c.get("Description", "")
        symbol = isin = None
        match = _DIVIDEND_DESC.match(description)
        if match and ttype in (TransactionType.DIVIDEND, TransactionType.TAX):
            symbol, isin = match["symbol"].strip(), match["isin"]

        out.transactions.append(
            build_transaction(
                row_number=row.line_no,
                ttype=ttype,
                trade_date=parse_date(c.get("Date") or c.get("Settle Date", "")),
                currency=c.get("Currency", ""),
                amount=amount,
                symbol=symbol,
                isin=isin,
                asset_name=instruments[symbol].name if symbol in instruments else None,
                description=description,
                amount_sign="as_is",
            )
        )
