"""Interactive Brokers: Activity Statement CSV and Flex Query XML (file upload or Flex Web Service)."""

import csv
import datetime as dt
import io
import re
from collections.abc import Callable
from decimal import Decimal
from functools import partial
from typing import ClassVar

from defusedxml import ElementTree
from pydantic import ValidationError

from app.enums import AssetClass, TransactionType
from app.parsers.base import (
    AccountHint,
    BaseBrokerParser,
    ParsedRow,
    ParseResult,
    RawRecord,
    RawStatement,
    RowError,
)
from app.parsers.source import SourceFile
from app.parsers.text import NumberFormatError, parse_date, parse_decimal
from app.schemas.standard import StandardTransaction

ZERO = Decimal(0)
Produced = StandardTransaction | list[StandardTransaction] | None
_DESCRIPTION_SECURITY = re.compile(r"^\s*([A-Za-z0-9.\-/ ]+?)\s*\(([A-Z]{2}[A-Z0-9]{9}[0-9])\)")

# IBKR listing exchange -> Yahoo Finance ticker suffix.
EXCHANGE_SUFFIX: dict[str, str] = {
    "EBS": ".SW",
    "SWX": ".SW",
    "VIRTX": ".SW",
    "IBIS": ".DE",
    "IBIS2": ".DE",
    "XETRA": ".DE",
    "FWB": ".F",
    "GETTEX": ".DE",
    "AEB": ".AS",
    "SBF": ".PA",
    "ENEXT.BE": ".BR",
    "BVME": ".MI",
    "BVME.ETF": ".MI",
    "LSE": ".L",
    "LSEETF": ".L",
    "BM": ".MC",
    "VSE": ".VI",
    "BUX": ".BD",
    "WSE": ".WA",
    "SFB": ".ST",
    "KFB": ".CO",
    "OSE": ".OL",
    "HEX": ".HE",
    "TSE": ".TO",
    "ASX": ".AX",
}


def yahoo_ticker(symbol: str, exchange: str | None) -> str | None:
    if not exchange:
        return None
    exchange = exchange.upper()
    if exchange in {"NASDAQ", "NYSE", "ARCA", "AMEX", "BATS", "IEX", "NYSEARCA", "PINK"}:
        return symbol.replace(" ", "-")
    suffix = EXCHANGE_SUFFIX.get(exchange)
    return f"{symbol.replace(' ', '-')}{suffix}" if suffix else None


def _num(raw: str | None) -> Decimal | None:
    # IBKR always writes "." decimals and "," thousands.
    return parse_decimal(raw, ".") if raw is not None else None


def _date(raw: str) -> dt.date:
    # "2024-01-05, 10:30:00" / "20240105;103000" -> date part only
    parsed = parse_date(re.split(r"[;,]", raw.strip(), maxsplit=1)[0].strip())
    if parsed is None:
        raise ValueError("Missing date")
    return parsed


def _security_from_description(description: str) -> tuple[str | None, str | None]:
    match = _DESCRIPTION_SECURITY.match(description)
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2)


class _Builder:
    """Collects transactions and row errors while normalizing, so one bad row never aborts a statement."""

    def __init__(self, result: ParseResult) -> None:
        self.result = result
        self._warned: set[str] = set()

    def add(self, row: int | None, raw: dict[str, str], factory: Callable[[], "Produced"]) -> None:
        try:
            produced = factory()
        except (ValueError, ValidationError, NumberFormatError) as exc:
            message = (
                "; ".join(str(e["msg"]).removeprefix("Value error, ") for e in exc.errors())
                if isinstance(exc, ValidationError)
                else str(exc)
            )
            self.result.errors.append(RowError(row=row, message=message, raw=raw))
            return
        if produced is None:
            return
        for transaction in [produced] if isinstance(produced, StandardTransaction) else produced:
            self.result.rows.append(ParsedRow(row=row, transaction=transaction))

    def warn_once(self, key: str, message: str) -> None:
        if key not in self._warned:
            self._warned.add(key)
            self.result.warnings.append(message)


