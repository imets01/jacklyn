import { TrendingDown, TrendingUp } from "lucide-react";
import { lazy, Suspense, useState } from "react";

import { api } from "@/lib/api";
import { formatMoney, formatPercent, splitMoney, toNumber } from "@/lib/format";
import { PERFORMANCE_RANGES, type PerformanceRange, type PortfolioSummary } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";

import { Card, Delta, SegmentedControl, Skeleton } from "../ui/primitives";
// Recharts is the heaviest dependency; load it in its own chunk.
const PerformanceChart = lazy(() =>
  import("./PerformanceChart").then((m) => ({ default: m.PerformanceChart })),
);

export function NetWorthCard({ summary }: { summary: PortfolioSummary }) {
  const currency = summary.base_currency;
  const [range, setRange] = useState<PerformanceRange>("1Y");
  const perf = useAsync(() => api.performance(currency, range), [currency, range]);

  const { whole, fraction } = splitMoney(summary.net_worth, currency);
  const totalGain = toNumber(summary.total_gain);
  const periodGain = perf.data ? toNumber(perf.data.gain) : 0;
  const TrendIcon = totalGain >= 0 ? TrendingUp : TrendingDown;

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-start justify-between gap-6">
        <div>
          <p className="text-sm font-medium text-muted">Total net worth</p>
          <p className="mt-2 flex items-baseline gap-2 tracking-tight">
            <span className="tabular text-4xl font-semibold text-ink sm:text-5xl">{whole}</span>
            <span className="tabular text-2xl font-semibold text-subtle sm:text-3xl">
              {fraction}
            </span>
            <span className="ml-1 text-lg font-medium text-muted">{currency}</span>
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span
              className={
                totalGain >= 0
                  ? "inline-flex items-center gap-1 rounded-full bg-positive-soft px-2.5 py-1 font-medium text-positive"
                  : "inline-flex items-center gap-1 rounded-full bg-negative-soft px-2.5 py-1 font-medium text-negative"
              }
            >
              <TrendIcon className="size-4" aria-hidden />
              <span className="tabular">
                {formatMoney(summary.total_gain, currency, { signed: true })} (
                {formatPercent(summary.total_gain_pct, { signed: true })})
              </span>
            </span>
            <span className="text-muted">all-time gain on net deposits</span>
          </div>
        </div>

        <dl className="grid grid-cols-3 gap-6 text-sm sm:gap-10">
          <Stat label="Invested" value={formatMoney(summary.invested, currency)} />
          <Stat label="Cash" value={formatMoney(summary.cash, currency)} />
          <Stat label="Net deposits" value={formatMoney(summary.net_contributions, currency)} />
        </dl>
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <div className="text-sm text-muted">
          {perf.data ? (
            <>
              <Delta value={periodGain}>
                {formatMoney(perf.data.gain, currency, { signed: true })} (
                {formatPercent(perf.data.gain_pct, { signed: true })})
              </Delta>{" "}
              market gain · {range === "ALL" ? "all time" : range}
            </>
          ) : (
            <span>&nbsp;</span>
          )}
        </div>
        <SegmentedControl
          label="Chart range"
          size="sm"
          value={range}
          options={PERFORMANCE_RANGES}
          onChange={setRange}
        />
      </div>

      <div className="mt-4" aria-busy={perf.loading}>
        {perf.error ? (
          <p className="grid h-64 place-items-center text-sm text-negative">
            {perf.error.message}
          </p>
        ) : perf.data ? (
          <div className={perf.loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
            <Suspense fallback={<Skeleton className="h-72" />}>
              <PerformanceChart points={perf.data.points} currency={currency} />
            </Suspense>
          </div>
        ) : (
          <Skeleton className="h-72" />
        )}
      </div>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium tracking-wide text-muted uppercase">{label}</dt>
      <dd className="tabular mt-1 font-semibold whitespace-nowrap text-ink">{value}</dd>
    </div>
  );
}
