import { ExternalLink } from 'lucide-react'
import { useState, type ReactNode } from 'react'

import type { HoldingDetail } from '../../api/types'
import { ASSET_CLASS_LABELS, formatCompactMoney, formatPercent } from '../../lib/format'
import { Card, CardHeader } from '../ui/primitives'

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-t border-line py-2.5 first:border-t-0">
      <dt className="text-sm text-ink-3">{label}</dt>
      <dd className="min-w-0 text-right text-sm font-medium text-ink">{children}</dd>
    </div>
  )
}

function safeWebsite(url: string | null | undefined): { href: string; label: string } | null {
  if (!url) return null
  try {
    const parsed = new URL(url)
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') return null
    return { href: parsed.href, label: parsed.hostname.replace(/^www\./, '') }
  } catch {
    return null
  }
}

/** Fund facts for ETFs and funds, company facts for stocks — only the rows the data source filled in. */
export function AssetInfoCard({ detail }: { detail: HoldingDetail }) {
  const [expanded, setExpanded] = useState(false)
  const { asset, profile } = detail
  const isFund = asset.asset_class === 'etf' || asset.asset_class === 'fund' || asset.asset_class === 'commodity'
  const website = safeWebsite(profile?.website)
  const description = profile?.description

  return (
    <Card>
      <CardHeader title={isFund ? 'About this fund' : 'About this asset'} />
      <dl className="px-6 pb-2 pt-3">
        {profile?.long_name && profile.long_name !== asset.name ? <Row label="Full name">{profile.long_name}</Row> : null}
        {isFund && profile?.provider ? <Row label="Provider">{profile.provider}</Row> : null}
        {isFund && profile?.expense_ratio ? (
          <Row label="Yearly fee (TER)">{formatPercent(profile.expense_ratio, { digits: 2 })}</Row>
        ) : null}
        {isFund && profile?.fund_size ? <Row label="Fund size">{formatCompactMoney(profile.fund_size, asset.currency)}</Row> : null}
        {!isFund && profile?.sector ? <Row label="Sector">{profile.sector}</Row> : null}
        {!isFund && profile?.industry ? <Row label="Industry">{profile.industry}</Row> : null}
        <Row label="Type">{ASSET_CLASS_LABELS[asset.asset_class]}</Row>
        {asset.isin ? <Row label="ISIN">{asset.isin}</Row> : null}
        <Row label="Trading currency">{asset.currency}</Row>
        {asset.yf_ticker ? <Row label="Quote">{asset.yf_ticker}</Row> : null}
        {website ? (
          <Row label="Website">
            <a
              href={website.href}
              target="_blank"
              rel="noreferrer noopener"
              className="inline-flex items-center gap-1 text-accent hover:underline"
            >
              {website.label} <ExternalLink className="size-3" aria-hidden />
            </a>
          </Row>
        ) : null}
      </dl>
      {description ? (
        <div className="border-t border-line px-6 py-4">
          <p className={expanded ? 'text-sm text-ink-2' : 'line-clamp-4 text-sm text-ink-2'}>{description}</p>
          <button
            type="button"
            className="mt-2 text-sm font-medium text-accent hover:underline"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? 'Show less' : 'Show more'}
          </button>
        </div>
      ) : null}
      {!profile ? (
        <p className="border-t border-line px-6 py-4 text-xs text-ink-3">
          Fund and company details load with the next price refresh, when the data source has them.
        </p>
      ) : (
        <div className="pb-3" />
      )}
    </Card>
  )
}
