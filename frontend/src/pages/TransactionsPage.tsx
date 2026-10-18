import { clsx } from 'clsx'
import { FileUp, Search, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { useAccounts, useTransactions, type TransactionFilters } from '../api/hooks'
import type { TransactionType } from '../api/types'
import { PageHeader } from '../components/layout/PageHeader'
import { TransactionsTable } from '../components/transactions/TransactionsTable'
import { Button, Card, EmptyState, Field, Input, Select, Spinner } from '../components/ui/primitives'
import { useDebounced } from '../lib/debounce'
import { usePreferences } from '../lib/preferences-context'
import { QueryError } from './QueryError'

const PAGE_SIZE = 50

/** Type filters as people think of them, not one chip per ledger type. */
const TYPE_GROUPS: { key: string; label: string; types: TransactionType[] }[] = [
  { key: 'trades', label: 'Trades', types: ['buy', 'sell'] },
  { key: 'income', label: 'Income', types: ['dividend', 'interest'] },
  { key: 'cash', label: 'Deposits & withdrawals', types: ['deposit', 'withdrawal', 'transfer_in', 'transfer_out'] },
  { key: 'costs', label: 'Fees & taxes', types: ['fee', 'tax'] },
  { key: 'fx', label: 'Currency exchange', types: ['fx_conversion'] },
]

function numberParam(value: string | null): number | null {
  const number = Number(value)
  return value && Number.isInteger(number) && number > 0 ? number : null
}

export function TransactionsPage() {
  const { baseCurrency } = usePreferences()
  const accounts = useAccounts(baseCurrency)
  const [params, setParams] = useSearchParams()
  const [searchText, setSearchText] = useState(params.get('q') ?? '')
  const debouncedSearch = useDebounced(searchText.trim(), 300)

  const accountId = numberParam(params.get('account'))
  const assetId = numberParam(params.get('asset'))
  const groups = params.getAll('type').filter((key) => TYPE_GROUPS.some((group) => group.key === key))
  const dateFrom = params.get('from') ?? ''
  const dateTo = params.get('to') ?? ''
  const page = Math.max(0, (numberParam(params.get('page')) ?? 1) - 1)

  const update = (changes: Record<string, string | string[] | null>, keepPage = false) => {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        for (const [key, value] of Object.entries(changes)) {
          next.delete(key)
          if (Array.isArray(value)) value.forEach((item) => next.append(key, item))
          else if (value) next.set(key, value)
        }
        if (!keepPage) next.delete('page')
        return next
      },
      { replace: true },
    )
  }

  // The search box updates the URL once typing pauses, so every keystroke doesn't hit the API.
  useEffect(() => {
    setParams(
      (current) => {
        if ((current.get('q') ?? '') === debouncedSearch) return current
        const next = new URLSearchParams(current)
        if (debouncedSearch) next.set('q', debouncedSearch)
        else next.delete('q')
        next.delete('page')
        return next
      },
      { replace: true },
    )
  }, [debouncedSearch, setParams])

  // Query keys are compared by value, so a fresh object each render doesn't refetch.
  const filters: TransactionFilters = {
    accountId,
    assetId,
    types: TYPE_GROUPS.filter((group) => groups.includes(group.key)).flatMap((group) => group.types),
    search: params.get('q') ?? '',
    dateFrom,
    dateTo,
  }
  const transactions = useTransactions(filters, page, PAGE_SIZE)
  const filtered = Boolean(accountId || assetId || groups.length || params.get('q') || dateFrom || dateTo)
  const data = transactions.data
  const assetLabel = assetId ? (data?.items.find((tx) => tx.symbol)?.symbol ?? 'one asset') : null

  const toggleGroup = (key: string) =>
    update({ type: groups.includes(key) ? groups.filter((group) => group !== key) : [...groups, key] })

  const clearAll = () => {
    setSearchText('')
    setParams({}, { replace: true })
  }

  return (
    <>
      <PageHeader
        title="Transactions"
        showCurrency={false}
        subtitle={data ? `${data.total} transaction${data.total === 1 ? '' : 's'}${filtered ? ' match your filters' : ''}` : ' '}
      />
      <div className="flex flex-col gap-4 sm:gap-5">
        <Card className="flex flex-col gap-4 px-5 py-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_minmax(0,1.4fr)_minmax(0,2fr)]">
            <Field label="Search">
              <span className="relative block">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
                <Input
                  value={searchText}
                  onChange={(event) => setSearchText(event.target.value)}
                  placeholder="Symbol, name, ISIN or note"
                  className="pl-9"
                  maxLength={100}
                  type="search"
                />
              </span>
            </Field>
            <Field label="Account">
              <Select value={accountId ?? ''} onChange={(event) => update({ account: event.target.value || null })}>
                <option value="">All accounts</option>
                {(accounts.data ?? []).map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-3 sm:col-span-2 lg:col-span-1">
            <Field label="From">
              <Input type="date" value={dateFrom} max={dateTo || undefined} onChange={(event) => update({ from: event.target.value || null })} />
            </Field>
            <Field label="To">
              <Input type="date" value={dateTo} min={dateFrom || undefined} onChange={(event) => update({ to: event.target.value || null })} />
            </Field>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Transaction types">
            {TYPE_GROUPS.map((group) => {
              const active = groups.includes(group.key)
              return (
                <button
                  key={group.key}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleGroup(group.key)}
                  className={clsx(
                    'h-8 rounded-full border px-3 text-[13px] font-medium transition-colors',
                    active ? 'border-accent bg-accent-soft text-accent' : 'border-line text-ink-2 hover:bg-surface-2',
                  )}
                >
                  {group.label}
                </button>
              )
            })}
            {assetLabel ? (
              <button
                type="button"
                onClick={() => update({ asset: null })}
                className="inline-flex h-8 items-center gap-1 rounded-full border border-accent bg-accent-soft px-3 text-[13px] font-medium text-accent"
              >
                Asset: {assetLabel} <X className="size-3.5" aria-label="Remove asset filter" />
              </button>
            ) : null}
            {filtered ? (
              <Button variant="ghost" size="sm" onClick={clearAll} className="ml-auto">
                Clear filters
              </Button>
            ) : null}
          </div>
        </Card>
        <Card className="overflow-hidden">
          {transactions.isLoading ? (
            <div className="grid h-60 place-items-center">
              <Spinner />
            </div>
          ) : transactions.error ? (
            <QueryError error={transactions.error} onRetry={() => void transactions.refetch()} />
          ) : !data || data.total === 0 ? (
            filtered ? (
              <EmptyState icon={<Search className="size-5" />} title="No matching transactions">
                <button type="button" className="font-medium text-accent hover:underline" onClick={clearAll}>
                  Clear the filters
                </button>{' '}
                to see everything.
              </EmptyState>
            ) : (
              <EmptyState icon={<FileUp className="size-5" />} title="No transactions yet">
                <Link to="/import" className="font-medium text-accent hover:underline">
                  Import a statement
                </Link>{' '}
                to get started.
              </EmptyState>
            )
          ) : (
            <div className="pt-1">
              <TransactionsTable
                data={data}
                page={page}
                pageSize={PAGE_SIZE}
                onPageChange={(next) => update({ page: next > 0 ? String(next + 1) : null }, true)}
                loadingMore={transactions.isPlaceholderData}
                showAccount={!accountId}
              />
            </div>
          )}
        </Card>
      </div>
    </>
  )
}
