import { ArrowRight, Info } from 'lucide-react'
import { useState, type FormEvent, type ReactNode } from 'react'

import { ApiError } from '../../api/client'
import { useAccounts, useAddTransactions, useAssetOptions, useEditTransaction } from '../../api/hooks'
import type { AssetOption, TransactionInput, TransactionRow, TransactionType } from '../../api/types'
import { useDebounced } from '../../lib/debounce'
import { formatMoney, TRANSACTION_TYPE_LABELS } from '../../lib/format'
import { usePreferences } from '../../lib/preferences-context'
import { Modal } from '../ui/Modal'
import { Button, Field, Input, Notice, SegmentedControl, Select } from '../ui/primitives'

const TYPE_GROUPS: { label: string; types: TransactionType[] }[] = [
  { label: 'Trades', types: ['buy', 'sell'] },
  { label: 'Cash', types: ['deposit', 'withdrawal'] },
  { label: 'Income', types: ['dividend', 'interest'] },
  { label: 'Costs', types: ['fee', 'tax'] },
  { label: 'Other', types: ['fx_conversion', 'transfer_in', 'transfer_out'] },
]
const CURRENCIES = ['CHF', 'EUR', 'USD', 'HUF', 'GBP']
const ISIN = /^[A-Z]{2}[A-Z0-9]{9}\d$/

type Moved = 'shares' | 'cash'
type Direction = 'spent' | 'received'

interface FormState {
  accountId: number | null
  type: TransactionType
  date: string
  currency: string
  asset: string
  quantity: string
  price: string
  amount: string
  fee: string
  tax: string
  note: string
  /** Transfers: securities or cash. */
  moved: Moved
  /** Editing one leg of a currency exchange: money out or in. */
  direction: Direction
  /** A new currency exchange: what was bought. */
  toAmount: string
  toCurrency: string
}

