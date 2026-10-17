import { ChevronDown, HeartPulse, Pencil, ShieldCheck } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'

import { useHealthReport } from '../api/hooks'
import type { HealthCategory, HealthReport } from '../api/types'
import { AssetIcon } from '../components/assets/AssetIcon'
import { BreakdownCard } from '../components/health/BreakdownCard'
import { CitationList, FindingsCard, ScoreCard } from '../components/health/Findings'
import { ProfileModal } from '../components/health/ProfileModal'
import { RebalanceCard } from '../components/health/RebalanceCard'
import { PageHeader } from '../components/layout/PageHeader'
import { Button, Card, CardHeader, EmptyState, Notice, Spinner } from '../components/ui/primitives'
import { formatMoney, formatPercent, toNumber } from '../lib/format'
import { CATEGORY_LABELS, RISK_LABELS } from '../lib/health'
import { usePreferences } from '../lib/preferences-context'
import { QueryError } from './QueryError'
import { Sensitive } from '../components/ui/Sensitive'

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])
  return debounced
}

function targetText(targets: HealthReport['targets']): string {
  if (!targets) return '—'
  return Object.entries(targets)
    .filter(([, weight]) => toNumber(weight) > 0)
    .map(([key, weight]) => `${formatPercent(weight, { digits: 0 })} ${CATEGORY_LABELS[key as HealthCategory].toLowerCase()}`)
    .join(' · ')
}

