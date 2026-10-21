import { Link } from 'react-router'

import type { AccountReturn, AccountSummary } from '../../api/types'
import { formatDate, formatMoney } from '../../lib/format'
import { totalReturn } from '../../lib/returns'
import { Sensitive } from '../ui/Sensitive'
import { ReturnRate } from './ReturnRate'

/** Every account side by side: value, gain and total return over the period, then the two yearly rates. */
export function AccountReturnsTable({
  rows,
  accounts,
  currency,
}: {
  rows: AccountReturn[]
  accounts: AccountSummary[]
  currency: string
}) {
  const byId = new Map(accounts.map((account) => [account.id, account]))
  const sorted = rows
    .filter((row) => byId.has(row.account_id))
    .map((row) => ({ row, total: totalReturn(row) }))
    .sort((a, b) => (b.total ?? -Infinity) - (a.total ?? -Infinity))
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] text-sm">
        <thead className="text-left text-xs text-ink-3">
          <tr>
            <th className="px-6 py-2.5 font-medium">Account</th>
            <th className="px-3 py-2.5 text-right font-medium">Value</th>
            <th className="px-3 py-2.5 text-right font-medium">Gain</th>
            <th className="px-3 py-2.5 text-right font-medium" title="Your money's return over the whole period">
              Total
            </th>
            <th className="px-3 py-2.5 text-right font-medium" title="Money-weighted: what your money earned">
              Your money
            </th>
            <th className="px-3 py-2.5 text-right font-medium" title="Time-weighted: how the investments did">
              Investments
            </th>
            <th className="px-6 py-2.5 text-right font-medium">Since</th>
          </tr>
        </thead>
        <tbody className="tabular">
          {sorted.map(({ row, total }) => (
            <tr key={row.account_id} className="border-t border-line">
              <td className="max-w-[220px] px-6 py-2.5">
                <Link to={`/accounts/${row.account_id}`} className="block truncate text-ink hover:text-accent hover:underline">
                  {byId.get(row.account_id)?.name}
                </Link>
              </td>
              <td className="px-3 py-2.5 text-right text-ink">
                <Sensitive>{formatMoney(row.end_value, currency)}</Sensitive>
              </td>
              <td className="px-3 py-2.5 text-right text-ink-2">
                <Sensitive>{formatMoney(row.gain, currency, { signed: true })}</Sensitive>
              </td>
              <td className="px-3 py-2.5 text-right">
                <ReturnRate rate={total} perYear={false} />
              </td>
              <td className="px-3 py-2.5 text-right">
                <ReturnRate rate={row.money_weighted} perYear={row.per_year} />
              </td>
              <td className="px-3 py-2.5 text-right">
                <ReturnRate rate={row.time_weighted} perYear={row.per_year} />
              </td>
              <td className="whitespace-nowrap px-6 py-2.5 text-right text-ink-3">{formatDate(row.start)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
