// Mirrors the FastAPI response models. Decimal values arrive as strings to keep them exact;
// they are only converted to numbers at the display edge (see lib/format.ts).

export type Money = string
export type Ratio = string
export type ISODate = string
export type ISODateTime = string

export const BASE_CURRENCIES = ['CHF', 'EUR', 'HUF', 'USD'] as const
export type BaseCurrency = (typeof BASE_CURRENCIES)[number]

export const ACCOUNT_TYPES = ['standard', 'swiss', 'tbsz', 'pension', 'savings', 'crypto', 'other'] as const
export type AccountType = (typeof ACCOUNT_TYPES)[number]

export const TRANSACTION_TYPES = [
  'buy',
  'sell',
  'dividend',
  'interest',
  'fee',
  'tax',
  'deposit',
  'withdrawal',
  'fx_conversion',
  'transfer_in',
  'transfer_out',
] as const
export type TransactionType = (typeof TRANSACTION_TYPES)[number]

export type AssetClass = 'stock' | 'etf' | 'fund' | 'bond' | 'crypto' | 'commodity' | 'cash' | 'other'
export type HistoryRange = '1W' | '1M' | '3M' | 'YTD' | '1Y' | 'ALL'
export const CHART_RANGES = ['1D', '1W', '1M', '6M', 'YTD', '1Y', '5Y', 'MAX'] as const
export type ChartRange = (typeof CHART_RANGES)[number]

export interface User {
  id: number
  email: string
  display_name: string
  base_currency: string
}

export interface AllocationSlice {
  key: string
  label: string
  value: Money
  weight: Ratio
}

export interface Allocations {
  asset_class: AllocationSlice[]
  currency: AllocationSlice[]
  broker: AllocationSlice[]
  wrapper: AllocationSlice[]
  account: AllocationSlice[]
}

export interface AccountSummary {
  id: number
  name: string
  broker: string
  account_type: AccountType
  tbsz_year: number | null
  tbsz_reduced_rate_from: ISODate | null
  tbsz_tax_free_from: ISODate | null
  currency: string
  external_account_id: string | null
  track_cash: boolean
  is_archived: boolean
  value: Money
  value_account_currency: Money | null
  cash: Money
  day_change: Money
  total_pnl: Money
  net_contributions: Money
  holdings_count: number
  transaction_count: number
  last_transaction_date: ISODate | null
}

export interface MarketStatus {
  live_enabled: boolean
  refreshing: boolean
  last_refresh_at: ISODateTime | null
  last_refresh_error: string | null
  prices_as_of: ISODate | null
  fx_as_of: ISODate | null
  synthetic_price_assets: number
  unpriced_assets: number
}

export interface PortfolioSummary {
  base_currency: string
  as_of: ISODate
  net_worth: Money
  holdings_value: Money
  cash: Money
  day_change: Money
  day_change_pct: Ratio | null
  total_pnl: Money
  total_pnl_pct: Ratio | null
  unrealized_pnl: Money
  realized_pnl: Money
  income: Money
  costs: Money
  net_contributions: Money
  allocations: Allocations
  accounts: AccountSummary[]
  market: MarketStatus
  warnings: string[]
}

export interface Holding {
  account_id: number
  account_name: string
  asset_id: number
  symbol: string
  name: string | null
  isin: string | null
  asset_class: AssetClass
  currency: string
  quantity: string
  price: string | null
  price_date: ISODate | null
  value_local: Money
  value: Money
  cost_basis: Money
  unrealized_pnl: Money
  unrealized_pnl_pct: Ratio | null
  day_change: Money
  weight: Ratio
  /** Per unit, in the asset's currency, fees included. */
  avg_cost: string | null
  logo_url: string | null
}

export interface AssetProfile {
  quote_type: string | null
  long_name: string | null
  provider: string | null
  sector: string | null
  industry: string | null
  description: string | null
  website: string | null
  /** Yearly fee as a fraction: 0.0007 = 0.07%. */
  expense_ratio: Ratio | null
  fund_size: Money | null
}

export interface AssetInfo {
  id: number
  symbol: string
  name: string | null
  isin: string | null
  asset_class: AssetClass
  currency: string
  exchange: string | null
  yf_ticker: string | null
  logo_url: string | null
}

export interface HoldingAccount {
  account_id: number
  account_name: string
  broker: string
  quantity: string
  value: Money
  cost_basis: Money
  unrealized_pnl: Money
  unrealized_pnl_pct: Ratio | null
}

export interface HoldingActivity {
  id: number
  account_id: number
  account_name: string
  date: ISODate
  type: TransactionType
  quantity: string | null
  unit_price: string | null
  amount: Money | null
  fee: Money
  tax: Money
  currency: string
}

export interface HoldingDetail {
  base_currency: string
  as_of: ISODate
  asset: AssetInfo
  profile: AssetProfile | null
  price: string | null
  price_date: ISODate | null
  previous_close: string | null
  price_change_pct: Ratio | null
  quantity: string
  avg_cost: string | null
  value_local: Money
  value: Money
  cost_basis: Money
  unrealized_pnl: Money
  unrealized_pnl_pct: Ratio | null
  day_change: Money
  weight: Ratio
  accounts: HoldingAccount[]
  /** Newest first. */
  activity: HoldingActivity[]
}

