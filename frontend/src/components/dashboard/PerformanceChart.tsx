import { useId, useMemo } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatDate, formatMoney, toNumber } from "@/lib/format";
import type { BaseCurrency, PerformancePoint } from "@/lib/types";

interface Datum {
  date: string;
  value: number;
  contributions: number;
}

interface TooltipProps {
  active?: boolean;
  payload?: readonly { payload: Datum }[];
  currency: BaseCurrency;
}

function ChartTooltip({ active, payload, currency }: TooltipProps) {
  const d = payload?.[0]?.payload;
  if (!active || !d) return null;
  const gain = d.value - d.contributions;
  return (
    <div className="min-w-48 rounded-2xl border border-line bg-surface px-4 py-3 text-sm shadow-card">
      <div className="mb-2 text-xs text-muted">{formatDate(d.date)}</div>
      <Row swatch="var(--chart-line)" label="Value" value={formatMoney(d.value, currency)} />
      <Row
        swatch="var(--chart-ref)"
        dashed
        label="Net deposits"
        value={formatMoney(d.contributions, currency)}
      />
      <div className="mt-2 flex justify-between border-t border-line pt-2 text-xs">
        <span className="text-muted">Gain</span>
        <span className={gain >= 0 ? "tabular text-positive" : "tabular text-negative"}>
          {formatMoney(gain, currency, { signed: true })}
        </span>
      </div>
    </div>
  );
}

function Row(props: { swatch: string; label: string; value: string; dashed?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-6 py-0.5">
      <span className="flex items-center gap-2 text-muted">
        <Swatch color={props.swatch} dashed={props.dashed} />
        {props.label}
      </span>
      <span className="tabular font-medium text-ink">{props.value}</span>
    </div>
  );
}

export function Swatch({ color, dashed }: { color: string; dashed?: boolean }) {
  return (
    <svg width="16" height="8" aria-hidden className="shrink-0">
      <line
        x1="1"
        y1="4"
        x2="15"
        y2="4"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeDasharray={dashed ? "3 3" : undefined}
      />
    </svg>
  );
}

export function PerformanceChart({
  points,
  currency,
}: {
  points: PerformancePoint[];
  currency: BaseCurrency;
}) {
  const gradientId = useId();
  const data = useMemo<Datum[]>(
    () =>
      points.map((p) => ({
        date: p.date,
        value: toNumber(p.value),
        contributions: toNumber(p.net_contributions),
      })),
    [points],
  );

  if (data.length < 2) {
    return (
      <div className="grid h-64 place-items-center text-sm text-muted">
        Not enough history yet for this range.
      </div>
    );
  }

  const spanDays =
    (new Date(data[data.length - 1]!.date).getTime() - new Date(data[0]!.date).getTime()) /
    86_400_000;

  return (
    <figure>
      <div className="h-64 sm:h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--chart-area)" stopOpacity={0.22} />
                <stop offset="100%" stopColor="var(--chart-area)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              minTickGap={48}
              tickMargin={10}
              tick={{ fill: "var(--chart-axis)", fontSize: 12 }}
              tickFormatter={(d: string) =>
                spanDays > 200
                  ? new Date(d).toLocaleDateString("en-GB", { month: "short", year: "2-digit" })
                  : formatDate(d, "short")
              }
            />
            <YAxis
              orientation="right"
              width={64}
              tickLine={false}
              axisLine={false}
              tickCount={4}
              domain={["auto", "auto"]}
              tick={{ fill: "var(--chart-axis)", fontSize: 12 }}
              tickFormatter={(v: number) =>
                formatMoney(v, currency, { compact: true }).replace(`${currency}\u00a0`, "")
              }
            />
            <Tooltip
              cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1, strokeDasharray: "4 4" }}
              content={(props) => (
                <ChartTooltip
                  active={props.active}
                  payload={props.payload as unknown as TooltipProps["payload"]}
                  currency={currency}
                />
              )}
            />
            <Line
              type="monotone"
              dataKey="contributions"
              name="Net deposits"
              stroke="var(--chart-ref)"
              strokeWidth={2}
              strokeDasharray="4 4"
              dot={false}
              activeDot={false}
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="value"
              name="Portfolio value"
              stroke="var(--chart-line)"
              strokeWidth={2}
              fill={`url(#${gradientId})`}
              activeDot={{ r: 5, strokeWidth: 2, stroke: "var(--surface)" }}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
        <span className="flex items-center gap-2">
          <Swatch color="var(--chart-line)" /> Portfolio value
        </span>
        <span className="flex items-center gap-2">
          <Swatch color="var(--chart-ref)" dashed /> Net deposits
        </span>
      </figcaption>
    </figure>
  );
}
