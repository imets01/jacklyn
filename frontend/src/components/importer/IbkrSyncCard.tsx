import { CircleAlert, Link2, RefreshCw, Settings } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'

import { useDeleteIbkrConnection, useIbkrConnection, useRunIbkrSync, useUpdateAccount } from '../../api/hooks'
import type { AccountSummary, IbkrConnection, SyncedAccount } from '../../api/types'
import { formatRelativeTime } from '../../lib/format'
import { importedState } from '../../lib/imported'
import { AccountFormModal } from '../accounts/AccountFormModal'
import { Badge, Button, Card, CardHeader, Notice, Select } from '../ui/primitives'
import { IbkrConnectModal } from './IbkrConnectModal'

const NEW_ACCOUNT = 'new'

function statusLine(connection: IbkrConnection): string {
  if (connection.running) return 'Syncing… IBKR is preparing your statement.'
  const last = connection.last_synced_at ? `Last synced ${formatRelativeTime(connection.last_synced_at)}` : 'Not synced yet'
  if (!connection.auto_sync) return `${last} · automatic sync off`
  return `${last} · syncs automatically once a day`
}

function runText(row: SyncedAccount): string {
  const waiting = `${row.received} transaction${row.received === 1 ? '' : 's'}`
  if (row.account_id === null) return `${waiting} waiting`
  // Linked after the last run: nothing was imported or matched yet.
  if (row.received && !row.imported && !row.duplicates) return `${waiting} to import on the next sync`
  const parts = [`${row.imported} new`]
  if (row.duplicates) parts.push(`${row.duplicates} already recorded`)
  if (row.errors) parts.push(`${row.errors} unreadable`)
  return `Last run: ${parts.join(' · ')}`
}

function AccountRow({
  row,
  accounts,
  onLink,
  onNewAccount,
  linking,
}: {
  row: SyncedAccount
  accounts: AccountSummary[]
  onLink: (accountId: number) => void
  onNewAccount: () => void
  linking: boolean
}) {
  return (
    <li className="flex flex-wrap items-center gap-3 rounded-2xl px-3 py-2.5 hover:bg-surface-2/60">
      <Badge tone={row.account_id === null ? 'warning' : 'neutral'}>{row.account}</Badge>
      <div className="min-w-0 flex-1">
        {row.account_id !== null ? (
          <Link to={`/accounts/${row.account_id}`} className="block truncate text-sm font-medium text-ink hover:text-accent">
            {row.account_name}
          </Link>
        ) : (
          <p className="text-sm font-medium text-ink">Not linked to an account</p>
        )}
        <p className="text-xs text-ink-3">{runText(row)}</p>
      </div>
      {row.account_id === null ? (
        <Select
          className="w-auto min-w-48"
          value=""
          disabled={linking}
          aria-label={`Link ${row.account} to an account`}
          onChange={(e) => (e.target.value === NEW_ACCOUNT ? onNewAccount() : onLink(Number(e.target.value)))}
        >
          <option value="" disabled>
            Link to…
          </option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.name}
              {account.external_account_id ? ` (linked to ${account.external_account_id})` : ''}
            </option>
          ))}
          <option value={NEW_ACCOUNT}>New account…</option>
        </Select>
      ) : null}
    </li>
  )
}