export interface ChartPoint {
  time: ISODateTime
  close: string
}

export interface ChartResponse {
  asset_id: number
  range: ChartRange
  currency: string
  intraday: boolean
  source: 'yfinance' | 'stored'
  points: ChartPoint[]
  change: string | null
  change_pct: Ratio | null
}

export interface CashBalance {
  account_id: number
  account_name: string
  currency: string
  amount: Money
  value: Money
  logo_url: string | null
}

export interface HoldingsResponse {
  base_currency: string
  as_of: ISODate
  holdings: Holding[]
  cash: CashBalance[]
}

export interface HistoryPoint {
  date: ISODate
  value: Money
  invested: Money
}

export interface HistoryResponse {
  base_currency: string
  range: HistoryRange
  points: HistoryPoint[]
  change: Money
  change_pct: Ratio | null
}

export interface TransactionRow {
  id: number
  account_id: number
  account_name: string
  date: ISODate
  type: TransactionType
  symbol: string | null
  name: string | null
  isin: string | null
  quantity: string | null
  unit_price: string | null
  amount: string | null
  fee: string
  tax: string
  currency: string
  description: string | null
  external_id: string | null
  import_log_id: number | null
}

export interface TransactionPage {
  total: number
  items: TransactionRow[]
}

export interface AccountCreate {
  name: string
  broker: string
  account_type: AccountType
  tbsz_year: number | null
  currency: string
  external_account_id: string | null
  track_cash: boolean
}

// ---------------------------------------------------------------- ingestion

export const MAPPING_FIELDS = [
  'date',
  'type',
  'symbol',
  'isin',
  'name',
  'quantity',
  'unit_price',
  'amount',
  'fee',
  'tax',
  'currency',
  'external_id',
  'description',
] as const
export type MappingField = (typeof MAPPING_FIELDS)[number]

export type DecimalSeparator = '.' | ','

export interface ColumnMappingConfig {
  columns: Partial<Record<MappingField, string>>
  header_row: number | null
  delimiter: string | null
  encoding: string | null
  decimal_separator: DecimalSeparator | null
  date_format: string | null
  type_map: Record<string, TransactionType>
  default_type: TransactionType | null
  default_currency: string | null
  infer_type_from_sign: boolean
}

export interface TablePreview {
  kind: 'csv' | 'xlsx' | 'xls' | 'html'
  headers: string[]
  sample_rows: string[][]
  header_row: number
  total_rows: number
  delimiter: string | null
  encoding: string | null
  sheet_name: string | null
  header_signature: string
  detected_decimal_separator: DecimalSeparator
  detected_date_format: string | null
  distinct_type_values: string[]
  distinct_values: Record<string, string[]>
  suggested: ColumnMappingConfig
}

/** The normalized StandardTransaction, exactly as the API emits and accepts it. */
export interface StandardTransaction {
  date: ISODate
  type: TransactionType
  symbol: string | null
  isin: string | null
  name: string | null
  asset_class: AssetClass | null
  exchange: string | null
  quantity: string | null
  unit_price: string | null
  amount: string | null
  fee: string
  tax: string
  currency: string
  external_id: string | null
  description: string | null
}

export interface PreviewTransaction {
  row: number | null
  duplicate: boolean
  transaction: StandardTransaction
}

export interface RowError {
  row: number | null
  message: string
  raw: Record<string, string> | null
}

export interface ImportPreview {
  status: 'parsed' | 'needs_mapping' | 'unsupported'
  filename: string
  file_sha256: string
  file_kind: string
  message: string | null
  detection: { parser_key: string; parser_label: string; broker: string | null; confidence: number } | null
  mapping_used: { id: number; name: string } | null
  table: TablePreview | null
  transactions: PreviewTransaction[]
  errors: RowError[]
  warnings: string[]
  summary: { total: number; new: number; duplicates: number; errors: number }
  account_hint: { broker: string | null; external_account_id: string | null; currency: string | null } | null
  suggested_account_id: number | null
}

export interface ImportCommitRequest {
  account_id: number
  transactions: StandardTransaction[]
  parser_key: string | null
  filename: string | null
  file_sha256: string | null
}

export interface ImportCommitResult {
  import_log_id: number
  received: number
  imported: number
  duplicates: number
}

export interface ImportLog {
  id: number
  account_id: number | null
  source: 'file' | 'api_sync' | 'seed' | 'manual' | 'webhook'
  status: 'committed' | 'failed'
  parser_key: string | null
  filename: string | null
  rows_received: number
  rows_imported: number
  rows_duplicate: number
  message: string | null
  created_at: ISODateTime
}

export interface SavedMapping {
  id: number
  name: string
  header_signature: string
  config: ColumnMappingConfig
  created_at: ISODateTime
  updated_at: ISODateTime
}

export interface MarketRefreshResult {
  started: boolean
  live_enabled: boolean
  refreshing: boolean
  last_refresh_at: ISODateTime | null
  last_refresh_error: string | null
}
