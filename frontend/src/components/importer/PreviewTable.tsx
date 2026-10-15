import { AlertCircle, CheckCircle2, CopyMinus } from "lucide-react";
import { useState } from "react";

import { formatDate, formatMoney, formatQuantity } from "@/lib/format";
import { TYPE_LABELS } from "@/lib/labels";
import type { ImportPreview, PreviewStatus } from "@/lib/types";

import { SegmentedControl, cx } from "../ui/primitives";

type Filter = "all" | PreviewStatus;

const STATUS: Record<PreviewStatus, { icon: typeof CheckCircle2; label: string; className: string }> =
  {
    new: { icon: CheckCircle2, label: "New", className: "text-positive" },
    duplicate: { icon: CopyMinus, label: "Already imported", className: "text-subtle" },
    error: { icon: AlertCircle, label: "Error", className: "text-negative" },
  };

export function PreviewTable({ preview }: { preview: ImportPreview }) {
  const [filter, setFilter] = useState<Filter>(preview.counts.error > 0 ? "error" : "all");
  const rows = filter === "all" ? preview.rows : preview.rows.filter((r) => r.status === filter);
  const c = preview.counts;

  return (
    <div>
      <SegmentedControl<Filter>
        label="Filter rows"
        size="sm"
        value={filter}
        onChange={setFilter}
        options={[
          { value: "all", label: `All ${c.total}` },
          { value: "new", label: `New ${c.new}` },
          { value: "duplicate", label: `Duplicates ${c.duplicate}` },
          { value: "error", label: `Errors ${c.error}` },
        ]}
      />
      <div className="mt-4 max-h-[28rem] overflow-auto rounded-2xl border border-line">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="sticky top-0 bg-surface-2 text-left text-xs font-medium tracking-wide text-muted uppercase">
            <tr>
              <th className="px-4 py-2.5 font-medium">Row</th>
              <th className="py-2.5 font-medium">Date</th>
              <th className="py-2.5 font-medium">Type</th>
              <th className="py-2.5 font-medium">Asset</th>
              <th className="py-2.5 text-right font-medium">Qty</th>
              <th className="py-2.5 text-right font-medium">Price</th>
              <th className="px-4 py-2.5 text-right font-medium">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-muted">
                  Nothing here.
                </td>
              </tr>
            )}
            {rows.map((r, i) => {
              const s = STATUS[r.status];
              const Icon = s.icon;
              return (
                <tr
                  key={`${r.row_number}-${i}`}
                  className={cx(r.status === "duplicate" && "opacity-60")}
                >
                  <td className="px-4 py-2.5">
                    <span className={cx("flex items-center gap-1.5", s.className)} title={s.label}>
                      <Icon className="size-4" aria-label={s.label} />
                      <span className="tabular text-xs text-muted">{r.row_number}</span>
                    </span>
                  </td>
                  {r.status === "error" ? (
                    <td colSpan={6} className="py-2.5 pr-4 text-negative">
                      {r.message}
                    </td>
                  ) : (
                    <>
                      <td className="py-2.5 whitespace-nowrap text-muted">
                        {r.trade_date && formatDate(r.trade_date)}
                      </td>
                      <td className="py-2.5">{r.type && TYPE_LABELS[r.type]}</td>
                      <td className="max-w-48 truncate py-2.5 font-medium" title={r.name ?? undefined}>
                        {r.symbol ?? r.isin ?? <span className="text-subtle">—</span>}
                      </td>
                      <td className="tabular py-2.5 text-right text-muted">
                        {r.quantity ? formatQuantity(r.quantity) : ""}
                      </td>
                      <td className="tabular py-2.5 text-right whitespace-nowrap text-muted">
                        {r.price && r.currency ? formatMoney(r.price, r.currency) : ""}
                      </td>
                      <td className="tabular px-4 py-2.5 text-right font-medium whitespace-nowrap">
                        {r.amount && r.currency ? formatMoney(r.amount, r.currency) : ""}
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {preview.rows_truncated && (
        <p className="mt-2 text-xs text-muted">
          Showing the first {preview.rows.length} rows; all {c.total} are imported.
        </p>
      )}
    </div>
  );
}
