"""GenericCSVParser: parses any tabular export given a JSON column mapping.

Example mapping::

    {
      "columns": {"trade_date": "Date", "type": "Action", "symbol": "Ticker",
                  "quantity": "Shares", "price": "Price", "amount": "Total",
                  "currency": "Currency"},
      "date_format": "%d.%m.%Y",
      "decimal_separator": ",",
      "type_map": {"Kauf": "buy", "Verkauf": "sell"}
    }
"""

import csv
import io
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.money import parse_decimal
from app.models.enums import Institution, TransactionType
from app.parsers.base import BaseBrokerParser, FileSample, ParsedTransaction, ParseResult, RowError
from app.parsers.csv_utils import (
    guess_date_format,
    guess_decimal_separator,
    normalise_header,
    parse_date,
    sniff_delimiter,
)
from app.parsers.normalize import AmountSign, build_transaction, guess_transaction_type

CanonicalField = Literal[
    "trade_date",
    "settle_date",
    "type",
    "symbol",
    "isin",
    "name",
    "quantity",
    "price",
    "amount",
    "fee",
    "currency",
    "description",
    "external_id",
]


class FieldSpec(BaseModel):
    key: CanonicalField
    label: str
    required: bool
    help: str


CANONICAL_FIELDS: list[FieldSpec] = [
    FieldSpec(key="trade_date", label="Trade date", required=True, help="When it happened"),
    FieldSpec(key="type", label="Type", required=True, help="Buy, sell, dividend, deposit…"),
    FieldSpec(key="symbol", label="Symbol / Ticker", required=False, help="e.g. VWCE, AAPL"),
    FieldSpec(key="isin", label="ISIN", required=False, help="12-character security ID"),
    FieldSpec(key="name", label="Security name", required=False, help="Human-readable name"),
    FieldSpec(key="quantity", label="Quantity", required=False, help="Units bought or sold"),
    FieldSpec(key="price", label="Price", required=False, help="Price per unit"),
    FieldSpec(
        key="amount",
        label="Amount",
        required=False,
        help="Net cash amount. Derived from quantity × price if omitted",
    ),
    FieldSpec(key="fee", label="Fee / Commission", required=False, help="Broker fees"),
    FieldSpec(key="currency", label="Currency", required=False, help="ISO code, e.g. EUR"),
    FieldSpec(key="description", label="Description", required=False, help="Free text"),
    FieldSpec(
        key="external_id",
        label="Reference / ID",
        required=False,
        help="Broker's unique ID, strengthens duplicate detection",
    ),
    FieldSpec(key="settle_date", label="Settlement date", required=False, help="Optional"),
]


class ColumnMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    columns: dict[CanonicalField, str] = Field(
        description="Canonical field -> header name in the file"
    )
    date_format: str | None = Field(
        default=None, description="strftime format; auto-detected per value when omitted"
    )
    decimal_separator: Literal[".", ","] = "."
    thousands_separator: Literal[",", ".", " ", "'"] | None = None
    delimiter: str | None = Field(default=None, max_length=1)
    type_map: dict[str, TransactionType] = Field(
        default_factory=dict, description="Raw type value (case-insensitive) -> transaction type"
    )
    default_currency: str | None = Field(default=None, min_length=3, max_length=3)
    amount_sign: AmountSign = "infer"

    @field_validator("columns")
    @classmethod
    def _non_empty_headers(cls, value: dict[CanonicalField, str]) -> dict[CanonicalField, str]:
        return {k: v for k, v in value.items() if v and v.strip()}

    @field_validator("default_currency")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @model_validator(mode="after")
    def _check_required(self) -> "ColumnMapping":
        missing = [f for f in ("trade_date", "type") if f not in self.columns]
        if "amount" not in self.columns and not {"quantity", "price"} <= self.columns.keys():
            missing.append("amount (or quantity + price)")
        if "currency" not in self.columns and not self.default_currency:
            missing.append("currency (or a default currency)")
        if missing:
            raise ValueError(f"Mapping is missing: {', '.join(missing)}")
        return self


