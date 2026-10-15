import type { DecimalString } from "./types";

/**
 * The API sends decimals as strings. We only convert to `number` at the very
 * edge, for display and chart geometry — never to do money arithmetic.
 */
export const toNumber = (value: DecimalString | null | undefined): number =>
  value == null || value === "" ? 0 : Number(value);

const NO_DECIMALS = new Set(["HUF", "JPY"]);

const cache = new Map<string, Intl.NumberFormat>();
function formatter(key: string, make: () => Intl.NumberFormat) {
  let f = cache.get(key);
  if (!f) {
    f = make();
    cache.set(key, f);
  }
  return f;
}

export function formatMoney(
  value: DecimalString | number,
  currency: string,
  opts: { compact?: boolean; signed?: boolean } = {},
): string {
  const n = typeof value === "number" ? value : toNumber(value);
  const digits = NO_DECIMALS.has(currency) || opts.compact ? 0 : 2;
  const key = `m|${digits}|${opts.compact ? 1 : 0}`;
  const body = formatter(
    key,
    () =>
      new Intl.NumberFormat("en-CH", {
        minimumFractionDigits: digits,
        maximumFractionDigits: opts.compact ? 1 : digits,
        notation: opts.compact ? "compact" : "standard",
      }),
  ).format(Math.abs(n));
  const isZero = body.replace(/[^1-9]/g, "") === "";
  const sign = isZero ? "" : n < 0 ? "\u2212" : opts.signed ? "+" : "";
  return `${sign}${currency}\u00a0${body}`;
}

/** Splits a money string into the big integer part and the small decimal part for hero numbers. */
export function splitMoney(value: DecimalString, currency: string) {
  const n = toNumber(value);
  const digits = NO_DECIMALS.has(currency) ? 0 : 2;
  const parts = formatter(
    `p|${digits}`,
    () =>
      new Intl.NumberFormat("en-CH", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }),
  ).formatToParts(n);
  const whole = parts
    .filter((p) => p.type !== "decimal" && p.type !== "fraction")
    .map((p) => p.value)
    .join("");
  const fraction = parts.find((p) => p.type === "fraction")?.value;
  return { whole, fraction: fraction ? `.${fraction}` : "" };
}

export function formatPercent(ratio: DecimalString | number, opts: { signed?: boolean } = {}) {
  const n = typeof ratio === "number" ? ratio : toNumber(ratio);
  return formatter(
    `pct|${opts.signed ? 1 : 0}`,
    () =>
      new Intl.NumberFormat("en-CH", {
        style: "percent",
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
        signDisplay: opts.signed ? "exceptZero" : "auto",
      }),
  ).format(n);
}

export function formatQuantity(value: DecimalString | null) {
  if (value == null) return "—";
  const n = toNumber(value);
  return formatter(
    "qty",
    () => new Intl.NumberFormat("en-CH", { maximumFractionDigits: 4 }),
  ).format(n);
}

export function formatDate(iso: string, style: "short" | "medium" = "medium") {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    ...(style === "medium" ? { year: "numeric" } : {}),
  });
}

export const signTone = (value: DecimalString | number) => {
  const n = typeof value === "number" ? value : toNumber(value);
  return n > 0 ? "positive" : n < 0 ? "negative" : "neutral";
};
