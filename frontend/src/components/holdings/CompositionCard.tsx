import { useState } from 'react'

import type { FundComposition } from '../../api/types'
import { formatPercent, toNumber } from '../../lib/format'
import { foldSmallRows } from '../../lib/weights'
import { WeightBars } from '../charts/WeightBars'
import { Card, SegmentedControl } from '../ui/primitives'

type Tab = 'countries' | 'sectors' | 'holdings'

function HoldingsList({ composition }: { composition: FundComposition }) {
  const max = Math.max(0.0001, ...composition.holdings.map((h) => toNumber(h.weight)))
  const shown = composition.holdings.reduce((sum, h) => sum + toNumber(h.weight), 0)
  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-3">
        {composition.holdings.map((holding, index) => (
          <li key={holding.key} className="text-sm">
            <div className="mb-1 flex items-center justify-between gap-3">
              <span className="flex min-w-0 items-center gap-2 text-ink-2">
                <span className="w-4 shrink-0 text-right text-xs tabular text-ink-3">{index + 1}</span>
                <span className="truncate">{holding.name ?? holding.key}</span>
              </span>
              <span className="shrink-0 font-semibold tabular text-ink">{formatPercent(holding.weight, { digits: 1 })}</span>
            </div>
            <div className="ml-6 h-2 rounded-full bg-surface-2">
              <div className="h-full rounded-full bg-accent" style={{ width: `${(toNumber(holding.weight) / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ol>
      <p className="text-xs text-ink-3">
        {composition.holdings_count
          ? `The largest ${composition.holdings.length} of ${composition.holdings_count.toLocaleString()} holdings, together ${formatPercent(shown, { digits: 1 })} of the fund.`
          : `The fund's ${composition.holdings.length} largest holdings, together ${formatPercent(shown, { digits: 1 })}.`}{' '}
        Source: {composition.holdings_source}.
      </p>
    </div>
  )
}

/** What a fund is made of: its countries, sectors and largest holdings. */
export function CompositionCard({ composition }: { composition: FundComposition }) {
  const tabs: { value: Tab; label: string }[] = [
    ...(composition.countries.length ? [{ value: 'countries' as const, label: 'Countries' }] : []),
    ...(composition.sectors.length ? [{ value: 'sectors' as const, label: 'Sectors' }] : []),
    ...(composition.holdings.length ? [{ value: 'holdings' as const, label: 'Top holdings' }] : []),
  ]
  const [selected, setSelected] = useState<Tab | null>(null)
  const tab = selected && tabs.some((t) => t.value === selected) ? selected : tabs[0]?.value
  const nonStock = composition.asset_classes.filter((row) => row.label !== 'Stocks' && toNumber(row.weight) >= 0.01)

  if (!tab) return null
  return (
    <Card className="flex flex-col gap-5 px-6 py-5">
      <div className="flex flex-col gap-3">
        <h2 className="text-[15px] font-semibold text-ink">What&apos;s inside</h2>
        <div className="max-w-full overflow-x-auto">
          <SegmentedControl label="Fund composition" size="sm" value={tab} onChange={setSelected} options={tabs} />
        </div>
      </div>
      {tab === 'countries' ? (
        <>
          <WeightBars
            rows={foldSmallRows(
              composition.countries.map((row) => ({ ...row, logoUrl: row.logo_url })),
              'countries',
            )}
            icons
          />
          <p className="text-xs text-ink-3">Source: {composition.countries_source}.</p>
        </>
      ) : tab === 'sectors' ? (
        <>
          <WeightBars rows={foldSmallRows(composition.sectors, 'sectors')} />
          <p className="text-xs text-ink-3">Source: {composition.sectors_source}.</p>
        </>
      ) : (
        <HoldingsList composition={composition} />
      )}
      {nonStock.length ? (
        <p className="text-xs text-ink-3">
          Besides stocks: {nonStock.map((row) => `${row.label.toLowerCase()} ${formatPercent(row.weight, { digits: 1 })}`).join(', ')}.
        </p>
      ) : null}
    </Card>
  )
}
