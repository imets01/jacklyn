/**
 * Categorical series colors. Eight validated slots (CVD-safe adjacent order, light + dark),
 * referenced through CSS variables so the theme swaps them. Colors follow the entity, never
 * its rank: each dimension maps keys to a stable slot, so re-sorting never repaints a slice.
 */
export const SERIES_SLOTS = 8

const ASSET_CLASS_ORDER = ['etf', 'stock', 'cash', 'bond', 'fund', 'crypto', 'commodity', 'other']
const CURRENCY_ORDER = ['CHF', 'EUR', 'USD', 'HUF', 'GBP']

export type AllocationDimension = 'asset_class' | 'currency' | 'broker' | 'wrapper' | 'account'

export function seriesVar(slot: number): string {
  return slot >= SERIES_SLOTS ? 'var(--series-other)' : `var(--series-${slot + 1})`
}

/** Stable slot per key: fixed orders where the domain is known, else first-seen order of `allKeys`. */
export function slotFor(dimension: AllocationDimension, key: string, allKeys: readonly string[]): number {
  const fixed = dimension === 'asset_class' ? ASSET_CLASS_ORDER : dimension === 'currency' ? CURRENCY_ORDER : null
  if (fixed) {
    const index = fixed.indexOf(key)
    if (index >= 0) return index
    const extras = allKeys.filter((k) => !fixed.includes(k)).sort()
    return fixed.length + extras.indexOf(key)
  }
  if (dimension === 'wrapper') {
    if (key === 'regular') return 0
    const vintages = allKeys.filter((k) => k !== 'regular').sort()
    return 1 + vintages.indexOf(key)
  }
  return [...allKeys].sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).indexOf(key)
}
