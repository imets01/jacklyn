import { useState } from 'react'

import type { HealthReport } from '../../api/types'
import { formatPercent, toNumber } from '../../lib/format'
import { foldSmallRows } from '../../lib/weights'
import { WeightBars, WeightDonut } from '../charts/WeightBars'
import { Card, SegmentedControl } from '../ui/primitives'

type Dimension = keyof HealthReport['breakdowns']

const NOUNS: Record<Dimension, string> = {
  asset_class: 'classes',
  country: 'countries',
  sector: 'sectors',
  currency: 'currencies',
  issuer: 'providers',
}

const TABS: { value: Dimension; label: string }[] = [
  { value: 'asset_class', label: 'Asset class' },
  { value: 'country', label: 'Country' },
  { value: 'sector', label: 'Sector' },
  { value: 'currency', label: 'Currency' },
  { value: 'issuer', label: 'Providers' },
]

export function BreakdownCard({ report }: { report: HealthReport }) {
  const [tab, setTab] = useState<Dimension>('asset_class')
  const breakdown = report.breakdowns[tab]
  const rows = foldSmallRows(breakdown.slices, NOUNS[tab])
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
      {rows.length ? (
        <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
          {donut ? <WeightDonut rows={rows} /> : null}
          <WeightBars rows={rows} compareLabel={breakdown.compare_label} colored={donut} currency={report.base_currency} />
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
