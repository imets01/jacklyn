import { useState } from 'react'
import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'

import type { HealthBreakdown, HealthReport, HealthSlice } from '../../api/types'
import { formatMoney, formatPercent, toNumber } from '../../lib/format'
import { seriesVar } from '../../lib/palette'
import { Card, SegmentedControl } from '../ui/primitives'

type Dimension = keyof HealthReport['breakdowns']

const MIN_WEIGHT = 0.005 // rows below 0.5% (and not compared with anything sizable) fold into one
const MAX_ROWS = 12
const NOUNS: Record<Dimension, string> = {
  asset_class: 'classes',
  country: 'countries',
  sector: 'sectors',
  currency: 'currencies',
  issuer: 'providers',
}

/** The meaningful slices, with the long tail of tiny ones summed into a single "N other …" row. */
function foldSmallSlices(breakdown: HealthBreakdown, noun: string): HealthBreakdown {
  const keep: HealthSlice[] = []
  const rest: HealthSlice[] = []
  for (const slice of breakdown.slices) {
    const matters = toNumber(slice.weight) >= MIN_WEIGHT || toNumber(slice.compare ?? 0) >= 0.01
    if (matters && keep.length < MAX_ROWS) keep.push(slice)
    else rest.push(slice)
  }
  if (rest.length < 2) return { ...breakdown, slices: [...keep, ...rest] }
  const folded: HealthSlice = {
    key: '__rest',
    label: `${rest.length} other ${noun}`,
    value: String(rest.reduce((sum, slice) => sum + toNumber(slice.value), 0)),
    weight: String(rest.reduce((sum, slice) => sum + toNumber(slice.weight), 0)),
    compare: null,
  }
  return { ...breakdown, slices: [...keep, folded] }
}

const TABS: { value: Dimension; label: string }[] = [
  { value: 'asset_class', label: 'Asset class' },
  { value: 'country', label: 'Country' },
  { value: 'sector', label: 'Sector' },
  { value: 'currency', label: 'Currency' },
  { value: 'issuer', label: 'Providers' },
]

function Donut({ breakdown }: { breakdown: HealthBreakdown }) {
  const data = breakdown.slices.filter((slice) => toNumber(slice.weight) > 0)
  return (
    <div className="mx-auto size-44 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data.map((slice) => ({ name: slice.label, value: toNumber(slice.weight) }))}
            dataKey="value"
            innerRadius="62%"
            outerRadius="100%"
            paddingAngle={1.5}
            stroke="none"
            isAnimationActive={false}
          >
            {data.map((slice, index) => (
              <Cell key={slice.key} fill={seriesVar(index)} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Your weight as a bar, the comparison (benchmark or target) as a marker on the same scale. */
function ComparisonRows({ breakdown, currency, colored }: { breakdown: HealthBreakdown; currency: string; colored: boolean }) {
  const max = Math.max(
    0.0001,
    ...breakdown.slices.map((slice) => Math.max(toNumber(slice.weight), toNumber(slice.compare ?? 0))),
  )
  return (
    <ul className="flex min-w-0 flex-1 flex-col gap-3">
      {breakdown.slices.map((slice, index) => {
        const weight = toNumber(slice.weight)
        const compare = slice.compare != null ? toNumber(slice.compare) : null
        return (
          <li key={slice.key} className="text-sm">
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <span className="flex min-w-0 items-center gap-2 text-ink-2">
                {colored ? <span className="size-2.5 shrink-0 rounded-full" style={{ background: seriesVar(index) }} aria-hidden /> : null}
                <span className="truncate">{slice.label}</span>
              </span>
              <span className="shrink-0 tabular text-ink" title={formatMoney(slice.value, currency)}>
                <span className="font-semibold">{formatPercent(weight, { digits: 1 })}</span>
                {compare != null ? (
                  <span className="text-xs text-ink-3">
                    {' '}
                    · {breakdown.compare_label} {formatPercent(compare, { digits: 1 })}
                  </span>
                ) : null}
              </span>
            </div>
            <div className="relative h-2 rounded-full bg-surface-2">
              <div
                className="h-full rounded-full"
                style={{ width: `${(weight / max) * 100}%`, background: colored ? seriesVar(index) : 'var(--accent)' }}
              />
              {compare != null ? (
                <span
                  className="absolute -top-1 h-4 w-0.5 rounded-full bg-ink"
                  style={{ left: `calc(${(compare / max) * 100}% - 1px)` }}
                  aria-hidden
                />
              ) : null}
            </div>
          </li>
        )
      })}
    </ul>
  )
}

export function BreakdownCard({ report }: { report: HealthReport }) {
  const [tab, setTab] = useState<Dimension>('asset_class')
  const breakdown = foldSmallSlices(report.breakdowns[tab], NOUNS[tab])
  const donut = tab === 'asset_class' || tab === 'currency' || tab === 'issuer'
  return (
    <Card className="flex flex-col gap-5 px-6 py-5">
      <div className="flex flex-col gap-3">
        <h2 className="text-[15px] font-semibold text-ink">Breakdown</h2>
        {/* Tabs on their own row so they stay put whatever the description below says. */}
        <div className="max-w-full overflow-x-auto">
          <SegmentedControl label="Breakdown" size="sm" value={tab} onChange={setTab} options={TABS} />
        </div>
        <p className="text-sm text-ink-3">
          {breakdown.compare_label
            ? `Bars are you, the dark marker is ${breakdown.compare_label === 'Target' ? 'your target' : breakdown.compare_label}.`
            : 'Your portfolio; there is no benchmark for this view.'}
        </p>
      </div>
      {breakdown.slices.length ? (
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
          {donut ? <Donut breakdown={breakdown} /> : null}
          <ComparisonRows breakdown={breakdown} currency={report.base_currency} colored={donut} />
        </div>
      ) : (
        <p className="text-sm text-ink-3">No data for this view yet.</p>
      )}
      {tab === 'country' && Object.keys(report.country_quality).length ? (
        <p className="text-xs text-ink-3">
          Country data for your stocks:{' '}
          {(['reported', 'estimated', 'unknown'] as const)
            .filter((key) => toNumber(report.country_quality[key] ?? 0) > 0)
            .map((key) => `${formatPercent(report.country_quality[key] ?? 0, { digits: 0 })} ${key}`)
            .join(' · ')}
        </p>
      ) : null}
      {breakdown.note ? <p className="text-xs text-ink-3">{breakdown.note}</p> : null}
    </Card>
  )
}
