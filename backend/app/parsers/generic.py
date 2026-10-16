"""Tier 2: the Universal Column Mapper. Ingests any tabular statement from a JSON mapping config."""

import hashlib
import re
import unicodedata
from decimal import Decimal
from enum import StrEnum
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.enums import TransactionType
from app.parsers.base import BaseBrokerParser, ParsedRow, ParseResult, RawRecord, RawStatement, RowError
from app.parsers.source import SourceFile, Table
from app.parsers.text import (
    DateFormatError,
    DecimalSeparator,
    NumberFormatError,
    detect_date_format,
    detect_decimal_separator,
    looks_numeric,
    parse_date,
    parse_decimal,
)
from app.schemas.standard import StandardTransaction


class MappingField(StrEnum):
    DATE = "date"
    TYPE = "type"
    SYMBOL = "symbol"
    ISIN = "isin"
    NAME = "name"
    QUANTITY = "quantity"
    UNIT_PRICE = "unit_price"
    AMOUNT = "amount"
    FEE = "fee"
    TAX = "tax"
    CURRENCY = "currency"
    EXTERNAL_ID = "external_id"
    DESCRIPTION = "description"


MAX_DISTINCT_VALUES = 40
NUMERIC_FIELDS = (
    MappingField.QUANTITY,
    MappingField.UNIT_PRICE,
    MappingField.AMOUNT,
    MappingField.FEE,
    MappingField.TAX,
)


