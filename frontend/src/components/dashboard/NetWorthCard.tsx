import { clsx } from 'clsx'
import { ChartArea, Table2 } from 'lucide-react'
import { useState } from 'react'

import { useHistory } from '../../api/hooks'
import type { HistoryRange, PortfolioSummary } from '../../api/types'
import { moneyParts } from '../../lib/format'
import { Sensitive } from '../ui/Sensitive'
import { ChartLegend, HistoryTable, PerformanceChart } from '../charts/PerformanceChart'
import { Delta } from '../ui/Delta'
import { Card, SegmentedControl, Spinner } from '../ui/primitives'

const RANGES: { value: HistoryRange; label: string }[] = [
  { value: '1W', label: '1W' },
  { value: '1M', label: '1M' },
  { value: '3M', label: '3M' },
  { value: 'YTD', label: 'YTD' },
  { value: '1Y', label: '1Y' },
  { value: 'ALL', label: 'All' },
]

const RANGE_LABELS: Record<HistoryRange, string> = {
  '1W': 'past week',
  '1M': 'past month',
  '3M': 'past 3 months',
  YTD: 'year to date',
  '1Y': 'past year',
  ALL: 'all time',
}

/** Big money figure. `reveal` keeps public numbers (like a share price) visible in private mode. */
export function HeroFigure({ value, currency, reveal = false }: { value: string; currency: string; reveal?: boolean }) {
  const parts = moneyParts(value, currency)
  return (
    <p className="font-display text-[40px] font-bold leading-none tracking-tight text-ink sm:text-[52px]">
      <span className="mr-2 align-[0.32em] text-lg font-semibold text-ink-3 sm:text-xl">{parts.currency}</span>
      <Sensitive reveal={reveal}>
        {parts.integer}
        <span className="text-ink-3">{parts.fraction}</span>
      </Sensitive>
    </p>
  )
}

export function NetWorthCard({
  summary,
  accountId,
  title = 'Net worth',
}: {
  summary: Pick<PortfolioSummary, 'net_worth' | 'day_change' | 'day_change_pct' | 'base_currency'>
  accountId?: number
  title?: string
}) {
  const [range, setRange] = useState<HistoryRange>('1Y')
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const currency = summary.base_currency
  const history = useHistory(currency, range, accountId)
  const points = history.data?.points ?? []

  return (
    <Card className="overflow-hidden">
      {/* The figure's width varies with currency and private mode; the controls never wrap or move because of it. */}
      <div className="flex flex-col gap-5 px-6 pt-6 sm:flex-row sm:flex-wrap sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-ink-3">{title}</p>
          <div className="mt-2">
            <HeroFigure value={summary.net_worth} currency={currency} />
          </div>
          <div className="mt-3 flex flex-col items-start gap-2 text-sm">
            {history.data ? (
              <span className="inline-flex items-center gap-1.5">
                <Delta amount={history.data.change} pct={history.data.change_pct} currency={currency} variant="pill" />
                <span className="text-ink-3">{RANGE_LABELS[range]}</span>
              </span>
            ) : null}
            <span className="inline-flex items-center gap-1.5">
              <Delta amount={summary.day_change} pct={summary.day_change_pct} currency={currency} />
              <span className="text-ink-3">today</span>
            </span>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 self-start sm:flex-nowrap">
          <SegmentedControl label="Time range" size="sm" value={range} onChange={setRange} options={RANGES} />
          <SegmentedControl
            label="View"
            size="sm"
            value={view}
            onChange={setView}
            options={[
              { value: 'chart', label: <ChartArea className="size-3.5" aria-label="Chart" />, title: 'Chart' },
              { value: 'table', label: <Table2 className="size-3.5" aria-label="Table" />, title: 'Table' },
            ]}
          />
        </div>
      </div>
      <div className="px-6 pt-4">
        <ChartLegend />
      </div>
      <div
        className={clsx('px-3 pb-4 pt-2 transition-opacity sm:px-4', history.isPlaceholderData && 'opacity-60')}
        aria-busy={history.isFetching}
      >
        {history.isLoading ? (
          <div className="grid h-[280px] place-items-center">
            <Spinner />
          </div>
        ) : view === 'chart' ? (
          <PerformanceChart points={points} currency={currency} range={range} />
        ) : (
          <div className="px-3">
            <HistoryTable points={points} currency={currency} />
          </div>
        )}
      </div>
    </Card>
  )
}
