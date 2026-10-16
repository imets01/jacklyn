import { clsx } from 'clsx'
import { ArrowLeft, ChevronLeft, ChevronRight, FileUp } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { useAccount, useHoldings, useTransactions } from '../api/hooks'
import type { TransactionRow } from '../api/types'
import { AccountTypeBadge, BrokerAvatar, TbszProgress } from '../components/accounts/AccountRow'
import { NetWorthCard } from '../components/dashboard/NetWorthCard'
import { PageHeader } from '../components/layout/PageHeader'
import { Delta } from '../components/ui/Delta'
import { Badge, Card, CardHeader, EmptyState, Spinner, type BadgeTone } from '../components/ui/primitives'
import {
  formatDate,
  formatMoney,
  formatPercent,
  formatPrice,
  formatQuantity,
  TRANSACTION_TYPE_LABELS,
} from '../lib/format'
import { usePreferences } from '../lib/preferences-context'
import { QueryError } from './QueryError'

const PAGE_SIZE = 50

function typeTone(type: TransactionRow['type']): BadgeTone {
  if (type === 'buy' || type === 'deposit' || type === 'transfer_in') return 'accent'
  if (type === 'dividend' || type === 'interest') return 'positive'
  if (type === 'fee' || type === 'tax') return 'negative'
  return 'neutral'
}