def _trade(
    *,
    date: dt.date,
    symbol: str,
    currency: str,
    quantity: Decimal,
    price: Decimal | None,
    proceeds: Decimal | None,
    commission: Decimal | None,
    commission_currency: str | None,
    isin: str | None,
    name: str | None,
    asset_class: AssetClass,
    exchange: str | None,
    external_id: str | None,
) -> list[StandardTransaction]:
    tx_type = TransactionType.BUY if quantity > 0 else TransactionType.SELL
    fee = abs(commission or ZERO)
    separate_fee = fee and commission_currency and commission_currency.upper() != currency.upper()
    transactions = [
        StandardTransaction(
            date=date,
            type=tx_type,
            symbol=symbol,
            isin=isin,
            name=name,
            asset_class=asset_class,
            exchange=exchange,
            quantity=abs(quantity),
            unit_price=price,
            amount=abs(proceeds) if proceeds else None,
            fee=ZERO if separate_fee else fee,
            currency=currency,
            external_id=external_id,
        )
    ]
    if separate_fee and commission_currency:
        transactions.append(
            StandardTransaction(
                date=date,
                type=TransactionType.FEE,
                symbol=symbol,
                amount=fee,
                currency=commission_currency,
                external_id=f"{external_id}:fee" if external_id else None,
                description=f"Commission for {symbol}",
            )
        )
    return transactions


def _fx_legs(
    *,
    date: dt.date,
    pair: str,
    quote_currency: str,
    quantity: Decimal,
    proceeds: Decimal,
    commission: Decimal | None,
    commission_currency: str | None,
    external_id: str | None,
) -> list[StandardTransaction]:
    base_currency = pair.split(".", maxsplit=1)[0]
    when = date
    legs = [
        StandardTransaction(
            date=when,
            type=TransactionType.FX_CONVERSION,
            amount=quantity,
            currency=base_currency,
            external_id=f"{external_id}:{base_currency}" if external_id else None,
            description=f"FX {pair}",
        ),
        StandardTransaction(
            date=when,
            type=TransactionType.FX_CONVERSION,
            amount=proceeds,
            currency=quote_currency,
            external_id=f"{external_id}:{quote_currency}" if external_id else None,
            description=f"FX {pair}",
        ),
    ]
    if commission and commission_currency:
        legs.append(
            StandardTransaction(
                date=when,
                type=TransactionType.FEE,
                amount=abs(commission),
                currency=commission_currency,
                external_id=f"{external_id}:fee" if external_id else None,
                description=f"FX commission {pair}",
            )
        )
    return legs


def _cash(
    *,
    kind: str,
    date: dt.date,
    currency: str,
    amount: Decimal,
    description: str,
    external_id: str | None = None,
) -> StandardTransaction | None:
    """Map an IBKR cash activity (dividends, WHT, deposits, fees, interest) to a StandardTransaction."""
    symbol, isin = _security_from_description(description)
    kind = kind.lower()
    if "withholding" in kind:
        # A positive withholding line is a refund / reversal: book it as income.
        tx_type = TransactionType.TAX if amount < 0 else TransactionType.DIVIDEND
        if amount > 0:
            description = f"Withholding tax refund: {description}"
    elif "dividend" in kind:
        tx_type = TransactionType.DIVIDEND
    elif "deposit" in kind or "withdrawal" in kind:
        tx_type = TransactionType.DEPOSIT if amount > 0 else TransactionType.WITHDRAWAL
    elif "interest" in kind:
        tx_type = TransactionType.INTEREST
    elif "fee" in kind or "commission" in kind:
        tx_type = TransactionType.FEE if amount < 0 else TransactionType.INTEREST
        if amount > 0:
            description = f"Fee rebate: {description}"
    else:
        return None
    if amount == 0:
        return None
    return StandardTransaction(
        date=date,
        type=tx_type,
        symbol=symbol if tx_type in (TransactionType.DIVIDEND, TransactionType.TAX) else None,
        isin=isin if tx_type in (TransactionType.DIVIDEND, TransactionType.TAX) else None,
        amount=amount,
        currency=currency,
        external_id=external_id,
        description=description,
    )


