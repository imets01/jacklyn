import { LEAF_BLADE as BLADE, LEAF_TRANSFORM as TRANSFORM, LEAF_VEINS as VEINS } from './leaf'

export function LogoMark({ className = 'size-8' }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden>
      <rect width="64" height="64" rx="18" fill="var(--accent)" />
      <g transform={TRANSFORM}>
        {/* Swings from the petiole (where the midrib starts) when a parent `group` is hovered. */}
        <g className="origin-[32px_23.5px] [transform-box:view-box] motion-safe:group-hover:animate-leaf-wiggle">
          <path d={BLADE} fill="var(--accent-soft)" />
          <path
            d={VEINS}
            fill="none"
            stroke="var(--accent)"
            strokeOpacity="0.5"
            strokeWidth="0.6"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </g>
      </g>
    </svg>
  )
}

export function Logo() {
  return (
    <div className="group flex items-center gap-3">
      <LogoMark className="size-10" />
      <span className="font-display text-xl font-bold tracking-tight text-ink">Jacklyn</span>
    </div>
  )
}
