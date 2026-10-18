import { useId, useMemo } from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from 'recharts'

import type { ChartPoint, ChartRange, HoldingActivity } from '../../api/types'
import { formatCompactNumber, formatDate, formatPrice, formatQuantity, toNumber, TRANSACTION_TYPE_LABELS } from '../../lib/format'
import { Sensitive } from '../ui/Sensitive'

/** Buys, sells and transfers are marked on the line; income rows are not. */
const MARKED_TYPES = new Set(['buy', 'sell', 'transfer_in', 'transfer_out'])

interface Datum {
  key: string
  close: number
  raw: string
  time: string
  trades: HoldingActivity[]
}

function dayOf(time: string): string {
  // The exchange's calendar date: ISO timestamps carry the exchange offset, so the prefix is that date.
  return time.slice(0, 10)
}

function isBuy(trade: HoldingActivity): boolean {
  return trade.type === 'buy' || trade.type === 'transfer_in'
}

function formatTick(time: string, range: ChartRange): string {
  if (range === '1D') return new Date(time).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  if (range === '1W') return new Date(`${dayOf(time)}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' })
  if (range === '5Y' || range === 'MAX') {
    return new Date(`${dayOf(time)}T12:00:00`).toLocaleDateString(undefined, { month: 'short', year: 'numeric' })
  }
  return formatDate(dayOf(time), 'short')
}

function formatMoment(time: string, intraday: boolean): string {
  if (!intraday) return formatDate(dayOf(time), 'long')
  return new Date(time).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function PriceTooltip({
  active,
  payload,
  currency,
  intraday,
}: TooltipContentProps<number, string> & { currency: string; intraday: boolean }) {
  const datum = payload?.[0]?.payload as Datum | undefined
  if (!active || !datum) return null
  return (
    <div className="min-w-44 max-w-64 rounded-2xl border border-line bg-surface px-3.5 py-3 text-[13px] shadow-[var(--shadow-pop)]">
      <p className="mb-1.5 text-xs font-medium text-ink-3">{formatMoment(datum.time, intraday)}</p>
      <p className="font-semibold tabular text-ink">{formatPrice(datum.raw, currency)}</p>
      {datum.trades.map((trade) => (
        <p key={trade.id} className="mt-2 border-t border-line pt-2 text-xs text-ink-2">
          <span className={isBuy(trade) ? 'font-semibold text-positive' : 'font-semibold text-negative'}>
            {TRANSACTION_TYPE_LABELS[trade.type]}
          </span>{' '}
          <Sensitive>{formatQuantity(trade.quantity)}</Sensitive>
          {trade.unit_price ? ` @ ${formatPrice(trade.unit_price, trade.currency)}` : ''}
          <span className="block text-ink-3">
            {formatDate(trade.date)} · {trade.account_name}
          </span>
        </p>
      ))}
    </div>
  )
}

function TradeDot(props: { cx?: number; cy?: number; payload?: Datum; index?: number }) {
  const { cx, cy, payload, index } = props
  if (cx === undefined || cy === undefined || !payload?.trades.length) return <g key={`dot-${index}`} />
  const buys = payload.trades.some(isBuy)
  const sells = payload.trades.some((trade) => !isBuy(trade))
  const fill = buys && sells ? 'var(--warning)' : buys ? 'var(--positive)' : 'var(--negative)'
  return <circle key={`dot-${index}`} cx={cx} cy={cy} r={5} fill={fill} stroke="var(--surface)" strokeWidth={2} />
}

/** An asset's price over a range, with the user's own buys and sells marked on the line. */
export function PriceChart({
  points,
  currency,
  range,
  intraday,
  trades,
}: {
  points: ChartPoint[]
  currency: string
  range: ChartRange
  intraday: boolean
  trades: HoldingActivity[]
}) {
  const gradientId = useId()
  const data = useMemo<Datum[]>(() => {
    const rows: Datum[] = points.map((point) => ({
      key: point.time,
      close: toNumber(point.close),
      raw: point.close,
      time: point.time,
      trades: [],
    }))
    const firstRow = rows[0]
    const lastRow = rows.at(-1)
    if (!firstRow || !lastRow) return rows
    const first = dayOf(firstRow.time)
    const last = dayOf(lastRow.time)
    for (const trade of trades) {
      if (!MARKED_TYPES.has(trade.type) || trade.date < first || trade.date > last) continue
      const row = rows.find((candidate) => dayOf(candidate.time) >= trade.date)
      row?.trades.push(trade)
    }
    return rows
  }, [points, trades])

  const rising = (data.at(-1)?.close ?? 0) >= (data[0]?.close ?? 0)
  const color = rising ? 'var(--positive)' : 'var(--negative)'

  return (
    <div className="h-[280px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 4, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.16} />
              <stop offset="100%" stopColor={color} stopOpacity={0.01} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
          <XAxis
            dataKey="key"
            tickLine={false}
            axisLine={false}
            minTickGap={56}
            tickMargin={10}
            tick={{ fill: 'var(--chart-axis)', fontSize: 12 }}
            tickFormatter={(value: string) => formatTick(value, range)}
          />
          <YAxis
            orientation="right"
            tickLine={false}
            axisLine={false}
            width={56}
            tickCount={5}
            domain={['auto', 'auto']}
            tick={{ fill: 'var(--chart-axis)', fontSize: 12, className: 'tabular' }}
            tickFormatter={(value: number) => (value >= 10_000 ? formatCompactNumber(value) : value.toLocaleString(undefined, { maximumFractionDigits: 2 }))}
          />
          <Tooltip
            cursor={{ stroke: 'var(--chart-axis)', strokeWidth: 1 }}
            content={(props) => (
              <PriceTooltip {...(props as TooltipContentProps<number, string>)} currency={currency} intraday={intraday} />
            )}
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="close"
            name="Price"
            stroke={color}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            fill={`url(#${gradientId})`}
            dot={(props: { cx?: number; cy?: number; payload?: Datum; index?: number }) => (
              <TradeDot key={`trade-${props.index}`} {...props} />
            )}
            activeDot={{ r: 5, fill: color, stroke: 'var(--surface)', strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
