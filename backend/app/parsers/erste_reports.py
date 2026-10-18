"""Erste Befektetési (NetBroker) daily reports: "Pénzügyi tranzakciók", "Befektetési jegyek", "Külföldi részvény".

NetBroker only exports one report per booking day and kind, so a full history is dozens of small .xls files; the
importer takes them all at once. Every report lists its rows under sub-account sections such as
"5606105 - TBSZ 2024 - MAGYAR FORINT", so each row is tagged with its sub-account (TBSZ 2024, TBSZ 2025, Normál)
and the preview routes it to the matching Jacklyn account.

The sheets use merged cells, so a value often sits a few columns off its header: each value is matched to the
nearest header column. Some records span two lines (the ETF trade's fee is on the line below it).
"""

import datetime as dt
import re
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import ClassVar

from pydantic import ValidationError

from app.enums import AssetClass, TransactionType
from app.parsers.base import AccountHint, BaseBrokerParser, ParsedRow, ParseResult, RawRecord, RawStatement, RowError
from app.parsers.source import SourceFile, UnsupportedFileError
from app.schemas.standard import StandardTransaction

BROKER = "Erste Bank"
CASH_REPORT = "Pénzügyi tranzakciók"
FUND_REPORT = "Befektetési jegyek"
SHARE_REPORT = "Külföldi részvény"
REPORT_KINDS = (CASH_REPORT, FUND_REPORT, SHARE_REPORT)

# "5606105 - TBSZ 2024 - MAGYAR FORINT", "5606105 - Normál - EURO", "5606105 - TBSZ 2024" (currency exchanges)
SECTION = re.compile(r"^(\d{4,})\s+-\s+(.+?)(?:\s+-\s+([^-]+))?$")
TBSZ = re.compile(r"\bTBSZ\s+(\d{4})\b", re.IGNORECASE)
CURRENCY_NAMES = {
    "MAGYAR FORINT": "HUF",
    "EURO": "EUR",
    "USA DOLLÁR": "USD",
    "AMERIKAI DOLLÁR": "USD",
    "SVÁJCI FRANK": "CHF",
    "ANGOL FONT": "GBP",
    "FONT STERLING": "GBP",
}
SIDES = {"vétel": TransactionType.BUY, "eladás": TransactionType.SELL}
EXCEL_EPOCH = dt.date(1899, 12, 30)
QUANTUM = Decimal("0.00000001")  # spreadsheet floats ("0.22699999999999998") are rounded to 8 places


class _Header:
    """Column positions of one header line; values are matched to the nearest header column."""

    def __init__(self, row: list[str]) -> None:
        self.columns = {col: cell.strip() for col, cell in enumerate(row) if cell.strip()}

    def read(self, row: list[str]) -> dict[str, str]:
        best: dict[str, tuple[int, str]] = {}
        for col, cell in enumerate(row):
            value = cell.strip()
            if not value or not self.columns:
                continue
            header_col = min(self.columns, key=lambda c: (abs(c - col), c))
            name = self.columns[header_col]
            distance = abs(header_col - col)
            if name not in best or distance < best[name][0]:
                best[name] = (distance, value)
        return {name: value for name, (_, value) in best.items()}


def _field(fields: dict[str, str], prefix: str) -> str:
    """The value whose header starts with `prefix` (headers carry footnote marks and doubled spaces)."""
    wanted = " ".join(prefix.split()).casefold()
    for name, value in fields.items():
        if " ".join(name.split()).casefold().startswith(wanted):
            return value
    return ""


def _exact(fields: dict[str, str], header: str) -> str:
    return next((value for name, value in fields.items() if name.strip() == header), "")


def _number(text: str) -> Decimal | None:
    if not text.strip():
        return None
    try:
        return Decimal(text.replace(" ", "")).quantize(QUANTUM).normalize()
    except InvalidOperation:
        return None


def _serial_date(text: str) -> dt.date | None:
    """Excel serial day numbers ("45362") as stored by NetBroker, or an ISO date from other readers."""
    value = text.strip()
    if re.fullmatch(r"\d{5}(\.0+)?", value):
        return EXCEL_EPOCH + dt.timedelta(days=int(float(value)))
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def _is_header(row: list[str]) -> bool:
    return row[0].strip() == "Kereskedési nap" if row else False


