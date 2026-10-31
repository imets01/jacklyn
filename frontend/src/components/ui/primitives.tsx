import { clsx } from 'clsx'
import { LoaderCircle } from 'lucide-react'
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx('rounded-3xl border border-line bg-surface shadow-[var(--shadow-card)]', className)}
      {...props}
    />
  )
}

export function CardHeader({ title, subtitle, action }: { title: ReactNode; subtitle?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3 px-6 pt-5">
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        {subtitle ? <p className="mt-0.5 text-sm text-ink-3">{subtitle}</p> : null}
      </div>
      {action}
    </div>
  )
}

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger'

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  className,
  children,
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: 'sm' | 'md'; loading?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled || loading}
      className={clsx(
        'inline-flex shrink-0 items-center justify-center gap-2 rounded-full font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'h-8 px-3 text-[13px]' : 'h-10 px-4 text-sm',
        variant === 'primary' && 'bg-accent text-accent-ink hover:bg-accent-hover',
        variant === 'secondary' && 'border border-line bg-surface text-ink hover:bg-surface-2',
        variant === 'ghost' && 'text-ink-2 hover:bg-surface-2 hover:text-ink',
        variant === 'danger' && 'bg-negative text-white hover:opacity-90',
        className,
      )}
      {...props}
    >
      {loading ? <LoaderCircle className="size-4 animate-spin" aria-hidden /> : null}
      {children}
    </button>
  )
}

export function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  label,
  size = 'md',
  fill = false,
}: {
  options: readonly { value: T; label: ReactNode; title?: string }[]
  value: T
  onChange: (value: T) => void
  label: string
  size?: 'sm' | 'md'
  /** Stretch to the container width on phones, sharing it equally between options. */
  fill?: boolean
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={clsx('rounded-full bg-surface-2 p-1', fill ? 'flex w-full sm:inline-flex sm:w-auto' : 'inline-flex')}
    >
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            title={option.title}
            onClick={() => onChange(option.value)}
            className={clsx(
              'inline-flex items-center justify-center gap-1.5 rounded-full font-medium transition-all',
              size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8 px-3.5 text-[13px]',
              fill && 'min-w-0 flex-1 px-0 sm:flex-none sm:px-2.5',
              active ? 'bg-surface text-ink shadow-[var(--shadow-card)]' : 'text-ink-3 hover:text-ink',
            )}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}

export type BadgeTone = 'neutral' | 'accent' | 'positive' | 'negative' | 'warning'

export function Badge({ tone = 'neutral', className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: BadgeTone }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-semibold tracking-wide',
        tone === 'neutral' && 'bg-surface-2 text-ink-2',
        tone === 'accent' && 'bg-accent-soft text-accent',
        tone === 'positive' && 'bg-positive-soft text-positive',
        tone === 'negative' && 'bg-negative-soft text-negative',
        tone === 'warning' && 'bg-warning-soft text-warning',
        className,
      )}
      {...props}
    />
  )
}

export function Spinner({ className }: { className?: string }) {
  return <LoaderCircle className={clsx('size-5 animate-spin text-ink-3', className)} aria-label="Loading" />
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[13px] font-medium text-ink-2">{label}</span>
      {children}
      {hint ? <span className="text-xs text-ink-3">{hint}</span> : null}
    </label>
  )
}

const controlClass =
  // 16px on phones: iOS zooms the whole page when focusing anything smaller.
  'h-10 w-full rounded-xl border border-line bg-surface px-3 text-base text-ink outline-none md:text-sm transition-colors placeholder:text-ink-3 focus:border-accent focus:ring-2 focus:ring-accent/20'

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={clsx(controlClass, className)} {...props} />
}

export function Select({ className, children, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={clsx(controlClass, 'cursor-pointer pr-8', className)} {...props}>
      {children}
    </select>
  )
}

export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <div className="grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent">{icon}</div>
      <div>
        <p className="font-semibold text-ink">{title}</p>
        {children ? <div className="mt-1 text-sm text-ink-3">{children}</div> : null}
      </div>
    </div>
  )
}

export function Notice({ tone = 'warning', icon, children }: { tone?: BadgeTone; icon?: ReactNode; children: ReactNode }) {
  return (
    <div
      role="status"
      className={clsx(
        'flex items-start gap-2.5 rounded-2xl px-4 py-3 text-sm',
        tone === 'warning' && 'bg-warning-soft text-warning',
        tone === 'negative' && 'bg-negative-soft text-negative',
        tone === 'positive' && 'bg-positive-soft text-positive',
        tone === 'accent' && 'bg-accent-soft text-accent',
        tone === 'neutral' && 'bg-surface-2 text-ink-2',
      )}
    >
      {icon ? <span className="mt-0.5 shrink-0">{icon}</span> : null}
      <div className="min-w-0">{children}</div>
    </div>
  )
}
