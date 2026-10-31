import { clsx } from 'clsx'
import { ChevronRight, Lock, LockOpen } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import type { AccountSummary } from '../../api/types'
import { formatMoney, formatMonthYear } from '../../lib/format'
import { Delta } from '../ui/Delta'
import { Badge } from '../ui/primitives'
import { Sensitive } from '../ui/Sensitive'

export function BrokerAvatar({ broker, className }: { broker: string; className?: string }) {
  const initials = broker
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase())
    .join('')
  return (
    <span
      className={clsx(
        'grid size-10 shrink-0 place-items-center rounded-2xl bg-accent-soft font-display text-sm font-bold text-accent',
        className,
      )}
      aria-hidden
    >
      {initials}
    </span>
  )
}

/** Hungarian TBSZ lock-up meter: vintage year start -> tax-free date, with the 10% milestone. */
/** Whole years and months from `now` until `until`: "3 years 2 months", or "3y 2m" when short. */
function timeLeft(now: number, until: string, short: boolean): string {
  const from = new Date(now)
  const to = new Date(until)
  let months = (to.getFullYear() - from.getFullYear()) * 12 + to.getMonth() - from.getMonth()
  if (to.getDate() < from.getDate()) months -= 1
  if (months < 1) return short ? '<1m' : 'less than a month'
  const years = Math.floor(months / 12)
  const rest = months % 12
  if (short) return [years ? `${years}y` : '', rest ? `${rest}m` : ''].filter(Boolean).join(' ')
  const part = (n: number, unit: string) => (n ? `${n} ${unit}${n === 1 ? '' : 's'}` : '')
  return [part(years, 'year'), part(rest, 'month')].filter(Boolean).join(' ')
}

export function TbszProgress({ account, compact = false }: { account: AccountSummary; compact?: boolean }) {
  const [now] = useState(() => Date.now())
  if (account.account_type !== 'tbsz' || !account.tbsz_year || !account.tbsz_tax_free_from) return null
  const start = new Date(account.tbsz_year, 0, 1).getTime()
  const end = new Date(account.tbsz_tax_free_from).getTime()
  const reduced = account.tbsz_reduced_rate_from ? new Date(account.tbsz_reduced_rate_from).getTime() : null
  const progress = Math.min(1, Math.max(0, (now - start) / (end - start)))
  const matured = progress >= 1
  return (
    <div className={clsx('flex flex-col gap-1.5', compact ? 'mt-2' : 'mt-3')}>
      {!matured && !compact ? (
        <p className="text-sm font-medium text-ink">{timeLeft(now, account.tbsz_tax_free_from, false)} until tax-free</p>
      ) : null}
      <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-accent-soft" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} aria-label="TBSZ lock-up progress">
        <div className="h-full rounded-full bg-accent" style={{ width: `${progress * 100}%` }} />
        {reduced ? (
          <span
            className="absolute top-0 h-full w-0.5 bg-surface"
            style={{ left: `${((reduced - start) / (end - start)) * 100}%` }}
            aria-hidden
          />
        ) : null}
      </div>
      <p className="flex items-center gap-1 text-xs text-ink-3">
        {matured ? <LockOpen className="size-3 shrink-0" aria-hidden /> : <Lock className="size-3 shrink-0" aria-hidden />}
        {matured ? 'Tax-free — lock-up complete' : `Tax-free from ${formatMonthYear(account.tbsz_tax_free_from)}`}
        {!matured && compact ? ` · ${timeLeft(now, account.tbsz_tax_free_from, true)} left` : ''}
        {!matured && account.tbsz_reduced_rate_from && !compact
          ? ` · 10% rate from ${formatMonthYear(account.tbsz_reduced_rate_from)}`
          : ''}
      </p>
    </div>
  )
}

export function AccountTypeBadge({ account }: { account: AccountSummary }) {
  return account.account_type === 'tbsz' ? <Badge tone="accent">TBSZ {account.tbsz_year}</Badge> : null
}

export function AccountRow({ account, currency }: { account: AccountSummary; currency: string }) {
  return (
    <Link
      to={`/accounts/${account.id}`}
      className="group grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 rounded-2xl px-3 py-3 transition-colors hover:bg-surface-2 active:bg-surface-2 sm:grid-cols-[auto_minmax(0,1fr)_auto_auto] sm:gap-x-4"
    >
      <BrokerAvatar broker={account.broker} className="sm:row-span-2" />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="min-w-0 truncate text-sm font-semibold text-ink">{account.name}</span>
          <AccountTypeBadge account={account} />
        </div>
        <p className="mt-0.5 truncate text-xs text-ink-3">
          {/* On a phone the section heading above already names the broker, and the width is needed. */}
          <span className="hidden sm:inline">{account.broker} · </span>
          {account.holdings_count} holding{account.holdings_count === 1 ? '' : 's'}
          {/* Cut off mid-number on a phone; the account's own page shows it. */}
          <span className="hidden sm:inline">
            <Sensitive>{account.currency !== currency && account.value_account_currency
              ? ` · ${formatMoney(account.value_account_currency, account.currency)}`
              : ''}</Sensitive>
          </span>
        </p>
      </div>
      <div className="text-right sm:row-span-2">
        <p className="tabular whitespace-nowrap text-sm font-semibold text-ink"><Sensitive>{formatMoney(account.value, currency)}</Sensitive></p>
        <Delta amount={account.total_pnl} currency={currency} className="text-xs" />
      </div>
      <ChevronRight className="hidden size-4 shrink-0 text-ink-3 transition-transform group-hover:translate-x-0.5 sm:row-span-2 sm:block" aria-hidden />
      {/* Full width on a phone, so the lock-up line stays on one line instead of wrapping in the narrow text column. */}
      <div className="col-span-full min-w-0 sm:col-span-1 sm:col-start-2">
        <TbszProgress account={account} compact />
      </div>
    </Link>
  )
}
