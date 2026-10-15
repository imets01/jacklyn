import { Hourglass, Landmark, Plus, ShieldCheck } from "lucide-react";

import { formatDate, formatMoney, formatPercent, toNumber } from "@/lib/format";
import { INSTITUTION_META } from "@/lib/palette";
import type { AccountSummary, BaseCurrency, Tbsz } from "@/lib/types";

import { Badge, Button, Card, CardHeader, Delta } from "../ui/primitives";

const TBSZ_PHASE: Record<Tbsz["phase"], { label: string; tone: "brand" | "warning" | "positive" }> =
  {
    collecting: { label: "Collection year", tone: "brand" },
    locked: { label: "Locked", tone: "warning" },
    reduced_tax: { label: "10% tax window", tone: "warning" },
    matured: { label: "Tax-free", tone: "positive" },
  };

export function AccountsList({
  accounts,
  currency,
  onAddAccount,
}: {
  accounts: AccountSummary[];
  currency: BaseCurrency;
  onAddAccount: () => void;
}) {
  return (
    <Card>
      <CardHeader
        title="Accounts & TBSZ"
        subtitle={`${accounts.length} accounts across ${new Set(accounts.map((a) => a.account.institution)).size} brokers`}
        action={
          <Button variant="ghost" onClick={onAddAccount} icon={<Plus className="size-4" aria-hidden />}>
            Add account
          </Button>
        }
      />
      <ul className="grid gap-3">
        {accounts.map((a) => (
          <AccountRow key={a.account.id} summary={a} currency={currency} />
        ))}
      </ul>
    </Card>
  );
}

function AccountRow({ summary, currency }: { summary: AccountSummary; currency: BaseCurrency }) {
  const { account } = summary;
  const meta = INSTITUTION_META[account.institution];
  const gain = toNumber(summary.gain);
  const contributions = toNumber(summary.net_contributions);
  const showNative = account.base_currency !== currency;

  return (
    <li className="rounded-2xl border border-line bg-surface-2/40 p-4 transition-colors hover:bg-surface-2">
      <div className="flex items-start gap-3">
        <div
          className="grid size-11 shrink-0 place-items-center rounded-2xl bg-brand-soft text-sm font-semibold text-brand-strong"
          aria-hidden
        >
          {meta.initials}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate font-semibold text-ink">{account.name}</h3>
            {account.account_type === "swiss" && (
              <Badge tone="neutral">
                <Landmark className="size-3" aria-hidden /> Swiss
              </Badge>
            )}
            {account.account_type === "tbsz" && (
              <Badge tone="brand">
                <ShieldCheck className="size-3" aria-hidden /> TBSZ {account.tbsz_year}
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted">
            {meta.label} · {summary.holdings_count} holdings · {account.base_currency}
          </p>
        </div>
        <div className="text-right">
          <div className="tabular font-semibold whitespace-nowrap text-ink">
            {formatMoney(summary.value, currency)}
          </div>
          {showNative && (
            <div className="tabular text-xs whitespace-nowrap text-muted">
              {formatMoney(summary.value_in_account_currency, account.base_currency)}
            </div>
          )}
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between text-xs">
        <span className="text-muted">
          {formatPercent(summary.weight)} of portfolio · cash{" "}
          {formatMoney(summary.cash, currency, { compact: Math.abs(toNumber(summary.cash)) >= 10_000 })}
        </span>
        <Delta value={gain}>
          {formatMoney(summary.gain, currency, { signed: true })}
          {contributions > 0 && ` · ${formatPercent(gain / contributions, { signed: true })}`}
        </Delta>
      </div>

      {account.tbsz && <TbszProgress tbsz={account.tbsz} />}
    </li>
  );
}

function TbszProgress({ tbsz }: { tbsz: Tbsz }) {
  const phase = TBSZ_PHASE[tbsz.phase];
  // Marker for the 3-year (reduced tax) milestone along the 6-year timeline.
  const reducedAt = 4 / 6;
  return (
    <div className="mt-4 rounded-xl bg-surface p-3">
      <div className="flex items-center justify-between text-xs">
        <Badge tone={phase.tone}>
          <Hourglass className="size-3" aria-hidden /> {phase.label}
        </Badge>
        <span className="text-muted">
          Tax-free from <span className="font-medium text-ink">{formatDate(tbsz.maturity_date)}</span>
        </span>
      </div>
      <div
        className="relative mt-3 h-2 rounded-full bg-surface-3"
        role="progressbar"
        aria-label="TBSZ lock-up progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(tbsz.progress * 100)}
      >
        <div
          className="h-full rounded-full bg-brand"
          style={{ width: `${tbsz.progress * 100}%` }}
        />
        <div
          className="absolute -top-1 h-4 w-0.5 rounded-full bg-subtle"
          style={{ left: `${reducedAt * 100}%` }}
          title={`10% tax from ${formatDate(tbsz.reduced_tax_date)}`}
        />
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-subtle">
        <span>{tbsz.year}</span>
        <span>{tbsz.days_to_maturity.toLocaleString("en-CH")} days to go</span>
        <span>{tbsz.year + 5}</span>
      </div>
    </div>
  );
}
