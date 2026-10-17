import { useState } from 'react'

import { useHoldings } from '../../api/hooks'
import { combineCash } from '../../lib/holdings'
import { formatMoney } from '../../lib/format'
import { usePreferences } from '../../lib/preferences-context'
import { CurrencyIcon } from '../assets/AssetIcon'
import { Sensitive } from '../ui/Sensitive'

const VISIBLE = 3

/** Cash per currency, in each currency's own amount, under the Cash total. Largest balances first. */
export function CashBreakdown({ currency, accountId }: { currency: string; accountId?: number }) {
  const holdings = useHoldings(currency, accountId)
  const { hideAmounts } = usePreferences()
  const [expanded, setExpanded] = useState(false)
  const cash = combineCash(holdings.data?.cash ?? [])
  if (cash.length === 0) return null
  const visible = expanded ? cash : cash.slice(0, VISIBLE)

  return (
    <div className="flex flex-col gap-1.5">
      <ul className="flex flex-col gap-1.5" aria-label="Cash by currency">
        {visible.map((total) => (
          <li
            key={total.currency}
            className="flex min-w-0 items-center gap-2 text-xs"
            title={total.currency !== currency && !hideAmounts ? `≈ ${formatMoney(total.value, currency)}` : undefined}
          >
            <CurrencyIcon currency={total.currency} logoUrl={total.logoUrl} size="xs" />
            <span className="tabular font-medium text-ink-2"><Sensitive>{formatMoney(total.amount, total.currency)}</Sensitive></span>
          </li>
        ))}
      </ul>
      {cash.length > VISIBLE ? (
        <button
          type="button"
          className="self-start text-xs font-medium text-accent hover:underline"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
        >
          {expanded ? 'Show less' : `+${cash.length - VISIBLE} more`}
        </button>
      ) : null}
    </div>
  )
}
