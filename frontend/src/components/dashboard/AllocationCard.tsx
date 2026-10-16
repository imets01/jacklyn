import { clsx } from 'clsx'
import { useState } from 'react'

import type { AllocationSlice, Allocations } from '../../api/types'
import { formatMoney, formatPercent, toNumber } from '../../lib/format'
import { seriesVar, slotFor, type AllocationDimension } from '../../lib/palette'
import { Card, CardHeader, SegmentedControl } from '../ui/primitives'

const DIMENSIONS: { value: AllocationDimension; label: string }[] = [
  { value: 'asset_class', label: 'Asset class' },
  { value: 'currency', label: 'Currency' },
  { value: 'broker', label: 'Broker' },
  { value: 'wrapper', label: 'TBSZ' },
  { value: 'account', label: 'Account' },
]

/**
 * Part-to-whole as a single 100% stacked bar (2px surface gaps between segments) plus a legend
 * list that doubles as the table view: every value is readable without hovering.
 */
export function AllocationCard({ allocations, currency }: { allocations: Allocations; currency: string }) {
  const [dimension, setDimension] = useState<AllocationDimension>('asset_class')
  const [hovered, setHovered] = useState<string | null>(null)
  const slices = allocations[dimension]
  const keys = slices.map((slice) => slice.key)
  const color = (slice: AllocationSlice) => seriesVar(slotFor(dimension, slice.key, keys))
  const active = slices.find((slice) => slice.key === hovered) ?? null

  return (
    <Card className="flex h-full min-w-0 flex-col">
      <CardHeader title="Allocation" subtitle={`By ${DIMENSIONS.find((d) => d.value === dimension)?.label.toLowerCase()}`} />
      <div className="px-6 pt-4">
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <SegmentedControl label="Group allocation by" size="sm" value={dimension} onChange={setDimension} options={DIMENSIONS} />
        </div>
      </div>

      <div className="px-6 pt-6">
        <div className="relative">
          <div className="flex h-3.5 w-full gap-0.5 overflow-hidden rounded-[4px]" onMouseLeave={() => setHovered(null)}>
            {slices.map((slice) => (
              <button
                key={slice.key}
                type="button"
                aria-label={`${slice.label}: ${formatMoney(slice.value, currency)}, ${formatPercent(slice.weight, { digits: 1 })}`}
                onMouseEnter={() => setHovered(slice.key)}
                onFocus={() => setHovered(slice.key)}
                onBlur={() => setHovered(null)}
                className={clsx(
                  'h-full min-w-1 transition-opacity first:rounded-l-[4px] last:rounded-r-[4px]',
                  hovered && hovered !== slice.key && 'opacity-35',
                )}
                style={{ flexGrow: toNumber(slice.weight), flexBasis: 0, background: color(slice) }}
              />
            ))}
          </div>
          <p className="mt-2 h-5 text-xs text-ink-3" aria-live="polite">
            {active ? (
              <>
                <span className="font-semibold text-ink">{formatPercent(active.weight, { digits: 1 })}</span> {active.label} ·{' '}
                <span className="tabular">{formatMoney(active.value, currency)}</span>
              </>
            ) : (
              'Hover a segment for details'
            )}
          </p>
        </div>
      </div>

      <ul className="flex-1 px-3 pb-4 pt-1">
        {slices.map((slice) => (
          <li
            key={slice.key}
            onMouseEnter={() => setHovered(slice.key)}
            onMouseLeave={() => setHovered(null)}
            className={clsx(
              'flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors',
              hovered === slice.key && 'bg-surface-2',
            )}
          >
            <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: color(slice) }} aria-hidden />
            <span className="min-w-0 flex-1 truncate text-sm text-ink">{slice.label}</span>
            <span className="tabular text-sm text-ink-2">{formatMoney(slice.value, currency)}</span>
            <span className="w-14 text-right tabular text-sm font-semibold text-ink">
              {formatPercent(slice.weight, { digits: 1 })}
            </span>
          </li>
        ))}
        {slices.length === 0 ? <li className="px-3 py-6 text-center text-sm text-ink-3">Nothing to allocate yet.</li> : null}
      </ul>
    </Card>
  )
}
