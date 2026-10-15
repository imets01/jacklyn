import { Info } from "lucide-react";
import { useState } from "react";

import { AccountsList } from "@/components/dashboard/AccountsList";
import { AddAccountModal } from "@/components/dashboard/AddAccountModal";
import { AllocationCard } from "@/components/dashboard/AllocationCard";
import { HoldingsTable } from "@/components/dashboard/HoldingsTable";
import { NetWorthCard } from "@/components/dashboard/NetWorthCard";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import { usePreferences } from "@/lib/preferences";
import { useAsync } from "@/lib/useAsync";

export function DashboardPage() {
  const { baseCurrency } = usePreferences();
  const summary = useAsync(() => api.summary(baseCurrency), [baseCurrency]);
  const [adding, setAdding] = useState(false);

  if (summary.error && !summary.data) {
    return <ErrorState error={summary.error} onRetry={summary.reload} />;
  }
  if (!summary.data) return <DashboardSkeleton />;

  const s = summary.data;
  return (
    <div className="grid grid-cols-1 gap-6">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Good to see you</h1>
          <p className="mt-1 text-sm text-muted">
            Your whole portfolio, in {s.base_currency}, as of{" "}
            {new Date(s.as_of).toLocaleDateString("en-GB", { dateStyle: "long" })}.
          </p>
        </div>
      </div>

      <NetWorthCard summary={s} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <div className="min-w-0 xl:col-span-2">
          <AllocationCard allocation={s.allocation} currency={s.base_currency} />
        </div>
        <div className="min-w-0 xl:col-span-3">
          <AccountsList
            accounts={s.accounts}
            currency={s.base_currency}
            onAddAccount={() => setAdding(true)}
          />
        </div>
      </div>

      <HoldingsTable holdings={s.holdings} currency={s.base_currency} />

      <p className="flex items-start gap-2 text-xs text-subtle">
        <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
        <span>
          Converted at {s.fx_source} FX rates:{" "}
          {Object.entries(s.fx_rates)
            .filter(([ccy]) => ccy !== s.base_currency)
            .map(([ccy, rate]) => `1 ${ccy} = ${Number(rate).toPrecision(4)} ${s.base_currency}`)
            .join(" · ")}
          {s.warnings.length > 0 && ` · ${s.warnings.join(" · ")}`}
        </span>
      </p>

      <AddAccountModal open={adding} onClose={() => setAdding(false)} onCreated={summary.reload} />
    </div>
  );
}

function DashboardSkeleton() {
  return (
    <div className="grid gap-6" aria-busy="true" aria-label="Loading dashboard">
      <Skeleton className="h-16 w-72" />
      <Skeleton className="h-[30rem]" />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-5">
        <Skeleton className="h-80 xl:col-span-2" />
        <Skeleton className="h-80 xl:col-span-3" />
      </div>
    </div>
  );
}