function today(): string {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

/** "1 234,5" → "1234.5"; null when it isn't a non-negative number. Kept as a string, so it stays exact. */
function decimal(value: string): string | null {
  const text = value.trim().replace(/[\s']/g, '').replace(',', '.')
  return /^\d+(\.\d+)?$/.test(text) ? text : null
}

function positive(value: string): string | null {
  const number = decimal(value)
  return number !== null && Number(number) > 0 ? number : null
}

function fromRow(row: TransactionRow): FormState {
  const amount = row.amount ?? ''
  return {
    accountId: row.account_id,
    type: row.type,
    date: row.date,
    currency: row.currency,
    asset: row.symbol ?? row.isin ?? '',
    quantity: row.quantity ?? '',
    price: row.unit_price ?? '',
    amount: amount.replace(/^-/, ''),
    fee: Number(row.fee) ? row.fee : '',
    tax: Number(row.tax) ? row.tax : '',
    note: row.description ?? '',
    moved: row.symbol || row.isin ? 'shares' : 'cash',
    direction: amount.startsWith('-') ? 'spent' : 'received',
    toAmount: '',
    toCurrency: row.currency === 'EUR' ? 'CHF' : 'EUR',
  }
}

function blank(accountId: number | null, currency: string): FormState {
  return {
    accountId,
    type: 'buy',
    date: today(),
    currency,
    asset: '',
    quantity: '',
    price: '',
    amount: '',
    fee: '',
    tax: '',
    note: '',
    moved: 'shares',
    direction: 'spent',
    toAmount: '',
    toCurrency: currency === 'EUR' ? 'CHF' : 'EUR',
  }
}

/** Symbol or ISIN as typed; a known asset also brings its ISIN, so it binds to the same listing. */
function assetFields(text: string, options: AssetOption[]): Pick<TransactionInput, 'symbol' | 'isin'> | null {
  const code = text.trim().toUpperCase()
  if (!code) return null
  const known = options.find((option) => option.symbol === code)
  if (known) return { symbol: known.symbol, isin: known.isin }
  return ISIN.test(code) ? { isin: code } : { symbol: code }
}

/** The transactions the form describes, or null while something required is missing or invalid. */
function build(form: FormState, options: AssetOption[], editing: boolean): TransactionInput[] | null {
  const base = { date: form.date, type: form.type, currency: form.currency, description: form.note.trim() || null }
  if (!form.date || !form.currency) return null
  const fee = form.fee.trim() ? decimal(form.fee) : '0'
  const tax = form.tax.trim() ? decimal(form.tax) : '0'
  if (fee === null || tax === null) return null
  const asset = assetFields(form.asset, options)

  switch (form.type) {
    case 'buy':
    case 'sell': {
      const quantity = positive(form.quantity)
      const price = decimal(form.price)
      return asset && quantity && price !== null ? [{ ...base, ...asset, quantity, unit_price: price, fee }] : null
    }
    case 'transfer_in':
    case 'transfer_out': {
      if (form.moved === 'cash') {
        const amount = positive(form.amount)
        return amount ? [{ ...base, amount }] : null
      }
      const quantity = positive(form.quantity)
      const price = form.price.trim() ? decimal(form.price) : null
      if (!asset || !quantity || (form.price.trim() && price === null)) return null
      return [{ ...base, ...asset, quantity, unit_price: price }]
    }
    case 'dividend': {
      const amount = positive(form.amount)
      return amount ? [{ ...base, ...(asset ?? {}), amount, tax }] : null
    }
    case 'fx_conversion': {
      const amount = positive(form.amount)
      if (!amount) return null
      if (editing) return [{ ...base, amount: form.direction === 'spent' ? `-${amount}` : amount }]
      const received = positive(form.toAmount)
      if (!received || form.toCurrency === form.currency) return null
      return [
        { ...base, amount: `-${amount}` },
        { ...base, amount: received, currency: form.toCurrency },
      ]
    }
    default: {
      const amount = positive(form.amount)
      return amount ? [{ ...base, amount }] : null
    }
  }
}

function tradeTotal(form: FormState): string | null {
  const quantity = positive(form.quantity)
  const price = decimal(form.price)
  if (!quantity || price === null) return null
  const fee = Number(decimal(form.fee) ?? 0)
  const gross = Number(quantity) * Number(price)
  return formatMoney(form.type === 'buy' ? gross + fee : gross - fee, form.currency)
}

interface TransactionFormProps {
  onClose: () => void
  /** Edit this transaction; omit to enter a new one. */
  transaction?: TransactionRow
  /** Preselected account for a new transaction. */
  accountId?: number | null
}

/** Enter a transaction by hand, or correct one. Mounted only while open, so it always starts fresh. */
export function TransactionFormModal({ open, ...props }: TransactionFormProps & { open: boolean }) {
  return open ? <TransactionFormDialog {...props} /> : null
}

function TransactionFormDialog({ onClose, transaction, accountId = null }: TransactionFormProps) {
  const { baseCurrency } = usePreferences()
  const accounts = useAccounts(baseCurrency).data ?? []
  const initialAccount = accounts.find((account) => account.id === accountId) ?? null
  const [form, setForm] = useState<FormState>(() =>
    transaction ? fromRow(transaction) : blank(accountId, initialAccount?.currency ?? 'CHF'),
  )
  const [duplicate, setDuplicate] = useState(false)
  const set = (patch: Partial<FormState>) => {
    setForm((current) => ({ ...current, ...patch }))
    setDuplicate(false)
  }

  const search = useDebounced(form.asset.trim(), 200)
  const options = useAssetOptions(search).data ?? []
  const add = useAddTransactions()
  const edit = useEditTransaction()
  const mutation = transaction ? edit : add
  const editing = Boolean(transaction)
  const rows = build(form, options, editing)
  const valid = rows !== null && form.accountId !== null

  const currencies = [...new Set([...CURRENCIES, form.currency, form.toCurrency])]
  const usesAsset = ['buy', 'sell', 'dividend'].includes(form.type) || (form.type.startsWith('transfer') && form.moved === 'shares')
  const usesAmount = !['buy', 'sell'].includes(form.type) && !(form.type.startsWith('transfer') && form.moved === 'shares')

  const submit = (event: FormEvent, allowDuplicate = false) => {
    event.preventDefault()
    if (!valid || form.accountId === null) return
    if (transaction) {
      const [values] = rows
      if (values) edit.mutate({ id: transaction.id, accountId: form.accountId, transaction: values }, { onSuccess: onClose })
      return
    }
    add.mutate(
      { account_id: form.accountId, transactions: rows, allow_duplicate: allowDuplicate },
      {
        onSuccess: onClose,
        onError: (error) => setDuplicate(error instanceof ApiError && error.code === 'duplicate'),
      },
    )
  }

  const pickAsset = (value: string) => {
    const known = options.find((option) => option.symbol === value.trim().toUpperCase())
    set(known ? { asset: value, currency: known.currency } : { asset: value })
  }

  const assetField = (
    <Field label={form.type === 'dividend' ? 'Asset (optional)' : 'Asset'} hint="Ticker or ISIN">
      <Input
        value={form.asset}
        onChange={(event) => pickAsset(event.target.value)}
        list="transaction-assets"
        placeholder="e.g. VWCE or IE00BK5BQT80"
        maxLength={32}
        autoCapitalize="characters"
        spellCheck={false}
      />
      <datalist id="transaction-assets">
        {options.map((option) => (
          <option key={option.id} value={option.symbol}>
            {[option.name, option.currency].filter(Boolean).join(' · ')}
          </option>
        ))}
      </datalist>
    </Field>
  )

  return (
    <Modal
      open
      onClose={onClose}
      title={transaction ? 'Edit transaction' : 'Add transaction'}
      description={
        transaction
          ? transaction.manual
            ? 'Entered by hand.'
            : 'Your correction stays when the same statement is imported again.'
          : 'For anything a statement or sync doesn’t bring in.'
      }
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          {duplicate ? (
            <Button variant="primary" loading={add.isPending} onClick={(event) => submit(event, true)}>
              Add anyway
            </Button>
          ) : (
            <Button variant="primary" type="submit" form="transaction-form" loading={mutation.isPending} disabled={!valid}>
              {transaction ? 'Save changes' : 'Add transaction'}
            </Button>
          )}
        </>
      }
    >
      <form id="transaction-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <Field label="Account">
          <Select
            value={form.accountId ?? ''}
            onChange={(event) => {
              const account = accounts.find((item) => item.id === Number(event.target.value))
              set({ accountId: account?.id ?? null, ...(account && !editing && !form.asset ? { currency: account.currency } : {}) })
            }}
            required
          >
            <option value="" disabled>
              Choose an account
            </option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Type">
          <Select value={form.type} onChange={(event) => set({ type: event.target.value as TransactionType })}>
            {TYPE_GROUPS.map((group) => (
              <optgroup key={group.label} label={group.label}>
                {group.types.map((type) => (
                  <option key={type} value={type}>
                    {TRANSACTION_TYPE_LABELS[type]}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
        </Field>
        <Field label="Date">
          <Input type="date" value={form.date} max={today()} onChange={(event) => set({ date: event.target.value })} required />
        </Field>

        {form.type.startsWith('transfer') ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-[13px] font-medium text-ink-2">Moved</span>
            <SegmentedControl<Moved>
              label="Moved"
              options={[
                { value: 'shares', label: 'Securities' },
                { value: 'cash', label: 'Cash' },
              ]}
              value={form.moved}
              onChange={(moved) => set({ moved })}
              fill
            />
          </div>
        ) : form.type === 'fx_conversion' && editing ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-[13px] font-medium text-ink-2">This leg</span>
            <SegmentedControl<Direction>
              label="Direction"
              options={[
                { value: 'spent', label: 'Money out' },
                { value: 'received', label: 'Money in' },
              ]}
              value={form.direction}
              onChange={(direction) => set({ direction })}
              fill
            />
          </div>
        ) : (
          <span className="hidden sm:block" />
        )}

        {usesAsset ? <div className="sm:col-span-2">{assetField}</div> : null}

        {form.type === 'buy' || form.type === 'sell' || (form.type.startsWith('transfer') && form.moved === 'shares') ? (
          <>
            <Field label="Quantity">
              <Input value={form.quantity} onChange={(event) => set({ quantity: event.target.value })} inputMode="decimal" placeholder="0" />
            </Field>
            <MoneyField
              label={form.type.startsWith('transfer') ? 'Cost per share (optional)' : 'Price per share'}
              value={form.price}
              onChange={(price) => set({ price })}
              currency={form.currency}
              currencies={currencies}
              onCurrencyChange={(currency) => set({ currency })}
            />
          </>
        ) : null}

        {usesAmount ? (
          <MoneyField
            label={form.type === 'fx_conversion' && !editing ? 'You sold' : 'Amount'}
            value={form.amount}
            onChange={(amount) => set({ amount })}
            currency={form.currency}
            currencies={currencies}
            onCurrencyChange={(currency) => set({ currency })}
          />
        ) : null}

        {form.type === 'fx_conversion' && !editing ? (
          <MoneyField
            label="You bought"
            icon={<ArrowRight className="size-3.5" aria-hidden />}
            value={form.toAmount}
            onChange={(toAmount) => set({ toAmount })}
            currency={form.toCurrency}
            currencies={currencies}
            onCurrencyChange={(toCurrency) => set({ toCurrency })}
          />
        ) : null}

        {form.type === 'buy' || form.type === 'sell' ? (
          <Field label="Fee (optional)" hint={tradeTotal(form) ? `Total ${tradeTotal(form)}` : undefined}>
            <Input value={form.fee} onChange={(event) => set({ fee: event.target.value })} inputMode="decimal" placeholder="0" />
          </Field>
        ) : null}
        {form.type === 'dividend' ? (
          <Field label="Tax withheld (optional)">
            <Input value={form.tax} onChange={(event) => set({ tax: event.target.value })} inputMode="decimal" placeholder="0" />
          </Field>
        ) : null}

        <div className="sm:col-span-2">
          <Field label="Note (optional)">
            <Input value={form.note} onChange={(event) => set({ note: event.target.value })} maxLength={500} />
          </Field>
        </div>

        {form.type === 'fx_conversion' && !editing && form.currency === form.toCurrency ? (
          <div className="sm:col-span-2">
            <Notice tone="neutral" icon={<Info className="size-4" />}>
              Pick two different currencies.
            </Notice>
          </div>
        ) : null}
        {duplicate ? (
          <div className="sm:col-span-2">
            <Notice tone="warning" icon={<Info className="size-4" />}>
              An identical transaction is already recorded on this account. Add it anyway if it happened twice.
            </Notice>
          </div>
        ) : mutation.error ? (
          <div className="sm:col-span-2">
            <Notice tone="negative">{mutation.error.message}</Notice>
          </div>
        ) : null}
      </form>
    </Modal>
  )
}

function MoneyField({
  label,
  icon,
  value,
  onChange,
  currency,
  currencies,
  onCurrencyChange,
}: {
  label: string
  icon?: ReactNode
  value: string
  onChange: (value: string) => void
  currency: string
  currencies: string[]
  onCurrencyChange: (currency: string) => void
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <span className="inline-flex items-center gap-1.5 text-[13px] font-medium text-ink-2">
        {icon}
        {label}
      </span>
      <div className="flex gap-2">
        <Input className="min-w-0 flex-1" value={value} onChange={(event) => onChange(event.target.value)} inputMode="decimal" placeholder="0" aria-label={label} />
        <span className="w-24 shrink-0">
          <Select value={currency} onChange={(event) => onCurrencyChange(event.target.value)} aria-label={`${label} currency`}>
            {currencies.map((code) => (
              <option key={code}>{code}</option>
            ))}
          </Select>
        </span>
      </div>
    </div>
  )
}