def _asset_class(category: str, sub_type: str | None) -> AssetClass | None:
    category = category.upper()
    sub = (sub_type or "").upper()
    if "ETF" in sub or category == "ETF":
        return AssetClass.ETF
    if category in {"STOCKS", "STK"}:
        return AssetClass.STOCK
    if category in {"BONDS", "BOND"}:
        return AssetClass.BOND
    if category in {"MUTUAL FUNDS", "FUND"}:
        return AssetClass.FUND
    if category in {"CRYPTO", "CRYPTOCURRENCY"}:
        return AssetClass.CRYPTO
    return None


CASH_SECTIONS = {
    "Dividends": "dividend",
    "Payment In Lieu Of Dividends": "dividend",
    "Withholding Tax": "withholding",
    "Deposits & Withdrawals": "deposit",
    "Fees": "fee",
    "Interest": "interest",
}


class IBKRActivityCSVParser(BaseBrokerParser):
    key: ClassVar[str] = "ibkr_activity_csv"
    label: ClassVar[str] = "IBKR Activity Statement (CSV)"
    broker: ClassVar[str | None] = "Interactive Brokers"

    def detect(self, source: SourceFile) -> float:
        try:
            if source.kind != "csv":
                return 0.0
            head = source.text[:4000]
        except Exception:  # noqa: BLE001 - detection must never raise
            return 0.0
        if head.lstrip().startswith("Statement,Header,Field Name,Field Value"):
            return 0.99
        if re.search(r"^Trades,Header,DataDiscriminator", head, re.MULTILINE):
            return 0.9
        return 0.0

    def parse(self, source: SourceFile) -> RawStatement:
        headers: dict[str, list[str]] = {}
        records: list[RawRecord] = []
        metadata: dict[str, str] = {}
        for line, row in enumerate(csv.reader(io.StringIO(source.text)), start=1):
            if len(row) < 3:
                continue
            section, row_type, values = row[0].strip(), row[1].strip(), row[2:]
            if row_type == "Header":
                headers[section] = [value.strip() for value in values]
                continue
            if row_type != "Data" or section not in headers:
                continue
            fields = dict(zip(headers[section], values, strict=False))
            if section == "Account Information":
                metadata[fields.get("Field Name", "")] = fields.get("Field Value", "")
            records.append(RawRecord(row=line, fields=fields, section=section))
        return RawStatement(records=records, metadata=metadata)

    def normalize(self, statement: RawStatement) -> ParseResult:
        result = self._result()
        builder = _Builder(result)
        instruments = {
            record.fields.get("Symbol", "").strip(): record.fields
            for record in statement.records
            if record.section == "Financial Instrument Information"
        }
        for record in statement.records:
            fields = record.fields
            if record.section == "Trades":
                factory = self._trade_factory(fields, instruments, builder)
                if factory is not None:
                    builder.add(record.row, fields, factory)
            elif record.section in CASH_SECTIONS:
                currency = fields.get("Currency", "")
                if not currency or currency.startswith("Total"):
                    continue
                builder.add(record.row, fields, partial(self._cash_row, fields, CASH_SECTIONS[record.section]))

        result.account_hint = AccountHint(
            broker=self.broker,
            external_account_id=statement.metadata.get("Account") or None,
            currency=statement.metadata.get("Base Currency") or None,
        )
        return result

    @staticmethod
    def _cash_row(fields: dict[str, str], kind: str) -> Produced:
        amount = _num(fields.get("Amount"))
        if amount is None:
            raise ValueError("Missing amount")
        return _cash(
            kind=kind,
            date=_date(fields.get("Date") or fields.get("Settle Date") or ""),
            currency=fields["Currency"],
            amount=amount,
            description=fields.get("Description", ""),
        )

    def _trade_factory(
        self, fields: dict[str, str], instruments: dict[str, dict[str, str]], builder: _Builder
    ) -> Callable[[], Produced] | None:
        if fields.get("DataDiscriminator", "Order") not in {"Order", "Trade", "Execution"}:
            return None
        category = fields.get("Asset Category", "")
        symbol = fields.get("Symbol", "").strip()
        commission_key = next((key for key in fields if key.startswith("Comm")), None)
        # Forex sections report "Comm in <base currency>"; stock sections report "Comm/Fee" in trade currency.
        commission_currency = (
            commission_key.removeprefix("Comm in ").strip()
            if commission_key and commission_key.startswith("Comm in ")
            else None
        )

        if category == "Forex":

            def forex() -> Produced:
                quantity, proceeds = _num(fields.get("Quantity")), _num(fields.get("Proceeds"))
                if quantity is None or proceeds is None:
                    raise ValueError("Forex trade without quantity or proceeds")
                return _fx_legs(
                    date=_date(fields.get("Date/Time", "")),
                    pair=symbol,
                    quote_currency=fields.get("Currency", ""),
                    quantity=quantity,
                    proceeds=proceeds,
                    commission=_num(fields.get(commission_key)) if commission_key else None,
                    commission_currency=commission_currency or fields.get("Currency"),
                    external_id=None,
                )

            return forex

        instrument = instruments.get(symbol, {})
        asset_class = _asset_class(category, instrument.get("Type"))
        if asset_class is None:
            builder.warn_once(f"cat:{category}", f"Skipped '{category}' trades — not supported yet.")
            return None

        def trade() -> Produced:
            quantity = _num(fields.get("Quantity"))
            if not quantity:
                raise ValueError("Trade without quantity")
            return _trade(
                date=_date(fields.get("Date/Time", "")),
                symbol=symbol,
                currency=fields.get("Currency", ""),
                quantity=quantity,
                price=_num(fields.get("T. Price")),
                proceeds=_num(fields.get("Proceeds")),
                commission=_num(fields.get(commission_key)) if commission_key else None,
                commission_currency=commission_currency,
                isin=instrument.get("Security ID") or None,
                name=instrument.get("Description") or None,
                asset_class=asset_class,
                exchange=instrument.get("Listing Exch") or None,
                external_id=None,
            )

        return trade


