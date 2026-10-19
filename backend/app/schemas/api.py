"""Request/response models for accounts, users, imports and mappings."""

import datetime as dt
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import AccountType, AssetClass, ImportSource, ImportStatus, TransactionType
from app.parsers.base import AccountHint, RowError
from app.parsers.generic import ColumnMappingConfig, TablePreview
from app.schemas.standard import StandardTransaction, currency_code


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    base_currency: str


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    base_currency: str | None = None

    @field_validator("base_currency")
    @classmethod
    def _base(cls, value: str | None) -> str | None:
        return currency_code(value) if value else None


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    broker: str = Field(min_length=1, max_length=120)
    account_type: AccountType = AccountType.STANDARD
    tbsz_year: int | None = Field(default=None, ge=2000, le=2100)
    currency: str
    external_account_id: str | None = Field(default=None, max_length=64)
    track_cash: bool = True
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def _currency_code(cls, value: str) -> str:
        return currency_code(value)

    @model_validator(mode="after")
    def _tbsz(self) -> Self:
        if self.account_type is AccountType.TBSZ and self.tbsz_year is None:
            raise ValueError("A TBSZ account needs its vintage year (tbsz_year).")
        if self.account_type is not AccountType.TBSZ:
            self.tbsz_year = None
        return self


class AccountUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    broker: str | None = Field(default=None, min_length=1, max_length=120)
    account_type: AccountType | None = None
    tbsz_year: int | None = Field(default=None, ge=2000, le=2100)
    currency: str | None = None
    external_account_id: str | None = Field(default=None, max_length=64)
    track_cash: bool | None = None
    is_archived: bool | None = None
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def _currency_code(cls, value: str | None) -> str | None:
        return None if value is None else currency_code(value)

    @model_validator(mode="after")
    def _required_stay_set(self) -> Self:
        # Omitting a field leaves it alone; explicitly clearing a required one is an error.
        cleared = [
            name for name in REQUIRED_ACCOUNT_FIELDS if name in self.model_fields_set and getattr(self, name) is None
        ]
        if cleared:
            raise ValueError(f"{', '.join(cleared)} cannot be empty.")
        return self


REQUIRED_ACCOUNT_FIELDS = ("name", "broker", "account_type", "currency", "track_cash", "is_archived")


class TransactionOut(BaseModel):
    id: int
    account_id: int
    account_name: str
    date: dt.date
    type: TransactionType
    symbol: str | None
    name: str | None
    isin: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None
    fee: Decimal
    tax: Decimal
    currency: str
    description: str | None
    external_id: str | None
    import_log_id: int | None
    manual: bool = False  # entered by hand, not imported or synced


class TransactionPage(BaseModel):
    total: int
    items: list[TransactionOut]


class ManualTransactionsIn(BaseModel):
    """One transaction entered by hand, or both legs of a currency exchange."""

    account_id: int
    transactions: list[StandardTransaction] = Field(min_length=1, max_length=2)
    # Store it although an identical transaction is already recorded (the user confirmed a second one).
    allow_duplicate: bool = False


class ManualTransactionsResult(BaseModel):
    ids: list[int]


class TransactionEdit(BaseModel):
    account_id: int
    transaction: StandardTransaction


class AssetOption(BaseModel):
    id: int
    symbol: str
    name: str | None
    isin: str | None
    currency: str
    asset_class: AssetClass


class Detection(BaseModel):
    parser_key: str
    parser_label: str
    broker: str | None
    confidence: float


class MappingRef(BaseModel):
    id: int
    name: str


class PreviewTransaction(BaseModel):
    row: int | None
    duplicate: bool
    transaction: StandardTransaction
    group: str | None = None  # key into ImportPreview.groups when the import spans several accounts


class PreviewSummary(BaseModel):
    total: int
    new: int
    duplicates: int
    errors: int


class PreviewGroup(BaseModel):
    """Rows bound for one account: a sub-account of a statement (Erste TBSZ 2024) or one file format."""

    key: str
    label: str
    parser_key: str
    account_hint: AccountHint | None
    # The account these rows go into; None = not imported unless one is chosen.
    suggested_account_id: int | None
    summary: PreviewSummary


class SkippedFile(BaseModel):
    filename: str
    reason: str


class ImportPreview(BaseModel):
    status: Literal["parsed", "needs_mapping", "unsupported"]
    filename: str
    file_sha256: str
    file_kind: str
    message: str | None = None
    detection: Detection | None = None
    mapping_used: MappingRef | None = None
    table: TablePreview | None = None
    transactions: list[PreviewTransaction] = Field(default_factory=list)
    errors: list[RowError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: PreviewSummary = Field(default_factory=lambda: PreviewSummary(total=0, new=0, duplicates=0, errors=0))
    account_hint: AccountHint | None = None
    suggested_account_id: int | None = None
    file_count: int = 1
    groups: list[PreviewGroup] = Field(default_factory=list)  # set when rows go to several accounts
    skipped_files: list[SkippedFile] = Field(default_factory=list)


class ImportCommitRequest(BaseModel):
    account_id: int
    transactions: list[StandardTransaction] = Field(min_length=1, max_length=50_000)
    parser_key: str | None = Field(default=None, max_length=64)
    filename: str | None = Field(default=None, max_length=255)
    file_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ImportCommitResult(BaseModel):
    import_log_id: int
    received: int
    imported: int
    duplicates: int


class ImportLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int | None
    source: ImportSource
    status: ImportStatus
    parser_key: str | None
    filename: str | None
    rows_received: int
    rows_imported: int
    rows_duplicate: int
    message: str | None
    created_at: dt.datetime


class MappingIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    header_signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    config: ColumnMappingConfig


class MappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    header_signature: str
    config: ColumnMappingConfig
    created_at: dt.datetime
    updated_at: dt.datetime


class MarketRefreshResult(BaseModel):
    started: bool
    live_enabled: bool
    refreshing: bool
    last_refresh_at: dt.datetime | None
    last_refresh_error: str | None
