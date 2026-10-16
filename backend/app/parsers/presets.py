"""Tier-1 presets for tabular exports, declared as column aliases on top of the Universal Column Mapper."""

from typing import ClassVar

from app.enums import TransactionType
from app.parsers.base import BaseBrokerParser, ParseResult, RawStatement
from app.parsers.generic import ColumnMappingConfig, GenericCSVParser, MappingField, normalize_label
from app.parsers.source import SourceFile, Table
from app.parsers.text import DecimalSeparator

TABULAR_KINDS = frozenset({"csv", "xlsx", "xls", "html"})


class PresetTableParser(BaseBrokerParser):
    column_aliases: ClassVar[dict[MappingField, tuple[str, ...]]]
    required_fields: ClassVar[frozenset[MappingField]]
    # Headers that, all present together, identify the export unambiguously.
    signature_headers: ClassVar[tuple[str, ...]] = ()
    brand_hints: ClassVar[tuple[str, ...]] = ()
    base_confidence: ClassVar[float] = 0.7
    type_map: ClassVar[dict[str, TransactionType]] = {}
    date_format: ClassVar[str | None] = None
    decimal_separator: ClassVar[DecimalSeparator | None] = None
    default_currency: ClassVar[str | None] = None

    def resolve_columns(self, headers: list[str]) -> dict[MappingField, str]:
        by_label = {normalize_label(header): header for header in headers}
        resolved: dict[MappingField, str] = {}
        for field, aliases in self.column_aliases.items():
            for alias in aliases:
                header = by_label.get(normalize_label(alias))
                if header is not None:
                    resolved[field] = header
                    break
        return resolved

    def config_for(self, table: Table) -> ColumnMappingConfig:
        header_row = table.detect_header_row()
        return ColumnMappingConfig(
            columns=self.resolve_columns(table.headers(header_row)),
            header_row=header_row,
            delimiter=table.delimiter,
            decimal_separator=self.decimal_separator,
            date_format=self.date_format,
            type_map=self.type_map,
            default_currency=self.default_currency,
        )

    def detect(self, source: SourceFile) -> float:
        try:
            if source.kind not in TABULAR_KINDS:
                return 0.0
            table = source.table
            headers = table.headers()
        except Exception:  # noqa: BLE001 - detection must never raise
            return 0.0
        labels = {normalize_label(header) for header in headers}
        if self.signature_headers and all(normalize_label(h) in labels for h in self.signature_headers):
            return 0.97
        if not self.required_fields.issubset(self.resolve_columns(headers)):
            return 0.0
        preamble = " ".join(" ".join(row) for row in table.rows[: table.detect_header_row()])
        haystack = normalize_label(f"{source.filename} {preamble}")
        branded = any(hint in haystack for hint in self.brand_hints)
        return min(0.95, self.base_confidence + (0.2 if branded else 0.0))

    def parse(self, source: SourceFile) -> RawStatement:
        config = self.config_for(source.table)
        statement = GenericCSVParser(config).parse(source)
        statement.metadata["config"] = config.model_dump_json()
        return statement

    def normalize(self, statement: RawStatement) -> ParseResult:
        config = ColumnMappingConfig.model_validate_json(statement.metadata["config"])
        result = GenericCSVParser(config, key=self.key, label=self.label).normalize(statement)
        result.broker = self.broker
        return result
