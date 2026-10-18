import { Columns3, FileSpreadsheet, Sparkles, X } from 'lucide-react'

import type { AccountSummary, ImportPreview } from '../../api/types'
import { Badge, Button, Card, Field, Select } from '../ui/primitives'
import { PreviewNotices, PreviewTable } from './PreviewParts'

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

      <PreviewNotices preview={preview} />

      {rows.length > 0 ? (
        <div className="mt-4">
          <PreviewTable rows={rows} selected={selected} onSelectedChange={onSelectedChange} />
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