FLEX_CASH_LEVELS = {"", "DETAIL"}
FLEX_TRADE_LEVELS = {"", "EXECUTION"}


class IBKRFlexXMLParser(BaseBrokerParser):
    key: ClassVar[str] = "ibkr_flex_xml"
    label: ClassVar[str] = "IBKR Flex Query (XML)"
    broker: ClassVar[str | None] = "Interactive Brokers"

    def detect(self, source: SourceFile) -> float:
        try:
            if source.kind != "xml":
                return 0.0
            return 0.99 if "<FlexQueryResponse" in source.text[:4000] else 0.0
        except Exception:  # noqa: BLE001 - detection must never raise
            return 0.0

    def parse(self, source: SourceFile) -> RawStatement:
        """Every account in the file as one statement (a manual upload goes into the one account picked)."""
        merged = RawStatement(records=[], metadata={})
        for statement in self._statements(source).values():
            merged.records.extend(statement.records)
            for key, value in statement.metadata.items():
                merged.metadata.setdefault(key, value)
        return merged

    def run_per_account(self, source: SourceFile) -> dict[str, ParseResult]:
        """One result per IBKR account number, so an API sync can route each to its own Jacklyn account."""
        return {account: self.normalize(statement) for account, statement in self._statements(source).items()}

    @staticmethod
    def _statements(source: SourceFile) -> dict[str, RawStatement]:
        root = ElementTree.fromstring(source.text.encode("utf-8"))
        statements: dict[str, RawStatement] = {}
        for node in root.iter("FlexStatement"):
            account = node.get("accountId", "")
            statement = statements.setdefault(account, RawStatement(records=[], metadata={"accountId": account}))
            info = node.find("AccountInformation")
            if info is not None and info.get("currency"):
                statement.metadata.setdefault("currency", info.get("currency", ""))
            for trade in node.iter("Trade"):
                if trade.get("levelOfDetail", "") in FLEX_TRADE_LEVELS:
                    statement.records.append(RawRecord(row=None, fields=dict(trade.attrib), section="Trade"))
            for cash in node.iter("CashTransaction"):
                if cash.get("levelOfDetail", "") in FLEX_CASH_LEVELS:
                    statement.records.append(RawRecord(row=None, fields=dict(cash.attrib), section="CashTransaction"))
        return statements

    def normalize(self, statement: RawStatement) -> ParseResult:
        result = self._result()
        builder = _Builder(result)
        for record in statement.records:
            if record.section == "Trade":
                factory = self._trade_factory(record.fields, builder)
                if factory is not None:
                    builder.add(None, record.fields, factory)
            elif record.section == "CashTransaction":
                builder.add(None, record.fields, partial(self._cash_row, record.fields))

        result.account_hint = AccountHint(
            broker=self.broker,
            external_account_id=statement.metadata.get("accountId") or None,
            currency=statement.metadata.get("currency") or None,
        )
        return result

    @staticmethod
    def _cash_row(fields: dict[str, str]) -> Produced:
        amount = _num(fields.get("amount"))
        if amount is None:
            raise ValueError("Missing amount")
        transaction_id = fields.get("transactionID") or fields.get("actionID")
        return _cash(
            kind=fields.get("type", ""),
            date=_date(fields.get("dateTime") or fields.get("settleDate") or fields.get("reportDate") or ""),
            currency=fields.get("currency", ""),
            amount=amount,
            description=fields.get("description", ""),
            external_id=f"C{transaction_id}" if transaction_id else None,
        )

    def _trade_factory(self, fields: dict[str, str], builder: _Builder) -> Callable[[], Produced] | None:
        category = fields.get("assetCategory", "")
        symbol = fields.get("symbol", "").strip()
        trade_id = fields.get("tradeID") or fields.get("transactionID")
        external_id = f"T{trade_id}" if trade_id else None
        raw_date = fields.get("tradeDate") or fields.get("dateTime") or ""

        if category == "CASH":

            def forex() -> Produced:
                quantity, proceeds = _num(fields.get("quantity")), _num(fields.get("proceeds"))
                if quantity is None or proceeds is None:
                    raise ValueError("Forex trade without quantity or proceeds")
                return _fx_legs(
                    date=_date(raw_date),
                    pair=symbol,
                    quote_currency=fields.get("currency", ""),
                    quantity=quantity,
                    proceeds=proceeds,
                    commission=_num(fields.get("ibCommission")),
                    commission_currency=fields.get("ibCommissionCurrency") or fields.get("currency"),
                    external_id=external_id,
                )

            return forex

        asset_class = _asset_class(category, fields.get("subCategory"))
        if asset_class is None:
            builder.warn_once(f"cat:{category}", f"Skipped '{category}' trades — not supported yet.")
            return None
        isin = fields.get("isin") or (
            fields.get("securityID") if fields.get("securityIDType", "").upper() == "ISIN" else None
        )

        def trade() -> Produced:
            quantity = _num(fields.get("quantity"))
            if not quantity:
                raise ValueError("Trade without quantity")
            return _trade(
                date=_date(raw_date),
                symbol=symbol,
                currency=fields.get("currency", ""),
                quantity=quantity,
                price=_num(fields.get("tradePrice")),
                proceeds=_num(fields.get("proceeds")),
                commission=_num(fields.get("ibCommission")),
                commission_currency=fields.get("ibCommissionCurrency"),
                isin=isin or None,
                name=fields.get("description") or None,
                asset_class=asset_class,
                exchange=fields.get("listingExchange") or None,
                external_id=external_id,
            )

        return trade
