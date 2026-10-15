"""API request/response models.

Decimals serialize as JSON *strings* (Pydantic v2 default) so no precision is
lost on the wire; the frontend only converts to numbers for display/charts.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.models.enums import AccountType, AssetClass, ImportStatus, Institution, TransactionType
from app.parsers.generic_csv import FieldSpec, MappingSuggestion
from app.services.tbsz import TbszPhase


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


CurrencyCode = Annotated[str, BeforeValidator(_upper), StringConstraints(pattern=r"^[A-Z]{3}$")]
BaseCurrency = Literal["CHF", "EUR", "HUF", "USD"]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------- users


class UserOut(ApiModel):
    id: int
    email: str
    display_name: str
    base_currency: str


# ---------------------------------------------------------------- accounts


class TbszOut(ApiModel):
    year: int
    phase: TbszPhase
    reduced_tax_date: date
    maturity_date: date
    days_to_maturity: int
    progress: float


class AccountBase(ApiModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    institution: Institution
    account_type: AccountType = AccountType.STANDARD
    tbsz_year: int | None = Field(default=None, ge=1995, le=2100)
    base_currency: CurrencyCode
    account_number: str | None = Field(default=None, max_length=64)


class AccountCreate(AccountBase):
    @model_validator(mode="after")
    def _tbsz_year_matches_type(self) -> Self:
        if self.account_type is AccountType.TBSZ and self.tbsz_year is None:
            raise ValueError("TBSZ accounts need a tbsz_year (the collection year)")
        if self.account_type is not AccountType.TBSZ and self.tbsz_year is not None:
            raise ValueError("tbsz_year is only valid for TBSZ accounts")
        return self


class AccountUpdate(ApiModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
        | None
    ) = None
    account_number: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


class AccountOut(AccountBase):
    id: int
    is_active: bool
    created_at: datetime
    tbsz: TbszOut | None = None
    transaction_count: int = 0


# --------------------------------------------------------------- portfolio


class BucketOut(ApiModel):
    key: str
    label: str
    value: Decimal
    weight: Decimal


class HoldingOut(ApiModel):
    asset_id: int
    symbol: str
    name: str
    isin: str | None
    asset_class: AssetClass
    currency: str
    quantity: Decimal
    price: Decimal | None
    value: Decimal
    cost: Decimal
    unrealized_gain: Decimal
    weight: Decimal


class AccountSummaryOut(ApiModel):
    account: AccountOut
    value: Decimal
    invested: Decimal
    cash: Decimal
    net_contributions: Decimal
    gain: Decimal
    value_in_account_currency: Decimal
    holdings_count: int
    cash_by_currency: dict[str, Decimal]
    weight: Decimal


class PortfolioSummaryOut(ApiModel):
    base_currency: str
    as_of: date
    net_worth: Decimal
    invested: Decimal
    cash: Decimal
    net_contributions: Decimal
    total_gain: Decimal
    total_gain_pct: Decimal
    allocation: dict[Literal["asset_class", "currency", "account"], list[BucketOut]]
    accounts: list[AccountSummaryOut]
    holdings: list[HoldingOut]
    fx_rates: dict[str, Decimal]
    fx_source: str
    warnings: list[str]


class PerformancePointOut(ApiModel):
    date: date
    value: Decimal
    net_contributions: Decimal


class PerformanceOut(ApiModel):
    base_currency: str
    range: str
    points: list[PerformancePointOut]
    start_value: Decimal
    end_value: Decimal
    change: Decimal
    gain: Decimal
    gain_pct: Decimal


# ------------------------------------------------------------------ import


class ParserInfo(ApiModel):
    key: str
    label: str
    institution: Institution
    is_stub: bool


class ImportOptionsOut(ApiModel):
    parsers: list[ParserInfo]
    fields: list[FieldSpec]
    transaction_types: list[TransactionType]
    max_upload_bytes: int


class PreviewRowOut(ApiModel):
    row_number: int
    status: Literal["new", "duplicate", "error"]
    message: str | None = None
    type: TransactionType | None = None
    trade_date: date | None = None
    symbol: str | None = None
    isin: str | None = None
    name: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    amount: Decimal | None = None
    fee: Decimal | None = None
    currency: str | None = None
    description: str | None = None


class PreviewCounts(ApiModel):
    total: int
    new: int
    duplicate: int
    error: int


class ImportPreviewOut(ApiModel):
    filename: str
    file_sha256: str
    account_id: int
    parser_key: str | None
    parser_label: str | None
    confidence: float
    is_stub: bool
    mapping_id: int | None
    needs_mapping: bool
    headers: list[str]
    sample_rows: list[list[str]]
    suggestion: MappingSuggestion | None
    counts: PreviewCounts
    rows: list[PreviewRowOut]
    rows_truncated: bool
    warnings: list[str]


class ImportCommitOut(ApiModel):
    import_id: int
    status: ImportStatus
    rows_total: int
    rows_imported: int
    rows_duplicate: int
    rows_failed: int
    mapping_id: int | None
    assets_created: int


class ImportLogOut(ApiModel):
    id: int
    account_id: int
    filename: str
    parser_key: str
    status: ImportStatus
    rows_total: int
    rows_imported: int
    rows_duplicate: int
    rows_failed: int
    errors: list[dict[str, Any]]
    created_at: datetime
    committed_at: datetime | None


class MappingOut(ApiModel):
    id: int
    name: str
    institution: Institution
    header_signature: str
    config: dict[str, Any]
    created_at: datetime
    updated_at: datetime