class GenericCSVParser(BaseBrokerParser):
    key = "generic"
    label = "Custom CSV (column mapping)"
    institution = Institution.OTHER

    def __init__(self, mapping: ColumnMapping) -> None:
        self.mapping = mapping
        self._type_map = {k.strip().lower(): v for k, v in mapping.type_map.items()}

    @classmethod
    def detect(cls, sample: FileSample) -> float:
        # Generic never auto-claims a file; it is chosen explicitly with a mapping.
        return 0.0

    def parse(self, text: str) -> ParseResult:
        delimiter = self.mapping.delimiter or sniff_delimiter(text)
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        reader.fieldnames = headers
        result = ParseResult(parser_key=self.key, headers=headers)

        missing = sorted({h for h in self.mapping.columns.values() if h not in headers})
        if missing:
            result.errors.append(
                RowError(row_number=1, message=f"Columns not found in file: {', '.join(missing)}")
            )
            return result

        for line_no, row in enumerate(reader, start=2):
            cells = {k: (v or "") for k, v in row.items() if k is not None}
            if not any(v.strip() for v in cells.values()):
                continue
            result.rows_total += 1
            try:
                result.transactions.append(self._parse_row(line_no, cells))
            except (ValueError, ArithmeticError) as exc:
                result.errors.append(RowError(row_number=line_no, message=str(exc), raw=cells))
        return result

    # ------------------------------------------------------------------ helpers

    def _cell(self, row: dict[str, str], field: CanonicalField) -> str:
        header = self.mapping.columns.get(field)
        return row.get(header, "").strip() if header else ""

    def _decimal(self, row: dict[str, str], field: CanonicalField) -> Decimal | None:
        raw = self._cell(row, field)
        if not raw:
            return None
        try:
            return parse_decimal(
                raw, self.mapping.decimal_separator, self.mapping.thousands_separator
            )
        except ValueError as exc:
            raise ValueError(f"{field}: {exc}") from exc

    def _resolve_type(self, raw: str) -> TransactionType:
        if not raw:
            raise ValueError("type: empty")
        mapped = self._type_map.get(raw.lower())
        if mapped:
            return mapped
        guessed = guess_transaction_type(raw)
        if guessed is None:
            raise ValueError(f"type: don't know what {raw!r} means; add it to the type map")
        return guessed

    def _parse_row(self, line_no: int, row: dict[str, str]) -> ParsedTransaction:
        date_raw = self._cell(row, "trade_date")
        if not date_raw:
            raise ValueError("trade_date: empty")
        settle_raw = self._cell(row, "settle_date")
        return build_transaction(
            row_number=line_no,
            ttype=self._resolve_type(self._cell(row, "type")),
            trade_date=parse_date(date_raw, self.mapping.date_format),
            settle_date=parse_date(settle_raw, self.mapping.date_format) if settle_raw else None,
            currency=self._cell(row, "currency") or self.mapping.default_currency or "",
            amount=self._decimal(row, "amount"),
            quantity=self._decimal(row, "quantity"),
            price=self._decimal(row, "price"),
            fee=self._decimal(row, "fee"),
            amount_sign=self.mapping.amount_sign,
            symbol=self._cell(row, "symbol"),
            isin=self._cell(row, "isin"),
            asset_name=self._cell(row, "name"),
            description=self._cell(row, "description"),
            external_id=self._cell(row, "external_id"),
        )


# --------------------------------------------------------------------------
# Mapping suggestions (powers the "Universal Column Mapper" pre-fill)

