import { Cell, Pie, PieChart, ResponsiveContainer } from 'recharts'

import { formatMoney, formatPercent, toNumber } from '../../lib/format'
import { seriesVar } from '../../lib/palette'
import type { WeightItem } from '../../lib/weights'
import { AssetIcon } from '../assets/AssetIcon'

export function WeightDonut({ rows }: { rows: WeightItem[] }) {
  const data = rows.filter((row) => toNumber(row.weight) > 0)
  return (
    <div className="mx-auto size-44 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data.map((row) => ({ name: row.label, value: toNumber(row.weight) }))}
            dataKey="value"
            innerRadius="62%"
            outerRadius="100%"
            paddingAngle={1.5}
            stroke="none"
            isAnimationActive={false}
          >
            {data.map((row, index) => (
              <Cell key={row.key} fill={seriesVar(index)} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}

/** Each row's weight as a bar; its comparison (benchmark or target) as a dark marker on the same scale. */
export function WeightBars({
  rows,
  compareLabel,
  colored = false,
  currency,
  icons = false,
}: {
  rows: WeightItem[]
  compareLabel?: string | null
  colored?: boolean
  currency?: string
  /** Show each row's flag or logo (initials when there is none yet). */
  icons?: boolean
}) {
  const max = Math.max(0.0001, ...rows.map((row) => Math.max(toNumber(row.weight), toNumber(row.compare ?? 0))))
  return (
    <ul className="flex min-w-0 flex-1 flex-col gap-3">
      {rows.map((row, index) => {
        const weight = toNumber(row.weight)
        const compare = row.compare != null ? toNumber(row.compare) : null
        return (
          <li key={row.key} className="text-sm">
            <div className={`mb-1 flex justify-between gap-3 ${icons ? 'items-center' : 'items-baseline'}`}>
              <span className="flex min-w-0 items-center gap-2 text-ink-2">
                {colored ? <span className="size-2.5 shrink-0 rounded-full" style={{ background: seriesVar(index) }} aria-hidden /> : null}
                {icons ? (
                  row.key === '__rest' ? (
                    <span className="size-5 shrink-0 rounded-full bg-surface-2 ring-1 ring-line" aria-hidden />
                  ) : (
                    <AssetIcon symbol={row.label} logoUrl={row.logoUrl} size="xs" />
                  )
                ) : null}
                <span className="truncate">{row.label}</span>
              </span>
              <span className="shrink-0 tabular text-ink" title={currency && row.value ? formatMoney(row.value, currency) : undefined}>
                <span className="font-semibold">{formatPercent(weight, { digits: 1 })}</span>
                {compare != null && compareLabel ? (
                  <span className="text-xs text-ink-3">
                    {' '}
                    · {compareLabel} {formatPercent(compare, { digits: 1 })}
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
