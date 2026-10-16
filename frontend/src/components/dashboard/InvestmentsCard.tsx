import { clsx } from 'clsx'
import { ChevronRight, FileUp } from 'lucide-react'
import { Link } from 'react-router'

import { useHoldings } from '../../api/hooks'
import { combinePositions, holdingTitle, type Position } from '../../lib/holdings'
import { formatMoney, formatPercent, formatPrice, formatQuantity } from '../../lib/format'
import { AssetIcon } from '../assets/AssetIcon'
import { Delta } from '../ui/Delta'
import { Card, CardHeader, EmptyState, Spinner } from '../ui/primitives'

const COLUMNS = 'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 lg:grid-cols-[minmax(0,2.4fr)_1fr_1fr_1.3fr_1.1fr_16px]'

function PositionRow({ position, currency }: { position: Position; currency: string }) {
  return (
    <Link
      to={`/holdings/${position.assetId}`}
      className={clsx(COLUMNS, 'group rounded-2xl px-3 py-3 transition-colors hover:bg-surface-2')}
    >
      <div className="flex min-w-0 items-center gap-3">
        <AssetIcon symbol={position.symbol} name={position.name} assetClass={position.assetClass} logoUrl={position.logoUrl} />
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-ink">{holdingTitle(position)}</p>
          <p className="truncate text-xs text-ink-3 tabular">
            {position.symbol} · {formatQuantity(String(position.quantity))} units
            {position.accounts > 1 ? ` · ${position.accounts} accounts` : ''}
          </p>
        </div>
      </div>
      <p className="hidden text-right text-sm tabular text-ink-2 lg:block">
        {position.avgCost === null ? '—' : formatPrice(String(position.avgCost), position.currency)}
      </p>
      <p className="hidden text-right text-sm tabular text-ink-2 lg:block">{formatPrice(position.price, position.currency)}</p>
      <div className="hidden text-right text-sm lg:block">
        <Delta amount={position.unrealizedPnl} currency={currency} className="justify-end" />
        <p className="text-xs tabular text-ink-3">{formatPercent(position.unrealizedPnlPct, { signed: true })}</p>
      </div>
      <div className="text-right">
        <p className="text-sm font-semibold tabular text-ink">{formatMoney(position.value, currency)}</p>
        <Delta amount={position.unrealizedPnl} currency={currency} className="text-xs lg:hidden" />
        <p className="hidden text-xs tabular text-ink-3 lg:block">{formatPercent(position.weight, { digits: 1 })}</p>
      </div>
      <ChevronRight
        className="hidden size-4 text-ink-3 transition-transform group-hover:translate-x-0.5 lg:block"
        aria-hidden
      />
    </Link>
  )
}

/** Every position across all accounts, Lightyear-style, each opening its holding page. */
export function InvestmentsCard({ currency }: { currency: string }) {
  const holdings = useHoldings(currency)
  const positions = combinePositions(holdings.data?.holdings ?? [])

  return (
    <Card>
      <CardHeader
        title="Investments"
        subtitle={holdings.data ? `${positions.length} position${positions.length === 1 ? '' : 's'} across all accounts` : undefined}
      />
      <div className={clsx('px-3 pb-3 pt-2 transition-opacity', holdings.isPlaceholderData && 'opacity-60')}>
        {holdings.isLoading ? (
          <Spinner className="m-6" />
        ) : positions.length === 0 ? (
          <EmptyState icon={<FileUp className="size-5" />} title="No investments yet">
            <Link to="/import" className="font-medium text-accent hover:underline">
              Import a statement
            </Link>{' '}
            to see your positions here.
          </EmptyState>
        ) : (
          <>
            <div className={clsx(COLUMNS, 'hidden px-3 pb-1 text-xs font-medium text-ink-3 lg:grid')}>
              <span>Name</span>
              <span className="text-right">Avg. buy price</span>
              <span className="text-right">Latest price</span>
              <span className="text-right">Profit</span>
              <span className="text-right">Value</span>
              <span />
            </div>
            <div className="flex flex-col gap-0.5">
              {positions.map((position) => (
                <PositionRow key={position.assetId} position={position} currency={currency} />
              ))}
            </div>
            <p className="px-3 pt-3 text-[11px] text-ink-3">
              Logos by{' '}
              <a href="https://elbstream.com" target="_blank" rel="noreferrer noopener" className="hover:text-ink">
                Elbstream
              </a>
            </p>
          </>
        )}
      </div>
    </Card>
  )
}
