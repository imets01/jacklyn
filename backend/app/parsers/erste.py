"""Erste Bank Hungary — NetBroker securities transaction export (CSV / XLS / XLSX).

Hungarian exports arrive in Windows-1250 or UTF-8, semicolon-delimited, with comma decimals
and dates like `2024.03.15.`. Encoding, delimiter and date format are auto-detected; the
column aliases cover the Hungarian header variants seen in NetBroker exports.
"""

from typing import ClassVar

from app.enums import TransactionType
from app.parsers.base import AccountHint, ParseResult, RawStatement
from app.parsers.generic import MappingField
from app.parsers.presets import PresetTableParser


class ErsteNetBrokerParser(PresetTableParser):
    key: ClassVar[str] = "erste_netbroker"
    label: ClassVar[str] = "Erste NetBroker export"
    broker: ClassVar[str | None] = "Erste Bank"

    brand_hints: ClassVar[tuple[str, ...]] = ("erste", "netbroker", "george")
    column_aliases: ClassVar[dict[MappingField, tuple[str, ...]]] = {
        MappingField.DATE: ("Kötésnap", "Kötés dátuma", "Kötés napja", "Teljesítés dátuma", "Dátum"),
        MappingField.TYPE: ("Ügylet típusa", "Ügylettípus", "Irány", "Vétel/Eladás", "Megbízás típusa", "Típus"),
        MappingField.SYMBOL: ("Tőzsdei kód", "Papír kód", "Kód", "Ticker"),
        MappingField.ISIN: ("ISIN", "ISIN kód"),
        MappingField.NAME: ("Értékpapír neve", "Értékpapír", "Megnevezés", "Papír neve", "Instrumentum"),
        MappingField.QUANTITY: ("Mennyiség", "Darabszám", "Darab", "Db"),
        MappingField.UNIT_PRICE: ("Árfolyam", "Kötési árfolyam", "Egységár", "Ár"),
        MappingField.AMOUNT: ("Kötési érték", "Érték", "Összeg", "Bruttó összeg"),
        MappingField.FEE: ("Jutalék", "Díj", "Költség"),
        MappingField.TAX: ("Adó", "Forrásadó", "Levont adó"),
        MappingField.CURRENCY: ("Deviza", "Devizanem", "Pénznem"),
        MappingField.EXTERNAL_ID: ("Megbízás száma", "Megbízásszám", "Ügyletszám", "Azonosító"),
        MappingField.DESCRIPTION: ("Megjegyzés", "Közlemény", "Leírás"),
    }
    required_fields: ClassVar[frozenset[MappingField]] = frozenset(
        {MappingField.DATE, MappingField.QUANTITY, MappingField.UNIT_PRICE}
    )
    decimal_separator = ","
    default_currency = "HUF"
    type_map: ClassVar[dict[str, TransactionType]] = {
        "Vétel": TransactionType.BUY,
        "Vásárlás": TransactionType.BUY,
        "Eladás": TransactionType.SELL,
        "Osztalék": TransactionType.DIVIDEND,
        "Hozamfizetés": TransactionType.DIVIDEND,
        "Kamat": TransactionType.INTEREST,
        "Befizetés": TransactionType.DEPOSIT,
        "Kifizetés": TransactionType.WITHDRAWAL,
        "Jutalék": TransactionType.FEE,
        "Díj": TransactionType.FEE,
        "Adó": TransactionType.TAX,
        "Átvezetés be": TransactionType.TRANSFER_IN,
        "Átvezetés ki": TransactionType.TRANSFER_OUT,
    }

    def normalize(self, statement: RawStatement) -> ParseResult:
        result = super().normalize(statement)
        result.account_hint = AccountHint(broker=self.broker, currency="HUF")
        return result
