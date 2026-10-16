import { Plus, Wallet } from 'lucide-react'
import { Link } from 'react-router'

import type { AccountSummary } from '../../api/types'
import { groupByBroker } from '../../lib/accounts'
import { AccountRow } from '../accounts/AccountRow'
import { Card, CardHeader, EmptyState } from '../ui/primitives'

export function AccountsCard({ accounts, currency }: { accounts: AccountSummary[]; currency: string }) {
  return (
    <Card className="h-full">
      <CardHeader
        title="Accounts & TBSZ"
        subtitle={`${accounts.length} accounts across ${new Set(accounts.map((a) => a.broker)).size} institutions`}
        action={
          <Link
            to="/accounts?new=1"
            className="inline-flex h-8 items-center gap-1.5 rounded-full border border-line px-3 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
          >
            <Plus className="size-3.5" aria-hidden /> Add
          </Link>
        }
      />
      <div className="px-3 pb-3 pt-3">
        {accounts.length === 0 ? (
          <EmptyState icon={<Wallet className="size-5" />} title="No accounts yet">
            Add an account, then import a statement.
          </EmptyState>
        ) : (
          groupByBroker(accounts).map(([broker, list]) => (
            <section key={broker} className="mb-1">
              <h3 className="px-3 pb-1 pt-3 font-sans text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-3">
                {broker}
              </h3>
              {list.map((account) => (
                <AccountRow key={account.id} account={account} currency={currency} />
              ))}
            </section>
          ))
        )}
      </div>
    </Card>
  )
}
