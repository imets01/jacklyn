import { clsx } from 'clsx'
import { CircleCheck, CircleAlert, ShoppingCart } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import type { HealthReport, RebalancePlan } from '../../api/types'
import { formatMoney, formatPercent, formatQuantity, toNumber } from '../../lib/format'
import { AssetIcon } from '../assets/AssetIcon'
import { Card, CardHeader, Field, Input } from '../ui/primitives'
import { CitationList } from './Findings'
import { Sensitive } from '../ui/Sensitive'

function BandPill({ ok, label }: { ok: boolean; label: string }) {
  const Icon = ok ? CircleCheck : CircleAlert
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium',
        ok ? 'bg-positive-soft text-positive' : 'bg-warning-soft text-warning',
      )}
    >
      <Icon className="size-3.5" aria-hidden /> {label}
    </span>
  )
}

function monthsText(plan: RebalancePlan, currency: string): ReactNode {
  const monthly = toNumber(plan.monthly_contribution)
  if (plan.in_band_before) return 'Every asset class is already within its band.'
  if (monthly <= 0) return 'Add a monthly contribution to your profile to see how long contributions alone take.'
  const perMonth = <Sensitive>{formatMoney(monthly, currency)}</Sensitive>
  if (plan.months_to_band === null) {
    return <>At {perMonth} a month, contributions alone won&apos;t get back within the bands in 20 years.</>
  }
  return (
    <>
      At {perMonth} a month, contributions alone bring every class back within its band in about{' '}
      {plan.months_to_band} month{plan.months_to_band === 1 ? '' : 's'} (if prices stay put).
    </>
  )
}

