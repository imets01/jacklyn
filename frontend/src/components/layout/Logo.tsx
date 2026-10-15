export function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <a href="#/" className="flex items-center gap-2.5" aria-label="Jacklyn home">
      <svg viewBox="0 0 32 32" className="size-9 shrink-0" aria-hidden>
        <rect width="32" height="32" rx="10" fill="var(--brand-strong)" />
        <path
          d="M16 6c-5.5 3.2-8.5 8-8.5 12.2C7.5 22.6 11.3 26 16 26s8.5-3.4 8.5-7.8C24.5 14 21.5 9.2 16 6Z"
          fill="var(--vein)"
        />
        <path
          d="M16 9v16M16 14l-4 3M16 14l4 3M16 19l-5 3.4M16 19l5 3.4"
          stroke="var(--brand-strong)"
          strokeWidth="1.4"
          strokeLinecap="round"
          fill="none"
        />
      </svg>
      {!compact && (
        <div className="leading-tight">
          <div className="text-lg font-semibold tracking-tight text-ink">Jacklyn</div>
          <div className="text-xs text-muted">Wealth, rooted.</div>
        </div>
      )}
      {compact && <span className="text-lg font-semibold tracking-tight">Jacklyn</span>}
    </a>
  );
}