function ProfileCard({ report, onEdit }: { report: HealthReport; onEdit: () => void }) {
  const profile = report.profile
  if (!profile) {
    return (
      <Card className="flex flex-col items-start gap-3 px-6 py-5 sm:flex-row sm:items-center">
        <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent">
          <HeartPulse className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-ink">Set up your investor profile</p>
          <p className="text-sm text-ink-3">
            Your horizon and risk tolerance give a target allocation, which unlocks the drift checks and the rebalancing
            assistant. The checks below already run without it.
          </p>
        </div>
        <Button variant="primary" onClick={onEdit}>
          Set up profile
        </Button>
      </Card>
    )
  }
  const facts = [
    report.horizon_years != null ? `${report.horizon_years} years horizon` : null,
    RISK_LABELS[profile.risk_tolerance].label,
    profile.goal,
  ].filter(Boolean)
  return (
    <Card className="flex flex-col gap-3 px-6 py-5 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink-3">
          {facts.join(' · ')}
          {profile.monthly_contribution ? (
            <>
              {' · '}
              <Sensitive>{formatMoney(profile.monthly_contribution, profile.currency)}</Sensitive> / month
            </>
          ) : null}
        </p>
        <p className="mt-1 font-semibold text-ink">Target: {targetText(report.targets)}</p>
        <p className="mt-0.5 text-xs text-ink-3">
          {report.targets_source === 'manual' ? (
            'Your own targets.'
          ) : (
            <>
              Suggested from{' '}
              <a href={report.glide_citation.url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
                Vanguard&apos;s target-date glide path
              </a>{' '}
              ({formatPercent(report.suggested_equity, { digits: 0 })} stocks), shifted by your risk tolerance (a Jacklyn
              convention).
            </>
          )}
        </p>
      </div>
      <Button size="sm" onClick={onEdit}>
        <Pencil className="size-3.5" aria-hidden /> Edit profile
      </Button>
    </Card>
  )
}

function PositionsCard({ report }: { report: HealthReport }) {
  const top = report.positions.slice(0, 8)
  const weighted = report.ter.weighted
  return (
    <Card className="overflow-hidden">
      <CardHeader title="Positions & costs" subtitle={`${report.positions.length} positions · share of your portfolio incl. cash`} />
      <ul className="flex flex-col gap-0.5 px-3 pt-3">
        {top.map((position) => (
          <li key={position.asset_id}>
            <Link to={`/holdings/${position.asset_id}`} className="flex items-center gap-3 rounded-2xl px-3 py-2 hover:bg-surface-2">
              <AssetIcon symbol={position.symbol} name={position.name} assetClass={position.asset_class} logoUrl={position.logo_url} size="sm" />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium text-ink">{position.name ?? position.symbol}</span>
                <span className="block text-xs text-ink-3">
                  {position.symbol}
                  {position.ter ? ` · TER ${formatPercent(position.ter, { digits: 2 })}` : ''}
                </span>
              </span>
              <span className="text-sm font-semibold tabular text-ink">{formatPercent(position.weight, { digits: 1 })}</span>
            </Link>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex flex-col gap-2 border-t border-line px-6 py-4 text-sm">
        <p className="flex justify-between gap-3">
          <span className="text-ink-3">Average fund cost (TER, value-weighted)</span>
          <span className="font-semibold tabular text-ink">{weighted ? formatPercent(weighted, { digits: 2 }) : '—'}</span>
        </p>
        {weighted ? (
          <p className="text-xs text-ink-3">
            ≈ <Sensitive>{formatMoney(toNumber(weighted) * toNumber(report.ter.covered_value), report.base_currency)}</Sensitive> a year on{' '}
            <Sensitive>{formatMoney(report.ter.covered_value, report.base_currency)}</Sensitive> in funds
            <Sensitive>{toNumber(report.ter.uncovered_value) ? `; TER unknown for ${formatMoney(report.ter.uncovered_value, report.base_currency)}` : ''}</Sensitive>.
          </p>
        ) : null}
        {report.overlaps.length ? (
          <div className="text-xs text-ink-3">
            <p className="mb-1 font-medium text-ink-2">Fund overlap (information only):</p>
            <ul>
              {report.overlaps.slice(0, 3).map((overlap) => (
                <li key={`${overlap.first}-${overlap.second}`}>
                  {overlap.first} & {overlap.second}: {overlap.complete ? '' : 'at least '}
                  {formatPercent(overlap.shared, { digits: 1 })} in the same companies
                  {overlap.complete ? '' : ' (top-10 holdings only)'}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Card>
  )
}

function MethodCard({ report }: { report: HealthReport }) {
  const [open, setOpen] = useState(false)
  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-3 px-6 py-4 text-left hover:bg-surface-2/60"
      >
        <ShieldCheck className="size-5 text-accent" aria-hidden />
        <span className="flex-1">
          <span className="block text-[15px] font-semibold text-ink">Rules, sources & data notes</span>
          <span className="block text-sm text-ink-3">{report.rules.length} rules, each with its thresholds and citations.</span>
        </span>
        <ChevronDown className={`size-4 text-ink-3 transition-transform ${open ? 'rotate-180' : ''}`} aria-hidden />
      </button>
      {open ? (
        <div className="flex flex-col gap-6 border-t border-line px-6 py-5 text-sm">
          <ul className="flex flex-col gap-4">
            {report.rules.map((rule) => (
              <li key={rule.id}>
                <p className="font-medium text-ink">
                  {rule.title}
                  {report.skipped_rules.includes(rule.id) ? <span className="text-xs font-normal text-ink-3"> · not applicable to your data</span> : null}
                </p>
                <p className="mb-1.5 text-xs text-ink-3">
                  {rule.levels.join(' · ')} — {rule.threshold_note}
                </p>
                <CitationList citations={rule.citations} />
              </li>
            ))}
          </ul>
          {report.look_through_provider ? (
            <div>
              <p className="mb-1 font-medium text-ink">Fund look-through</p>
              <p className="text-xs text-ink-3">
                Fund country mixes and full holdings from{' '}
                <a href="https://eulerpool.com" target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
                  {report.look_through_provider}
                </a>
                ; fund sectors, costs and prices from Yahoo Finance.
              </p>
            </div>
          ) : null}
          <div>
            <p className="mb-1 font-medium text-ink">Benchmark</p>
            <ul className="text-xs text-ink-3">
              {report.benchmark_sources.map((source) => (
                <li key={source.url}>
                  <a href={source.url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
                    {source.title}
                  </a>{' '}
                  — {source.publisher}, as of {source.as_of}
                </li>
              ))}
            </ul>
          </div>
          {report.notes.length ? (
            <div>
              <p className="mb-1 font-medium text-ink">Approximations in your data</p>
              <ul className="list-disc pl-5 text-xs text-ink-3">
                {report.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </Card>
  )
}

export function HealthPage() {
  const { baseCurrency } = usePreferences()
  const [editing, setEditing] = useState(false)
  const [amountText, setAmountText] = useState<string | null>(null)
  const [includeCash, setIncludeCash] = useState(false)
  const amount = useDebounced(amountText, 400)
  const health = useHealthReport(baseCurrency, amount !== null && amount !== '' ? amount : null, includeCash)
  const report = health.data

  return (
    <>
      <PageHeader title="Portfolio health" subtitle="Evidence-based checks of your diversification, costs and allocation." />
      <div className="flex flex-col gap-4 sm:gap-5">
        <Notice tone="neutral" icon={<ShieldCheck className="size-4" />}>
          Educational information, not personal financial advice. Findings comes from a fixed rule with published
          sources you can check below; nothing here is made up by AI.
        </Notice>
        {health.isLoading ? (
          <div className="grid h-80 place-items-center">
            <Spinner />
          </div>
        ) : health.error || !report ? (
          <QueryError error={health.error ?? new Error('No report')} onRetry={() => void health.refetch()} />
        ) : !report.has_holdings ? (
          <Card>
            <EmptyState icon={<HeartPulse className="size-5" />} title="Nothing to check yet">
              <Link to="/import" className="font-medium text-accent hover:underline">
                Import a statement
              </Link>{' '}
              and the health check runs on your holdings.
            </EmptyState>
          </Card>
        ) : (
          <>
            <ProfileCard report={report} onEdit={() => setEditing(true)} />
            <div className="grid grid-cols-1 gap-4 sm:gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
              <ScoreCard report={report} />
              <FindingsCard
                title="Issues"
                subtitle="Warnings and problems lower the score; info notes don't."
                findings={report.findings.filter((f) => f.severity !== 'good')}
                empty="No issues found by the current rules."
              />
            </div>
            <FindingsCard
              title="Strengths"
              subtitle="Rules your portfolio passes."
              findings={report.findings.filter((f) => f.severity === 'good')}
              empty="No strengths yet — the rules above show what to work on."
            />
            <div className="grid grid-cols-1 gap-4 sm:gap-5 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
              <BreakdownCard report={report} />
              <PositionsCard report={report} />
            </div>
            {report.rebalance ? (
              <RebalanceCard
                report={report}
                plan={report.rebalance}
                amount={amountText ?? report.rebalance.monthly_contribution.replace(/\.0+$/, '')}
                onAmountChange={setAmountText}
                includeCash={includeCash}
                onIncludeCashChange={setIncludeCash}
              />
            ) : (
              <Card className="px-6 py-5 text-sm text-ink-3">
                The rebalancing assistant needs a target allocation.{' '}
                <button type="button" className="font-medium text-accent hover:underline" onClick={() => setEditing(true)}>
                  Set up your profile
                </button>{' '}
                to use it.
              </Card>
            )}
            <MethodCard report={report} />
          </>
        )}
      </div>
      <ProfileModal open={editing} profile={report?.profile ?? null} onClose={() => setEditing(false)} />
    </>
  )
}
