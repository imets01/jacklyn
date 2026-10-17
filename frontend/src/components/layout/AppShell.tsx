import { clsx } from 'clsx'
import { Eye, EyeOff, FileUp, HeartPulse, LayoutDashboard, LogOut, Monitor, Moon, ReceiptText, Settings, Sun, Wallet } from 'lucide-react'
import { useEffect } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'

import { useLogout, useSession } from '../../api/auth'

import { usePreferences, type ThemePreference } from '../../lib/preferences-context'
import { Logo, LogoMark } from '../ui/Logo'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/accounts', label: 'Accounts', icon: Wallet, end: false },
  { to: '/transactions', label: 'Transactions', icon: ReceiptText, end: false },
  { to: '/health', label: 'Health', icon: HeartPulse, end: false },
  { to: '/import', label: 'Import', icon: FileUp, end: false },
] as const

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'system', label: 'System', icon: Monitor },
  { value: 'dark', label: 'Dark', icon: Moon },
]

function ThemeSwitch({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = usePreferences()
  return (
    <div role="radiogroup" aria-label="Theme" className="inline-flex rounded-full bg-surface-2 p-1">
      {THEMES.map(({ value, label, icon: Icon }) => (
        <button
          key={value}
          type="button"
          role="radio"
          aria-checked={theme === value}
          title={`${label} theme`}
          onClick={() => setTheme(value)}
          className={clsx(
            'grid place-items-center rounded-full transition-all',
            compact ? 'size-7' : 'h-7 flex-1 px-3',
            theme === value ? 'bg-surface text-ink shadow-[var(--shadow-card)]' : 'text-ink-3 hover:text-ink',
          )}
        >
          <Icon className="size-3.5" aria-hidden />
          <span className="sr-only">{label}</span>
        </button>
      ))}
    </div>
  )
}

/** Private mode: masks money amounts and quantities, e.g. for screenshots or showing the app to someone. */
function PrivacyToggle() {
  const { hideAmounts, setHideAmounts } = usePreferences()
  const Icon = hideAmounts ? EyeOff : Eye
  const label = hideAmounts ? 'Show amounts' : 'Hide amounts'
  return (
    <button
      type="button"
      aria-pressed={hideAmounts}
      title={label}
      onClick={() => setHideAmounts(!hideAmounts)}
      className={clsx(
        'grid size-9 shrink-0 place-items-center rounded-full transition-colors',
        hideAmounts ? 'bg-accent-soft text-accent' : 'bg-surface-2 text-ink-3 hover:text-ink',
      )}
    >
      <Icon className="size-4" aria-hidden />
      <span className="sr-only">{label}</span>
    </button>
  )
}

function UserCard() {
  const session = useSession()
  const logout = useLogout()
  const me = session.data?.user
  if (!me) return null
  return (
    <div className="flex items-center gap-2 rounded-2xl border border-line bg-surface p-2">
      <Link to="/settings" className="flex min-w-0 flex-1 items-center gap-2.5 rounded-xl p-1 hover:bg-surface-2" title="Settings">
        <span className="grid size-8 shrink-0 place-items-center rounded-xl bg-accent-soft font-display text-sm font-bold text-accent" aria-hidden>
          {me.display_name.slice(0, 1).toUpperCase()}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-ink">{me.display_name}</span>
          <span className="block truncate text-xs text-ink-3">{me.email}</span>
        </span>
      </Link>
      <button
        type="button"
        onClick={() => logout.mutate()}
        className="grid size-8 shrink-0 place-items-center rounded-xl text-ink-3 hover:bg-surface-2 hover:text-ink"
        title="Sign out"
        aria-label="Sign out"
      >
        <LogOut className="size-4" aria-hidden />
      </button>
    </div>
  )
}

/** New pages open at the top; query-string changes (filters, paging) keep the scroll position. */
function useScrollTopOnNavigate() {
  const { pathname } = useLocation()
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [pathname])
}

export function AppShell() {
  useScrollTopOnNavigate()
  return (
    <div className="min-h-dvh bg-canvas">
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-20 hidden w-60 flex-col border-r border-line bg-surface/60 px-4 py-6 backdrop-blur lg:flex">
        <div className="px-2">
          <Logo />
        </div>
        <nav className="mt-10 flex flex-col gap-1" aria-label="Main">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium transition-colors',
                  isActive ? 'bg-accent-soft text-accent' : 'text-ink-2 hover:bg-surface-2 hover:text-ink',
                )
              }
            >
              <Icon className="size-[18px]" aria-hidden />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-3">
          <div className="flex items-center gap-2 px-2">
            <div className="min-w-0 flex-1">
              <ThemeSwitch />
            </div>
            <PrivacyToggle />
          </div>
          <UserCard />
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-canvas/85 px-4 py-3 backdrop-blur lg:hidden">
        <div className="flex items-center gap-2">
          <LogoMark className="size-7" />
          <span className="font-display font-bold">Jacklyn</span>
        </div>
        <div className="flex items-center gap-2">
          <PrivacyToggle />
          <ThemeSwitch compact />
        </div>
      </header>

      <main className="pb-24 lg:pb-12 lg:pl-60">
        <div className="mx-auto w-full max-w-[1240px] px-4 pt-6 sm:px-6 lg:px-10 lg:pt-10">
          <Outlet />
        </div>
      </main>

      {/* Mobile tab bar */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-6 border-t border-line bg-surface/95 px-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-2 backdrop-blur lg:hidden"
      >
        {[...NAV, { to: '/settings', label: 'Settings', icon: Settings, end: false }].map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              clsx(
                'flex min-w-0 flex-col items-center gap-1 rounded-xl py-1.5 text-[10px] font-medium',
                isActive ? 'text-accent' : 'text-ink-3',
              )
            }
          >
            <Icon className="size-5" aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
