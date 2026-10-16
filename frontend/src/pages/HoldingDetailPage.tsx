import { ArrowLeft, ChevronRight } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'

import { useHoldingDetail } from '../api/hooks'
import type { HoldingActivity, HoldingDetail, TransactionType } from '../api/types'
import { BrokerAvatar } from '../components/accounts/AccountRow'
import { AssetIcon } from '../components/assets/AssetIcon'
import { AssetInfoCard } from '../components/holdings/AssetInfoCard'
import { PriceCard } from '../components/holdings/PriceCard'
import { PageHeader } from '../components/layout/PageHeader'
import { Delta } from '../components/ui/Delta'
import { Badge, Card, CardHeader, Spinner, type BadgeTone } from '../components/ui/primitives'
import {
  ASSET_CLASS_LABELS,
  formatDate,
  formatMoney,
  formatPercent,
  formatPrice,
  formatQuantity,
  TRANSACTION_TYPE_LABELS,
} from '../lib/format'
import { usePreferences } from '../lib/preferences-context'
import { QueryError } from './QueryError'

function Tile({ label, value, detail }: { label: string; value: ReactNode; detail?: ReactNode }) {
  return (
    <Card className="flex min-w-0 flex-col gap-2 px-5 py-4">
      <p className="text-[13px] font-medium text-ink-3">{label}</p>
      <div className="font-display text-lg font-semibold leading-tight text-ink">{value}</div>
      {detail ? <div className="text-xs text-ink-3">{detail}</div> : null}
    </Card>
  )
}

function PositionTiles({ detail }: { detail: HoldingDetail }) {
  const base = detail.base_currency
  const local = detail.asset.currency
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 sm:gap-4 xl:grid-cols-1">
      <Tile
        label="Market value"
        value={formatMoney(detail.value, base)}
        detail={local !== base ? <span className="tabular">{formatMoney(detail.value_local, local)}</span> : undefined}
      />
      <Tile
        label="Unrealized P&L"
        value={<Delta amount={detail.unrealized_pnl} pct={detail.unrealized_pnl_pct} currency={base} />}
        detail={<span className="tabular">cost basis {formatMoney(detail.cost_basis, base)}</span>}
      />
      <Tile
        label="Quantity"
        value={<span className="tabular">{formatQuantity(detail.quantity)}</span>}
        detail={detail.avg_cost ? <span className="tabular">avg. buy price {formatPrice(detail.avg_cost, local)}</span> : undefined}
      />
      <Tile
        label="Today"
        value={<Delta amount={detail.day_change} currency={base} />}
        detail={<span className="tabular">{formatPercent(detail.weight, { digits: 1 })} of your portfolio</span>}
      />
    </div>
  )
}

function AccountsCard({ detail }: { detail: HoldingDetail }) {
  const base = detail.base_currency
  return (
    <Card>
      <CardHeader title="Held in" subtitle={`${detail.accounts.length} account${detail.accounts.length === 1 ? '' : 's'}`} />
      <div className="flex flex-col gap-0.5 px-3 pb-3 pt-2">
        {detail.accounts.length === 0 ? (
          <p className="px-3 py-4 text-sm text-ink-3">You no longer hold this asset.</p>
        ) : (
          detail.accounts.map((account) => (
            <Link
              key={account.account_id}
              to={`/accounts/${account.account_id}`}
              className="group flex items-center gap-3 rounded-2xl px-3 py-3 transition-colors hover:bg-surface-2"
            >
              <BrokerAvatar broker={account.broker} className="size-9" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink">{account.account_name}</p>
                <p className="truncate text-xs text-ink-3 tabular">{formatQuantity(account.quantity)} units</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold tabular text-ink">{formatMoney(account.value, base)}</p>
                <Delta amount={account.unrealized_pnl} currency={base} className="text-xs" />
              </div>
              <ChevronRight className="size-4 shrink-0 text-ink-3 transition-transform group-hover:translate-x-0.5" aria-hidden />
            </Link>
          ))
        )}
      </div>
    </Card>
  )
}

function activityTone(type: TransactionType): BadgeTone {
  if (type === 'buy' || type === 'transfer_in') return 'accent'
  if (type === 'dividend' || type === 'interest') return 'positive'
  if (type === 'fee' || type === 'tax' || type === 'sell' || type === 'transfer_out') return 'negative'
  return 'neutral'
}

