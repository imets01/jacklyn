import { clsx } from 'clsx'
import { CalendarClock, ChartColumn, Coins, Table2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'

import { useIncome } from '../api/hooks'
import type { IncomeHolding, IncomeMonth, IncomeResponse } from '../api/types'
import { AssetIcon } from '../components/assets/AssetIcon'
import { IncomeChart, IncomeLegend } from '../components/charts/IncomeChart'
import { PageHeader } from '../components/layout/PageHeader'
import { Card, CardHeader, EmptyState, SegmentedControl, Spinner } from '../components/ui/primitives'
import { Sensitive } from '../components/ui/Sensitive'
import { formatDate, formatMoney, formatMonthYear, formatPercent, toNumber } from '../lib/format'
import { usePreferences } from '../lib/preferences-context'
import { QueryError } from './QueryError'

function Tile({ label, value, detail }: { label: string; value: ReactNode; detail?: ReactNode }) {
  return (
    <Card className="flex min-w-0 flex-col justify-between gap-3 px-5 py-4">
      <p className="text-[13px] font-medium text-ink-3">{label}</p>
      <div className="font-display text-xl font-semibold leading-tight text-ink sm:text-[22px]">{value}</div>
      {detail ? <div className="text-xs text-ink-3">{detail}</div> : null}
    </Card>
  )
}

function Tiles({ data }: { data: IncomeResponse }) {
  const { totals, base_currency: currency } = data
  const previous = toNumber(totals.previous_12m)
  const change = previous > 0 ? toNumber(totals.trailing_12m) / previous - 1 : null
  return (
    <div className="grid grid-cols-1 gap-3 min-[420px]:grid-cols-2 sm:gap-4 xl:grid-cols-4">
      <Tile
        label="Last 12 months"
        value={<Sensitive>{formatMoney(totals.trailing_12m, currency)}</Sensitive>}
        detail={
          <>
            {change !== null ? <>{formatPercent(change, { signed: true, digits: 0 })} on the year before · </> : null}
            <Sensitive>{formatMoney(totals.withheld_12m, currency)}</Sensitive> withheld
          </>
        }
      />
      <Tile
        label={`This year`}
        value={<Sensitive>{formatMoney(totals.this_year, currency)}</Sensitive>}
        detail={<><Sensitive>{formatMoney(totals.all_time, currency)}</Sensitive> since you started</>}
      />
      <Tile
        label="Next 12 months"
        value={<Sensitive>{formatMoney(totals.expected_12m, currency)}</Sensitive>}
        detail="Expected, if each holding pays what it paid per share last year"
      />
      <Tile
        label="Portfolio yield"
        value={formatPercent(totals.portfolio_yield, { digits: 2 })}
        detail="Last 12 months' income on today's value"
      />
    </div>
  )
}

function MonthsTable({ months, currency }: { months: IncomeMonth[]; currency: string }) {
  return (
    <div className="max-h-[280px] overflow-y-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface text-left text-xs text-ink-3">
          <tr>
            <th className="px-6 py-2 font-medium">Month</th>
            <th className="px-3 py-2 text-right font-medium">Dividends</th>
            <th className="px-3 py-2 text-right font-medium">Interest</th>
            <th className="px-6 py-2 text-right font-medium">Withheld</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {[...months].reverse().map((month) => (
            <tr key={month.month} className="border-t border-line">
              <td className="px-6 py-2 text-ink-2">{formatMonthYear(month.month)}</td>
              <td className="px-3 py-2 text-right text-ink"><Sensitive>{formatMoney(month.dividends, currency)}</Sensitive></td>
              <td className="px-3 py-2 text-right text-ink"><Sensitive>{formatMoney(month.interest, currency)}</Sensitive></td>
              <td className="px-6 py-2 text-right text-ink-3"><Sensitive>{formatMoney(month.withheld, currency)}</Sensitive></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function MonthlyCard({ data }: { data: IncomeResponse }) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  return (
    <Card>
      <CardHeader
        title="Monthly income"
        subtitle="After withholding tax, the last 24 months"
        action={
          <SegmentedControl
            label="View"
            size="sm"
            value={view}
            onChange={setView}
            options={[
              { value: 'chart', label: <ChartColumn className="size-3.5" aria-label="Chart" />, title: 'Chart' },
              { value: 'table', label: <Table2 className="size-3.5" aria-label="Table" />, title: 'Table' },
            ]}
          />
        }
      />
      <div className="px-6 pb-5 pt-3">
        {view === 'chart' ? (
          <div className="flex flex-col gap-3">
            <IncomeLegend months={data.months} />
            <IncomeChart months={data.months} currency={data.base_currency} />
          </div>
        ) : null}
      </div>
      {view === 'table' ? <MonthsTable months={data.months} currency={data.base_currency} /> : null}
    </Card>
  )
}

function UpcomingCard({ data }: { data: IncomeResponse }) {
  return (
    <Card className="h-full">
      <CardHeader title="Coming up" subtitle="Next 90 days, estimated from each holding's rhythm" />
      <div className="px-3 pb-4 pt-2">
        {data.upcoming.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-ink-3">Nothing expected in the next three months.</p>
        ) : (
          <ul className="flex flex-col">
            {data.upcoming.map((payment) => (
              <li key={payment.asset_id}>
                <Link
                  to={`/holdings/${payment.asset_id}`}
                  className="flex items-center gap-3 rounded-2xl px-3 py-2.5 transition-colors hover:bg-surface-2"
                >
                  <AssetIcon symbol={payment.symbol} name={payment.name} logoUrl={payment.logo_url} size="sm" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink">{payment.symbol}</span>
                    <span className="block text-xs text-ink-3">around {formatDate(payment.expected_on)}</span>
                  </span>
                  <span className="text-sm tabular text-ink">
                    ≈ <Sensitive>{formatMoney(payment.estimate, data.base_currency)}</Sensitive>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  )
}

function HoldingRow({ holding, currency }: { holding: IncomeHolding; currency: string }) {
  return (
    <tr className={clsx('border-t border-line', !holding.held && 'text-ink-3')}>
      <td className="max-w-[260px] px-6 py-3">
        <Link to={`/holdings/${holding.asset_id}`} className="flex items-center gap-3 hover:text-accent">
          <AssetIcon symbol={holding.symbol} name={holding.name} logoUrl={holding.logo_url} size="sm" />
          <span className="min-w-0">
            <span className={clsx('block truncate font-medium', holding.held ? 'text-ink' : 'text-ink-3')}>{holding.symbol}</span>
            <span className="block truncate text-xs text-ink-3">{holding.held ? holding.name : 'Sold'}</span>
          </span>
        </Link>
      </td>
      <td className="px-3 py-3 text-right">
        <Sensitive>{formatMoney(holding.trailing_12m, currency)}</Sensitive>
      </td>
      <td className="px-3 py-3 text-right">{formatPercent(holding.yield_pct)}</td>
      <td className="px-3 py-3 text-right">{formatPercent(holding.yield_on_cost)}</td>
      <td className="px-3 py-3 text-ink-2">{holding.cadence ?? '—'}</td>
      <td className="whitespace-nowrap px-3 py-3 text-ink-2">{holding.last_paid ? formatDate(holding.last_paid) : '—'}</td>
      <td className="whitespace-nowrap px-6 py-3 text-ink-2">{holding.next_expected ? formatDate(holding.next_expected) : '—'}</td>
    </tr>
  )
}

function HoldingsCard({ data }: { data: IncomeResponse }) {
  const [showSold, setShowSold] = useState(false)
  const sold = data.holdings.filter((holding) => !holding.held).length
  const rows = data.holdings.filter((holding) => showSold || holding.held)
  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="By holding"
        subtitle="Income over the last 12 months, and how often each one pays"
        action={
          sold ? (
            <button type="button" className="text-[13px] font-medium text-accent hover:underline" onClick={() => setShowSold((value) => !value)}>
              {showSold ? 'Hide sold' : `Show ${sold} sold`}
            </button>
          ) : undefined
        }
      />
      <div className="overflow-x-auto pt-1">
        <table className="w-full min-w-[820px] text-sm">
          <thead className="text-left text-xs text-ink-3">
            <tr>
              <th className="px-6 py-3 font-medium">Holding</th>
              <th className="px-3 py-3 text-right font-medium">Last 12 months</th>
              <th className="px-3 py-3 text-right font-medium" title="Last 12 months' income on today's value">Yield</th>
              <th className="px-3 py-3 text-right font-medium" title="Last 12 months' income on what you paid">On cost</th>
              <th className="px-3 py-3 font-medium">Pays</th>
              <th className="px-3 py-3 font-medium">Last paid</th>
              <th className="px-6 py-3 font-medium">Next, around</th>
            </tr>
          </thead>
          <tbody className="tabular">
            {rows.map((holding) => (
              <HoldingRow key={holding.asset_id} holding={holding} currency={data.base_currency} />
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

export function IncomePage() {
  const { baseCurrency } = usePreferences()
  const income = useIncome(baseCurrency)
  const data = income.data
  return (
    <>
      <PageHeader title="Income" subtitle="Dividends and interest, after withholding tax." />
      {income.isLoading ? (
        <div className="grid h-96 place-items-center">
          <Spinner />
        </div>
      ) : income.error ? (
        <QueryError error={income.error} onRetry={() => void income.refetch()} />
      ) : !data || data.holdings.length + data.months.filter((m) => toNumber(m.interest)).length === 0 ? (
        <Card>
          <EmptyState icon={<Coins className="size-5" />} title="No dividends or interest yet">
            They appear here once a statement with payouts is imported.
          </EmptyState>
        </Card>
      ) : (
        <div className={clsx('flex flex-col gap-4 transition-opacity sm:gap-5', income.isPlaceholderData && 'opacity-60')}>
          <Tiles data={data} />
          <div className="grid grid-cols-1 gap-4 sm:gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
            <MonthlyCard data={data} />
            <UpcomingCard data={data} />
          </div>
          <HoldingsCard data={data} />
          <p className="flex items-center gap-1.5 text-xs text-ink-3">
            <CalendarClock className="size-3.5" aria-hidden /> Dates and amounts ahead are estimates from past payments, not
            announcements.
          </p>
        </div>
      )}
    </>
  )
}
