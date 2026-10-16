import { clsx } from 'clsx'
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'

import { formatMoney, formatPercent, trend } from '../../lib/format'

/** Signed change. Direction is carried by icon + sign as well as color, never color alone. */
export function Delta({
  amount,
  pct,
  currency,
  variant = 'text',
  className,
}: {
  amount: string | number
  pct?: string | null
  currency: string
  variant?: 'text' | 'pill'
  className?: string
}) {
  const direction = trend(amount)
  const Icon = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : Minus
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 font-medium tabular whitespace-nowrap',
        direction === 'up' && 'text-positive',
        direction === 'down' && 'text-negative',
        direction === 'flat' && 'text-ink-3',
        variant === 'pill' && 'rounded-full px-2.5 py-1 text-[13px]',
        variant === 'pill' && direction === 'up' && 'bg-positive-soft',
        variant === 'pill' && direction === 'down' && 'bg-negative-soft',
        variant === 'pill' && direction === 'flat' && 'bg-surface-2',
        className,
      )}
    >
      <Icon className="size-3.5 shrink-0" aria-hidden strokeWidth={2.5} />
      {formatMoney(amount, currency, { signed: true })}
      {pct !== undefined && pct !== null ? <span className="opacity-80">({formatPercent(pct, { signed: true })})</span> : null}
    </span>
  )
}
