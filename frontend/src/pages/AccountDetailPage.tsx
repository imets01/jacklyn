import { ArrowLeft, ChevronRight, Pencil, ReceiptText } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { useAccount, useHoldings, usePerformance } from '../api/hooks'
import { AccountFormModal } from '../components/accounts/AccountFormModal'
import { AccountTypeBadge, BrokerAvatar, TbszProgress } from '../components/accounts/AccountRow'
import { DeleteAccountCard } from '../components/accounts/DeleteAccountCard'
import { ImportedBanner } from '../components/accounts/ImportedBanner'
import { AssetIcon } from '../components/assets/AssetIcon'
import { CashBreakdown } from '../components/dashboard/CashBreakdown'
import { NetWorthCard } from '../components/dashboard/NetWorthCard'
import { ReturnRate } from '../components/returns/ReturnRate'
import { PageHeader } from '../components/layout/PageHeader'
import { Delta } from '../components/ui/Delta'
import { Button, Card, CardHeader, Spinner } from '../components/ui/primitives'
import {
  ASSET_CLASS_LABELS,
  formatDate,
  formatMoney,
  formatPercent,
  formatPrice,
  formatQuantity,
} from '../lib/format'
import { useIsCompact } from '../lib/media'
import { usePreferences } from '../lib/preferences-context'
import { QueryError } from './QueryError'
import { Sensitive } from '../components/ui/Sensitive'