/** One-click IBKR sync: connect once, then Sync now or let the daily auto-sync keep the ledger current. */
export function IbkrSyncCard({ accounts }: { accounts: AccountSummary[] }) {
  const connection = useIbkrConnection()
  const run = useRunIbkrSync()
  const disconnect = useDeleteIbkrConnection()
  const updateAccount = useUpdateAccount()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [newAccountFor, setNewAccountFor] = useState<string | null>(null)
  const navigate = useNavigate()
  // A run the user started (connect, Sync now, linking): once it ends, show them the account it filled.
  const awaiting = useRef(false)
  const justLinked = useRef<number | null>(null)
  const data = connection.data

  const startRun = (linkedAccountId: number | null = null) => {
    awaiting.current = true
    justLinked.current = linkedAccountId
    run.mutate()
  }

  useEffect(() => {
    if (!awaiting.current || run.isPending || !data || data.running) return
    awaiting.current = false
    // Stay here when there is something to fix: an error, or an IBKR account still to link.
    if (run.isError || data.last_status === 'failed' || data.accounts.some((row) => row.account_id === null)) return
    // The account just linked, else the one that received the most.
    const target =
      data.accounts.find((row) => row.account_id === justLinked.current) ??
      [...data.accounts].sort((a, b) => b.imported - a.imported)[0]
    if (target?.account_id) {
      navigate(`/accounts/${target.account_id}`, { state: importedState('IBKR sync', target.imported, target.duplicates) })
    }
  }, [data, run.isPending, run.isError, navigate])

  const link = (accountId: number, ibkrAccount: string) =>
    updateAccount.mutate({ id: accountId, patch: { external_account_id: ibkrAccount } }, { onSuccess: () => startRun(accountId) })

  if (connection.isLoading) return null
  if (!data) {
    return (
      <Card className="flex flex-wrap items-center gap-4 px-6 py-5">
        <div className="grid size-10 place-items-center rounded-2xl bg-accent-soft text-accent">
          <RefreshCw className="size-5" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-ink">Sync Interactive Brokers</p>
          <p className="text-sm text-ink-3">Connect a read-only Flex query once; new activity then arrives every day.</p>
        </div>
        <Button variant="primary" onClick={() => setSettingsOpen(true)}>
          Connect IBKR
        </Button>
        <IbkrConnectModal open={settingsOpen} onClose={() => setSettingsOpen(false)} onConnected={() => startRun()} />
      </Card>
    )
  }

  const busy = data.running || run.isPending
  return (
    <Card>
      <CardHeader
        title="Interactive Brokers sync"
        subtitle={statusLine(data)}
        action={
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              className="size-8 px-0"
              aria-label="IBKR sync settings"
              onClick={() => setSettingsOpen(true)}
            >
              <Settings className="size-4" aria-hidden />
            </Button>
            <Button variant="primary" size="sm" loading={busy} onClick={() => startRun()}>
              {busy ? null : <RefreshCw className="size-3.5" aria-hidden />}
              Sync now
            </Button>
          </div>
        }
      />
      <div className="flex flex-col gap-3 px-6 pb-5 pt-3">
        {data.last_status === 'failed' && data.last_message && !busy ? (
          <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
            {data.last_message}
          </Notice>
        ) : null}
        {run.error ? <Notice tone="negative">{run.error.message}</Notice> : null}
        {data.accounts.length ? (
          <ul className="-mx-3 flex flex-col gap-0.5">
            {data.accounts.map((row) => (
              <AccountRow
                key={row.account}
                row={row}
                accounts={accounts}
                onLink={(accountId) => link(accountId, row.account)}
                onNewAccount={() => setNewAccountFor(row.account)}
                linking={updateAccount.isPending}
              />
            ))}
          </ul>
        ) : null}
        {data.accounts.some((row) => row.account_id === null) && !busy ? (
          <p className="flex items-center gap-1.5 text-xs text-ink-3">
            <Link2 className="size-3.5" aria-hidden /> Link each IBKR account to a Jacklyn account; it syncs right away.
          </p>
        ) : null}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-xs text-ink-3">
          <span>
            Token {data.token_hint} · Query {data.query_id}
          </span>
          <button
            type="button"
            className="font-medium hover:text-negative disabled:opacity-50"
            disabled={disconnect.isPending || busy}
            onClick={() => {
              if (window.confirm('Disconnect IBKR? Synced transactions stay; the token is deleted.')) disconnect.mutate()
            }}
          >
            Disconnect
          </button>
        </div>
      </div>
      <IbkrConnectModal open={settingsOpen} onClose={() => setSettingsOpen(false)} connection={data} />
      <AccountFormModal
        open={newAccountFor !== null}
        onClose={() => setNewAccountFor(null)}
        defaultBroker="Interactive Brokers"
        defaultExternalId={newAccountFor}
        onSaved={(account) => startRun(account.id)}
      />
    </Card>
  )
}
