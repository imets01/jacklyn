import { clsx } from 'clsx'
import { Coins, FileUp, HeartPulse, LayoutDashboard, LogOut, ReceiptText, Wallet } from 'lucide-react'
import { useEffect } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router'

import { useLogout, useSession } from '../../api/auth'

import { useIsDesktop } from '../../lib/media'
import { Logo } from '../ui/Logo'
import { PrivacyToggle, ThemeSwitch } from './Controls'
import { DemoBanner } from './DemoBanner'
import { MobileSidebar, MobileTabs, MobileTopBar } from './MobileNav'
import { useMobileMenu } from './useMobileMenu'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/accounts', label: 'Accounts', icon: Wallet, end: false },
  { to: '/transactions', label: 'Transactions', icon: ReceiptText, end: false },
  { to: '/income', label: 'Income', icon: Coins, end: false },
  { to: '/health', label: 'Health', icon: HeartPulse, end: false },
  { to: '/import', label: 'Import', icon: FileUp, end: false },
] as const

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
  const desktop = useIsDesktop()
  const menu = useMobileMenu(desktop)
  return (
    <>
    {desktop ? null : <MobileSidebar menu={menu} />}
    <div inert={menu.menuOpen} style={menu.screenStyle} className={clsx('relative z-10 min-h-dvh bg-canvas', menu.screenClass)}>
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

      {desktop ? null : <MobileTopBar menu={menu} />}

      <main style={menu.mainStyle} className="pb-[calc(8rem+env(safe-area-inset-bottom))] lg:pb-12 lg:pl-60">
        <div className="mx-auto w-full max-w-[1240px] px-4 pt-6 sm:px-6 lg:px-10 lg:pt-10">
          <DemoBanner />
          <Outlet />
        </div>
      </main>

      {desktop ? null : <MobileTabs />}
    </div>
    </>
  )
}
