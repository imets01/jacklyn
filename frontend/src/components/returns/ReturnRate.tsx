import { clsx } from 'clsx'
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'

import { formatPercent, trend } from '../../lib/format'

/** A rate of return with direction shown by icon and sign as well as colour. Percentages stay visible in
 * private mode: they don't reveal amounts. */
export function ReturnRate({
  rate,
  perYear,
  className,
}: {
  rate: string | number | null
  perYear: boolean
  className?: string
}) {
  if (rate === null) return <span className={clsx('text-ink-3', className)}>—</span>
  const direction = trend(rate)
  const Icon = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : Minus
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 whitespace-nowrap font-medium tabular',
        direction === 'up' && 'text-positive',
        direction === 'down' && 'text-negative',
        direction === 'flat' && 'text-ink-3',
        className,
      )}
    >
      <Icon className="size-[0.85em] shrink-0" aria-hidden strokeWidth={2.5} />
      {formatPercent(rate, { signed: true, digits: 1 })}
      {perYear ? <span className="text-[0.7em] font-normal opacity-80">/ yr</span> : null}
    </span>
  )
}
