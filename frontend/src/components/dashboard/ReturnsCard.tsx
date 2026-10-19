import { clsx } from 'clsx'
import { ArrowDownRight, ArrowUpRight, Info, Minus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { usePerformance } from '../../api/hooks'
import { RETURN_PERIODS, type AccountSummary, type PeriodReturn, type ReturnPeriod } from '../../api/types'
import { formatDate, formatMoney, formatPercent, trend } from '../../lib/format'
import { Card, CardHeader, SegmentedControl, Spinner } from '../ui/primitives'
import { Sensitive } from '../ui/Sensitive'

const PERIOD_LABELS: Record<ReturnPeriod, string> = { YTD: 'YTD', '1Y': '1Y', '3Y': '3Y', '5Y': '5Y', ALL: 'All' }

/** A rate of return with direction shown by icon and sign as well as colour. Percentages stay visible in
 * private mode: they don't reveal amounts. */
export function ReturnRate({
  rate,
  perYear,
  className,
}: {
  rate: string | null
  perYear: boolean
  className?: string
}) {
  if (rate === null) return <span className={clsx('text-ink-3', className)}>—</span>
  const direction = trend(rate)
  const Icon = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : Minus
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 whitespace-nowrap font-medium tabular',
        direction === 'up' && 'text-positive',
        direction === 'down' && 'text-negative',
        direction === 'flat' && 'text-ink-3',
        className,
      )}
    >
      <Icon className="size-[0.85em] shrink-0" aria-hidden strokeWidth={2.5} />
      {formatPercent(rate, { signed: true, digits: 1 })}
      {perYear ? <span className="text-[0.7em] font-normal opacity-80">/ yr</span> : null}
    </span>
  )
}

function since(result: PeriodReturn): string {
  return `${result.per_year ? 'Per year' : 'In total'} since ${formatDate(result.start)}`
}

function Explainer() {
  return (
    <div className="mx-6 mb-2 grid gap-3 rounded-2xl bg-surface-2 px-4 py-3 text-sm text-ink-2 sm:grid-cols-2">
      <p>
        <span className="font-medium text-ink">Your money</span> (money-weighted, XIRR) is what your money actually
        earned. A deposit made just before a rise or a fall counts for as long as it was invested, so your timing is
        part of it.
      </p>
      <p>
        <span className="font-medium text-ink">Investments</span> (time-weighted) is how the holdings themselves did,
        whatever was deposited when. Use it to compare accounts with each other or with an index.
      </p>
    </div>
  )
}

/** Returns as rates, overall and per account, so accounts of different ages and sizes compare. */
export function ReturnsCard({ currency, accounts }: { currency: string; accounts: AccountSummary[] }) {
  const [period, setPeriod] = useState<ReturnPeriod>('ALL')
  const [explain, setExplain] = useState(false)
  const performance = usePerformance(currency, period)
  const data = performance.data
  const total = data?.total ?? null
  const names = new Map(accounts.map((account) => [account.id, account.name]))
  const rows = [...(data?.accounts ?? [])]
    .filter((row) => names.has(row.account_id))
    .sort((a, b) => Number(b.money_weighted ?? -Infinity) - Number(a.money_weighted ?? -Infinity))

  return (
    <Card>
      <CardHeader
        title={
          <span className="inline-flex items-center gap-2">
            Returns
            <button
              type="button"
              onClick={() => setExplain((value) => !value)}
              aria-expanded={explain}
              aria-label="What these numbers mean"
              className="grid size-6 place-items-center rounded-full text-ink-3 hover:bg-surface-2 hover:text-ink"
            >
              <Info className="size-4" aria-hidden />
            </button>
          </span>
        }
        subtitle={total ? since(total) : 'Rates of return, net of deposits and withdrawals'}
        action={
          <SegmentedControl<ReturnPeriod>
            label="Period"
            size="sm"
            options={RETURN_PERIODS.map((value) => ({ value, label: PERIOD_LABELS[value] }))}
            value={period}
            onChange={setPeriod}
          />
        }
      />
      {explain ? <Explainer /> : null}
      {performance.isLoading ? (
        <div className="grid h-40 place-items-center">
          <Spinner />
        </div>
      ) : !total ? (
        <p className="px-6 pb-6 pt-2 text-sm text-ink-3">Nothing was invested in this period.</p>
      ) : (
        <div className={clsx('transition-opacity', performance.isPlaceholderData && 'opacity-60')}>
          <div className="grid grid-cols-1 gap-4 px-6 pb-5 pt-2 sm:grid-cols-3">
            <div>
              <p className="text-[13px] font-medium text-ink-3">Your money</p>
              <ReturnRate rate={total.money_weighted} perYear={total.per_year} className="mt-1 font-display text-[26px] font-semibold" />
            </div>
            <div>
              <p className="text-[13px] font-medium text-ink-3">Investments</p>
              <ReturnRate rate={total.time_weighted} perYear={total.per_year} className="mt-1 font-display text-[26px] font-semibold" />
            </div>
            <div>
              <p className="text-[13px] font-medium text-ink-3">Gain</p>
              <p className="mt-1 font-display text-[26px] font-semibold tabular text-ink">
                <Sensitive>{formatMoney(total.gain, currency, { signed: true })}</Sensitive>
              </p>
              <p className="text-xs text-ink-3">
                after <Sensitive>{formatMoney(total.net_flows, currency)}</Sensitive> net deposits
              </p>
            </div>
          </div>
          {rows.length > 1 ? (
            <div className="overflow-x-auto border-t border-line">
              <table className="w-full min-w-[480px] text-sm">
                <thead className="text-left text-xs text-ink-3">
                  <tr>
                    <th className="px-6 py-2.5 font-medium">Account</th>
                    <th className="px-3 py-2.5 text-right font-medium">Your money</th>
                    <th className="px-3 py-2.5 text-right font-medium">Investments</th>
                    <th className="px-6 py-2.5 text-right font-medium">Since</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.account_id} className="border-t border-line">
                      <td className="max-w-[220px] px-6 py-2.5">
                        <Link to={`/accounts/${row.account_id}`} className="block truncate text-ink hover:text-accent hover:underline">
                          {names.get(row.account_id)}
                        </Link>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <ReturnRate rate={row.money_weighted} perYear={row.per_year} />
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        <ReturnRate rate={row.time_weighted} perYear={row.per_year} />
                      </td>
                      <td className="whitespace-nowrap px-6 py-2.5 text-right text-ink-3">{formatDate(row.start, 'short')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      )}
    </Card>
  )
}
