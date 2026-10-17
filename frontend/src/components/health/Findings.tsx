import { clsx } from 'clsx'
import { ChevronDown, CircleAlert, CircleCheck, ExternalLink, Info, OctagonAlert } from 'lucide-react'
import { useState } from 'react'

import type { Citation, Finding, HealthReport, Severity } from '../../api/types'
import { Card, CardHeader } from '../ui/primitives'

const SEVERITY: Record<Severity, { label: string; icon: typeof Info; tone: string; chip: string }> = {
  problem: { label: 'Problem', icon: OctagonAlert, tone: 'text-negative', chip: 'bg-negative-soft text-negative' },
  warning: { label: 'Warning', icon: CircleAlert, tone: 'text-warning', chip: 'bg-warning-soft text-warning' },
  info: { label: 'Info', icon: Info, tone: 'text-ink-2', chip: 'bg-surface-2 text-ink-2' },
  good: { label: 'Good', icon: CircleCheck, tone: 'text-positive', chip: 'bg-positive-soft text-positive' },
}

export function CitationList({ citations }: { citations: Citation[] }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {citations.map((citation) => (
        <li key={citation.url} className="text-xs text-ink-2">
          <a href={citation.url} target="_blank" rel="noreferrer noopener" className="inline-flex items-start gap-1 font-medium text-accent hover:underline">
            {citation.title} <ExternalLink className="mt-0.5 size-3 shrink-0" aria-hidden />
          </a>
          <span className="text-ink-3">
            {' '}
            — {citation.publisher}, {citation.year}
            {citation.note ? `. ${citation.note}` : ''}
          </span>
        </li>
      ))}
    </ul>
  )
}

function FindingRow({ finding }: { finding: Finding }) {
  const [open, setOpen] = useState(false)
  const meta = SEVERITY[finding.severity]
  const Icon = meta.icon
  return (
    <li className="border-t border-line first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-start gap-3 px-6 py-4 text-left hover:bg-surface-2/60"
      >
        <Icon className={clsx('mt-0.5 size-5 shrink-0', meta.tone)} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold text-ink">{finding.title}</span>
            <span className={clsx('rounded-full px-2 py-0.5 text-[11px] font-semibold', meta.chip)}>{meta.label}</span>
          </span>
          <span className="mt-1 block text-sm text-ink-2">{finding.message}</span>
        </span>
        <span className="mt-0.5 inline-flex shrink-0 items-center gap-1 text-xs font-medium text-ink-3">
          Why?
          <ChevronDown className={clsx('size-3.5 transition-transform', open && 'rotate-180')} aria-hidden />
        </span>
      </button>
      {open ? (
        <div className="flex flex-col gap-3 px-6 pb-5 pl-14 text-sm">
          <p className="text-ink-2">{finding.explanation}</p>
          <p className="text-xs text-ink-3">
            <span className="font-medium text-ink-2">Threshold:</span> {finding.threshold}. {finding.threshold_note}
          </p>
          <CitationList citations={finding.citations} />
        </div>
      ) : null}
    </li>
  )
}

export function FindingsCard({ title, subtitle, findings, empty }: { title: string; subtitle: string; findings: Finding[]; empty: string }) {
  return (
    <Card className="overflow-hidden">
      <CardHeader title={title} subtitle={subtitle} />
      {findings.length ? (
        <ul className="mt-3">
          {findings.map((finding) => (
            <FindingRow key={finding.rule_id} finding={finding} />
          ))}
        </ul>
      ) : (
        <p className="px-6 pb-6 pt-3 text-sm text-ink-3">{empty}</p>
      )}
    </Card>
  )
}

export function ScoreCard({ report }: { report: HealthReport }) {
  const tone = report.score >= 85 ? 'text-positive' : report.score >= 65 ? 'text-warning' : 'text-negative'
  return (
    <Card className="flex flex-col gap-4 px-6 py-5">
      <div>
        <p className="text-sm font-medium text-ink-3">Health score</p>
        <p className={clsx('mt-1 font-display text-5xl font-bold tabular', tone)}>
          {report.score}
          <span className="text-xl font-semibold text-ink-3">/{report.score_start}</span>
        </p>
      </div>
      <div className="text-xs text-ink-3">
        <p className="mb-2">
          Starts at {report.score_start}. Each warning subtracts {report.score_penalties.warning ?? 0} and each problem{' '}
          {report.score_penalties.problem ?? 0}; info and strengths don&apos;t count.
        </p>
        {report.score_lines.length ? (
          <ul className="flex flex-col gap-1">
            {report.score_lines.map((line) => (
              <li key={line.rule_id} className="flex justify-between gap-3">
                <span className="truncate text-ink-2">{line.title}</span>
                <span className="tabular font-semibold text-negative">{line.points}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="font-medium text-positive">No warnings or problems.</p>
        )}
      </div>
    </Card>
  )
}
