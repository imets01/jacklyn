import { useId, useMemo } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
} from 'recharts'

import type { HistoryPoint, HistoryRange } from '../../api/types'
import { formatCompactNumber, formatDate, formatMoney, formatMonthYear, toNumber } from '../../lib/format'

interface Datum {
  date: string
  value: number
  invested: number
  rawValue: string
  rawInvested: string
}

function ChartTooltip({ active, payload, currency }: TooltipContentProps<number, string> & { currency: string }) {
  const datum = payload?.[0]?.payload as Datum | undefined
  if (!active || !datum) return null
  const gain = datum.value - datum.invested
  return (
    <div className="min-w-48 rounded-2xl border border-line bg-surface px-3.5 py-3 text-[13px] shadow-[var(--shadow-pop)]">
      <p className="mb-2 text-xs font-medium text-ink-3">{formatDate(datum.date, 'long')}</p>
      <div className="flex items-center gap-2">
        <span className="h-0.5 w-3 rounded-full bg-[var(--chart-line)]" aria-hidden />
        <span className="font-semibold tabular text-ink">{formatMoney(datum.rawValue, currency)}</span>
        <span className="text-ink-3">Value</span>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <span className="h-0.5 w-3 rounded-full bg-[var(--chart-muted)]" aria-hidden />
        <span className="font-semibold tabular text-ink">{formatMoney(datum.rawInvested, currency)}</span>
        <span className="text-ink-3">Net invested</span>
      </div>
      <p className="mt-2 border-t border-line pt-2 text-xs text-ink-3">
        Gain vs invested{' '}
        <span className={gain >= 0 ? 'font-semibold text-positive' : 'font-semibold text-negative'}>
          {formatMoney(gain, currency, { signed: true })}
        </span>
      </p>
    </div>
  )
}

export function PerformanceChart({
  points,
  currency,
  range,
  height = 280,
}: {
  points: HistoryPoint[]
  currency: string
  range: HistoryRange
  height?: number
}) {
  const gradientId = useId()
  const data = useMemo<Datum[]>(
    () =>
      points.map((point) => ({
        date: point.date,
        value: toNumber(point.value),
        invested: toNumber(point.invested),
        rawValue: point.value,
        rawInvested: point.invested,
      })),
    [points],
  )
  const longRange = range === '1Y' || range === 'ALL'

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-fill)" stopOpacity={0.16} />
              <stop offset="100%" stopColor="var(--chart-fill)" stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={false}
            minTickGap={48}
            tickMargin={10}
            tick={{ fill: 'var(--chart-axis)', fontSize: 12 }}
            tickFormatter={(value: string) => (longRange ? formatMonthYear(value) : formatDate(value, 'short'))}
          />
          <YAxis
            orientation="right"
            tickLine={false}
            axisLine={false}
            width={56}
            tickCount={5}
            domain={['auto', 'auto']}
            tick={{ fill: 'var(--chart-axis)', fontSize: 12, className: 'tabular' }}
            tickFormatter={(value: number) => formatCompactNumber(value)}
          />
          <Tooltip
            cursor={{ stroke: 'var(--chart-axis)', strokeWidth: 1 }}
            content={(props) => <ChartTooltip {...(props as TooltipContentProps<number, string>)} currency={currency} />}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="invested"
            name="Net invested"
            stroke="var(--chart-muted)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            dot={false}
            activeDot={{ r: 4, fill: 'var(--chart-muted)', stroke: 'var(--surface)', strokeWidth: 2 }}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="value"
            name="Value"
            stroke="var(--chart-line)"
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            fill={`url(#${gradientId})`}
            activeDot={{ r: 5, fill: 'var(--chart-line)', stroke: 'var(--surface)', strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

export function ChartLegend() {
  return (
    <div className="flex items-center gap-4 text-xs text-ink-3">
      <span className="inline-flex items-center gap-1.5">
        <span className="h-0.5 w-3.5 rounded-full bg-[var(--chart-line)]" aria-hidden />
        Portfolio value
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-0.5 w-3.5 rounded-full bg-[var(--chart-muted)]" aria-hidden />
        Net invested
      </span>
    </div>
  )
}

export function HistoryTable({ points, currency }: { points: HistoryPoint[]; currency: string }) {
  const rows = [...points].reverse()
  return (
    <div className="max-h-[280px] overflow-y-auto rounded-2xl border border-line">
      <table className="w-full text-sm">
        <caption className="sr-only">Portfolio value and net invested by date</caption>
        <thead className="sticky top-0 bg-surface-2 text-left text-xs text-ink-3">
          <tr>
            <th className="px-4 py-2 font-medium">Date</th>
            <th className="px-4 py-2 text-right font-medium">Value</th>
            <th className="px-4 py-2 text-right font-medium">Net invested</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {rows.map((point) => (
            <tr key={point.date} className="border-t border-line">
              <td className="px-4 py-2 text-ink-2">{formatDate(point.date)}</td>
              <td className="px-4 py-2 text-right text-ink">{formatMoney(point.value, currency)}</td>
              <td className="px-4 py-2 text-right text-ink-2">{formatMoney(point.invested, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
