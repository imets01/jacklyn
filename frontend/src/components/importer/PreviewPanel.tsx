import { clsx } from 'clsx'
import { CircleAlert, Columns3, FileSpreadsheet, Sparkles, TriangleAlert, X } from 'lucide-react'

import type { AccountSummary, ImportPreview } from '../../api/types'
import { formatDate, formatMoney, formatPrice, formatQuantity, TRANSACTION_TYPE_LABELS } from '../../lib/format'
import { Badge, Button, Card, Field, Notice, Select } from '../ui/primitives'
import { Sensitive } from '../ui/Sensitive'

const MAX_ROWS_SHOWN = 300

export function PreviewPanel({
  preview,
  accounts,
  accountId,
  onAccountChange,
  onNewAccount,
  selected,
  onSelectedChange,
  onCommit,
  committing,
  onOpenMapper,
  onClear,
}: {
  preview: ImportPreview
  accounts: AccountSummary[]
  accountId: number | null
  onAccountChange: (id: number | null) => void
  onNewAccount: () => void
  selected: Set<number>
  onSelectedChange: (next: Set<number>) => void
  onCommit: () => void
  committing: boolean
  onOpenMapper: (() => void) | null
  onClear: () => void
}) {
  const rows = preview.transactions
  const shown = rows.slice(0, MAX_ROWS_SHOWN)
  const allSelectable = rows.map((_, index) => index)
  const allChecked = selected.size === rows.length && rows.length > 0

  const toggle = (index: number) => {
    const next = new Set(selected)
    if (next.has(index)) next.delete(index)
    else next.add(index)
    onSelectedChange(next)
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-6 py-5">
        <div className="flex min-w-0 items-start gap-3">
          <div className="grid size-10 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent">
            <FileSpreadsheet className="size-5" aria-hidden />
          </div>
          <div className="min-w-0">
            <p className="truncate font-semibold text-ink">{preview.filename}</p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {preview.detection ? (
                <Badge tone="accent">
                  <Sparkles className="size-3" aria-hidden /> {preview.detection.parser_label}
                </Badge>
              ) : null}
              {preview.mapping_used ? <Badge tone="accent">Preset · {preview.mapping_used.name}</Badge> : null}
              {!preview.detection && !preview.mapping_used && preview.status === 'parsed' ? (
                <Badge>Custom column mapping</Badge>
              ) : null}
              <span className="text-xs text-ink-3">
                {preview.summary.total} transactions · <span className="text-positive">{preview.summary.new} new</span>
                {preview.summary.duplicates ? ` · ${preview.summary.duplicates} already imported` : ''}
                {preview.summary.errors ? (
                  <span className="text-negative"> · {preview.summary.errors} rows with errors</span>
                ) : null}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {onOpenMapper ? (
            <Button size="sm" onClick={onOpenMapper}>
              <Columns3 className="size-3.5" aria-hidden />
              {preview.detection ? 'Map columns manually' : 'Edit mapping'}
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={onClear} aria-label="Remove file">
            <X className="size-4" aria-hidden />
          </Button>
        </div>
      </div>

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

      {rows.length > 0 ? (
        <div className="mt-4 max-h-[460px] overflow-auto border-y border-line">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="sticky top-0 z-[1] bg-surface-2 text-left text-xs text-ink-3">
              <tr>
                <th className="w-10 px-4 py-2.5">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    className="size-4 accent-[var(--accent)]"
                    checked={allChecked}
                    onChange={() => onSelectedChange(allChecked ? new Set() : new Set(allSelectable))}
                  />
                </th>
                <th className="px-3 py-2.5 font-medium">Date</th>
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
                  className={clsx('border-t border-line transition-opacity', !selected.has(index) && 'opacity-45')}
                >
                  <td className="px-4 py-2">
                    <input
                      type="checkbox"
                      aria-label={`Import row ${row ?? index + 1}`}
                      className="size-4 accent-[var(--accent)]"
                      checked={selected.has(index)}
                      onChange={() => toggle(index)}
                    />
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-ink-2">{formatDate(tx.date)}</td>
                  <td className="px-3 py-2">
                    <Badge>{TRANSACTION_TYPE_LABELS[tx.type]}</Badge>
                  </td>
                  <td className="max-w-[260px] px-3 py-2">
                    <p className="truncate text-ink">{tx.symbol ?? tx.isin ?? tx.description ?? '—'}</p>
                    {tx.name ? <p className="truncate text-xs text-ink-3">{tx.name}</p> : null}
                  </td>
                  <td className="px-3 py-2 text-right text-ink-2"><Sensitive>{formatQuantity(tx.quantity)}</Sensitive></td>
                  <td className="px-3 py-2 text-right text-ink-2">{tx.unit_price ? formatPrice(tx.unit_price, tx.currency) : '—'}</td>
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
              Showing the first {MAX_ROWS_SHOWN} of {rows.length} rows. Hidden rows follow the “select all” choice.
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-col gap-4 px-6 py-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex w-full max-w-md items-end gap-2">
          <div className="flex-1">
            <Field label="Import into">
              <Select
                value={accountId ?? ''}
                onChange={(event) => onAccountChange(event.target.value ? Number(event.target.value) : null)}
              >
                <option value="">Choose an account…</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name} · {account.broker}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Button onClick={onNewAccount}>New</Button>
        </div>
        <Button variant="primary" onClick={onCommit} loading={committing} disabled={!accountId || selected.size === 0}>
          Import {selected.size} transaction{selected.size === 1 ? '' : 's'}
        </Button>
      </div>
    </Card>
  )
}
