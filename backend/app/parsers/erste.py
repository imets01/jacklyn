"""Erste NetBroker (Hungary) transaction export.

NetBroker exports are semicolon-separated, Windows-1250 or UTF-8, with
Hungarian headers, comma decimals and ``YYYY.MM.DD.`` dates, e.g.::

    Dátum;Megbízás típusa;Értékpapír;ISIN;Mennyiség;Árfolyam;Összeg;Deviza;Jutalék

The exact column set differs between NetBroker report types, so instead of a
fixed mapping this parser resolves columns from Hungarian synonyms at parse
time. Stub until verified against real exports.
"""

from app.models.enums import Institution, TransactionType
from app.parsers.base import BaseBrokerParser, FileSample, ParseResult, RowError
from app.parsers.csv_utils import build_sample, normalise_header
from app.parsers.generic_csv import ColumnMapping, GenericCSVParser, suggest_mapping

_HUNGARIAN_MARKERS = {
    "datum",
    "ertekpapir",
    "ertekpapir neve",
    "mennyiseg",
    "arfolyam",
    "osszeg",
    "deviza",
    "jutalek",
    "megbizas tipusa",
    "ugylet tipusa",
    "kotesnap",
}

ERSTE_TYPE_MAP: dict[str, TransactionType] = {
    "Vétel": TransactionType.BUY,
    "Eladás": TransactionType.SELL,
    "Osztalék": TransactionType.DIVIDEND,
    "Hozamfizetés": TransactionType.DIVIDEND,
    "Kamat": TransactionType.INTEREST,
    "Befizetés": TransactionType.DEPOSIT,
    "Jóváírás": TransactionType.DEPOSIT,
    "Kifizetés": TransactionType.WITHDRAWAL,
    "Kivét": TransactionType.WITHDRAWAL,
    "Jutalék": TransactionType.FEE,
    "Díj": TransactionType.FEE,
    "Adó": TransactionType.TAX,
    "Devizaváltás": TransactionType.FX,
}


class ErsteNetBrokerParser(BaseBrokerParser):
    key = "erste"
    label = "Erste NetBroker – Transactions"
    institution = Institution.ERSTE
    is_stub = True

    @classmethod
    def detect(cls, sample: FileSample) -> float:
        markers = {normalise_header(h) for h in sample.headers} & _HUNGARIAN_MARKERS
        name = sample.filename.lower()
        if len(markers) >= 4:
            return 0.9 if sample.delimiter == ";" else 0.75
        if ("netbroker" in name or "erste" in name) and len(markers) >= 2:
            return 0.7
        return 0.0

    def parse(self, text: str) -> ParseResult:
        sample = build_sample("erste.csv", text)
        suggestion = suggest_mapping(sample)
        try:
            mapping = ColumnMapping(
                columns=suggestion.columns,
                date_format=suggestion.date_format,
                decimal_separator=suggestion.decimal_separator,
                thousands_separator=" " if suggestion.decimal_separator == "," else None,
                delimiter=sample.delimiter,
                type_map=ERSTE_TYPE_MAP,
                default_currency="HUF",
            )
        except ValueError as exc:
            return ParseResult(
                parser_key=self.key,
                headers=sample.headers,
                errors=[RowError(row_number=1, message=f"Unrecognised NetBroker layout: {exc}")],
            )
        result = GenericCSVParser(mapping).parse(text)
        result.parser_key = self.key
        return result