function HoldingsTable({ accountId, currency }: { accountId: number; currency: string }) {
  const holdings = useHoldings(currency, accountId)
  const navigate = useNavigate()
  const compact = useIsCompact()
  if (holdings.isLoading) return <Spinner className="m-6" />
  const data = holdings.data
  if (!data || data.holdings.length === 0) {
    return <p className="px-6 py-8 text-sm text-ink-3">No open positions.</p>
  }
  if (compact) {
    return (
      <ul className="tabular pb-1">
        {data.holdings.map((holding) => (
          <li key={holding.asset_id} className="border-t border-line">
            <Link to={`/holdings/${holding.asset_id}`} className="flex items-center gap-3 px-5 py-3 transition-colors active:bg-surface-2">
              <AssetIcon
                symbol={holding.symbol}
                name={holding.name}
                assetClass={holding.asset_class}
                logoUrl={holding.logo_url}
                size="sm"
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-ink">{holding.symbol}</span>
                <span className="block truncate text-xs text-ink-3">
                  {holding.name ?? holding.isin ?? ASSET_CLASS_LABELS[holding.asset_class]}
                </span>
              </span>
              <span className="shrink-0 text-right">
                <span className="block text-sm font-semibold text-ink"><Sensitive>{formatMoney(holding.value, currency)}</Sensitive></span>
                <Delta amount={holding.unrealized_pnl} currency={currency} className="justify-end text-xs" />
              </span>
            </Link>
          </li>
        ))}
      </ul>
    )
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="text-left text-xs text-ink-3">
          <tr>
            <th className="px-6 py-3 font-medium">Asset</th>
            <th className="px-3 py-3 text-right font-medium">Quantity</th>
            <th className="px-3 py-3 text-right font-medium">Price</th>
            <th className="px-3 py-3 text-right font-medium">Value</th>
            <th className="px-3 py-3 text-right font-medium">Unrealized P&amp;L</th>
            <th className="px-6 py-3 text-right font-medium">Weight</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {data.holdings.map((holding) => (
            <tr
              key={holding.asset_id}
              className="cursor-pointer border-t border-line transition-colors hover:bg-surface-2"
              onClick={() => void navigate(`/holdings/${holding.asset_id}`)}
            >
              <td className="px-6 py-3">
                <Link
                  to={`/holdings/${holding.asset_id}`}
                  className="flex items-center gap-3"
                  onClick={(event) => event.stopPropagation()}
                >
                  <AssetIcon
                    symbol={holding.symbol}
                    name={holding.name}
                    assetClass={holding.asset_class}
                    logoUrl={holding.logo_url}
                    size="sm"
                  />
                  <span className="min-w-0">
                    <span className="block font-semibold text-ink">{holding.symbol}</span>
                    <span className="block max-w-[240px] truncate text-xs text-ink-3">
                      {holding.name ?? holding.isin ?? ASSET_CLASS_LABELS[holding.asset_class]}
                    </span>
                  </span>
                </Link>
              </td>
              <td className="px-3 py-3 text-right text-ink-2"><Sensitive>{formatQuantity(holding.quantity)}</Sensitive></td>
              <td className="px-3 py-3 text-right text-ink-2">
                {formatPrice(holding.price, holding.currency)}
                <p className="text-xs text-ink-3">{formatDate(holding.price_date, 'short')}</p>
              </td>
              <td className="px-3 py-3 text-right">
                <p className="font-semibold text-ink"><Sensitive>{formatMoney(holding.value, currency)}</Sensitive></p>
                {holding.currency !== currency ? (
                  <p className="text-xs text-ink-3"><Sensitive>{formatMoney(holding.value_local, holding.currency)}</Sensitive></p>
                ) : null}
              </td>
              <td className="px-3 py-3 text-right">
                <Delta amount={holding.unrealized_pnl} pct={holding.unrealized_pnl_pct} currency={currency} className="justify-end" />
              </td>
              <td className="px-6 py-3 text-right text-ink-2">{formatPercent(holding.weight, { digits: 1 })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function AccountDetailPage() {
  const { accountId } = useParams()
  const id = Number(accountId)
  const { baseCurrency } = usePreferences()
  const account = useAccount(baseCurrency, id)
  const [editing, setEditing] = useState(false)

  if (account.isLoading) {
    return (
      <div className="grid h-96 place-items-center">
        <Spinner />
      </div>
    )
  }
  if (account.error || !account.data) {
    return <QueryError error={account.error ?? new Error('Account not found')} />
  }
  const data = account.data

  return (
    <>
      {/* Below lg the tab bar already goes to the overview and to this account's transactions. */}
      <Link to="/accounts" className="mb-4 hidden items-center gap-1.5 text-sm font-medium text-ink-3 hover:text-ink lg:inline-flex">
        <ArrowLeft className="size-4" aria-hidden /> All accounts
      </Link>
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            <BrokerAvatar broker={data.broker} className="size-11" />
            <span className="min-w-0">
              <span className="flex flex-wrap items-center gap-2">
                {data.name} <AccountTypeBadge account={data} />
              </span>
            </span>
          </span>
        }
        subtitle={`${data.broker} · ${data.currency} account${data.external_account_id ? ` · ${data.external_account_id}` : ''}`}
        actions={
          <Button size="sm" onClick={() => setEditing(true)}>
            <Pencil className="size-3.5" aria-hidden /> Edit
          </Button>
        }
      />
      <AccountFormModal open={editing} onClose={() => setEditing(false)} account={data} />
      <ImportedBanner />
      <div className="flex flex-col gap-5">
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_280px]">
          <NetWorthCard
            title="Account value"
            accountId={id}
            summary={{ net_worth: data.value, day_change: data.day_change, day_change_pct: null, base_currency: baseCurrency }}
          />
          <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 sm:gap-4 xl:grid-cols-1">
            <Card className="px-5 py-4">
              <p className="text-[13px] font-medium text-ink-3">All-time P&amp;L</p>
              <p className="mt-2 text-lg">
                <Delta amount={data.total_pnl} currency={baseCurrency} />
              </p>
            </Card>
            <AccountReturnCard accountId={id} currency={baseCurrency} />
            <Card className="px-5 py-4">
              <p className="text-[13px] font-medium text-ink-3">Net invested</p>
              <p className="mt-2 font-display text-lg font-semibold text-ink"><Sensitive>{formatMoney(data.net_contributions, baseCurrency)}</Sensitive></p>
            </Card>
            <Card className="px-5 py-4">
              <p className="text-[13px] font-medium text-ink-3">In account currency</p>
              <p className="mt-2 font-display text-lg font-semibold text-ink">
                <Sensitive>{data.value_account_currency ? formatMoney(data.value_account_currency, data.currency) : '—'}</Sensitive>
              </p>
            </Card>
            {data.track_cash ? (
              <Card className="px-5 py-4">
                <p className="text-[13px] font-medium text-ink-3">Cash</p>
                <p className="mt-2 font-display text-lg font-semibold text-ink"><Sensitive>{formatMoney(data.cash, baseCurrency)}</Sensitive></p>
                <div className="mt-3">
                  <CashBreakdown currency={baseCurrency} accountId={id} />
                </div>
              </Card>
            ) : null}
            {data.account_type === 'tbsz' ? (
              <Card className="px-5 py-4">
                <p className="text-[13px] font-medium text-ink-3">Lock-up</p>
                <TbszProgress account={data} />
              </Card>
            ) : null}
          </div>
        </div>
        <Card>
          <CardHeader title="Holdings" subtitle={`${data.holdings_count} open positions`} />
          <div className="pt-2">
            <HoldingsTable accountId={id} currency={baseCurrency} />
          </div>
        </Card>
        <Link
          to={`/transactions?account=${id}`}
          className="group hidden items-center gap-4 rounded-3xl border border-line bg-surface px-6 py-4 lg:flex shadow-[var(--shadow-card)] transition-colors hover:bg-surface-2"
        >
          <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent">
            <ReceiptText className="size-5" aria-hidden />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-[15px] font-semibold text-ink">Transactions</span>
            <span className="block text-sm text-ink-3">
              {data.transaction_count} recorded
              {data.last_transaction_date ? ` · latest ${formatDate(data.last_transaction_date)}` : ''}
            </span>
          </span>
          <ChevronRight className="size-4 shrink-0 text-ink-3 transition-transform group-hover:translate-x-0.5" aria-hidden />
        </Link>
        <DeleteAccountCard account={data} />
      </div>
    </>
  )
}

function AccountReturnCard({ accountId, currency }: { accountId: number; currency: string }) {
  const result = usePerformance(currency, 'ALL').data?.accounts.find((row) => row.account_id === accountId)
  if (!result) return null
  return (
    <Card className="px-5 py-4">
      <p className="text-[13px] font-medium text-ink-3">Return</p>
      <div className="mt-2 flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="text-lg" title="Your money: what it earned, timing of deposits included">
          <ReturnRate rate={result.money_weighted} perYear={result.per_year} />
        </span>
        <span className="text-sm text-ink-3">
          investments <ReturnRate rate={result.time_weighted} perYear={result.per_year} />
        </span>
      </div>
      <p className="mt-1 text-xs text-ink-3">
        {result.per_year ? 'Per year' : 'In total'} since {formatDate(result.start)}
      </p>
    </Card>
  )
}