function HoldingsTable({ accountId, currency }: { accountId: number; currency: string }) {
  const holdings = useHoldings(currency, accountId)
  if (holdings.isLoading) return <Spinner className="m-6" />
  const data = holdings.data
  if (!data || (data.holdings.length === 0 && data.cash.length === 0)) {
    return <p className="px-6 py-8 text-sm text-ink-3">No open positions.</p>
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
            <tr key={holding.asset_id} className="border-t border-line">
              <td className="px-6 py-3">
                <p className="font-semibold text-ink">{holding.symbol}</p>
                <p className="max-w-[260px] truncate text-xs text-ink-3">{holding.name ?? holding.isin ?? holding.asset_class}</p>
              </td>
              <td className="px-3 py-3 text-right text-ink-2">{formatQuantity(holding.quantity)}</td>
              <td className="px-3 py-3 text-right text-ink-2">
                {formatPrice(holding.price, holding.currency)}
                <p className="text-xs text-ink-3">{formatDate(holding.price_date, 'short')}</p>
              </td>
              <td className="px-3 py-3 text-right">
                <p className="font-semibold text-ink">{formatMoney(holding.value, currency)}</p>
                {holding.currency !== currency ? (
                  <p className="text-xs text-ink-3">{formatMoney(holding.value_local, holding.currency)}</p>
                ) : null}
              </td>
              <td className="px-3 py-3 text-right">
                <Delta amount={holding.unrealized_pnl} pct={holding.unrealized_pnl_pct} currency={currency} className="justify-end" />
              </td>
              <td className="px-6 py-3 text-right text-ink-2">{formatPercent(holding.weight, { digits: 1 })}</td>
            </tr>
          ))}
          {data.cash.map((cash) => (
            <tr key={cash.currency} className="border-t border-line">
              <td className="px-6 py-3">
                <p className="font-semibold text-ink">Cash {cash.currency}</p>
                <p className="text-xs text-ink-3">Settled balance</p>
              </td>
              <td className="px-3 py-3 text-right text-ink-2" colSpan={2}>
                {formatMoney(cash.amount, cash.currency)}
              </td>
              <td className="px-3 py-3 text-right font-semibold text-ink">{formatMoney(cash.value, currency)}</td>
              <td colSpan={2} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TransactionsTable({ accountId }: { accountId: number }) {
  const [page, setPage] = useState(0)
  const transactions = useTransactions(accountId, page, PAGE_SIZE)
  if (transactions.isLoading) return <Spinner className="m-6" />
  const data = transactions.data
  if (!data || data.total === 0) {
    return (
      <EmptyState icon={<FileUp className="size-5" />} title="No transactions yet">
        <Link to="/import" className="font-medium text-accent hover:underline">
          Import a statement
        </Link>{' '}
        to fill this account.
      </EmptyState>
    )
  }
  const pages = Math.ceil(data.total / PAGE_SIZE)
  return (
    <>
      <div className={clsx('overflow-x-auto transition-opacity', transactions.isPlaceholderData && 'opacity-60')}>
        <table className="w-full min-w-[760px] text-sm">
          <thead className="text-left text-xs text-ink-3">
            <tr>
              <th className="px-6 py-3 font-medium">Date</th>
              <th className="px-3 py-3 font-medium">Type</th>
              <th className="px-3 py-3 font-medium">Asset / description</th>
              <th className="px-3 py-3 text-right font-medium">Quantity</th>
              <th className="px-3 py-3 text-right font-medium">Price</th>
              <th className="px-6 py-3 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody className="tabular">
            {data.items.map((tx) => (
              <tr key={tx.id} className="border-t border-line">
                <td className="whitespace-nowrap px-6 py-3 text-ink-2">{formatDate(tx.date)}</td>
                <td className="px-3 py-3">
                  <Badge tone={typeTone(tx.type)}>{TRANSACTION_TYPE_LABELS[tx.type]}</Badge>
                </td>
                <td className="max-w-[320px] px-3 py-3">
                  <p className="truncate text-ink">{tx.symbol ?? tx.description ?? '—'}</p>
                  {tx.symbol && (tx.name ?? tx.description) ? (
                    <p className="truncate text-xs text-ink-3">{tx.name ?? tx.description}</p>
                  ) : null}
                </td>
                <td className="px-3 py-3 text-right text-ink-2">{formatQuantity(tx.quantity)}</td>
                <td className="px-3 py-3 text-right text-ink-2">{tx.unit_price ? formatPrice(tx.unit_price, tx.currency) : '—'}</td>
                <td className="px-6 py-3 text-right">
                  <p className="text-ink">{tx.amount ? formatMoney(tx.amount, tx.currency) : '—'}</p>
                  {Number(tx.fee) || Number(tx.tax) ? (
                    <p className="text-xs text-ink-3">
                      {Number(tx.fee) ? `fee ${formatMoney(tx.fee, tx.currency)}` : ''}
                      {Number(tx.fee) && Number(tx.tax) ? ' · ' : ''}
                      {Number(tx.tax) ? `tax ${formatMoney(tx.tax, tx.currency)}` : ''}
                    </p>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pages > 1 ? (
        <div className="flex items-center justify-between border-t border-line px-6 py-3 text-sm text-ink-3">
          <span>
            {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, data.total)} of {data.total}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              className="grid size-8 place-items-center rounded-full hover:bg-surface-2 disabled:opacity-40"
              disabled={page === 0}
              onClick={() => setPage((p) => p - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              type="button"
              className="grid size-8 place-items-center rounded-full hover:bg-surface-2 disabled:opacity-40"
              disabled={page + 1 >= pages}
              onClick={() => setPage((p) => p + 1)}
              aria-label="Next page"
            >
              <ChevronRight className="size-4" />
            </button>
          </div>
        </div>
      ) : null}
    </>
  )
}

export function AccountDetailPage() {
  const { accountId } = useParams()
  const id = Number(accountId)
  const { baseCurrency } = usePreferences()
  const account = useAccount(baseCurrency, id)

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
      <Link to="/accounts" className="mb-4 inline-flex items-center gap-1.5 text-sm font-medium text-ink-3 hover:text-ink">
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
      />
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
            <Card className="px-5 py-4">
              <p className="text-[13px] font-medium text-ink-3">Net invested</p>
              <p className="mt-2 font-display text-lg font-semibold text-ink">{formatMoney(data.net_contributions, baseCurrency)}</p>
            </Card>
            <Card className="px-5 py-4">
              <p className="text-[13px] font-medium text-ink-3">In account currency</p>
              <p className="mt-2 font-display text-lg font-semibold text-ink">
                {data.value_account_currency ? formatMoney(data.value_account_currency, data.currency) : '—'}
              </p>
            </Card>
            <Card className="px-5 py-4">
              <p className="text-[13px] font-medium text-ink-3">{data.account_type === 'tbsz' ? 'Lock-up' : 'Cash'}</p>
              {data.account_type === 'tbsz' ? (
                <TbszProgress account={data} />
              ) : (
                <p className="mt-2 font-display text-lg font-semibold text-ink">{formatMoney(data.cash, baseCurrency)}</p>
              )}
            </Card>
          </div>
        </div>
        <Card>
          <CardHeader title="Holdings" subtitle={`${data.holdings_count} open positions`} />
          <div className="pt-2">
            <HoldingsTable accountId={id} currency={baseCurrency} />
          </div>
        </Card>
        <Card>
          <CardHeader title="Transactions" subtitle={`${data.transaction_count} recorded`} />
          <div className="pt-2">
            <TransactionsTable accountId={id} />
          </div>
        </Card>
      </div>
    </>
  )
}
