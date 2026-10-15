import { useState } from "react";

import { formatMoney, formatPercent, formatQuantity, toNumber } from "@/lib/format";
import type { BaseCurrency, Holding } from "@/lib/types";

import { Badge, Button, Card, CardHeader, Delta } from "../ui/primitives";

const CLASS_LABEL: Record<Holding["asset_class"], string> = {
  equity: "Stock",
  etf: "ETF",
  bond: "Bond",
  fund: "Fund",
  crypto: "Crypto",
  commodity: "Commodity",
  other: "Other",
};

export function HoldingsTable({
  holdings,
  currency,
}: {
  holdings: Holding[];
  currency: BaseCurrency;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? holdings : holdings.slice(0, 6);

  return (
    <Card>
      <CardHeader title="Holdings" subtitle={`${holdings.length} positions, valued in ${currency}`} />
      <div className="-mx-5 overflow-x-auto sm:-mx-6">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="text-left text-xs font-medium tracking-wide text-muted uppercase">
              <th className="px-5 pb-3 font-medium sm:px-6">Asset</th>
              <th className="pb-3 text-right font-medium">Quantity</th>
              <th className="pb-3 text-right font-medium">Price</th>
              <th className="pb-3 text-right font-medium">Value</th>
              <th className="pb-3 text-right font-medium">Return</th>
              <th className="px-5 pb-3 text-right font-medium sm:px-6">Weight</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {visible.map((h) => {
              const gain = toNumber(h.unrealized_gain);
              const cost = toNumber(h.cost);
              return (
                <tr key={h.asset_id} className="hover:bg-surface-2/60">
                  <td className="px-5 py-3 sm:px-6">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-ink">{h.symbol}</span>
                      <Badge>{CLASS_LABEL[h.asset_class]}</Badge>
                    </div>
                    <div className="max-w-64 truncate text-xs text-muted">{h.name}</div>
                  </td>
                  <td className="tabular py-3 text-right text-muted">
                    {formatQuantity(h.quantity)}
                  </td>
                  <td className="tabular py-3 text-right whitespace-nowrap text-muted">
                    {h.price ? formatMoney(h.price, h.currency) : "—"}
                  </td>
                  <td className="tabular py-3 text-right font-medium whitespace-nowrap text-ink">
                    {formatMoney(h.value, currency)}
                  </td>
                  <td className="py-3 text-right whitespace-nowrap">
                    <Delta value={gain}>
                      {cost > 0 ? formatPercent(gain / cost, { signed: true }) : "—"}
                    </Delta>
                  </td>
                  <td className="px-5 py-3 sm:px-6">
                    <div className="flex items-center justify-end gap-2">
                      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-3">
                        <div
                          className="h-full rounded-full bg-brand"
                          style={{ width: `${Math.min(toNumber(h.weight) * 100 * 2.5, 100)}%` }}
                        />
                      </div>
                      <span className="tabular w-12 text-right text-muted">
                        {formatPercent(h.weight)}
                      </span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {holdings.length > 6 && (
        <div className="mt-4 flex justify-center">
          <Button variant="ghost" onClick={() => setExpanded((e) => !e)}>
            {expanded ? "Show fewer" : `Show all ${holdings.length}`}
          </Button>
        </div>
      )}
    </Card>
  );
}
