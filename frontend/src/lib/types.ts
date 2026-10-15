// Mirrors backend/app/schemas.py. Money/quantity fields are decimal *strings*.

export type DecimalString = string;

export const BASE_CURRENCIES = ["CHF", "EUR", "HUF", "USD"] as const;
export type BaseCurrency = (typeof BASE_CURRENCIES)[number];

export type Institution = "ibkr" | "lightyear" | "erste" | "other";
export type AccountType = "standard" | "swiss" | "tbsz";
export type AssetClass = "equity" | "etf" | "bond" | "fund" | "crypto" | "commodity" | "other";
export type TransactionType =
  | "buy"
  | "sell"
  | "dividend"
  | "interest"
  | "deposit"
  | "withdrawal"
  | "fee"
  | "tax"
  | "fx"
  | "transfer_in"
  | "transfer_out";

export interface User {
  id: number;
  email: string;
  display_name: string;
  base_currency: string;
}

export interface Tbsz {
  year: number;
  phase: "collecting" | "locked" | "reduced_tax" | "matured";
  reduced_tax_date: string;
  maturity_date: string;
  days_to_maturity: number;
  progress: number;
}

export interface Account {
  id: number;
  name: string;
  institution: Institution;
  account_type: AccountType;
  tbsz_year: number | null;
  base_currency: string;
  account_number: string | null;
  is_active: boolean;
  created_at: string;
  tbsz: Tbsz | null;
  transaction_count: number;
}

export interface AccountCreate {
  name: string;
  institution: Institution;
  account_type: AccountType;
  tbsz_year: number | null;
  base_currency: string;
  account_number?: string | null;
}

export interface Bucket {
  key: string;
  label: string;
  value: DecimalString;
  weight: DecimalString;
}

export interface Holding {
  asset_id: number;
  symbol: string;
  name: string;
  isin: string | null;
  asset_class: AssetClass;
  currency: string;
  quantity: DecimalString;
  price: DecimalString | null;
  value: DecimalString;
  cost: DecimalString;
  unrealized_gain: DecimalString;
  weight: DecimalString;
}

export interface AccountSummary {
  account: Account;
  value: DecimalString;
  invested: DecimalString;
  cash: DecimalString;
  net_contributions: DecimalString;
  gain: DecimalString;
  value_in_account_currency: DecimalString;
  holdings_count: number;
  cash_by_currency: Record<string, DecimalString>;
  weight: DecimalString;
}

export type AllocationDimension = "asset_class" | "currency" | "account";

export interface PortfolioSummary {
  base_currency: BaseCurrency;
  as_of: string;
  net_worth: DecimalString;
  invested: DecimalString;
  cash: DecimalString;
  net_contributions: DecimalString;
  total_gain: DecimalString;
  total_gain_pct: DecimalString;
  allocation: Record<AllocationDimension, Bucket[]>;
  accounts: AccountSummary[];
  holdings: Holding[];
  fx_rates: Record<string, DecimalString>;
  fx_source: string;
  warnings: string[];
}

export const PERFORMANCE_RANGES = ["1M", "3M", "6M", "YTD", "1Y", "ALL"] as const;
export type PerformanceRange = (typeof PERFORMANCE_RANGES)[number];

export interface PerformancePoint {
  date: string;
  value: DecimalString;
  net_contributions: DecimalString;
}

export interface Performance {
  base_currency: BaseCurrency;
  range: PerformanceRange;
  points: PerformancePoint[];
  start_value: DecimalString;
  end_value: DecimalString;
  change: DecimalString;
  gain: DecimalString;
  gain_pct: DecimalString;
}

// ---- import

export type CanonicalField =
  | "trade_date"
  | "settle_date"
  | "type"
  | "symbol"
  | "isin"
  | "name"
  | "quantity"
  | "price"
  | "amount"
  | "fee"
  | "currency"
  | "description"
  | "external_id";

export interface FieldSpec {
  key: CanonicalField;
  label: string;
  required: boolean;
  help: string;
}

export interface ParserInfo {
  key: string;
  label: string;
  institution: Institution;
  is_stub: boolean;
}

export interface ImportOptions {
  parsers: ParserInfo[];
  fields: FieldSpec[];
  transaction_types: TransactionType[];
  max_upload_bytes: number;
}

export interface ColumnMapping {
  columns: Partial<Record<CanonicalField, string>>;
  date_format: string | null;
  decimal_separator: "." | ",";
  thousands_separator: "," | "." | " " | "'" | null;
  delimiter: string | null;
  type_map: Record<string, TransactionType>;
  default_currency: string | null;
  amount_sign: "infer" | "as_is";
}

export interface MappingSuggestion {
  columns: Partial<Record<CanonicalField, string>>;
  date_format: string | null;
  decimal_separator: "." | ",";
  delimiter: string;
  type_map: Record<string, TransactionType | null>;
  is_complete: boolean;
}

export type PreviewStatus = "new" | "duplicate" | "error";

export interface PreviewRow {
  row_number: number;
  status: PreviewStatus;
  message: string | null;
  type: TransactionType | null;
  trade_date: string | null;
  symbol: string | null;
  isin: string | null;
  name: string | null;
  quantity: DecimalString | null;
  price: DecimalString | null;
  amount: DecimalString | null;
  fee: DecimalString | null;
  currency: string | null;
  description: string | null;
}

export interface ImportPreview {
  filename: string;
  file_sha256: string;
  account_id: number;
  parser_key: string | null;
  parser_label: string | null;
  confidence: number;
  is_stub: boolean;
  mapping_id: number | null;
  needs_mapping: boolean;
  headers: string[];
  sample_rows: string[][];
  suggestion: MappingSuggestion | null;
  counts: { total: number; new: number; duplicate: number; error: number };
  rows: PreviewRow[];
  rows_truncated: boolean;
  warnings: string[];
}

export interface ImportCommit {
  import_id: number;
  status: "committed" | "failed";
  rows_total: number;
  rows_imported: number;
  rows_duplicate: number;
  rows_failed: number;
  mapping_id: number | null;
  assets_created: number;
}

export interface ImportLog {
  id: number;
  account_id: number;
  filename: string;
  parser_key: string;
  status: "committed" | "failed";
  rows_total: number;
  rows_imported: number;
  rows_duplicate: number;
  rows_failed: number;
  created_at: string;
  committed_at: string | null;
}

export interface SavedMapping {
  id: number;
  name: string;
  institution: Institution;
  header_signature: string;
  config: ColumnMapping;
  created_at: string;
  updated_at: string;
}
