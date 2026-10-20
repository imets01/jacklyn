import { DatabaseBackup, Download, KeyRound, Trash2, TriangleAlert, Upload } from 'lucide-react'
import { useRef, useState } from 'react'

import { backupDownloadUrl, useBackups, useCreateBackup, useDeleteBackup, useRestoreBackup, type Backup } from '../../api/auth'
import { Modal } from '../../components/ui/Modal'
import { Badge, Button, Card, CardHeader, Field, Input, Notice, Spinner } from '../../components/ui/primitives'
import { formatDate, formatRelativeTime } from '../../lib/format'

const KIND_LABELS: Record<Backup['kind'], string> = {
  manual: 'Manual',
  daily: 'Daily',
  'before-restore': 'Before restore',
}

function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Replace the whole database with an uploaded backup, after typing RESTORE. */
function RestoreModal({ file, onClose }: { file: File; onClose: () => void }) {
  const restore = useRestoreBackup()
  const [typed, setTyped] = useState('')
  const done = restore.isSuccess
  return (
    <Modal
      open
      onClose={done ? () => window.location.reload() : onClose}
      title={done ? 'Backup restored' : 'Restore this backup?'}
      description={`${file.name} · ${formatSize(file.size)}`}
      footer={
        done ? (
          <Button variant="primary" onClick={() => window.location.reload()}>
            Reload Jacklyn
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button variant="danger" loading={restore.isPending} disabled={typed !== 'RESTORE'} onClick={() => restore.mutate(file)}>
              Replace everything
            </Button>
          </>
        )
      }
    >
      {done ? (
        <Notice tone="positive">
          Restored. The data from just before is kept as <span className="font-medium">{restore.data.safety_backup.name}</span>, in
          case you need it back. Reload to see the restored data; you may have to sign in again.
        </Notice>
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-ink-2">
            Every person's accounts, transactions and settings are replaced by what's in the backup. A copy of the current data is
            saved first.
          </p>
          <Field label="Type RESTORE to confirm">
            <Input value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" spellCheck={false} />
          </Field>
          {restore.error ? <Notice tone="negative">{restore.error.message}</Notice> : null}
        </div>
      )}
    </Modal>
  )
}

/** Admin only: the backup holds everyone's data. */
export function BackupsSection() {
  const backups = useBackups(true)
  const create = useCreateBackup()
  const remove = useDeleteBackup()
  const picker = useRef<HTMLInputElement>(null)
  const [restoring, setRestoring] = useState<File | null>(null)
  const data = backups.data
  const latest = data?.backups[0]

  return (
    <section className="flex flex-col gap-5">
      <h2 className="text-lg font-semibold text-ink">Backups</h2>
      <Card>
        <CardHeader
          title="Database backups"
          subtitle={
            latest ? `Latest ${formatRelativeTime(latest.created_at)} · everyone's data in one file` : "Everyone's data in one file"
          }
          action={
            data?.supported ? (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => picker.current?.click()}>
                  <Upload className="size-3.5" aria-hidden /> Restore…
                </Button>
                <Button size="sm" variant="primary" loading={create.isPending} onClick={() => create.mutate()}>
                  <DatabaseBackup className="size-3.5" aria-hidden /> Back up now
                </Button>
              </div>
            ) : undefined
          }
        />
        <input
          ref={picker}
          type="file"
          accept=".db,.sqlite,.sqlite3,application/vnd.sqlite3"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0]
            if (file) setRestoring(file)
            event.target.value = ''
          }}
        />
        <div className="flex flex-col gap-3 px-6 pb-5 pt-3">
          {backups.isLoading ? <Spinner /> : null}
          {data && !data.supported ? (
            <Notice tone="neutral" icon={<TriangleAlert className="size-4" />}>
              Backups from the app work with SQLite. With PostgreSQL, back up with <code>pg_dump</code>.
            </Notice>
          ) : null}
          {data?.supported ? (
            <>
              <p className="text-sm text-ink-3">
                {data.automatic ? 'A copy is made every day; the last 14 are kept. ' : ''}
                Stored on the server in <code className="break-all text-xs">{data.folder}</code>. Download one now and then to keep a copy
                somewhere else too.
              </p>
              <Notice tone="neutral" icon={<KeyRound className="size-4" />}>
                Two-step codes and the IBKR token are encrypted with the server's <code>secret.key</code>, which isn't in the backup.
                Restoring on this server needs nothing else; on a new one, copy that key across as well.
              </Notice>
              {create.error ? <Notice tone="negative">{create.error.message}</Notice> : null}
              {data.backups.length ? (
                <ul className="-mx-3 flex flex-col">
                  {data.backups.map((backup) => (
                    <li key={backup.name} className="flex items-center gap-3 rounded-xl px-3 py-2.5 hover:bg-surface-2">
                      <DatabaseBackup className="size-4 shrink-0 text-ink-3" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
                          {formatDate(backup.created_at, 'long')}{' '}
                          {new Date(backup.created_at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}
                          <Badge tone={backup.kind === 'manual' ? 'accent' : 'neutral'}>{KIND_LABELS[backup.kind]}</Badge>
                        </p>
                        <p className="text-xs text-ink-3">{formatSize(backup.size)}</p>
                      </div>
                      <a
                        href={backupDownloadUrl(backup.name)}
                        download={backup.name}
                        className="inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] font-medium text-ink-2 hover:bg-surface hover:text-ink"
                      >
                        <Download className="size-3.5" aria-hidden /> Download
                      </a>
                      <button
                        type="button"
                        className="grid size-8 place-items-center rounded-full text-ink-3 hover:bg-surface hover:text-negative"
                        onClick={() => remove.mutate(backup.name)}
                        aria-label={`Delete backup from ${formatDate(backup.created_at)}`}
                      >
                        <Trash2 className="size-3.5" aria-hidden />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-ink-3">No backups yet.</p>
              )}
            </>
          ) : null}
        </div>
      </Card>
      {restoring ? <RestoreModal file={restoring} onClose={() => setRestoring(null)} /> : null}
    </section>
  )
}
