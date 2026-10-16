import { clsx } from 'clsx'
import { useState, type ReactNode } from 'react'

import type { AssetClass } from '../../api/types'
import { seriesVar, SERIES_SLOTS } from '../../lib/palette'

type IconSize = 'xs' | 'sm' | 'md' | 'lg'

const SIZE_CLASS: Record<IconSize, string> = { xs: 'size-5 text-[8px]', sm: 'size-8 text-[11px]', md: 'size-10 text-xs', lg: 'size-14 text-base' }

function Frame({ size, className, children, label }: { size: IconSize; className?: string; children: ReactNode; label?: string }) {
  return (
    <span
      className={clsx(
        'relative grid shrink-0 place-items-center overflow-hidden rounded-full ring-1 ring-line',
        SIZE_CLASS[size],
        className,
      )}
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {children}
    </span>
  )
}

/** Stable small hash so a ticker keeps its color across renders, pages and reloads. */
function hash(text: string): number {
  let value = 0
  for (const char of text) value = (value * 31 + char.charCodeAt(0)) >>> 0
  return value
}

function initials(symbol: string): string {
  const letters = symbol.split(/[.\-:]/)[0]?.replace(/[^A-Za-z0-9]/g, '').toUpperCase() ?? ''
  return letters.slice(0, letters.length <= 3 ? 3 : 2) || '?'
}

function InitialsBadge({ symbol, size, className }: { symbol: string; size: IconSize; className?: string }) {
  const color = seriesVar(hash(symbol) % SERIES_SLOTS)
  const text = initials(symbol)
  return (
    <Frame size={size} className={className}>
      <span
        className="absolute inset-0"
        style={{ background: `color-mix(in oklab, ${color} 16%, var(--surface))` }}
        aria-hidden
      />
      <span
        className={clsx('relative font-display font-bold tracking-tight', text.length > 2 && 'scale-90')}
        style={{ color: `color-mix(in oklab, ${color} 80%, var(--ink))` }}
      >
        {text}
      </span>
    </Frame>
  )
}

const METALS = {
  gold: { bg: '#f7ecc9', face: '#e3b341', top: '#f4d27a', edge: '#b8862a' },
  silver: { bg: '#eceff2', face: '#b4bcc4', top: '#dde2e7', edge: '#88929c' },
} as const

function MetalBar({ name, size, className }: { name: string; size: IconSize; className?: string }) {
  const metal = /silver|platinum|palladium/i.test(name) ? METALS.silver : METALS.gold
  return (
    <Frame size={size} className={className}>
      <svg viewBox="0 0 32 32" className="size-full" aria-hidden>
        <rect width="32" height="32" fill={metal.bg} />
        <path d="M9.5 13h13l3.5 8H6z" fill={metal.face} />
        <path d="M9.5 13h13l-1.6-3.2h-9.8z" fill={metal.top} />
        <path d="M6 21h20l-.6 1.4H6.6z" fill={metal.edge} />
        <path d="M12 11.2h4.5" stroke="#fff" strokeOpacity={0.7} strokeWidth={0.9} strokeLinecap="round" />
      </svg>
    </Frame>
  )
}

/** A cached logo; calls `onError` so the caller can swap in its drawn fallback. */
function LogoImage({ url, size, className, onError }: { url: string; size: IconSize; className?: string; onError: () => void }) {
  return (
    <Frame size={size} className={clsx('bg-white', className)}>
      <img
        src={url}
        alt=""
        loading="lazy"
        decoding="async"
        draggable={false}
        className="size-full object-cover"
        onError={onError}
      />
    </Frame>
  )
}

/**
 * Round avatar for any holding: the logo the server has cached (Elbstream tile, or a website icon), else
 * a drawn bar for metals, a flag for cash and colored initials for the rest — also when an image fails.
 */
