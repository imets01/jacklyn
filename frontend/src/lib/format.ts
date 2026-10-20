// Display-only formatting. Amounts stay strings (exact decimals) until this edge.
// Private mode blurs personal figures where they are rendered (components/ui/Sensitive), not here.

const ZERO_DECIMAL_CURRENCIES = new Set(['HUF', 'JPY', 'KRW', 'CLP', 'ISK'])

export function toNumber(value: string | number | null | undefined): number {
  if (value === null || value === undefined || value === '') return 0
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function fractionDigits(currency: string, compact = false): number {
  if (ZERO_DECIMAL_CURRENCIES.has(currency)) return 0
  return compact ? 1 : 2
}

const formatters = new Map<string, Intl.NumberFormat>()

function formatter(key: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  let cached = formatters.get(key)
  if (!cached) {
    cached = new Intl.NumberFormat(undefined, options)
    formatters.set(key, cached)
  }
  return cached
}

export function formatMoney(
  value: string | number | null | undefined,
  currency: string,
  opts: { signed?: boolean } = {},
): string {
  const digits = fractionDigits(currency)
  const f = formatter(`money:${currency}:${opts.signed ? 's' : ''}`, {
    style: 'currency',
    currency,
    currencyDisplay: 'code',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: opts.signed ? 'exceptZero' : 'auto',
  })
  return f.format(toNumber(value))
}

/** Splits a money value so the hero figure can de-emphasize the currency code and decimals. */
export function moneyParts(value: string | number, currency: string): { currency: string; integer: string; fraction: string } {
  const digits = fractionDigits(currency)
  const f = formatter(`parts:${currency}`, {
    style: 'currency',
    currency,
    currencyDisplay: 'code',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
  let code = currency
  let integer = ''
  let fraction = ''
  let seenDecimal = false
  for (const part of f.formatToParts(toNumber(value))) {
    if (part.type === 'currency') code = part.value
    else if (part.type === 'literal' && !integer) continue
    else if (part.type === 'decimal') {
      seenDecimal = true
      fraction += part.value
    } else if (seenDecimal) fraction += part.value
    else if (part.type !== 'literal') integer += part.value
  }
  return { currency: code, integer, fraction }
}

export function formatCompactMoney(value: string | number, currency: string): string {
  const f = formatter(`compact:${currency}`, {
    style: 'currency',
    currency,
    currencyDisplay: 'code',
    notation: 'compact',
    maximumFractionDigits: fractionDigits(currency, true),
  })
  return f.format(toNumber(value))
}

export function formatCompactNumber(value: number): string {
  return formatter('compact-number', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

export function formatPercent(ratio: string | number | null | undefined, opts: { signed?: boolean; digits?: number } = {}): string {
  if (ratio === null || ratio === undefined) return '—'
  const digits = opts.digits ?? 2
  const f = formatter(`pct:${digits}:${opts.signed ? 's' : ''}`, {
    style: 'percent',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    signDisplay: opts.signed ? 'exceptZero' : 'auto',
  })
  return f.format(toNumber(ratio))
}

export function formatQuantity(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return formatter('qty', { maximumFractionDigits: 6 }).format(toNumber(value))
}

export function formatPrice(value: string | null | undefined, currency: string): string {
  if (value === null || value === undefined) return '—'
  const number = toNumber(value)
  const digits = Math.abs(number) >= 1000 || ZERO_DECIMAL_CURRENCIES.has(currency) ? 2 : 4
  return `${formatter(`price:${digits}`, { minimumFractionDigits: 2, maximumFractionDigits: digits }).format(number)} ${currency}`
}

function parseISODate(value: string): Date {
  // Treat plain dates as local calendar dates (not UTC midnight).
  const [year, month, day] = value.slice(0, 10).split('-').map(Number)
  return new Date(year ?? 1970, (month ?? 1) - 1, day ?? 1)
}

export function formatDate(value: string | null | undefined, style: 'short' | 'medium' | 'long' = 'medium'): string {
  if (!value) return '—'
  const date = parseISODate(value)
  const options: Intl.DateTimeFormatOptions =
    style === 'short'
      ? date.getFullYear() === new Date().getFullYear()
        ? { day: 'numeric', month: 'short' }
        : { day: 'numeric', month: 'short', year: 'numeric' }
      : style === 'long'
        ? { day: 'numeric', month: 'long', year: 'numeric' }
        : { day: 'numeric', month: 'short', year: 'numeric' }
  return date.toLocaleDateString(undefined, options)
}

export function formatMonthYear(value: string): string {
  return parseISODate(value).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
}

export function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return 'never'
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000)
  if (seconds < 45) return 'just now'
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  if (seconds < 3600) return rtf.format(-Math.round(seconds / 60), 'minute')
  if (seconds < 86_400) return rtf.format(-Math.round(seconds / 3600), 'hour')
  return rtf.format(-Math.round(seconds / 86_400), 'day')
}

export function trend(value: string | number | null | undefined): 'up' | 'down' | 'flat' {
  const number = toNumber(value)
  if (number > 0) return 'up'
  if (number < 0) return 'down'
  return 'flat'
}

export const TRANSACTION_TYPE_LABELS: Record<string, string> = {
  buy: 'Buy',
  sell: 'Sell',
  dividend: 'Dividend',
  interest: 'Interest',
  fee: 'Fee',
  tax: 'Tax',
  deposit: 'Deposit',
  withdrawal: 'Withdrawal',
  fx_conversion: 'FX exchange',
  transfer_in: 'Transfer in',
  transfer_out: 'Transfer out',
}

export const ASSET_CLASS_LABELS: Record<string, string> = {
  stock: 'Stock',
  etf: 'ETF',
  fund: 'Fund',
  bond: 'Bond',
  crypto: 'Crypto',
  commodity: 'Commodity',
  cash: 'Cash',
  other: 'Other',
}
