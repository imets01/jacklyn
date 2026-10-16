import type { ColumnMappingConfig, MappingField, TransactionType } from '../../api/types'

export const FIELD_META: Record<MappingField, { label: string; hint: string }> = {
  date: { label: 'Date', hint: 'Trade or booking date' },
  type: { label: 'Transaction type', hint: 'Buy, sell, dividend…' },
  symbol: { label: 'Symbol / ticker', hint: 'e.g. AAPL' },
  isin: { label: 'ISIN', hint: '12-character security ID' },
  name: { label: 'Security name', hint: 'Shown when no symbol' },
  quantity: { label: 'Quantity', hint: 'Shares or units' },
  unit_price: { label: 'Unit price', hint: 'Price per share' },
  amount: { label: 'Amount', hint: 'Gross cash value' },
  fee: { label: 'Fee / commission', hint: 'Trading costs' },
  tax: { label: 'Tax withheld', hint: 'e.g. dividend withholding' },
  currency: { label: 'Currency', hint: 'ISO code per row' },
  external_id: { label: 'Transaction ID', hint: 'Broker reference, used for de-duplication' },
  description: { label: 'Description', hint: 'Free-text note' },
}

export const DATE_FORMATS: { value: string; label: string }[] = [
  { value: '', label: 'Auto-detect' },
  { value: 'ISO8601', label: 'ISO 8601 (2025-03-14)' },
  { value: '%d.%m.%Y', label: '14.03.2025' },
  { value: '%d/%m/%Y', label: '14/03/2025' },
  { value: '%m/%d/%Y', label: '03/14/2025 (US)' },
  { value: '%Y.%m.%d.', label: '2025.03.14. (HU)' },
  { value: '%d.%m.%Y %H:%M:%S', label: '14.03.2025 09:30:00' },
  { value: '%d/%m/%Y %H:%M:%S', label: '14/03/2025 09:30:00' },
  { value: '%Y-%m-%d %H:%M:%S', label: '2025-03-14 09:30:00' },
  { value: '%Y%m%d', label: '20250314' },
]

/** Mirrors ColumnMappingConfig.missing_requirements() in the backend. */
export function missingRequirements(config: ColumnMappingConfig): string[] {
  const has = (field: MappingField) => Boolean(config.columns[field])
  const problems: string[] = []
  if (!has('date')) problems.push('Map a date column.')
  if (!has('currency') && !config.default_currency) problems.push('Map a currency column or pick a default currency.')
  if (!has('amount') && !(has('quantity') && has('unit_price'))) problems.push('Map an amount, or both quantity and unit price.')
  if (!has('type') && !config.default_type && !(config.infer_type_from_sign && has('quantity'))) {
    problems.push('Map a type column or pick a default transaction type.')
  }
  return problems
}

export function withColumn(config: ColumnMappingConfig, field: MappingField, header: string | null): ColumnMappingConfig {
  const columns = { ...config.columns }
  // A source column feeds one field at a time.
  for (const [key, value] of Object.entries(columns)) {
    if (header && value === header) delete columns[key as MappingField]
  }
  if (header) columns[field] = header
  else delete columns[field]
  return { ...config, columns }
}

export function withTypeMapping(config: ColumnMappingConfig, raw: string, type: TransactionType | null): ColumnMappingConfig {
  const typeMap = { ...config.type_map }
  if (type) typeMap[raw] = type
  else delete typeMap[raw]
  return { ...config, type_map: typeMap }
}
