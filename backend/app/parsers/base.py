"""Universal ingestion pipeline: the contract every broker parser implements.

Pipeline::

    bytes ──decode──▶ text ──sample──▶ FileSample ──detect()──▶ parser
                                                       │
                     ParseResult ◀──parse(text)────────┘
    (ParsedTransaction rows + per-row errors, all values Decimal)

Parsers are pure: no DB access, no FX, no dedupe. The importer service takes a
:class:`ParseResult` and decides what to persist.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import ClassVar

from app.core.money import ZERO
from app.models.enums import AssetClass, Institution, TransactionType


@dataclass(frozen=True, slots=True)
class ParsedTransaction:
    row_number: int
    type: TransactionType
    trade_date: date
    amount: Decimal  # signed net cash impact in ``currency``, fees included
    currency: str
    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal = ZERO
    symbol: str | None = None
    isin: str | None = None
    asset_name: str | None = None
    asset_class: AssetClass | None = None
    description: str | None = None
    external_id: str | None = None
    settle_date: date | None = None

    @property
    def has_asset(self) -> bool:
        return bool(self.symbol or self.isin)


@dataclass(frozen=True, slots=True)
class RowError:
    row_number: int
    message: str
    raw: dict[str, str] | None = None


@dataclass(slots=True)
class ParseResult:
    parser_key: str
    headers: list[str]
    transactions: list[ParsedTransaction] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rows_total: int = 0


@dataclass(frozen=True, slots=True)
class FileSample:
    """What detectors get to look at: cheap to build, no full parse."""

    filename: str
    text: str
    delimiter: str
    headers: list[str]
    rows: list[list[str]]  # first N data rows (raw cells)

    @property
    def header_set(self) -> set[str]:
        return {h.strip().lower() for h in self.headers}


class BaseBrokerParser(ABC):
    """Base class for all broker statement parsers.

    Subclasses declare a unique ``key`` and implement :meth:`detect` (a
    confidence score in ``[0, 1]``) and :meth:`parse`.
    """

    key: ClassVar[str]
    label: ClassVar[str]
    institution: ClassVar[Institution]
    # True while a parser is built from documentation/guesswork rather than
    # verified against real exports. Surfaced in the UI as "beta".
    is_stub: ClassVar[bool] = False

    @classmethod
    @abstractmethod
    def detect(cls, sample: FileSample) -> float:
        """Return how confident this parser is that it understands ``sample``."""

    @abstractmethod
    def parse(self, text: str) -> ParseResult:
        """Parse the full decoded file."""
