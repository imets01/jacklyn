import { useMemo } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, type TooltipContentProps } from 'recharts'

import type { IncomeMonth } from '../../api/types'
import { formatCompactNumber, formatMoney, formatMonthYear, toNumber } from '../../lib/format'
import { usePreferences } from '../../lib/preferences-context'
import { Sensitive } from '../ui/Sensitive'

/** Fixed series order: dividends take the first categorical slot, interest the second. */
const INCOME_SERIES = [
  { key: 'dividends', label: 'Dividends', color: 'var(--series-1)' },
  { key: 'interest', label: 'Interest', color: 'var(--series-2)' },
] as const

interface Datum {
  month: string
  dividends: number
  interest: number
  raw: IncomeMonth
}

function MonthTooltip({ active, payload, currency }: TooltipContentProps<number, string> & { currency: string }) {
  const datum = payload?.[0]?.payload as Datum | undefined
  if (!active || !datum) return null
  const { raw } = datum
  return (
    <div className="min-w-48 rounded-2xl border border-line bg-surface px-3.5 py-3 text-[13px] shadow-[var(--shadow-pop)]">
      <p className="mb-2 text-xs font-medium text-ink-3">{formatMonthYear(raw.month)}</p>
      {INCOME_SERIES.map((series) => (
        <div key={series.key} className="mt-1 flex items-center gap-2">
          <span className="size-2.5 rounded-sm" style={{ background: series.color }} aria-hidden />
          <span className="font-semibold tabular text-ink">
            <Sensitive>{formatMoney(raw[series.key], currency)}</Sensitive>
          </span>
          <span className="text-ink-3">{series.label}</span>
        </div>
      ))}
      {toNumber(raw.withheld) ? (
        <p className="mt-2 border-t border-line pt-2 text-xs text-ink-3">
          <Sensitive>{formatMoney(raw.withheld, currency)}</Sensitive> withheld in tax
        </p>
      ) : null}
    </div>
  )
}

/** Series with any income in these months; a series that never paid stays out of the chart and legend. */
function incomeSeries(months: IncomeMonth[]) {
  return INCOME_SERIES.filter((series) => months.some((month) => toNumber(month[series.key]) > 0))
}

export function IncomeLegend({ months }: { months: IncomeMonth[] }) {
  const series = incomeSeries(months)
  if (series.length < 2) return null // one series: the card title names it
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
      {series.map((series) => (
        <span key={series.key} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: series.color }} aria-hidden />
          {series.label}
        </span>
      ))}
    </div>
  )
}

/** Monthly income, net of withholding: dividends and interest stacked, one bar per month. */
export function IncomeChart({ months, currency }: { months: IncomeMonth[]; currency: string }) {
  const { hideAmounts } = usePreferences()
  const shown = incomeSeries(months)
  const data = useMemo<Datum[]>(
    () =>
      months.map((month) => ({
        month: month.month,
        dividends: Math.max(0, toNumber(month.dividends)),
        interest: Math.max(0, toNumber(month.interest)),
        raw: month,
      })),
    [months],
  )
  return (
    <div className="h-[240px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 0 }} barCategoryGap="22%">
          <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
          <XAxis
            dataKey="month"
            tickLine={false}
            axisLine={false}
            minTickGap={24}
            tickMargin={10}
            tick={{ fill: 'var(--chart-axis)', fontSize: 12 }}
            tickFormatter={(value: string) => formatMonthYear(value)}
          />
          <YAxis
            orientation="right"
            tickLine={false}
            axisLine={false}
            width={48}
            tickCount={4}
            allowDecimals={false}
            tick={{ fill: 'var(--chart-axis)', fontSize: 12, className: 'tabular' }}
            tickFormatter={(value: number) => (hideAmounts ? '' : formatCompactNumber(value))}
          />
          <Tooltip
            cursor={{ fill: 'var(--chart-grid)', opacity: 0.6 }}
            content={(props) => <MonthTooltip {...(props as TooltipContentProps<number, string>)} currency={currency} />}
            isAnimationActive={false}
          />
          {/* A 2px surface stroke separates stacked segments; the top series gets the rounded data end. */}
          {shown.map((series, index) => (
            <Bar
              key={series.key}
              dataKey={series.key}
              name={series.label}
              stackId="income"
              fill={series.color}
              stroke="var(--surface)"
              strokeWidth={shown.length > 1 ? 2 : 0}
              radius={index === shown.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
