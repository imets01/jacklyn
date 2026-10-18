import { CircleAlert, CircleCheck, History, Trash2 } from 'lucide-react'

import { useDeleteMapping, useImportLogs, useMappings } from '../../api/hooks'
import type { AccountSummary, ImportLog } from '../../api/types'
import { formatRelativeTime } from '../../lib/format'
import { Badge, Card, CardHeader, Spinner } from '../ui/primitives'

const PRESETS = [
  { broker: 'Interactive Brokers', formats: 'Activity Statement CSV · Flex Query XML' },
  { broker: 'Lightyear', formats: 'Account statement CSV' },
  { broker: 'Erste NetBroker', formats: 'Daily reports (.xls): drop the whole folder · CSV / XLSX exports' },
  { broker: 'Anything else', formats: 'Universal column mapper for any CSV or Excel' },
]

export function SupportedFormats() {
  return (
    <Card>
      <CardHeader title="Recognized automatically" subtitle="Drop the raw export — no conversion needed." />
      <ul className="flex flex-col gap-1 px-3 pb-4 pt-3">
        {PRESETS.map((preset) => (
          <li key={preset.broker} className="flex items-start gap-3 rounded-xl px-3 py-2">
            <CircleCheck className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
            <div>
              <p className="text-sm font-medium text-ink">{preset.broker}</p>
              <p className="text-xs text-ink-3">{preset.formats}</p>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}

export function SavedPresets() {
  const mappings = useMappings()
  const remove = useDeleteMapping()
  if (!mappings.data || mappings.data.length === 0) return null
  return (
    <Card>
      <CardHeader title="Your mapping presets" subtitle="Applied automatically when the columns match." />
      <ul className="flex flex-col gap-1 px-3 pb-4 pt-3">
        {mappings.data.map((mapping) => (
          <li key={mapping.id} className="flex items-center gap-3 rounded-xl px-3 py-2 hover:bg-surface-2">
            <span className="min-w-0 flex-1 truncate text-sm text-ink">{mapping.name}</span>
            <button
              type="button"
              className="grid size-7 place-items-center rounded-full text-ink-3 hover:bg-negative-soft hover:text-negative"
              aria-label={`Delete preset ${mapping.name}`}
              onClick={() => remove.mutate(mapping.id)}
            >
              <Trash2 className="size-3.5" />
            </button>
          </li>
        ))}
      </ul>
    </Card>
  )
}

function logTitle(log: ImportLog): string {
  if (log.filename) return log.filename
  if (log.source === 'seed') return 'Demo portfolio'
  if (log.source === 'api_sync') return 'IBKR API sync'
  return 'Import'
}

export function ImportHistory({ accounts }: { accounts: AccountSummary[] }) {
  const logs = useImportLogs()
  const names = new Map(accounts.map((account) => [account.id, account.name]))
  return (
    <Card>
      <CardHeader title="Import history" subtitle="Every import is logged; re-imports skip what’s already recorded." />
      <div className="px-3 pb-4 pt-3">
        {logs.isLoading ? (
          <Spinner className="m-4" />
        ) : !logs.data || logs.data.length === 0 ? (
          <p className="px-3 py-6 text-sm text-ink-3">Nothing imported yet.</p>
        ) : (
          <ul className="flex flex-col">
            {logs.data.slice(0, 12).map((log) => (
              <li key={log.id} className="flex items-center gap-3 rounded-xl px-3 py-2.5">
                {log.status === 'failed' ? (
                  <CircleAlert className="size-4 shrink-0 text-negative" aria-label="Failed" />
                ) : (
                  <History className="size-4 shrink-0 text-ink-3" aria-hidden />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-ink">{logTitle(log)}</p>
                  <p className="truncate text-xs text-ink-3">
                    {log.account_id ? (names.get(log.account_id) ?? `Account ${log.account_id}`) : '—'} ·{' '}
                    {formatRelativeTime(log.created_at)}
                  </p>
                </div>
                <div className="text-right text-xs">
                  {log.status === 'failed' ? (
                    <Badge tone="negative">Failed</Badge>
                  ) : (
                    <>
                      <p className="font-semibold text-ink">{log.rows_imported} imported</p>
                      {log.rows_duplicate ? <p className="text-ink-3">{log.rows_duplicate} skipped</p> : null}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}
