import type { PeriodReturn } from '../api/types'

/**
 * The money-weighted return over the whole period: the yearly rate compounded over its days, so "+10.1% / yr"
 * for 5.6 years reads as "+71%". Periods under a year already come as totals.
 */
export function totalReturn(result: PeriodReturn): number | null {
  if (result.money_weighted === null) return null
  const rate = Number(result.money_weighted)
  return result.per_year ? (1 + rate) ** (result.days / 365) - 1 : rate
}
