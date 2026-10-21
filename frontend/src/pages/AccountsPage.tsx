import { clsx } from 'clsx'
import { Plus, Sprout } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { useAccounts, usePerformance } from '../api/hooks'
import type { AccountReturn, AccountSummary } from '../api/types'
import { AccountTypeBadge, BrokerAvatar, TbszProgress } from '../components/accounts/AccountRow'
import { AccountFormModal } from '../components/accounts/AccountFormModal'
import { PageHeader } from '../components/layout/PageHeader'
import { AccountReturnsTable } from '../components/returns/AccountReturnsTable'
import { ReturnRate } from '../components/returns/ReturnRate'
import { Delta } from '../components/ui/Delta'
import { Button, Card, CardHeader, EmptyState, Spinner } from '../components/ui/primitives'
import { groupByBroker } from '../lib/accounts'
import { formatDate, formatMoney } from '../lib/format'
import { totalReturn } from '../lib/returns'
import { usePreferences } from '../lib/preferences-context'
import { QueryError } from './QueryError'
import { Sensitive } from '../components/ui/Sensitive'

function AccountCard({ account, currency, result }: { account: AccountSummary; currency: string; result?: AccountReturn }) {
  return (
    <Link to={`/accounts/${account.id}`} className="group">
      <Card className="flex h-full flex-col gap-4 p-5 transition-shadow group-hover:shadow-[var(--shadow-pop)]">
        <div className="flex items-start gap-3">
          <BrokerAvatar broker={account.broker} />
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold text-ink">{account.name}</p>
            <p className="truncate text-xs text-ink-3">
              {account.broker}
              {account.external_account_id ? ` · ${account.external_account_id}` : ''}
            </p>
          </div>
          <AccountTypeBadge account={account} />
        </div>
        <div>
          <p className="font-display text-2xl font-semibold text-ink"><Sensitive>{formatMoney(account.value, currency)}</Sensitive></p>
          {account.currency !== currency && account.value_account_currency ? (
            <p className="tabular text-xs text-ink-3"><Sensitive>{formatMoney(account.value_account_currency, account.currency)}</Sensitive></p>
          ) : null}
          {result ? (
            <p className="mt-1 flex flex-wrap items-baseline gap-x-2 text-sm">
              <ReturnRate rate={totalReturn(result)} perYear={false} />
              <span className="text-xs text-ink-3">since {formatDate(result.start)}</span>
              {result.per_year ? (
                <span className="text-xs text-ink-3">
                  · <ReturnRate rate={result.money_weighted} perYear className="text-xs" />
                </span>
              ) : null}
            </p>
          ) : null}
        </div>
        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className="inline-flex items-center gap-1 text-ink-3">
            P&amp;L <Delta amount={account.total_pnl} currency={currency} />
          </span>
          <span className="text-ink-3">
            {account.transaction_count} transactions · last {formatDate(account.last_transaction_date, 'short')}
          </span>
        </div>
        <TbszProgress account={account} />
      </Card>
    </Link>
  )
}

export function AccountsPage() {
  const { baseCurrency } = usePreferences()
  const accounts = useAccounts(baseCurrency)
  const [params, setParams] = useSearchParams()
  const modalOpen = params.get('new') === '1'
  const list = accounts.data ?? []
  const performance = usePerformance(baseCurrency, 'ALL')
  const results = new Map((performance.data?.accounts ?? []).map((row) => [row.account_id, row]))

  return (
    <>
      <PageHeader
        title="Accounts"
        subtitle="Every account, grouped by broker — drill into any of them."
        actions={
          <Button variant="primary" onClick={() => setParams({ new: '1' })}>
            <Plus className="size-4" aria-hidden /> New account
          </Button>
        }
      />
      {accounts.isLoading ? (
        <div className="grid h-80 place-items-center">
          <Spinner />
        </div>
      ) : accounts.error ? (
        <QueryError error={accounts.error} onRetry={() => void accounts.refetch()} />
      ) : list.length === 0 ? (
        <Card>
          <EmptyState icon={<Sprout className="size-5" />} title="Plant the first seed">
            Create an account for each broker or TBSZ vintage, then import its statements.
          </EmptyState>
        </Card>
      ) : (
        <div className={clsx('flex flex-col gap-8 transition-opacity', accounts.isPlaceholderData && 'opacity-60')}>
          {results.size > 1 ? (
            <Card className="overflow-hidden">
              <CardHeader
                title="Returns since the start"
                subtitle="Every account side by side. Total is what your money made over the account's whole life; the yearly rates make accounts of different ages comparable."
              />
              <div className="pt-2">
                <AccountReturnsTable rows={[...results.values()]} accounts={list} currency={baseCurrency} />
              </div>
            </Card>
          ) : null}
          {groupByBroker(list).map(([broker, group]) => (
            <section key={broker}>
              <h2 className="mb-4 text-lg font-semibold text-ink">{broker}</h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {group.map((account) => (
                  <AccountCard key={account.id} account={account} currency={baseCurrency} result={results.get(account.id)} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
      <AccountFormModal open={modalOpen} onClose={() => setParams({})} />
    </>
  )
}
