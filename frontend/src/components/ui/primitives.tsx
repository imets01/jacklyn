import { AlertTriangle, Loader2, RotateCw } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export const cx = (...classes: (string | false | null | undefined)[]) =>
  classes.filter(Boolean).join(" ");

export function Card({
  children,
  className,
  as: Tag = "section",
}: {
  children: ReactNode;
  className?: string;
  as?: "section" | "div" | "article";
}) {
  return (
    <Tag
      className={cx(
        "min-w-0 rounded-card border border-line bg-surface shadow-card",
        "p-5 sm:p-6",
        className,
      )}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({
  title,
  subtitle,
  action,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h2 className="text-base font-semibold tracking-tight text-ink">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-muted">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost";

export function Button({
  variant = "secondary",
  loading,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  loading?: boolean;
  icon?: ReactNode;
}) {
  const styles: Record<ButtonVariant, string> = {
    primary: "bg-brand text-brand-contrast hover:bg-brand-strong shadow-sm",
    secondary: "bg-surface-2 text-ink hover:bg-surface-3 border border-line",
    ghost: "text-muted hover:text-ink hover:bg-surface-2",
  };
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={cx(
        "inline-flex h-10 items-center justify-center gap-2 rounded-full px-4 text-sm font-medium",
        "transition-colors disabled:cursor-not-allowed disabled:opacity-50",
        styles[variant],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  label,
  size = "md",
}: {
  value: T;
  options: readonly T[] | readonly { value: T; label: ReactNode }[];
  onChange: (v: T) => void;
  label: string;
  size?: "sm" | "md";
}) {
  const items = options.map((o) =>
    typeof o === "string" ? { value: o as T, label: o as ReactNode } : o,
  );
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex rounded-full border border-line bg-surface-2 p-1"
    >
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(item.value)}
            className={cx(
              "rounded-full font-medium transition-colors",
              size === "sm" ? "px-2.5 py-1 text-xs" : "px-3.5 py-1.5 text-sm",
              active
                ? "bg-surface text-ink shadow-sm"
                : "text-muted hover:text-ink",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

type Tone = "neutral" | "brand" | "positive" | "negative" | "warning";

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  const tones: Record<Tone, string> = {
    neutral: "bg-surface-2 text-muted",
    brand: "bg-brand-soft text-brand-strong",
    positive: "bg-positive-soft text-positive",
    negative: "bg-negative-soft text-negative",
    warning: "bg-warning-soft text-warning",
  };
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-xl bg-surface-2", className)} />;
}

export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-card border border-negative/30 bg-negative-soft/50 p-8 text-center">
      <AlertTriangle className="size-6 text-negative" aria-hidden />
      <p className="max-w-md text-sm text-ink">{error.message}</p>
      {onRetry && (
        <Button onClick={onRetry} icon={<RotateCw className="size-4" aria-hidden />}>
          Try again
        </Button>
      )}
    </div>
  );
}

export function Delta({
  value,
  children,
  className,
}: {
  value: number;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "tabular font-medium",
        value > 0 ? "text-positive" : value < 0 ? "text-negative" : "text-muted",
        className,
      )}
    >
      {children}
    </span>
  );
}
