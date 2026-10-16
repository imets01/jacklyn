import { useState, type FormEvent } from 'react'

import { useCreateAccount } from '../../api/hooks'
import { ACCOUNT_TYPES, type AccountSummary, type AccountType } from '../../api/types'
import { ACCOUNT_TYPE_LABELS } from '../../lib/format'
import { Modal } from '../ui/Modal'
import { Button, Field, Input, Notice, Select } from '../ui/primitives'

const COMMON_BROKERS = ['Interactive Brokers', 'Lightyear', 'Erste Bank', 'Revolut', 'Degiro', 'Trading 212', 'Swissquote', 'OTP Bank']
const CURRENCIES = ['CHF', 'EUR', 'USD', 'HUF', 'GBP']

export function NewAccountModal({
  open,
  onClose,
  onCreated,
  defaultBroker,
}: {
  open: boolean
  onClose: () => void
  onCreated?: (account: AccountSummary) => void
  defaultBroker?: string | null
}) {
  const [thisYear] = useState(() => new Date().getFullYear())
  const [name, setName] = useState('')
  const [broker, setBroker] = useState(defaultBroker ?? '')
  const [accountType, setAccountType] = useState<AccountType>('standard')
  const [tbszYear, setTbszYear] = useState(thisYear)
  const [currency, setCurrency] = useState('CHF')
  const [externalId, setExternalId] = useState('')
  const [trackCash, setTrackCash] = useState(true)
  const create = useCreateAccount()

  const submit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate(
      {
        name: name.trim(),
        broker: broker.trim(),
        account_type: accountType,
        tbsz_year: accountType === 'tbsz' ? tbszYear : null,
        currency,
        external_account_id: externalId.trim() || null,
        track_cash: trackCash,
      },
      {
        onSuccess: (account) => {
          onCreated?.(account)
          setName('')
          setExternalId('')
          onClose()
        },
      },
    )
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New account"
      description="Any bank or broker works — Jacklyn is broker-agnostic."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="new-account" loading={create.isPending} disabled={!name.trim() || !broker.trim()}>
            Create account
          </Button>
        </>
      }
    >
      <form id="new-account" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Account name">
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Revolut Trading" autoFocus required />
          </Field>
        </div>
        <Field label="Broker / bank">
          <Input value={broker} onChange={(e) => setBroker(e.target.value)} list="known-brokers" placeholder="Interactive Brokers" required />
          <datalist id="known-brokers">
            {COMMON_BROKERS.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        </Field>
        <Field label="Account currency">
          <Select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {CURRENCIES.map((code) => (
              <option key={code}>{code}</option>
            ))}
          </Select>
        </Field>
        <Field label="Account type">
          <Select value={accountType} onChange={(e) => setAccountType(e.target.value as AccountType)}>
            {ACCOUNT_TYPES.map((type) => (
              <option key={type} value={type}>
                {ACCOUNT_TYPE_LABELS[type]}
              </option>
            ))}
          </Select>
        </Field>
        {accountType === 'tbsz' ? (
          <Field label="TBSZ vintage year" hint="The collection year deposits are made in.">
            <Input
              type="number"
              min={2000}
              max={thisYear + 1}
              value={tbszYear}
              onChange={(e) => setTbszYear(Number(e.target.value))}
            />
          </Field>
        ) : (
          <Field label="Broker account ID" hint="Optional — e.g. IBKR U1234567, used to match statements.">
            <Input value={externalId} onChange={(e) => setExternalId(e.target.value)} placeholder="U1234567" />
          </Field>
        )}
        <label className="flex items-start gap-3 rounded-2xl bg-surface-2 px-4 py-3 text-sm sm:col-span-2">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-[var(--accent)]"
            checked={trackCash}
            onChange={(e) => setTrackCash(e.target.checked)}
          />
          <span>
            <span className="font-medium text-ink">Track cash balance</span>
            <span className="block text-ink-3">
              Turn off for trades-only exports without deposits, so buys count as money invested.
            </span>
          </span>
        </label>
        {create.error ? (
          <div className="sm:col-span-2">
            <Notice tone="negative">{create.error.message}</Notice>
          </div>
        ) : null}
      </form>
    </Modal>
  )
}