class ErsteDailyReportParser(BaseBrokerParser):
    key: ClassVar[str] = "erste_daily_report"
    label: ClassVar[str] = "Erste NetBroker daily report"
    broker: ClassVar[str | None] = BROKER

    def detect(self, source: SourceFile) -> float:
        try:
            if source.kind not in ("xls", "xlsx"):
                return 0.0
            rows = source.table.rows
        except (UnsupportedFileError, ValueError):
            return 0.0
        except Exception:  # noqa: BLE001 - detection must never raise
            return 0.0
        titles = {row[0].strip() for row in rows[:12] if row}
        has_header = any(_is_header(row) for row in rows[:40])
        return 0.95 if has_header and titles & set(REPORT_KINDS) else 0.0

    def parse(self, source: SourceFile) -> RawStatement:
        rows = source.table.rows
        kind = ""
        records: list[RawRecord] = []
        header: _Header | None = None
        second_header: _Header | None = None
        section = ""
        current: RawRecord | None = None
        for number, row in enumerate(rows, start=1):
            first = row[0].strip() if row else ""
            if first in REPORT_KINDS:  # one sheet can hold several reports (ETF trades, then cash movements)
                kind, header, second_header, current = first, None, None, None
                continue
            if _is_header(row):
                header, second_header, current = _Header(row), None, None
                continue
            if header is not None and first == "Elszámolás napja" and current is None:
                second_header = _Header(row)  # the ETF table's second header line (settlement, fee)
                continue
            if SECTION.match(first):
                section, current = first, None
                continue
            if header is None or not first:
                continue
            fields = header.read(row)
            transaction_id = _field(fields, "Tranzakció azonosító")
            if _serial_date(first) is not None and transaction_id:
                current = RawRecord(row=number, fields={**fields, "_kind": kind, "_section": section})
                records.append(current)
            elif current is not None and (first == "---" or _serial_date(first) is not None):
                # Continuation line: settlement date, the ETF fee, execution time.
                extra = second_header.read(row) if second_header else {}
                current.fields.update({f"_2:{name}": value for name, value in extra.items()})
                current = None
            else:
                current = None  # totals, closing balances, footnotes
        return RawStatement(records=records)

    def normalize(self, statement: RawStatement) -> ParseResult:
        result = self._result()
        for record in statement.records:
            account, currency = self._section(record.fields["_section"], result)
            try:
                for transaction in self._transactions(record.fields, currency):
                    result.rows.append(ParsedRow(row=record.row, transaction=transaction, account=account))
            except (ValueError, ValidationError) as exc:
                message = (
                    "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in exc.errors())
                    if isinstance(exc, ValidationError)
                    else str(exc)
                )
                raw = {k: v for k, v in record.fields.items() if not k.startswith("_")}
                result.errors.append(RowError(row=record.row, message=message, raw=raw))
        if len(result.accounts) == 1:
            result.account_hint = next(iter(result.accounts.values()))
        return result

    @staticmethod
    def _section(text: str, result: ParseResult) -> tuple[str | None, str | None]:
        match = SECTION.match(text)
        if not match:
            return None, None
        _client, name, currency_name = match.groups()
        name = name.strip()
        currency = CURRENCY_NAMES.get((currency_name or "").strip().upper())
        if name not in result.accounts:
            year = TBSZ.search(name)
            result.accounts[name] = AccountHint(
                broker=BROKER,
                name=name,
                tbsz_year=int(year.group(1)) if year else None,
                currency=currency,
            )
        return name, currency

    def _transactions(self, fields: dict[str, str], section_currency: str | None) -> list[StandardTransaction]:
        handlers: dict[str, Callable[[dict[str, str], str | None], list[StandardTransaction]]] = {
            CASH_REPORT: self._cash,
            FUND_REPORT: self._trade,
            SHARE_REPORT: self._share_or_fx,
        }
        handler = handlers.get(fields["_kind"])
        if handler is None:
            raise ValueError("Unknown Erste report kind")
        return handler(fields, section_currency)

    @staticmethod
    def _date(fields: dict[str, str]) -> dt.date:
        date = _serial_date(_field(fields, "Kereskedési nap"))
        if date is None:
            raise ValueError("Missing trade date")
        return date

    def _cash(self, fields: dict[str, str], currency: str | None) -> list[StandardTransaction]:
        name = _exact(fields, "Tranzakció")
        direction = _field(fields, "Művelet").casefold()
        amount = _number(_field(fields, "Összérték"))
        fee = _number(_exact(fields, "Költség")) or Decimal(0)
        currency = currency or _field(fields, "Költség devizaneme")
        lowered = name.casefold()
        if "osztalék" in lowered or "hozam" in lowered:
            tx_type = TransactionType.DIVIDEND
        elif "kamat" in lowered:
            tx_type = TransactionType.INTEREST
        elif "adó" in lowered:
            tx_type = TransactionType.TAX
        elif "díj" in lowered or "jutalék" in lowered:
            tx_type = TransactionType.FEE
        elif direction.startswith("jóváírás"):
            tx_type = TransactionType.DEPOSIT
        elif direction.startswith("terhelés"):
            tx_type = TransactionType.WITHDRAWAL
        else:
            raise ValueError(f"Unknown cash movement '{name}' ({direction or 'no direction'})")
        return [
            StandardTransaction(
                date=self._date(fields),
                type=tx_type,
                amount=amount,
                fee=fee,
                currency=currency,
                description=name,
                external_id=_field(fields, "Tranzakció azonosító"),
            )
        ]

    def _trade(self, fields: dict[str, str], currency: str | None) -> list[StandardTransaction]:
        side = _exact(fields, "Tranzakció")
        tx_type = SIDES.get(side.casefold())
        if tx_type is None:
            raise ValueError(f"Unknown trade type '{side}'")
        is_fund = fields["_kind"] == FUND_REPORT
        venue = _field(fields, "Kereskedési helyszín")
        # Funds carry the fee on the trade line, ETFs on the line below it.
        fee = _number(_exact(fields, "Költség") or _exact(fields, "_2:Költség"))
        currency = _field(fields, "Instrumentum devizaneme") or currency or ""
        amount = _number(_field(fields, "Összérték"))
        if amount is not None and currency == "HUF":
            amount = amount.quantize(Decimal(1), ROUND_HALF_UP)  # Erste settles forint trades in whole forints
        return [
            StandardTransaction(
                date=self._date(fields),
                type=tx_type,
                isin=_field(fields, "Instrumentum azonosító") or None,
                name=_field(fields, "Instrumentum neve") or None,
                asset_class=AssetClass.FUND if is_fund else None,
                exchange=venue.rsplit(" - ", 1)[-1][:32] if venue and venue != "OTC" else None,
                quantity=_number(_field(fields, "Mennyiség")),
                unit_price=_number(_field(fields, "Ár/")),
                amount=amount,
                fee=fee or Decimal(0),
                tax=_number(_field(fields, "Levont adó")) or Decimal(0),
                currency=currency,
                external_id=_field(fields, "Tranzakció azonosító"),
            )
        ]

    def _share_or_fx(self, fields: dict[str, str], currency: str | None) -> list[StandardTransaction]:
        if not _field(fields, "Terhelt devizanem"):
            return self._trade(fields, currency)
        # A currency exchange: one leg out of the debited currency, one into the credited one.
        date = self._date(fields)
        transaction_id = _field(fields, "Tranzakció azonosító")
        debited, credited = _field(fields, "Terhelt devizanem"), _field(fields, "Jóváírt devizanem")
        out = _number(_field(fields, "Terhelt deviza mennyiség"))
        into = _number(_field(fields, "Jóváírt deviza mennyiség"))
        if not (debited and credited and out and into):
            raise ValueError("Incomplete currency exchange")
        rate = _field(fields, "Árfolyam")
        description = f"FX {debited}.{credited}" + (f" @ {rate}" if rate else "")
        return [
            StandardTransaction(
                date=date,
                type=TransactionType.FX_CONVERSION,
                amount=-out,
                fee=_number(_exact(fields, "Költség")) or Decimal(0),
                currency=debited,
                description=description,
                external_id=transaction_id,
            ),
            StandardTransaction(
                date=date,
                type=TransactionType.FX_CONVERSION,
                amount=into,
                currency=credited,
                description=description,
                external_id=transaction_id,
            ),
        ]
