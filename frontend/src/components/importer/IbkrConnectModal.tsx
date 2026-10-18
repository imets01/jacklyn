import { useState, type FormEvent } from 'react'

import { useSaveIbkrConnection } from '../../api/hooks'
import type { IbkrConnection } from '../../api/types'
import { Modal } from '../ui/Modal'
import { Button, Field, Input, Notice } from '../ui/primitives'

const STEPS = [
  <>
    In IBKR&apos;s Client Portal open <b>Performance &amp; Reports → Flex Queries</b> and create an{' '}
    <b>Activity Flex Query</b> with the sections <b>Trades</b> (executions), <b>Cash Transactions</b> and{' '}
    <b>Account Information</b>. Format <b>XML</b>, period <b>Last 365 calendar days</b>.
  </>,
  <>
    On the same page open <b>Flex Web Service</b>, turn it on and generate a token. It can only read
    reports; it can&apos;t trade or move money.
  </>,
  <>Paste the token and the query&apos;s ID below. Older history: import Activity Statement files once.</>,
]

interface ConnectProps {
  onClose: () => void
  /** Edit this connection; omit to connect for the first time. */
  connection?: IbkrConnection
  onConnected?: () => void
}

/** Connect or edit the IBKR Flex Web Service connection. Mounted only while open, so it starts fresh. */
export function IbkrConnectModal({ open, ...props }: ConnectProps & { open: boolean }) {
  return open ? <ConnectDialog {...props} /> : null
}

function ConnectDialog({ onClose, connection, onConnected }: ConnectProps) {
  const [token, setToken] = useState('')
  const [queryId, setQueryId] = useState(connection?.query_id ?? '')
  const [autoSync, setAutoSync] = useState(connection?.auto_sync ?? true)
  const save = useSaveIbkrConnection()
  const tokenValid = token === '' ? Boolean(connection) : /^\S{8,128}$/.test(token)
  const valid = tokenValid && /^\d{1,20}$/.test(queryId)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!valid) return
    save.mutate(
      { ...(token ? { token } : {}), query_id: queryId, auto_sync: autoSync },
      {
        onSuccess: () => {
          if (!connection) onConnected?.()
          onClose()
        },
      },
    )
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={connection ? 'IBKR sync settings' : 'Connect Interactive Brokers'}
      description="Jacklyn pulls trades, dividends and deposits through IBKR's read-only Flex Web Service."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="ibkr-connect" disabled={!valid} loading={save.isPending}>
            {connection ? 'Save' : 'Connect and sync'}
          </Button>
        </>
      }
    >
      <form id="ibkr-connect" onSubmit={submit} className="flex flex-col gap-4">
        {connection ? null : (
          <ol className="flex flex-col gap-2.5 rounded-2xl bg-surface-2/60 px-4 py-3 text-sm text-ink-2">
            {STEPS.map((step, index) => (
              <li key={index} className="flex gap-3">
                <span className="grid size-5 shrink-0 place-items-center rounded-full bg-accent-soft text-xs font-semibold text-accent">
                  {index + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        )}
        <Field
          label="Flex token"
          hint={connection ? 'Leave empty to keep the current token.' : 'Stored encrypted and never shown again.'}
        >
          <Input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => setToken(e.target.value.trim())}
            placeholder={connection ? `Current token ${connection.token_hint}` : 'Paste the token'}
            maxLength={128}
          />
        </Field>
        <Field label="Query ID">
          <Input
            inputMode="numeric"
            value={queryId}
            onChange={(e) => setQueryId(e.target.value.replace(/\D/g, '').slice(0, 20))}
            placeholder="e.g. 1234567"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm text-ink-2">
          <input
            type="checkbox"
            className="size-4 accent-[var(--accent)]"
            checked={autoSync}
            onChange={(e) => setAutoSync(e.target.checked)}
          />
          Sync automatically once a day
        </label>
        {save.error ? <Notice tone="negative">{save.error.message}</Notice> : null}
      </form>
    </Modal>
  )
}