export function AssetIcon({
  symbol,
  name,
  assetClass,
  logoUrl,
  size = 'md',
  className,
}: {
  symbol: string
  name?: string | null
  assetClass?: AssetClass
  logoUrl?: string | null
  size?: IconSize
  className?: string
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  if (assetClass === 'cash') return <CurrencyIcon currency={symbol} logoUrl={logoUrl} size={size} className={className} />
  if (logoUrl && failedUrl !== logoUrl) {
    return <LogoImage url={logoUrl} size={size} className={className} onError={() => setFailedUrl(logoUrl)} />
  }
  if (assetClass === 'commodity') return <MetalBar name={name ?? symbol} size={size} className={className} />
  return <InitialsBadge symbol={symbol} size={size} className={className} />
}

// ---------------------------------------------------------------- currencies

function Flag({ currency }: { currency: string }): ReactNode {
  switch (currency) {
    case 'CHF':
      return (
        <>
          <rect width="32" height="32" fill="#da291c" />
          <path d="M13.5 7.5h5v6h6v5h-6v6h-5v-6h-6v-5h6z" fill="#fff" />
        </>
      )
    case 'EUR':
      return (
        <>
          <rect width="32" height="32" fill="#003399" />
          {Array.from({ length: 12 }, (_, i) => {
            const angle = (i * Math.PI) / 6
            return <circle key={i} cx={16 + 8.5 * Math.sin(angle)} cy={16 - 8.5 * Math.cos(angle)} r={1.35} fill="#ffcc00" />
          })}
        </>
      )
    case 'USD':
      return (
        <>
          <rect width="32" height="32" fill="#fff" />
          {Array.from({ length: 7 }, (_, i) => (
            <rect key={i} y={i * 4.92} width="32" height="2.46" fill="#b22234" />
          ))}
          <rect width="16" height="17.2" fill="#3c3b6e" />
          {[4, 8, 12].flatMap((y) => [4, 8, 12].map((x) => <circle key={`${x}-${y}`} cx={x} cy={y + 1} r={0.9} fill="#fff" />))}
        </>
      )
    case 'HUF':
      return (
        <>
          <rect width="32" height="11" fill="#cd2a3e" />
          <rect y="11" width="32" height="10" fill="#fff" />
          <rect y="21" width="32" height="11" fill="#436f4d" />
        </>
      )
    case 'GBP':
      return (
        <>
          <rect width="32" height="32" fill="#012169" />
          <path d="M0 0l32 32M32 0L0 32" stroke="#fff" strokeWidth={6} />
          <path d="M0 0l32 32M32 0L0 32" stroke="#c8102e" strokeWidth={2} />
          <path d="M16 0v32M0 16h32" stroke="#fff" strokeWidth={9} />
          <path d="M16 0v32M0 16h32" stroke="#c8102e" strokeWidth={5} />
        </>
      )
    default:
      return null
  }
}

function currencySymbol(currency: string): string {
  try {
    const parts = new Intl.NumberFormat(undefined, { style: 'currency', currency, currencyDisplay: 'narrowSymbol' }).formatToParts(0)
    return parts.find((part) => part.type === 'currency')?.value ?? currency
  } catch {
    return currency
  }
}

/** The cached currency tile when there is one, else a drawn flag (main currencies) or a symbol badge. */
export function CurrencyIcon({
  currency,
  logoUrl,
  size = 'md',
  className,
}: {
  currency: string
  logoUrl?: string | null
  size?: IconSize
  className?: string
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null)
  if (logoUrl && failedUrl !== logoUrl) {
    return <LogoImage url={logoUrl} size={size} className={className} onError={() => setFailedUrl(logoUrl)} />
  }
  const flag = Flag({ currency })
  if (flag) {
    return (
      <Frame size={size} className={className} label={currency}>
        <svg viewBox="0 0 32 32" className="size-full">
          {flag}
        </svg>
      </Frame>
    )
  }
  const symbol = currencySymbol(currency)
  return (
    <Frame size={size} className={clsx('bg-accent-soft text-accent', className)} label={currency}>
      <span className="font-display font-bold">{symbol.length <= 3 ? symbol : currency.slice(0, 2)}</span>
    </Frame>
  )
}