export function RebalanceCard({
  report,
  plan,
  amount,
  onAmountChange,
  includeCash,
  onIncludeCashChange,
}: {
  report: HealthReport
  plan: RebalancePlan
  amount: string
  onAmountChange: (value: string) => void
  includeCash: boolean
  onIncludeCashChange: (value: boolean) => void
}) {
  const [showFull, setShowFull] = useState(false)
  const currency = report.base_currency
  const driftRule = report.rules.find((rule) => rule.id === 'allocation_drift')
  const idle = toNumber(plan.idle_cash)

  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="Rebalancing assistant"
        subtitle="What to buy with new money to move back toward your target, without selling."
        action={<BandPill ok={plan.in_band_before} label={plan.in_band_before ? 'Within bands' : 'Outside a band'} />}
      />
      <div className="flex flex-col gap-5 px-6 pb-6 pt-4">
        <div className="flex flex-wrap items-end gap-4">
          <div className="w-44">
            <Field label={`Amount to invest (${currency})`}>
              <Input type="number" min={0} step="any" value={amount} onChange={(e) => onAmountChange(e.target.value)} />
            </Field>
          </div>
          {idle > 0 ? (
            <label className="flex items-center gap-2 pb-2.5 text-sm text-ink-2">
              <input
                type="checkbox"
                className="size-4 accent-[var(--accent)]"
                checked={includeCash}
                onChange={(e) => onIncludeCashChange(e.target.checked)}
              />
              Also invest idle cash (<Sensitive>{formatMoney(idle, currency)}</Sensitive>)
            </label>
          ) : null}
          <label className="ml-auto flex items-center gap-2 pb-2.5 text-sm text-ink-2">
            <input type="checkbox" className="size-4 accent-[var(--accent)]" checked={showFull} onChange={(e) => setShowFull(e.target.checked)} />
            Show a full rebalance (with sells)
          </label>
        </div>

        <div className="-mx-6 overflow-x-auto">
          <table className={clsx('w-full text-sm', showFull ? 'min-w-[720px]' : 'min-w-[560px]')}>
            <thead className="text-left text-xs text-ink-3">
              <tr>
                <th className="px-6 py-2 font-medium">Asset class</th>
                <th className="px-3 py-2 text-right font-medium">Now</th>
                <th className="px-3 py-2 text-right font-medium">Target</th>
                <th className="px-3 py-2 text-right font-medium">After buys</th>
                <th className="px-3 py-2 text-right font-medium">Buy</th>
                {showFull ? <th className="px-6 py-2 text-right font-medium">Full rebalance</th> : null}
              </tr>
            </thead>
            <tbody className="tabular">
              {plan.rows.map((row) => {
                const off = Math.abs(toNumber(row.before) - toNumber(row.target)) > toNumber(row.band)
                return (
                  <tr key={row.category} className="border-t border-line">
                    <td className="px-6 py-2.5 text-ink">{row.label}</td>
                    <td className={clsx('px-3 py-2.5 text-right', off ? 'font-semibold text-warning' : 'text-ink-2')}>
                      {formatPercent(row.before, { digits: 1 })}
                    </td>
                    <td className="px-3 py-2.5 text-right text-ink-2">
                      {formatPercent(row.target, { digits: 0 })}
                      <span className="text-xs text-ink-3"> ±{formatPercent(row.band, { digits: 1 })}</span>
                    </td>
                    <td className="px-3 py-2.5 text-right text-ink-2">{formatPercent(row.after, { digits: 1 })}</td>
                    <td className="px-3 py-2.5 text-right font-semibold text-ink">
                      <Sensitive>{toNumber(row.buy) ? formatMoney(row.buy, currency) : '—'}</Sensitive>
                    </td>
                    {showFull ? (
                      <td
                        className={clsx(
                          'px-6 py-2.5 text-right font-medium',
                          toNumber(row.full_rebalance) > 0 ? 'text-positive' : toNumber(row.full_rebalance) < 0 ? 'text-negative' : 'text-ink-3',
                        )}
                      >
                        <Sensitive>{toNumber(row.full_rebalance) ? formatMoney(row.full_rebalance, currency, { signed: true }) : '—'}</Sensitive>
                      </td>
                    ) : null}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>

        <div>
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-ink">
            <ShoppingCart className="size-4 text-ink-3" aria-hidden /> Suggested buys
          </h3>
          {plan.orders.length ? (
            <ul className="flex flex-col gap-1">
              {plan.orders.map((order, index) => (
                <li key={`${order.category}-${order.asset_id ?? index}`} className="flex items-center gap-3 rounded-2xl bg-surface-2/60 px-3 py-2.5">
                  {order.symbol ? (
                    <AssetIcon symbol={order.symbol} name={order.name} assetClass={order.asset_class ?? undefined} logoUrl={order.logo_url} size="sm" />
                  ) : (
                    <span className="grid size-8 place-items-center rounded-full border border-dashed border-line-strong text-xs text-ink-3">?</span>
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-ink">
                      {order.symbol ? (order.name ?? order.symbol) : `No ${order.category_label.toLowerCase()} holding yet`}
                    </p>
                    <p className="truncate text-xs text-ink-3">
                      {order.symbol && order.quantity ? (
                        <>
                          {order.symbol} ·{' '}
                          <Sensitive>
                            {formatQuantity(order.quantity)} shares
                            {order.currency !== currency && order.local_amount
                              ? ` · ${formatMoney(order.local_amount, order.currency ?? currency)}`
                              : ''}
                          </Sensitive>
                        </>
                      ) : (
                        `${order.category_label}: pick an instrument you'd like to hold`
                      )}
                    </p>
                  </div>
                  <span className="shrink-0 text-sm font-semibold tabular text-ink"><Sensitive>{formatMoney(order.amount, currency)}</Sensitive></span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink-3">Nothing to buy for this amount.</p>
          )}
          <p className="mt-3 text-xs text-ink-3">
            Picks the cheapest fund you already hold in each class (then the largest).{' '}
            {plan.fractional_shares ? 'Fractional shares allowed.' : 'Whole shares only.'}
            <Sensitive>{toNumber(plan.min_order) ? ` Minimum order ${formatMoney(plan.min_order, currency)}.` : ''}</Sensitive>
            <Sensitive>{toNumber(plan.unspent) ? ` ${formatMoney(plan.unspent, currency)} stays uninvested.` : ''}</Sensitive>
          </p>
        </div>

        <div className="flex flex-col gap-2 rounded-2xl bg-surface-2/60 px-4 py-3 text-sm text-ink-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-ink-3">After these buys:</span>
            <BandPill ok={plan.in_band_after} label={plan.in_band_after ? 'within all bands' : 'still outside a band'} />
          </div>
          <p>{monthsText(plan, currency)}</p>
        </div>

        {showFull ? (
          <div className="flex flex-col gap-2 rounded-2xl border border-line px-4 py-3 text-xs text-ink-3">
            <p>
              A full rebalance sells what is overweight. Selling can trigger trading costs, currency conversion fees and,
              depending on where you live and your status, taxes. Check your own situation before selling. Research finds
              that rebalancing more often mostly adds costs.
            </p>
            {driftRule ? <CitationList citations={driftRule.citations} /> : null}
          </div>
        ) : null}
      </div>
    </Card>
  )
}
