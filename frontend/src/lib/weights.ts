import { toNumber } from './format'

/** A labelled share of something, optionally with a comparison (benchmark or target) and a money value. */
export interface WeightItem {
  key: string
  label: string
  weight: string
  compare?: string | null
  value?: string
  /** Flag or logo; `null` means "has an icon slot but no image yet" (initials are shown). */
  logoUrl?: string | null
}

const MIN_WEIGHT = 0.005 // rows below 0.5% (and not compared with anything sizable) fold into one
const MAX_ROWS = 12

/** The meaningful rows, with the long tail of tiny ones summed into a single "N other …" row. */
export function foldSmallRows<T extends WeightItem>(rows: readonly T[], noun: string): WeightItem[] {
  const keep: WeightItem[] = []
  const rest: WeightItem[] = []
  for (const row of rows) {
    const matters = toNumber(row.weight) >= MIN_WEIGHT || toNumber(row.compare ?? 0) >= 0.01
    if (matters && keep.length < MAX_ROWS) keep.push(row)
    else rest.push(row)
  }
  if (rest.length < 2) return [...keep, ...rest]
  const hasValues = rest.some((row) => row.value !== undefined)
  return [
    ...keep,
    {
      key: '__rest',
      label: `${rest.length} other ${noun}`,
      weight: String(rest.reduce((sum, row) => sum + toNumber(row.weight), 0)),
      compare: null,
      value: hasValues ? String(rest.reduce((sum, row) => sum + toNumber(row.value ?? 0), 0)) : undefined,
    },
  ]
}
