import { useState } from "react";

import { formatMoney, formatPercent, toNumber } from "@/lib/format";
import { seriesColor } from "@/lib/palette";
import type { AllocationDimension, BaseCurrency, Bucket } from "@/lib/types";

import { Card, CardHeader, SegmentedControl, cx } from "../ui/primitives";

const DIMENSIONS: { value: AllocationDimension; label: string }[] = [
  { value: "asset_class", label: "Class" },
  { value: "currency", label: "Currency" },
  { value: "account", label: "Account" },
];

export function AllocationCard({
  allocation,
  currency,
}: {
  allocation: Record<AllocationDimension, Bucket[]>;
  currency: BaseCurrency;
}) {
  const [dimension, setDimension] = useState<AllocationDimension>("asset_class");
  const [hovered, setHovered] = useState<string | null>(null);
  const buckets = allocation[dimension].filter((b) => toNumber(b.value) > 0);
  const keys = buckets.map((b) => b.key);

  return (
    <Card className="h-full">
      <CardHeader
        title="Allocation"
        subtitle="Share of net worth"
        action={
          <SegmentedControl
            label="Allocation by"
            size="sm"
            value={dimension}
            options={DIMENSIONS}
            onChange={(d) => {
              setDimension(d);
              setHovered(null);
            }}
          />
        }
      />

      {/* 100% bar: one segment per bucket, 2px surface gaps between fills */}
      <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full" role="img"
        aria-label={buckets.map((b) => `${b.label} ${formatPercent(b.weight)}`).join(", ")}
      >
        {buckets.map((b) => (
          <div
            key={b.key}
            title={`${b.label}: ${formatPercent(b.weight)}`}
            onMouseEnter={() => setHovered(b.key)}
            onMouseLeave={() => setHovered(null)}
            className="h-full transition-opacity first:rounded-l-full last:rounded-r-full"
            style={{
              width: `${toNumber(b.weight) * 100}%`,
              background: seriesColor(dimension, b.key, keys),
              opacity: hovered && hovered !== b.key ? 0.35 : 1,
            }}
          />
        ))}
      </div>

      <ul className="mt-5 divide-y divide-line">
        {buckets.map((b) => (
          <li
            key={b.key}
            onMouseEnter={() => setHovered(b.key)}
            onMouseLeave={() => setHovered(null)}
            className={cx(
              "-mx-2 flex items-center gap-3 rounded-xl px-2 py-2.5 text-sm transition-colors",
              hovered === b.key && "bg-surface-2",
            )}
          >
            <span
              className="size-2.5 shrink-0 rounded-full"
              style={{ background: seriesColor(dimension, b.key, keys) }}
              aria-hidden
            />
            <span className="min-w-0 flex-1 truncate font-medium text-ink">{b.label}</span>
            <span className="tabular text-muted">{formatMoney(b.value, currency)}</span>
            <span className="tabular w-14 text-right font-semibold text-ink">
              {formatPercent(b.weight)}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
