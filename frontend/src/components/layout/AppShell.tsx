import { clsx } from 'clsx'
import { FileUp, LayoutDashboard, Monitor, Moon, Sun, Wallet } from 'lucide-react'
import { NavLink, Outlet } from 'react-router'

import { usePreferences, type ThemePreference } from '../../lib/preferences-context'
import { Logo, LogoMark } from '../ui/Logo'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/accounts', label: 'Accounts', icon: Wallet, end: false },
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

export function AppShell() {
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
        <div className="mt-auto flex flex-col gap-4 px-2">
          <ThemeSwitch />
          <p className="text-xs leading-relaxed text-ink-3">
            Self-hosted · your data stays on your machine.
          </p>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sticky top-0 z-20 flex items-center justify-between border-b border-line bg-canvas/85 px-4 py-3 backdrop-blur lg:hidden">
        <div className="flex items-center gap-2">
          <LogoMark className="size-7" />
          <span className="font-display font-bold">Jacklyn</span>
        </div>
        <ThemeSwitch compact />
      </header>

      <main className="pb-24 lg:pb-12 lg:pl-60">
        <div className="mx-auto w-full max-w-[1240px] px-4 pt-6 sm:px-6 lg:px-10 lg:pt-10">
          <Outlet />
        </div>
      </main>

      {/* Mobile tab bar */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-20 grid grid-cols-3 border-t border-line bg-surface/95 px-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-2 backdrop-blur lg:hidden"
      >
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              clsx(
                'flex flex-col items-center gap-1 rounded-xl py-1.5 text-[11px] font-medium',
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