FIELD_SYNONYMS: dict[CanonicalField, tuple[str, ...]] = {
    "trade_date": (
        "date",
        "trade date",
        "transaction date",
        "date time",
        "datum",
        "trade datum",
        "buchungsdatum",
        "datum ido",
        "kotesnap",
        "teljesites datuma",
        "tranzakcio datuma",
        "booking date",
        "executed at",
        "time",
    ),
    "settle_date": (
        "settle date",
        "settlement date",
        "value date",
        "valuta",
        "erteknap",
        "elszamolas napja",
    ),
    "type": (
        "type",
        "action",
        "transaction type",
        "activity",
        "side",
        "operation",
        "buy sell",
        "transaktionstyp",
        "art",
        "tipus",
        "megbizas tipusa",
        "ugylet tipusa",
        "muvelet",
    ),
    "symbol": ("symbol", "ticker", "instrument", "code", "kurzel", "ticker symbol", "termekkod"),
    "isin": ("isin", "isin code", "isin kod"),
    "name": (
        "name",
        "security",
        "security name",
        "instrument name",
        "product",
        "description of security",
        "wertpapier",
        "ertekpapir",
        "ertekpapir neve",
        "termek",
        "megnevezes",
    ),
    "quantity": (
        "quantity",
        "shares",
        "units",
        "qty",
        "anzahl",
        "stuck",
        "mennyiseg",
        "darab",
        "no of shares",
    ),
    "price": (
        "price",
        "price share",
        "unit price",
        "share price",
        "t price",
        "kurs",
        "preis",
        "arfolyam",
        "egysegar",
        "price per share",
    ),
    "amount": (
        "amount",
        "total",
        "net amount",
        "net amt",
        "value",
        "betrag",
        "osszeg",
        "netto osszeg",
        "total amount",
        "proceeds",
        "gross amount",
        "ertek",
    ),
    "fee": (
        "fee",
        "fees",
        "commission",
        "comm fee",
        "gebuhr",
        "provision",
        "jutalek",
        "dij",
        "kezelesi dij",
    ),
    "currency": ("currency", "ccy", "curr", "cur", "wahrung", "deviza", "penznem"),
    "description": (
        "description",
        "details",
        "notes",
        "comment",
        "beschreibung",
        "megjegyzes",
        "leiras",
        "kozlemeny",
    ),
    "external_id": (
        "id",
        "reference",
        "transaction id",
        "order id",
        "ref",
        "trade id",
        "referenz",
        "azonosito",
        "hivatkozas",
        "megbizas szama",
    ),
}

# Field order matters: specific fields claim their headers before broad ones.
_MATCH_ORDER: tuple[CanonicalField, ...] = (
    "isin",
    "settle_date",
    "trade_date",
    "currency",
    "fee",
    "quantity",
    "price",
    "type",
    "symbol",
    "external_id",
    "amount",
    "name",
    "description",
)


class MappingSuggestion(BaseModel):
    columns: dict[CanonicalField, str]
    date_format: str | None
    decimal_separator: Literal[".", ","]
    delimiter: str
    type_map: dict[str, TransactionType | None]
    is_complete: bool


def suggest_mapping(sample: FileSample) -> MappingSuggestion:
    normalised = {h: normalise_header(h) for h in sample.headers if h}
    claimed: set[str] = set()
    columns: dict[CanonicalField, str] = {}

    for exact in (True, False):
        for field in _MATCH_ORDER:
            if field in columns:
                continue
            for header, norm in normalised.items():
                if header in claimed:
                    continue
                synonyms = FIELD_SYNONYMS[field]
                hit = norm in synonyms if exact else any(len(s) > 3 and s in norm for s in synonyms)
                if hit:
                    columns[field] = header
                    claimed.add(header)
                    break

    def column_values(field: CanonicalField) -> list[str]:
        header = columns.get(field)
        if header is None or header not in sample.headers:
            return []
        idx = sample.headers.index(header)
        return [r[idx] for r in sample.rows if idx < len(r)]

    numeric_values = [v for f in ("amount", "price", "quantity") for v in column_values(f)]
    type_map = {
        raw.strip(): guess_transaction_type(raw)
        for raw in dict.fromkeys(column_values("type"))
        if raw.strip()
    }
    has_value = "amount" in columns or {"quantity", "price"} <= columns.keys()
    return MappingSuggestion(
        columns=columns,
        date_format=guess_date_format(column_values("trade_date")),
        decimal_separator=guess_decimal_separator(numeric_values),
        delimiter=sample.delimiter,
        type_map=type_map,
        is_complete="trade_date" in columns
        and "type" in columns
        and has_value
        and "currency" in columns
        and all(type_map.values()),
    )
