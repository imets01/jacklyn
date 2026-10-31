import { clsx } from 'clsx'
import { ChevronDown, ChevronLeft, ChevronRight, Pencil, Trash2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import type { TransactionPage, TransactionRow } from '../../api/types'
import { formatDate, formatMoney, formatPrice, formatQuantity, TRANSACTION_TYPE_LABELS } from '../../lib/format'
import { useIsCompact } from '../../lib/media'
import { Badge, Button, type BadgeTone } from '../ui/primitives'
import { Sensitive } from '../ui/Sensitive'

function typeTone(type: TransactionRow['type']): BadgeTone {
  if (type === 'buy' || type === 'deposit' || type === 'transfer_in') return 'accent'
  if (type === 'dividend' || type === 'interest') return 'positive'
  if (type === 'fee' || type === 'tax') return 'negative'
  return 'neutral'
}

const rowAction =
  'grid size-8 place-items-center rounded-full text-ink-3 transition-opacity hover:bg-surface-2 hover:text-ink focus-visible:opacity-100 [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100'

/** The phone version of the table: one line per transaction, tap for the rest and the actions. */
function TransactionList({
  items,
  showAccount,
  onEdit,
  onDelete,
}: {
  items: TransactionRow[]
  showAccount: boolean
  onEdit?: (transaction: TransactionRow) => void
  onDelete?: (transaction: TransactionRow) => void
}) {
  const [expanded, setExpanded] = useState<number | null>(null)
  return (
    <ul className="tabular">
      {items.map((tx) => {
        const open = expanded === tx.id
        const name = tx.symbol ? (tx.name ?? tx.description) : null
        return (
          <li key={tx.id} className="border-t border-line first:border-t-0">
            <button
              type="button"
              aria-expanded={open}
              onClick={() => setExpanded(open ? null : tx.id)}
              className="flex w-full items-center gap-3 px-5 py-3 text-left transition-colors active:bg-surface-2"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink">{tx.symbol ?? tx.description ?? '—'}</span>
                <span className="mt-1 flex items-center gap-2 text-xs text-ink-3">
                  <Badge tone={typeTone(tx.type)}>{TRANSACTION_TYPE_LABELS[tx.type]}</Badge>
                  <span className="whitespace-nowrap">{formatDate(tx.date)}</span>
                </span>
              </span>
              <span className="shrink-0 text-right text-sm font-medium text-ink">
                <Sensitive>{tx.amount ? formatMoney(tx.amount, tx.currency) : '—'}</Sensitive>
              </span>
              <ChevronDown className={clsx('size-4 shrink-0 text-ink-3 transition-transform', open && 'rotate-180')} aria-hidden />
            </button>
            {open ? (
              <div className="px-5 pb-4">
                <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 rounded-2xl bg-surface-2 px-4 py-3 text-[13px]">
                  {name ? <DetailRow label="Name">{name}</DetailRow> : null}
                  {showAccount ? (
                    <DetailRow label="Account">
                      <Link to={`/accounts/${tx.account_id}`} className="font-medium text-accent">
                        {tx.account_name}
                      </Link>
                    </DetailRow>
                  ) : null}
                  {Number(tx.quantity) ? <DetailRow label="Quantity"><Sensitive>{formatQuantity(tx.quantity)}</Sensitive></DetailRow> : null}
                  {tx.unit_price ? <DetailRow label="Price">{formatPrice(tx.unit_price, tx.currency)}</DetailRow> : null}
                  {Number(tx.fee) ? <DetailRow label="Fee"><Sensitive>{formatMoney(tx.fee, tx.currency)}</Sensitive></DetailRow> : null}
                  {Number(tx.tax) ? <DetailRow label="Tax"><Sensitive>{formatMoney(tx.tax, tx.currency)}</Sensitive></DetailRow> : null}
                  {tx.manual ? <DetailRow label="Source">Entered by hand</DetailRow> : null}
                </dl>
                {onEdit || onDelete ? (
                  <div className="mt-3 flex justify-end gap-2">
                    {onDelete ? (
                      <Button size="sm" variant="ghost" onClick={() => onDelete(tx)}>
                        <Trash2 className="size-3.5" aria-hidden /> Delete
                      </Button>
                    ) : null}
                    {onEdit ? (
                      <Button size="sm" onClick={() => onEdit(tx)}>
                        <Pencil className="size-3.5" aria-hidden /> Edit
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

function DetailRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-ink-3">{label}</dt>
      <dd className="min-w-0 truncate text-right text-ink">{children}</dd>
    </>
  )
}

/** One page of ledger rows plus pager. `showAccount` adds the account column for cross-account lists. */
export function TransactionsTable({
  data,
  page,
  pageSize,
  onPageChange,
  loadingMore = false,
  showAccount = false,
  onEdit,
  onDelete,
}: {
  data: TransactionPage
  page: number
  pageSize: number
  onPageChange: (page: number) => void
  loadingMore?: boolean
  showAccount?: boolean
  onEdit?: (transaction: TransactionRow) => void
  onDelete?: (transaction: TransactionRow) => void
}) {
  const actions = Boolean(onEdit || onDelete)
  const pages = Math.ceil(data.total / pageSize)
  const compact = useIsCompact()
  return (
    <>
      <div className={clsx('overflow-x-auto transition-opacity', loadingMore && 'opacity-60')}>
        {compact ? (
          <TransactionList items={data.items} showAccount={showAccount} onEdit={onEdit} onDelete={onDelete} />
        ) : (
        <table className={clsx('w-full text-sm', showAccount ? 'min-w-[940px]' : 'min-w-[820px]')}>
          <thead className="text-left text-xs text-ink-3">
            <tr>
              <th className="px-6 py-3 font-medium">Date</th>
              <th className="px-3 py-3 font-medium">Type</th>
              <th className="px-3 py-3 font-medium">Asset / description</th>
              {showAccount ? <th className="px-3 py-3 font-medium">Account</th> : null}
              <th className="px-3 py-3 text-right font-medium">Quantity</th>
              <th className="px-3 py-3 text-right font-medium">Price</th>
              <th className={clsx('py-3 text-right font-medium', actions ? 'pl-3 pr-2' : 'px-6')}>Amount</th>
              {actions ? <th className="w-20 pr-4"><span className="sr-only">Actions</span></th> : null}
            </tr>
          </thead>
          <tbody className="tabular">
            {data.items.map((tx) => (
              <tr key={tx.id} className="group border-t border-line">
                <td className="whitespace-nowrap px-6 py-3 text-ink-2">{formatDate(tx.date)}</td>
                <td className="px-3 py-3">
                  <span className="flex flex-wrap items-center gap-1">
                    <Badge tone={typeTone(tx.type)}>{TRANSACTION_TYPE_LABELS[tx.type]}</Badge>
                    {tx.manual ? (
                      <Badge tone="neutral" title="Entered by hand">
                        Manual
                      </Badge>
                    ) : null}
                  </span>
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
                <td className={clsx('py-3 text-right', actions ? 'pl-3 pr-2' : 'px-6')}>
                  <p className="whitespace-nowrap text-ink"><Sensitive>{tx.amount ? formatMoney(tx.amount, tx.currency) : '—'}</Sensitive></p>
                  {Number(tx.fee) || Number(tx.tax) ? (
                    <p className="text-xs text-ink-3">
                      <Sensitive>{Number(tx.fee) ? `fee ${formatMoney(tx.fee, tx.currency)}` : ''}</Sensitive>
                      {Number(tx.fee) && Number(tx.tax) ? ' · ' : ''}
                      <Sensitive>{Number(tx.tax) ? `tax ${formatMoney(tx.tax, tx.currency)}` : ''}</Sensitive>
                    </p>
                  ) : null}
                </td>
                {actions ? (
                  <td className="pr-4">
                    <span className="flex justify-end">
                      {onEdit ? (
                        <button type="button" className={rowAction} onClick={() => onEdit(tx)} aria-label={`Edit ${TRANSACTION_TYPE_LABELS[tx.type]} on ${formatDate(tx.date)}`}>
                          <Pencil className="size-3.5" aria-hidden />
                        </button>
                      ) : null}
                      {onDelete ? (
                        <button type="button" className={clsx(rowAction, 'hover:text-negative')} onClick={() => onDelete(tx)} aria-label={`Delete ${TRANSACTION_TYPE_LABELS[tx.type]} on ${formatDate(tx.date)}`}>
                          <Trash2 className="size-3.5" aria-hidden />
                        </button>
                      ) : null}
                    </span>
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
        )}
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
