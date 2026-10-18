import { clsx } from 'clsx'
import { CircleAlert, TriangleAlert } from 'lucide-react'

import type { ImportPreview, PreviewTransaction } from '../../api/types'
import { formatDate, formatMoney, formatPrice, formatQuantity, TRANSACTION_TYPE_LABELS } from '../../lib/format'
import { Badge, Notice } from '../ui/primitives'
import { Sensitive } from '../ui/Sensitive'

const MAX_ROWS_SHOWN = 300

/** The preview's message, parser warnings and unreadable rows. */
export function PreviewNotices({ preview }: { preview: ImportPreview }) {
  return (
    <div className="flex flex-col gap-3 px-6 pt-4 empty:hidden">
      {preview.message ? <Notice icon={<CircleAlert className="size-4" />}>{preview.message}</Notice> : null}
      {preview.warnings.map((warning) => (
        <Notice key={warning} icon={<TriangleAlert className="size-4" />}>
          {warning}
        </Notice>
      ))}
      {preview.errors.length > 0 ? (
        <details className="rounded-2xl bg-negative-soft px-4 py-3 text-sm text-negative">
          <summary className="cursor-pointer font-medium">
            {preview.summary.errors} row{preview.summary.errors === 1 ? '' : 's'} couldn’t be read — they won’t be imported
          </summary>
          <ul className="mt-2 flex flex-col gap-1 text-xs">
            {preview.errors.map((error, index) => (
              <li key={index}>
                {error.row !== null ? <span className="font-semibold">Row {error.row}: </span> : null}
                {error.message}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}

/**
 * Normalized rows as they will be imported. With `selected`, each row gets a checkbox (indexes into `rows`);
 * without, rows already recorded are dimmed because they are skipped anyway.
 */
export function PreviewTable({
  rows,
  selected,
  onSelectedChange,
}: {
  rows: PreviewTransaction[]
  selected?: Set<number>
  onSelectedChange?: (next: Set<number>) => void
}) {
  const shown = rows.slice(0, MAX_ROWS_SHOWN)
  const selectable = selected !== undefined && onSelectedChange !== undefined
  const allChecked = selectable && selected.size === rows.length && rows.length > 0
  const included = (index: number, duplicate: boolean) => (selectable ? selected.has(index) : !duplicate)

  const toggle = (index: number) => {
    if (!selectable) return
    const next = new Set(selected)
    if (next.has(index)) next.delete(index)
    else next.add(index)
    onSelectedChange(next)
  }

  return (
    <div className="max-h-[460px] overflow-auto border-y border-line">
      <table className="w-full min-w-[820px] text-sm">
        <thead className="sticky top-0 z-[1] bg-surface-2 text-left text-xs text-ink-3">
          <tr>
            {selectable ? (
              <th className="w-10 px-4 py-2.5">
                <input
                  type="checkbox"
                  aria-label="Select all"
                  className="size-4 accent-[var(--accent)]"
                  checked={allChecked}
                  onChange={() => onSelectedChange(allChecked ? new Set() : new Set(rows.map((_, index) => index)))}
                />
              </th>
            ) : null}
            <th className={clsx('py-2.5 font-medium', selectable ? 'px-3' : 'pl-6 pr-3')}>Date</th>
            <th className="px-3 py-2.5 font-medium">Type</th>
            <th className="px-3 py-2.5 font-medium">Asset / description</th>
            <th className="px-3 py-2.5 text-right font-medium">Quantity</th>
            <th className="px-3 py-2.5 text-right font-medium">Price</th>
            <th className="px-3 py-2.5 text-right font-medium">Amount</th>
            <th className="px-3 py-2.5 text-right font-medium">Fee / tax</th>
            <th className="px-4 py-2.5 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {shown.map(({ transaction: tx, duplicate, row }, index) => (
            <tr
              key={index}
              className={clsx('border-t border-line transition-opacity', !included(index, duplicate) && 'opacity-45')}
            >
              {selectable ? (
                <td className="px-4 py-2">
                  <input
                    type="checkbox"
                    aria-label={`Import row ${row ?? index + 1}`}
                    className="size-4 accent-[var(--accent)]"
                    checked={selected.has(index)}
                    onChange={() => toggle(index)}
                  />
                </td>
              ) : null}
              <td className={clsx('whitespace-nowrap py-2 text-ink-2', selectable ? 'px-3' : 'pl-6 pr-3')}>
                {formatDate(tx.date)}
              </td>
              <td className="px-3 py-2">
                <Badge>{TRANSACTION_TYPE_LABELS[tx.type]}</Badge>
              </td>
              <td className="max-w-[260px] px-3 py-2">
                <p className="truncate text-ink">{tx.symbol ?? tx.isin ?? tx.description ?? '—'}</p>
                {tx.name ? <p className="truncate text-xs text-ink-3">{tx.name}</p> : null}
              </td>
              <td className="px-3 py-2 text-right text-ink-2">
                <Sensitive>{formatQuantity(tx.quantity)}</Sensitive>
              </td>
              <td className="px-3 py-2 text-right text-ink-2">
                {tx.unit_price ? formatPrice(tx.unit_price, tx.currency) : '—'}
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right text-ink">
                <Sensitive>{tx.amount ? formatMoney(tx.amount, tx.currency) : '—'}</Sensitive>
              </td>
              <td className="whitespace-nowrap px-3 py-2 text-right text-xs text-ink-3">
                <Sensitive>{Number(tx.fee) ? formatMoney(tx.fee, tx.currency) : ''}</Sensitive>
                {Number(tx.fee) && Number(tx.tax) ? ' · ' : ''}
                <Sensitive>{Number(tx.tax) ? formatMoney(tx.tax, tx.currency) : ''}</Sensitive>
              </td>
              <td className="px-4 py-2">
                {duplicate ? <Badge tone="warning">Already imported</Badge> : <Badge tone="positive">New</Badge>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > MAX_ROWS_SHOWN ? (
        <p className="border-t border-line px-6 py-3 text-xs text-ink-3">
          Showing the first {MAX_ROWS_SHOWN} of {rows.length} rows.
          {selectable ? ' Hidden rows follow the “select all” choice.' : ''}
        </p>
      ) : null}
    </div>
  )
}
