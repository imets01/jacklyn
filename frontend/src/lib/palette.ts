import type { Institution } from "./types";

/**
 * Categorical slots (see --series-* in index.css). Colors are bound to the
 * *entity* via fixed key orders, never to rank, so filtering never repaints.
 */
export const SERIES = [1, 2, 3, 4, 5, 6].map((i) => `var(--series-${i})`);
const OTHER = "var(--text-subtle)";

const FIXED_ORDER: Record<string, readonly string[]> = {
  asset_class: ["etf", "equity", "bond", "cash", "fund", "crypto"],
  currency: ["CHF", "EUR", "USD", "HUF", "GBP"],
};

export function seriesColor(dimension: string, key: string, allKeys: readonly string[]) {
  const order = FIXED_ORDER[dimension] ?? [...allKeys].sort((a, b) => Number(a) - Number(b));
  const idx = order.indexOf(key);
  return idx >= 0 && idx < SERIES.length ? SERIES[idx]! : OTHER;
}

export const INSTITUTION_META: Record<Institution, { label: string; initials: string }> = {
  ibkr: { label: "Interactive Brokers", initials: "IB" },
  lightyear: { label: "Lightyear", initials: "LY" },
  erste: { label: "Erste NetBroker", initials: "ER" },
  other: { label: "Other", initials: "··" },
};
