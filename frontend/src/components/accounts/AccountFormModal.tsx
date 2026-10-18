import { Info } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { useCreateAccount, useUpdateAccount } from '../../api/hooks'
import { ACCOUNT_TYPES, type AccountCreate, type AccountSummary, type AccountType } from '../../api/types'
import { ACCOUNT_TYPE_LABELS } from '../../lib/format'
import { Modal } from '../ui/Modal'
import { Button, Field, Input, Notice, Select } from '../ui/primitives'

const COMMON_BROKERS = ['Interactive Brokers', 'Lightyear', 'Erste Bank', 'Revolut', 'Degiro', 'Trading 212', 'Swissquote', 'OTP Bank']
const CURRENCIES = ['CHF', 'EUR', 'USD', 'HUF', 'GBP']

interface AccountFormProps {
  onClose: () => void
  /** Edit this account; omit to create a new one. */
  account?: AccountSummary
  onSaved?: (account: AccountSummary) => void
  defaultBroker?: string | null
  defaultExternalId?: string | null
}

/** Create or edit an account. Mounted only while open, so every opening starts from fresh values. */
export function AccountFormModal({ open, ...props }: AccountFormProps & { open: boolean }) {
  return open ? <AccountFormDialog {...props} /> : null
}

function AccountFormDialog({ onClose, account, onSaved, defaultBroker, defaultExternalId }: AccountFormProps) {
  const [thisYear] = useState(() => new Date().getFullYear())
  const [name, setName] = useState(account?.name ?? '')
  const [broker, setBroker] = useState(account?.broker ?? defaultBroker ?? '')
  const [accountType, setAccountType] = useState<AccountType>(account?.account_type ?? 'standard')
  const [tbszYear, setTbszYear] = useState(account?.tbsz_year ?? thisYear)
  const [currency, setCurrency] = useState(account?.currency ?? 'CHF')
  const [externalId, setExternalId] = useState(account?.external_account_id ?? defaultExternalId ?? '')
  const [trackCash, setTrackCash] = useState(account?.track_cash ?? true)
  const create = useCreateAccount()
  const update = useUpdateAccount()
  const mutation = account ? update : create

  const currencies = CURRENCIES.includes(currency) ? CURRENCIES : [...CURRENCIES, currency]
  const tbszValid = accountType !== 'tbsz' || (Number.isInteger(tbszYear) && tbszYear >= 2000 && tbszYear <= thisYear + 1)
  const valid = name.trim() !== '' && broker.trim() !== '' && tbszValid

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!valid) return
    const payload: AccountCreate = {
      name: name.trim(),
      broker: broker.trim(),
      account_type: accountType,
      tbsz_year: accountType === 'tbsz' ? tbszYear : null,
      currency,
      // The broker account ID field is hidden for TBSZ accounts; keep whatever was stored.
      external_account_id: accountType === 'tbsz' && account ? account.external_account_id : externalId.trim() || null,
      track_cash: trackCash,
    }
    const onSuccess = (saved: AccountSummary) => {
      onSaved?.(saved)
      onClose()
    }
    if (account) update.mutate({ id: account.id, patch: payload }, { onSuccess })
    else create.mutate(payload, { onSuccess })
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={account ? `Edit ${account.name}` : 'New account'}
      description={account ? 'Fix a name, broker or setting.' : 'Any bank or broker works — Jacklyn is broker-agnostic.'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="account-form" loading={mutation.isPending} disabled={!valid}>
            {account ? 'Save changes' : 'Create account'}
          </Button>
        </>
      }
    >
      <form id="account-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <Field label="Account name">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Revolut Trading"
              maxLength={120}
              autoFocus
              required
            />
          </Field>
        </div>
        <Field label="Broker / bank">
          <Input
            value={broker}
            onChange={(e) => setBroker(e.target.value)}
            list="known-brokers"
            placeholder="Interactive Brokers"
            maxLength={120}
            required
          />
          <datalist id="known-brokers">
            {COMMON_BROKERS.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        </Field>
        <Field label="Account currency">
          <Select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {currencies.map((code) => (
              <option key={code}>{code}</option>
            ))}
          </Select>
        </Field>
        {account && currency !== account.currency ? (
          <div className="sm:col-span-2">
            <Notice tone="neutral" icon={<Info className="size-4" />}>
              Only the label changes from {account.currency} to {currency}. Transactions keep their own currencies,
              so no amounts are converted.
            </Notice>
          </div>
        ) : null}
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
              aria-invalid={!tbszValid}
            />
          </Field>
        ) : (
          <Field label="Broker account ID" hint="Optional — e.g. IBKR U1234567, used to match statements.">
            <Input value={externalId} onChange={(e) => setExternalId(e.target.value)} placeholder="U1234567" maxLength={64} />
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
        {mutation.error ? (
          <div className="sm:col-span-2">
            <Notice tone="negative">{mutation.error.message}</Notice>
          </div>
        ) : null}
      </form>
    </Modal>
  )
}