function ActivityCard({ activity, assetId }: { activity: HoldingActivity[]; assetId: number }) {
  return (
    <Card>
      <CardHeader
        title="Your activity"
        subtitle={`${activity.length} transaction${activity.length === 1 ? '' : 's'}`}
        action={
          <Link to={`/transactions?asset=${assetId}`} className="text-sm font-medium text-accent hover:underline">
            Filter in Transactions
          </Link>
        }
      />
      <div className="overflow-x-auto pt-2">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-xs text-ink-3">
            <tr>
              <th className="px-6 py-3 font-medium">Date</th>
              <th className="px-3 py-3 font-medium">Type</th>
              <th className="px-3 py-3 font-medium">Account</th>
              <th className="px-3 py-3 text-right font-medium">Quantity</th>
              <th className="px-3 py-3 text-right font-medium">Price</th>
              <th className="px-6 py-3 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody className="tabular">
            {activity.map((tx) => (
              <tr key={tx.id} className="border-t border-line">
                <td className="whitespace-nowrap px-6 py-3 text-ink-2">{formatDate(tx.date)}</td>
                <td className="px-3 py-3">
                  <Badge tone={activityTone(tx.type)}>{TRANSACTION_TYPE_LABELS[tx.type]}</Badge>
                </td>
                <td className="max-w-[200px] truncate px-3 py-3 text-ink-2">{tx.account_name}</td>
                <td className="px-3 py-3 text-right text-ink-2">{formatQuantity(tx.quantity)}</td>
                <td className="px-3 py-3 text-right text-ink-2">{tx.unit_price ? formatPrice(tx.unit_price, tx.currency) : '—'}</td>
                <td className="px-6 py-3 text-right">
                  <p className="text-ink">{tx.amount ? formatMoney(tx.amount, tx.currency) : '—'}</p>
                  {Number(tx.fee) ? <p className="text-xs text-ink-3">fee {formatMoney(tx.fee, tx.currency)}</p> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

function BackLink() {
  const location = useLocation()
  const navigate = useNavigate()
  const className = 'mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-ink-3 hover:text-ink'
  // Opened directly (bookmark, new tab): there is no in-app page to return to.
  if (location.key === 'default') {
    return (
      <Link to="/" className={className}>
        <ArrowLeft className="size-4" aria-hidden /> Dashboard
      </Link>
    )
  }
  return (
    <button type="button" onClick={() => void navigate(-1)} className={className}>
      <ArrowLeft className="size-4" aria-hidden /> Back
    </button>
  )
}

export function HoldingDetailPage() {
  const { assetId } = useParams()
  const id = Number(assetId)
  const { baseCurrency } = usePreferences()
  const holding = useHoldingDetail(baseCurrency, id)

  if (holding.isLoading) {
    return (
      <div className="grid h-96 place-items-center">
        <Spinner />
      </div>
    )
  }
  if (holding.error || !holding.data) {
    return <QueryError error={holding.error ?? new Error('Holding not found')} />
  }
  const detail = holding.data
  const { asset } = detail
  const subtitle = [asset.symbol, asset.isin, ASSET_CLASS_LABELS[asset.asset_class], asset.exchange]
    .filter(Boolean)
    .join(' · ')

  return (
    <>
      <BackLink />
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            <AssetIcon symbol={asset.symbol} name={asset.name} assetClass={asset.asset_class} logoUrl={asset.logo_url} size="lg" />
            <span className="min-w-0 break-words text-xl leading-snug sm:text-2xl lg:text-[28px] lg:leading-tight">
              {asset.name ?? asset.symbol}
            </span>
          </span>
        }
        subtitle={subtitle}
      />
      <div className="flex flex-col gap-4 sm:gap-5">
        <div className="grid grid-cols-1 gap-4 sm:gap-5 xl:grid-cols-[minmax(0,1fr)_280px]">
          <PriceCard detail={detail} />
          <PositionTiles detail={detail} />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:gap-5 lg:grid-cols-2">
          <AssetInfoCard detail={detail} />
          <AccountsCard detail={detail} />
        </div>
        <ActivityCard activity={detail.activity} assetId={asset.id} />
      </div>
    </>
  )
}
