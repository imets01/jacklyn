"""The shared contract every broker parser implements: detect() -> parse() -> normalize()."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from pydantic import BaseModel, Field

from app.parsers.source import SourceFile
from app.schemas.standard import StandardTransaction


@dataclass
class RawRecord:
    """One source row before normalization. `section` distinguishes multi-table statements (IBKR)."""

    row: int | None
    fields: dict[str, str]
    section: str | None = None


@dataclass
class RawStatement:
    records: list[RawRecord]
    metadata: dict[str, str] = field(default_factory=dict)


class RowError(BaseModel):
    row: int | None = None
    message: str
    raw: dict[str, str] | None = None


class ParsedRow(BaseModel):
    row: int | None = None
    transaction: StandardTransaction


class AccountHint(BaseModel):
    broker: str | None = None
    external_account_id: str | None = None
    currency: str | None = None


class ParseResult(BaseModel):
    parser_key: str
    parser_label: str
    broker: str | None = None
    rows: list[ParsedRow] = Field(default_factory=list)
    errors: list[RowError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    account_hint: AccountHint | None = None

    @property
    def transactions(self) -> list[StandardTransaction]:
        return [parsed.transaction for parsed in self.rows]


class BaseBrokerParser(ABC):
    """Tier-1 preset parser. Implementations must be stateless so one instance can serve every request."""

    key: ClassVar[str]
    label: ClassVar[str]
    broker: ClassVar[str | None] = None

    @abstractmethod
    def detect(self, source: SourceFile) -> float:
        """Confidence in [0, 1] that this parser understands `source`. Must never raise."""

    @abstractmethod
    def parse(self, source: SourceFile) -> RawStatement:
        """Extract raw records from the file without interpreting them."""

    @abstractmethod
    def normalize(self, statement: RawStatement) -> ParseResult:
        """Turn raw records into StandardTransactions, collecting per-row errors instead of failing."""

    def run(self, source: SourceFile) -> ParseResult:
        return self.normalize(self.parse(source))

    def _result(self) -> ParseResult:
        return ParseResult(parser_key=self.key, parser_label=self.label, broker=self.broker)
