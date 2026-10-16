import { clsx } from 'clsx'
import { TriangleAlert } from 'lucide-react'
import { useState } from 'react'

import { useSummary } from '../api/hooks'
import { PageHeader } from '../components/layout/PageHeader'
import { AccountsCard } from '../components/dashboard/AccountsCard'
import { AllocationCard } from '../components/dashboard/AllocationCard'
import { InvestmentsCard } from '../components/dashboard/InvestmentsCard'
import { NetWorthCard } from '../components/dashboard/NetWorthCard'
import { StatTiles } from '../components/dashboard/StatTiles'
import { Notice, Spinner } from '../components/ui/primitives'
import { usePreferences } from '../lib/preferences-context'
import { QueryError } from './QueryError'

function greeting(now: Date): string {
  const hour = now.getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

export function DashboardPage() {
  const { baseCurrency } = usePreferences()
  const summary = useSummary(baseCurrency)
  const [now] = useState(() => new Date())
  const today = now.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })

  return (
    <>
      <PageHeader title={greeting(now)} subtitle={`Your wealth at a glance · ${today}`} />
      {summary.isLoading ? (
        <div className="grid h-96 place-items-center">
          <Spinner />
        </div>
      ) : summary.error ? (
        <QueryError error={summary.error} onRetry={() => void summary.refetch()} />
      ) : summary.data ? (
        <div className={clsx('flex flex-col gap-4 transition-opacity sm:gap-5', summary.isPlaceholderData && 'opacity-60')}>
          {summary.data.warnings.length > 0 ? (
            <Notice icon={<TriangleAlert className="size-4" />}>
              {summary.data.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </Notice>
          ) : null}
          <div className="grid grid-cols-1 gap-4 sm:gap-5 xl:grid-cols-[minmax(0,1fr)_280px]">
            <NetWorthCard summary={summary.data} />
            <StatTiles summary={summary.data} />
          </div>
          <InvestmentsCard currency={summary.data.base_currency} />
          <div className="grid grid-cols-1 gap-4 sm:gap-5 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
            <AllocationCard allocations={summary.data.allocations} currency={summary.data.base_currency} />
            <AccountsCard accounts={summary.data.accounts} currency={summary.data.base_currency} />
          </div>
        </div>
      ) : null}
    </>
  )
}
