import { clsx } from 'clsx'
import { Plus, Sprout } from 'lucide-react'
import { Link, useSearchParams } from 'react-router'

import { useAccounts } from '../api/hooks'
import type { AccountSummary } from '../api/types'
import { AccountTypeBadge, BrokerAvatar, TbszProgress } from '../components/accounts/AccountRow'
import { AccountFormModal } from '../components/accounts/AccountFormModal'
import { PageHeader } from '../components/layout/PageHeader'
import { Delta } from '../components/ui/Delta'
import { Button, Card, EmptyState, Spinner } from '../components/ui/primitives'
import { groupByBroker } from '../lib/accounts'
import { formatDate, formatMoney } from '../lib/format'
import { usePreferences } from '../lib/preferences-context'
import { QueryError } from './QueryError'

function AccountCard({ account, currency }: { account: AccountSummary; currency: string }) {
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
          <p className="font-display text-2xl font-semibold text-ink">{formatMoney(account.value, currency)}</p>
          {account.currency !== currency && account.value_account_currency ? (
            <p className="tabular text-xs text-ink-3">{formatMoney(account.value_account_currency, account.currency)}</p>
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
  const tbsz = list.filter((account) => account.account_type === 'tbsz').sort((a, b) => (a.tbsz_year ?? 0) - (b.tbsz_year ?? 0))

  return (
    <>
      <PageHeader
        title="Accounts"
        subtitle="Every broker, sub-account and TBSZ vintage — drill into any of them."
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
          {tbsz.length > 0 ? (
            <section>
              <h2 className="mb-1 text-lg font-semibold text-ink">TBSZ vintages</h2>
              <p className="mb-4 text-sm text-ink-3">
                Each vintage locks for five years after its collection year: 10% tax after three, tax-free after five.
              </p>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {tbsz.map((account) => (
                  <AccountCard key={account.id} account={account} currency={baseCurrency} />
                ))}
              </div>
            </section>
          ) : null}
          {groupByBroker(list).map(([broker, group]) => (
            <section key={broker}>
              <h2 className="mb-4 text-lg font-semibold text-ink">{broker}</h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {group.map((account) => (
                  <AccountCard key={account.id} account={account} currency={baseCurrency} />
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
