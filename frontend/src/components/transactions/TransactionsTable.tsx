import { clsx } from 'clsx'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Link } from 'react-router'

import type { TransactionPage, TransactionRow } from '../../api/types'
import { formatDate, formatMoney, formatPrice, formatQuantity, TRANSACTION_TYPE_LABELS } from '../../lib/format'
import { Badge, type BadgeTone } from '../ui/primitives'
import { Sensitive } from '../ui/Sensitive'

function typeTone(type: TransactionRow['type']): BadgeTone {
  if (type === 'buy' || type === 'deposit' || type === 'transfer_in') return 'accent'
  if (type === 'dividend' || type === 'interest') return 'positive'
  if (type === 'fee' || type === 'tax') return 'negative'
  return 'neutral'
}

/** One page of ledger rows plus pager. `showAccount` adds the account column for cross-account lists. */
export function TransactionsTable({
  data,
  page,
  pageSize,
  onPageChange,
  loadingMore = false,
  showAccount = false,
}: {
  data: TransactionPage
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  loadingMore?: boolean
  showAccount?: boolean
}) {
  const pages = Math.ceil(data.total / pageSize)
  return (
    <>
      <div className={clsx('overflow-x-auto transition-opacity', loadingMore && 'opacity-60')}>
        <table className={clsx('w-full text-sm', showAccount ? 'min-w-[880px]' : 'min-w-[760px]')}>
          <thead className="text-left text-xs text-ink-3">
            <tr>
              <th className="px-6 py-3 font-medium">Date</th>
              <th className="px-3 py-3 font-medium">Type</th>
              <th className="px-3 py-3 font-medium">Asset / description</th>
              {showAccount ? <th className="px-3 py-3 font-medium">Account</th> : null}
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
                {showAccount ? (
                  <td className="max-w-[200px] px-3 py-3">
                    <Link to={`/accounts/${tx.account_id}`} className="block truncate text-ink-2 hover:text-accent hover:underline">
                      {tx.account_name}
                    </Link>
                  </td>
                ) : null}
                <td className="px-3 py-3 text-right text-ink-2"><Sensitive>{formatQuantity(tx.quantity)}</Sensitive></td>
                <td className="px-3 py-3 text-right text-ink-2">{tx.unit_price ? formatPrice(tx.unit_price, tx.currency) : '—'}</td>
                <td className="px-6 py-3 text-right">
                  <p className="text-ink"><Sensitive>{tx.amount ? formatMoney(tx.amount, tx.currency) : '—'}</Sensitive></p>
                  {Number(tx.fee) || Number(tx.tax) ? (
                    <p className="text-xs text-ink-3">
                      <Sensitive>{Number(tx.fee) ? `fee ${formatMoney(tx.fee, tx.currency)}` : ''}</Sensitive>
                      {Number(tx.fee) && Number(tx.tax) ? ' · ' : ''}
                      <Sensitive>{Number(tx.tax) ? `tax ${formatMoney(tx.tax, tx.currency)}` : ''}</Sensitive>
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
            {page * pageSize + 1}–{Math.min((page + 1) * pageSize, data.total)} of {data.total}
          </span>
          <div className="flex gap-1">
            <button
              type="button"
              className="grid size-8 place-items-center rounded-full hover:bg-surface-2 disabled:opacity-40"
              disabled={page === 0}
              onClick={() => onPageChange(page - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft className="size-4" />
            </button>
            <button
              type="button"
              className="grid size-8 place-items-center rounded-full hover:bg-surface-2 disabled:opacity-40"
              disabled={page + 1 >= pages}
              onClick={() => onPageChange(page + 1)}
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