def normalize_label(value: str) -> str:
    """Case-, accent- and punctuation-insensitive form used to compare headers and type values."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9/]+", " ", stripped).split())


# English / German / Hungarian header synonyms. Order inside a tuple does not matter.
FIELD_ALIASES: dict[MappingField, tuple[str, ...]] = {
    MappingField.DATE: (
        "date",
        "trade date",
        "transaction date",
        "date/time",
        "datetime",
        "time",
        "completed date",
        "booking date",
        "execution date",
        "settlement date",
        "value date",
        "datum",
        "buchungsdatum",
        "handelsdatum",
        "schlusstag",
        "kotesnap",
        "kotes datuma",
        "kotes napja",
        "teljesites datuma",
        "konyveles datuma",
        "ertéknap",
        "ugylet datuma",
    ),
    MappingField.TYPE: (
        "type",
        "transaction type",
        "action",
        "side",
        "buy/sell",
        "operation",
        "activity",
        "direction",
        "order type",
        "typ",
        "transaktionstyp",
        "buchungsart",
        "tipus",
        "ugylet tipusa",
        "ugylettipus",
        "irany",
        "megbizas tipusa",
        "muvelet",
        "tranzakcio tipusa",
        "vetel/eladas",
    ),
    MappingField.SYMBOL: (
        "symbol",
        "ticker",
        "ticker symbol",
        "instrument code",
        "security code",
        "code",
        "tickersymbol",
        "papir kod",
        "kod",
        "tozsdei kod",
        "rovid nev",
    ),
    MappingField.ISIN: ("isin", "isin code", "isin kod", "isin number"),
    MappingField.NAME: (
        "name",
        "security",
        "security name",
        "instrument",
        "instrument name",
        "product",
        "asset",
        "asset name",
        "stock",
        "wertpapier",
        "bezeichnung",
        "ertekpapir",
        "ertekpapir neve",
        "megnevezes",
        "termek",
        "papir neve",
        "instrumentum",
    ),
    MappingField.QUANTITY: (
        "quantity",
        "qty",
        "shares",
        "units",
        "no of shares",
        "number of shares",
        "quantity/units",
        "stuck",
        "anzahl",
        "menge",
        "nominal",
        "mennyiseg",
        "darab",
        "darabszam",
        "db",
    ),
    MappingField.UNIT_PRICE: (
        "price",
        "price per share",
        "price/share",
        "unit price",
        "share price",
        "execution price",
        "t price",
        "trade price",
        "avg price",
        "kurs",
        "preis",
        "ausfuhrungskurs",
        "arfolyam",
        "ar",
        "egysegar",
        "kotesi arfolyam",
        "kotesi ar",
    ),
    MappingField.AMOUNT: (
        "amount",
        "total",
        "total amount",
        "gross amount",
        "value",
        "net amount",
        "proceeds",
        "cash amount",
        "trade value",
        "betrag",
        "gesamt",
        "kurswert",
        "osszeg",
        "ertek",
        "kotesi ertek",
        "brutto osszeg",
        "teljes osszeg",
    ),
    MappingField.FEE: (
        "fee",
        "fees",
        "commission",
        "comm/fee",
        "costs",
        "charges",
        "transaction fee",
        "gebuhr",
        "gebuhren",
        "provision",
        "jutalek",
        "dij",
        "koltseg",
        "kezelesi dij",
    ),
    MappingField.TAX: (
        "tax",
        "taxes",
        "withholding tax",
        "tax amount",
        "tax amt",
        "wht",
        "steuer",
        "quellensteuer",
        "ado",
        "forrasado",
        "levont ado",
    ),
    MappingField.CURRENCY: (
        "currency",
        "ccy",
        "curr",
        "currency code",
        "wahrung",
        "deviza",
        "penznem",
        "devizanem",
    ),
    MappingField.EXTERNAL_ID: (
        "id",
        "transaction id",
        "reference",
        "ref",
        "order id",
        "trade id",
        "reference number",
        "booking id",
        "referenz",
        "auftragsnummer",
        "azonosito",
        "megbizas szama",
        "megbizasszam",
        "hivatkozas",
        "tranzakcio azonosito",
        "ugyletszam",
    ),
    MappingField.DESCRIPTION: (
        "description",
        "details",
        "notes",
        "memo",
        "comment",
        "beschreibung",
        "verwendungszweck",
        "leiras",
        "megjegyzes",
        "kozlemeny",
    ),
}
_NORMALIZED_ALIASES = {
    field: tuple(dict.fromkeys(normalize_label(alias) for alias in aliases)) for field, aliases in FIELD_ALIASES.items()
}

TYPE_ALIASES: dict[TransactionType, tuple[str, ...]] = {
    TransactionType.BUY: (
        "buy",
        "bought",
        "purchase",
        "b",
        "market buy",
        "limit buy",
        "buy market",
        "buy limit",
        "savings plan",
        "sparplan",
        "kauf",
        "vetel",
        "vasarlas",
    ),
    TransactionType.SELL: (
        "sell",
        "sold",
        "sale",
        "s",
        "market sell",
        "limit sell",
        "sell market",
        "sell limit",
        "verkauf",
        "eladas",
    ),
    TransactionType.DIVIDEND: (
        "dividend",
        "dividends",
        "cash dividend",
        "distribution",
        "dividende",
        "ausschuttung",
        "osztalek",
        "hozamfizetes",
        "hozam",
    ),
    TransactionType.INTEREST: ("interest", "zinsen", "reward", "rewards", "cashback", "kamat", "kamatjovairas"),
    TransactionType.FEE: (
        "fee",
        "fees",
        "commission",
        "custody fee",
        "service fee",
        "gebuhr",
        "dij",
        "jutalek",
        "koltseg",
        "szamlavezetesi dij",
    ),
    TransactionType.TAX: ("tax", "withholding tax", "steuer", "ado", "forrasado"),
    TransactionType.DEPOSIT: (
        "deposit",
        "top up",
        "topup",
        "cash in",
        "card top up",
        "einzahlung",
        "befizetes",
        "penz befizetes",
        "jovairas",
    ),
    TransactionType.WITHDRAWAL: ("withdrawal", "withdraw", "cash out", "auszahlung", "kifizetes", "penzkivet"),
    TransactionType.FX_CONVERSION: (
        "exchange",
        "conversion",
        "fx",
        "currency exchange",
        "forex",
        "devizavaltas",
        "konverzio",
        "valtas",
    ),
    TransactionType.TRANSFER_IN: ("transfer in", "incoming transfer", "transfer_in", "security transfer in"),
    TransactionType.TRANSFER_OUT: ("transfer out", "outgoing transfer", "transfer_out", "security transfer out"),
}
_TYPE_LOOKUP = {normalize_label(alias): tx_type for tx_type, aliases in TYPE_ALIASES.items() for alias in aliases}
_TYPE_KEYWORDS: tuple[tuple[str, TransactionType], ...] = (
    ("withholding", TransactionType.TAX),
    ("dividend", TransactionType.DIVIDEND),
    ("osztalek", TransactionType.DIVIDEND),
    ("interest", TransactionType.INTEREST),
    ("kamat", TransactionType.INTEREST),
    ("commission", TransactionType.FEE),
    ("fee", TransactionType.FEE),
    ("tax", TransactionType.TAX),
    ("buy", TransactionType.BUY),
    ("vetel", TransactionType.BUY),
    ("sell", TransactionType.SELL),
    ("eladas", TransactionType.SELL),
    ("deposit", TransactionType.DEPOSIT),
    ("top up", TransactionType.DEPOSIT),
    ("withdraw", TransactionType.WITHDRAWAL),
    ("exchange", TransactionType.FX_CONVERSION),
    ("conversion", TransactionType.FX_CONVERSION),
)


def guess_transaction_type(raw: str) -> TransactionType | None:
    label = normalize_label(raw)
    if not label:
        return None
    if label in _TYPE_LOOKUP:
        return _TYPE_LOOKUP[label]
    padded = f" {label} "
    for keyword, tx_type in _TYPE_KEYWORDS:
        if f" {keyword} " in padded or label.startswith(keyword):
            return tx_type
    return None


def guess_columns(headers: list[str]) -> dict[MappingField, str]:
    """Best-effort header -> field assignment; each header and field is used at most once."""
    candidates: list[tuple[int, int, MappingField, str]] = []
    field_order = list(MappingField)
    for header in headers:
        label = normalize_label(header)
        if not label:
            continue
        for field, aliases in _NORMALIZED_ALIASES.items():
            score = 0
            for alias in aliases:
                if label == alias:
                    score = max(score, 100)
                elif re.search(rf"(^| ){re.escape(alias)}( |$)", label) and len(alias) >= 3:
                    score = max(score, 60 - min(len(label) - len(alias), 30))
            if score:
                candidates.append((score, -field_order.index(field), field, header))
    candidates.sort(reverse=True)
    assigned: dict[MappingField, str] = {}
    used: set[str] = set()
    for _score, _order, field, header in candidates:
        if field in assigned or header in used:
            continue
        assigned[field] = header
        used.add(header)
    return assigned


def header_signature(headers: list[str]) -> str:
    return hashlib.sha256("|".join(normalize_label(h) for h in headers).encode()).hexdigest()


class ColumnMappingConfig(BaseModel):
    """JSON-serializable mapping from a file's columns to StandardTransaction fields."""

    columns: dict[MappingField, str] = Field(default_factory=dict)
    header_row: int | None = Field(default=None, ge=0, description="0-based; None = auto-detect")
    delimiter: str | None = None
    encoding: str | None = None
    decimal_separator: DecimalSeparator | None = None
    date_format: str | None = Field(default=None, description="strptime format, 'ISO8601', or None = auto")
    type_map: dict[str, TransactionType] = Field(default_factory=dict, description="raw value -> type")
    default_type: TransactionType | None = None
    default_currency: str | None = None
    infer_type_from_sign: bool = True

    @field_validator("default_currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        return value.strip().upper() or None if value else None

    @field_validator("delimiter")
    @classmethod
    def _delimiter(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if value in ("\\t", "tab"):
            return "\t"
        if len(value) != 1:
            raise ValueError("delimiter must be a single character")
        return value

    def missing_requirements(self) -> list[str]:
        problems: list[str] = []
        if MappingField.DATE not in self.columns:
            problems.append("Map a date column.")
        if MappingField.CURRENCY not in self.columns and not self.default_currency:
            problems.append("Map a currency column or choose a default currency.")
        has_values = MappingField.AMOUNT in self.columns or (
            MappingField.QUANTITY in self.columns and MappingField.UNIT_PRICE in self.columns
        )
        if not has_values:
            problems.append("Map an amount column, or both quantity and unit price.")
        if (
            MappingField.TYPE not in self.columns
            and not self.default_type
            and not (self.infer_type_from_sign and MappingField.QUANTITY in self.columns)
        ):
            problems.append("Map a type column or choose a default transaction type.")
        return problems


class GenericCSVParser(BaseBrokerParser):
    """Applies a ColumnMappingConfig to any CSV / XLSX / XLS / HTML-table export."""

    key: ClassVar[str] = "generic_csv"
    label: ClassVar[str] = "Universal column mapper"

    def __init__(self, config: ColumnMappingConfig, *, key: str | None = None, label: str | None = None) -> None:
        self.config = config
        self.instance_key = key or self.key
        self.instance_label = label or self.label

    def detect(self, source: SourceFile) -> float:
        return 0.0  # Never auto-selected; chosen explicitly or through a saved preset's header signature.

    def table_for(self, source: SourceFile) -> Table:
        return source.table_with(delimiter=self.config.delimiter, encoding=self.config.encoding)

    def parse(self, source: SourceFile) -> RawStatement:
        table = self.table_for(source)
        headers = table.headers(self.config.header_row)
        records = [
            RawRecord(row=line, fields={h: (cells[i] if i < len(cells) else "") for i, h in enumerate(headers)})
            for line, cells in table.data_rows(self.config.header_row)
        ]
        return RawStatement(records=records, metadata={"typed_cells": "1" if table.typed_cells else ""})

    def normalize(self, statement: RawStatement) -> ParseResult:
        result = self._result()
        result.parser_key, result.parser_label = self.instance_key, self.instance_label
        problems = self.config.missing_requirements()
        if problems:
            result.errors.extend(RowError(message=problem) for problem in problems)
            return result

        columns = self.config.columns
        records = statement.records
        date_format = self.config.date_format or detect_date_format(
            r.fields.get(columns[MappingField.DATE], "") for r in records
        )
        separator: DecimalSeparator | None
        if statement.metadata.get("typed_cells"):
            separator = None
        else:
            separator = self.config.decimal_separator or detect_decimal_separator(
                r.fields.get(columns[f], "") for r in records for f in NUMERIC_FIELDS if f in columns
            )
        type_map = {normalize_label(raw): tx_type for raw, tx_type in self.config.type_map.items()}

        for record in records:
            try:
                transaction = self._normalize_record(record, date_format, separator, type_map)
            except (ValueError, ValidationError) as exc:
                result.errors.append(RowError(row=record.row, message=_error_message(exc), raw=record.fields))
                continue
            if transaction is not None:
                result.rows.append(ParsedRow(row=record.row, transaction=transaction))
        return result

    def _value(self, record: RawRecord, field: MappingField) -> str:
        header = self.config.columns.get(field)
        return record.fields.get(header, "").strip() if header else ""

    def _normalize_record(
        self,
        record: RawRecord,
        date_format: str | None,
        separator: DecimalSeparator | None,
        type_map: dict[str, TransactionType],
    ) -> StandardTransaction | None:
        if not any(value.strip() for value in record.fields.values()):
            return None
        raw_date = self._value(record, MappingField.DATE)
        if not raw_date:
            raise ValueError("Missing date")
        try:
            date = parse_date(raw_date, date_format)
        except DateFormatError as exc:
            raise ValueError(str(exc)) from exc
        if date is None:
            raise ValueError("Missing date")

        numbers: dict[MappingField, Decimal | None] = {}
        for field in NUMERIC_FIELDS:
            try:
                numbers[field] = parse_decimal(self._value(record, field), separator)
            except NumberFormatError as exc:
                raise ValueError(f"{field.value}: {exc}") from exc

        tx_type = self._resolve_type(record, numbers, type_map)
        currency = self._value(record, MappingField.CURRENCY) or self.config.default_currency or ""
        return StandardTransaction(
            date=date,
            type=tx_type,
            symbol=self._value(record, MappingField.SYMBOL) or None,
            isin=self._value(record, MappingField.ISIN) or None,
            name=self._value(record, MappingField.NAME) or None,
            quantity=numbers[MappingField.QUANTITY],
            unit_price=numbers[MappingField.UNIT_PRICE],
            amount=numbers[MappingField.AMOUNT],
            fee=numbers[MappingField.FEE] or Decimal(0),
            tax=numbers[MappingField.TAX] or Decimal(0),
            currency=currency,
            external_id=self._value(record, MappingField.EXTERNAL_ID) or None,
            description=self._value(record, MappingField.DESCRIPTION) or None,
        )

    def _resolve_type(
        self, record: RawRecord, numbers: dict[MappingField, Decimal | None], type_map: dict[str, TransactionType]
    ) -> TransactionType:
        quantity = numbers[MappingField.QUANTITY]
        resolved: TransactionType | None = None
        if MappingField.TYPE in self.config.columns:
            raw = self._value(record, MappingField.TYPE)
            resolved = type_map.get(normalize_label(raw)) or guess_transaction_type(raw)
            if resolved is None:
                raise ValueError(f"Unknown transaction type '{raw}' — map it in the column mapper")
        elif self.config.default_type:
            resolved = self.config.default_type
        elif self.config.infer_type_from_sign and quantity is not None and quantity != 0:
            resolved = TransactionType.BUY
        if resolved is None:
            raise ValueError("Cannot determine the transaction type")
        if (
            resolved is TransactionType.BUY
            and self.config.infer_type_from_sign
            and quantity is not None
            and quantity < 0
        ):
            return TransactionType.SELL
        return resolved


class TablePreview(BaseModel):
    kind: Literal["csv", "xlsx", "xls", "html"]
    headers: list[str]
    sample_rows: list[list[str]]
    header_row: int
    total_rows: int
    delimiter: str | None
    encoding: str | None
    sheet_name: str | None
    header_signature: str
    detected_decimal_separator: DecimalSeparator
    detected_date_format: str | None
    distinct_type_values: list[str]
    # Low-cardinality text columns -> their distinct values, so the UI can map types for any column.
    distinct_values: dict[str, list[str]]
    suggested: ColumnMappingConfig


def build_table_preview(table: Table, header_row: int | None = None, sample_size: int = 5) -> TablePreview:
    index = table.detect_header_row() if header_row is None else header_row
    headers = table.headers(index)
    data = table.data_rows(index)
    guessed = guess_columns(headers)

    def column_values(field: MappingField, limit: int | None = 500) -> list[str]:
        header = guessed.get(field)
        if header is None:
            return []
        position = headers.index(header)
        rows = data if limit is None else data[:limit]
        return [cells[position] for _, cells in rows if position < len(cells) and cells[position].strip()]

    numeric_cells = [cell for field in NUMERIC_FIELDS for cell in column_values(field) if looks_numeric(cell)] or [
        cell for _, cells in data[:200] for cell in cells if looks_numeric(cell)
    ]
    separator = detect_decimal_separator(numeric_cells)
    date_format = detect_date_format(column_values(MappingField.DATE))
    distinct_types = list(dict.fromkeys(v.strip() for v in column_values(MappingField.TYPE, limit=None)))[:60]
    type_map = {raw: tx_type for raw in distinct_types if (tx_type := guess_transaction_type(raw)) is not None}

    suggested = ColumnMappingConfig(
        columns=guessed,
        header_row=index,
        delimiter=table.delimiter,
        decimal_separator=None if table.typed_cells else separator,
        date_format=date_format,
        type_map=type_map,
    )
    width = len(headers)
    distinct_values: dict[str, list[str]] = {}
    for position, header in enumerate(headers):
        values = list(dict.fromkeys(cells[position].strip() for _, cells in data if position < len(cells)))
        values = [value for value in values if value]
        if 0 < len(values) <= MAX_DISTINCT_VALUES and not any(looks_numeric(value) for value in values):
            distinct_values[header] = values
    return TablePreview(
        kind=table.kind,
        headers=headers,
        sample_rows=[(cells + [""] * width)[:width] for _, cells in data[:sample_size]],
        header_row=index,
        total_rows=len(data),
        delimiter=table.delimiter,
        encoding=table.encoding,
        sheet_name=table.sheet_name,
        header_signature=header_signature(headers),
        detected_decimal_separator=separator,
        detected_date_format=date_format,
        distinct_type_values=distinct_types,
        distinct_values=distinct_values,
        suggested=suggested,
    )


def _error_message(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(str(error["msg"]).removeprefix("Value error, ") for error in exc.errors())
    return str(exc)
