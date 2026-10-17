import { clsx } from 'clsx'
import { ArrowDownRight, ArrowUpRight, Info } from 'lucide-react'
import { useState } from 'react'

import { useAssetChart } from '../../api/hooks'
import { CHART_RANGES, type ChartRange, type HoldingDetail } from '../../api/types'
import { formatDate, formatPercent } from '../../lib/format'
import { PriceChart } from '../charts/PriceChart'
import { HeroFigure } from '../dashboard/NetWorthCard'
import { Delta } from '../ui/Delta'
import { Card, SegmentedControl, Spinner } from '../ui/primitives'

const RANGE_LABELS: Record<ChartRange, string> = {
  '1D': 'today',
  '1W': 'past week',
  '1M': 'past month',
  '6M': 'past 6 months',
  YTD: 'year to date',
  '1Y': 'past year',
  '5Y': 'past 5 years',
  MAX: 'since listing',
}

function PercentPill({ ratio }: { ratio: string }) {
  const value = Number(ratio)
  const Icon = value < 0 ? ArrowDownRight : ArrowUpRight
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[13px] font-medium tabular',
        value > 0 && 'bg-positive-soft text-positive',
        value < 0 && 'bg-negative-soft text-negative',
        value === 0 && 'bg-surface-2 text-ink-3',
      )}
    >
      {value !== 0 ? <Icon className="size-3.5" aria-hidden strokeWidth={2.5} /> : null}
      {formatPercent(ratio, { signed: true })}
    </span>
  )
}

/** Latest price, change over the chosen range, and the chart with the user's trades marked. */
export function PriceCard({ detail }: { detail: HoldingDetail }) {
  const [range, setRange] = useState<ChartRange>('1Y')
  const chart = useAssetChart(detail.asset.id, range)
  const currency = detail.asset.currency
  const points = chart.data?.points ?? []

  return (
    <Card className="overflow-hidden">
      <div className="px-6 pt-6">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink-3">
            Latest price{detail.price_date ? ` · ${formatDate(detail.price_date, 'short')}` : ''}
          </p>
          <div className="mt-2">
            {detail.price ? <HeroFigure value={detail.price} currency={currency} reveal /> : <p className="text-2xl text-ink-3">No price yet</p>}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
            {chart.data?.change && range !== '1D' ? (
              <span className="inline-flex items-center gap-1.5">
                <Delta amount={chart.data.change} pct={chart.data.change_pct} currency={currency} variant="pill" reveal />
                <span className="text-ink-3">{RANGE_LABELS[range]}</span>
              </span>
            ) : null}
            {detail.price_change_pct ? (
              <span className="inline-flex items-center gap-1.5">
                <PercentPill ratio={detail.price_change_pct} />
                <span className="text-ink-3">since previous close</span>
              </span>
            ) : null}
          </div>
        </div>
        <div className="mt-5 sm:flex sm:justify-end">
          <SegmentedControl
            label="Chart range"
            size="sm"
            fill
            value={range}
            onChange={setRange}
            options={CHART_RANGES.map((value) => ({ value, label: value === 'MAX' ? 'Max' : value }))}
          />
        </div>
      </div>
      <div
        className={clsx('px-3 pb-4 pt-2 transition-opacity sm:px-4', chart.isPlaceholderData && 'opacity-60')}
        aria-busy={chart.isFetching}
      >
        {chart.isLoading ? (
          <div className="grid h-[280px] place-items-center">
            <Spinner />
          </div>
        ) : chart.error ? (
          <p className="grid h-[280px] place-items-center px-6 text-center text-sm text-ink-3">
            Couldn't load the chart: {chart.error.message}
          </p>
        ) : points.length < 2 ? (
          <p className="grid h-[280px] place-items-center px-6 text-center text-sm text-ink-3">
            No price history for this range yet.
          </p>
        ) : (
          <PriceChart
            points={points}
            currency={currency}
            range={range}
            intraday={chart.data?.intraday ?? false}
            trades={detail.activity}
          />
        )}
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 pt-2 text-xs text-ink-3">
          <span className="inline-flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-positive" aria-hidden /> Your buys
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-negative" aria-hidden /> Your sells
            </span>
          </span>
          {chart.data?.source === 'stored' ? (
            <span className="inline-flex items-center gap-1">
              <Info className="size-3" aria-hidden /> Live chart unavailable — showing stored daily closes
            </span>
          ) : (
            <span>Prices in {currency} via Yahoo Finance</span>
          )}
        </div>
      </div>
    </Card>
  )
}
