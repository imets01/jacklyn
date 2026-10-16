import { clsx } from 'clsx'
import { RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'

import { useRefreshMarket, useSummary } from '../../api/hooks'
import { BASE_CURRENCIES, type BaseCurrency } from '../../api/types'
import { formatDate, formatRelativeTime } from '../../lib/format'
import { usePreferences } from '../../lib/preferences-context'
import { SegmentedControl } from '../ui/primitives'

export function BaseCurrencySwitch() {
  const { baseCurrency, setBaseCurrency } = usePreferences()
  return (
    <SegmentedControl<BaseCurrency>
      label="Base currency"
      value={baseCurrency}
      onChange={setBaseCurrency}
      options={BASE_CURRENCIES.map((currency) => ({ value: currency, label: currency }))}
    />
  )
}

function MarketStatusChip() {
  const { baseCurrency } = usePreferences()
  const summary = useSummary(baseCurrency)
  const refresh = useRefreshMarket()
  const market = summary.data?.market
  if (!market) return null

  const refreshing = market.refreshing || refresh.isPending
  let label: string
  let dot: string
  let title: string
  if (market.synthetic_price_assets > 0 && !market.last_refresh_at) {
    label = 'Demo prices'
    dot = 'bg-warning'
    title = 'Valued with the synthetic demo history. Enable live market data to fetch real quotes.'
  } else if (market.last_refresh_error) {
    label = `Prices ${formatDate(market.prices_as_of, 'short')}`
    dot = 'bg-warning'
    title = `Last refresh failed: ${market.last_refresh_error}`
  } else if (market.live_enabled) {
    label = `Live · ${formatRelativeTime(market.last_refresh_at)}`
    dot = 'bg-positive'
    title = `Quotes via Yahoo Finance, cached. Prices as of ${formatDate(market.prices_as_of)}.`
  } else {
    label = `Prices ${formatDate(market.prices_as_of, 'short')}`
    dot = 'bg-ink-3'
    title = 'Live market data is disabled; valuing with stored prices.'
  }

  return (
    <div className="flex items-center gap-1 rounded-full border border-line bg-surface py-1 pl-3 pr-1 text-[13px] text-ink-2">
      <span className={clsx('size-1.5 rounded-full', dot)} aria-hidden />
      <span title={title} className="whitespace-nowrap">
        {label}
      </span>
      <button
        type="button"
        onClick={() => refresh.mutate()}
        disabled={!market.live_enabled || refreshing}
        className="ml-1 grid size-7 place-items-center rounded-full text-ink-3 hover:bg-surface-2 hover:text-ink disabled:opacity-40"
        title={market.live_enabled ? 'Refresh quotes and FX rates now' : 'Live market data is disabled'}
        aria-label="Refresh prices"
      >
        <RefreshCw className={clsx('size-3.5', refreshing && 'animate-spin')} aria-hidden />
      </button>
    </div>
  )
}

export function PageHeader({
  title,
  subtitle,
  actions,
  showMarket = true,
  showCurrency = true,
}: {
  title: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  showMarket?: boolean
  /** Hide on pages that show no base-currency values, where switching would do nothing. */
  showCurrency?: boolean
}) {
  return (
    <div className="mb-6 flex flex-col gap-4 lg:mb-8 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold text-ink sm:text-[28px]">{title}</h1>
        {subtitle ? <div className="mt-1 text-sm text-ink-3">{subtitle}</div> : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {actions}
        {showMarket ? <MarketStatusChip /> : null}
        {showCurrency ? <BaseCurrencySwitch /> : null}
      </div>
    </div>
  )
}
