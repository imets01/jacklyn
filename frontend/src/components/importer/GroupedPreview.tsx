import { clsx } from 'clsx'
import { ChevronRight, FileStack, FileX, Sparkles, X } from 'lucide-react'
import { useState } from 'react'

import type { AccountSummary, ImportPreview, PreviewGroup } from '../../api/types'
import { Badge, Button, Card, Select } from '../ui/primitives'
import { PreviewNotices, PreviewTable } from './PreviewParts'

const NEW_ACCOUNT = 'new'

function GroupRow({
  group,
  preview,
  accounts,
  onAccountChange,
  onNewAccount,
  disabled,
}: {
  group: PreviewGroup
  preview: ImportPreview
  accounts: AccountSummary[]
  onAccountChange: (accountId: number | null) => void
  onNewAccount: () => void
  disabled: boolean
}) {
  const [open, setOpen] = useState(false)
  const rows = preview.transactions.filter((row) => row.group === group.key)
  const skipped = group.suggested_account_id === null
  const broker = group.account_hint?.broker
  return (
    <li className="border-t border-line first:border-t-0">
      <div className="flex flex-wrap items-center gap-3 px-6 py-4">
        <button
          type="button"
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
        >
          <ChevronRight className={clsx('size-4 shrink-0 text-ink-3 transition-transform', open && 'rotate-90')} aria-hidden />
          <span className="min-w-0">
            <span className="block truncate font-medium text-ink">
              {group.label}
              {broker ? <span className="font-normal text-ink-3"> · {broker}</span> : null}
            </span>
            <span className="block text-xs text-ink-3">
              {group.summary.total} transaction{group.summary.total === 1 ? '' : 's'}
              {skipped ? (
                ' · not imported'
              ) : (
                <>
                  {' · '}
                  <span className="text-positive">{group.summary.new} new</span>
                  {group.summary.duplicates ? ` · ${group.summary.duplicates} already imported` : ''}
                </>
              )}
            </span>
          </span>
        </button>
        <Select
          className={clsx('w-auto min-w-56', skipped && 'text-ink-3')}
          value={group.suggested_account_id ?? ''}
          disabled={disabled}
          aria-label={`Import ${group.label} into`}
          onChange={(event) => {
            const value = event.target.value
            if (value === NEW_ACCOUNT) onNewAccount()
            else onAccountChange(value ? Number(value) : null)
          }}
        >
          <option value="">Don’t import</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name} · {account.broker}
            </option>
          ))}
          <option value={NEW_ACCOUNT}>New account…</option>
        </Select>
      </div>
      {open ? <PreviewTable rows={rows} /> : null}
    </li>
  )
}

/** Preview of an import that spans several accounts: many files, or one statement with sub-accounts. */
export function GroupedPreview({
  preview,
  accounts,
  onGroupAccountChange,
  onNewAccount,
  onCommit,
  committing,
  busy,
  onClear,
}: {
  preview: ImportPreview
  accounts: AccountSummary[]
  onGroupAccountChange: (group: PreviewGroup, accountId: number | null) => void
  onNewAccount: (group: PreviewGroup) => void
  onCommit: () => void
  committing: boolean
  busy: boolean
  onClear: () => void
}) {
  const chosen = preview.groups.filter((group) => group.suggested_account_id !== null)
  const newRows = chosen.reduce((sum, group) => sum + group.summary.new, 0)
  const parsers = [...new Set(preview.groups.map((group) => group.parser_key))]
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line px-6 py-5">
        <div className="flex min-w-0 items-start gap-3">
          <div className="grid size-10 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent">
            <FileStack className="size-5" aria-hidden />
          </div>
          <div className="min-w-0">
            <p className="truncate font-semibold text-ink">{preview.filename}</p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              {preview.detection && parsers.length === 1 ? (
                <Badge tone="accent">
                  <Sparkles className="size-3" aria-hidden /> {preview.detection.parser_label}
                </Badge>
              ) : null}
              <span className="text-xs text-ink-3">
                {preview.summary.total} transactions in {preview.groups.length} account
                {preview.groups.length === 1 ? '' : 's'}
              </span>
            </div>
          </div>
        </div>
        <Button size="sm" variant="ghost" onClick={onClear} aria-label="Remove files">
          <X className="size-4" aria-hidden />
        </Button>
      </div>

      <PreviewNotices preview={preview} />
      {preview.skipped_files.length ? (
        <details className="mx-6 mt-4 rounded-2xl bg-surface-2 px-4 py-3 text-sm text-ink-2">
          <summary className="flex cursor-pointer items-center gap-2 font-medium">
            <FileX className="size-4 text-ink-3" aria-hidden />
            {preview.skipped_files.length} file{preview.skipped_files.length === 1 ? '' : 's'} skipped
          </summary>
          <ul className="mt-2 flex flex-col gap-1 text-xs text-ink-3">
            {preview.skipped_files.map((file) => (
              <li key={file.filename}>
                <span className="font-medium text-ink-2">{file.filename}</span>: {file.reason}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <ul className={clsx('mt-4 border-t border-line transition-opacity', busy && 'opacity-60')}>
        {preview.groups.map((group) => (
          <GroupRow
            key={group.key}
            group={group}
            preview={preview}
            accounts={accounts}
            onAccountChange={(accountId) => onGroupAccountChange(group, accountId)}
            onNewAccount={() => onNewAccount(group)}
            disabled={busy || committing}
          />
        ))}
      </ul>

      <div className="flex flex-col gap-3 border-t border-line px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-ink-3">
          {chosen.length
            ? 'Rows already recorded are skipped, so importing the same files again is safe.'
            : 'Choose an account for at least one group.'}
        </p>
        <Button variant="primary" onClick={onCommit} loading={committing} disabled={busy || newRows === 0}>
          Import {newRows} transaction{newRows === 1 ? '' : 's'}
          {chosen.length > 1 ? ` into ${chosen.length} accounts` : ''}
        </Button>
      </div>
    </Card>
  )
}
