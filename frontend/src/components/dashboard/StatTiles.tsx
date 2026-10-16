import type { ReactNode } from 'react'

import type { PortfolioSummary } from '../../api/types'
import { formatMoney } from '../../lib/format'
import { Delta } from '../ui/Delta'
import { CashBreakdown } from './CashBreakdown'
import { Card } from '../ui/primitives'

function Tile({ label, value, detail }: { label: string; value: ReactNode; detail?: ReactNode }) {
  return (
    <Card className="flex min-w-0 flex-col justify-between gap-3 px-5 py-4">
      <p className="text-[13px] font-medium text-ink-3">{label}</p>
      <div className="font-display text-xl font-semibold leading-tight text-ink sm:text-[22px]">{value}</div>
      {detail ? <div className="text-xs text-ink-3">{detail}</div> : null}
    </Card>
  )
}

export function StatTiles({ summary }: { summary: PortfolioSummary }) {
  const currency = summary.base_currency
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 sm:gap-4 xl:grid-cols-1">
      <Tile
        label="All-time P&L"
        value={<Delta amount={summary.total_pnl} currency={currency} />}
        detail={
          <span className="tabular">
            {formatMoney(summary.unrealized_pnl, currency, { signed: true })} open ·{' '}
            {formatMoney(summary.realized_pnl, currency, { signed: true })} realized
          </span>
        }
      />
      <Tile
        label="Net invested"
        value={formatMoney(summary.net_contributions, currency)}
        detail="Deposits minus withdrawals, at historical FX"
      />
      <Tile
        label="Dividends & interest"
        value={formatMoney(summary.income, currency)}
        detail={<span className="tabular">after withholding · {formatMoney(summary.costs, currency)} fees &amp; taxes</span>}
      />
      <Tile
        label="Cash"
        value={formatMoney(summary.cash, currency)}
        detail={<CashBreakdown currency={currency} />}
      />
    </div>
  )
}
