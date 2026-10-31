import { clsx } from 'clsx'
import { Coins, FileUp, HeartPulse, LayoutDashboard, LogOut, Menu, Plus, ReceiptText, Settings, Wallet, X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { Link, NavLink, useLocation } from 'react-router'

import { useLogout } from '../../api/auth'
import { useAccounts } from '../../api/hooks'
import type { AccountSummary } from '../../api/types'
import { groupByBroker } from '../../lib/accounts'
import { formatMoney } from '../../lib/format'
import { usePreferences } from '../../lib/preferences-context'
import { useAccountIdInUrl, useSelectedAccount } from '../../lib/selected-account'
import { BrokerAvatar } from '../accounts/AccountRow'
import { Logo, LogoMark } from '../ui/Logo'
import { Sensitive } from '../ui/Sensitive'
import { PrivacyToggle, ThemeSwitch } from './Controls'
import type { useMobileMenu } from './useMobileMenu'

type MobileMenu = ReturnType<typeof useMobileMenu>

const MENU_LINKS = [
  { to: '/income', label: 'Income', icon: Coins },
  { to: '/health', label: 'Health', icon: HeartPulse },
  { to: '/import', label: 'Import', icon: FileUp },
  { to: '/settings', label: 'Settings', icon: Settings },
] as const

function MenuAccount({
  account,
  selected,
  currency,
  to,
  onSelect,
}: {
  account: AccountSummary
  selected: boolean
  currency: string
  to: string
  onSelect: () => void
}) {
  return (
    <Link
      to={to}
      onClick={onSelect}
      aria-current={selected ? 'true' : undefined}
      className={clsx(
        'flex items-center gap-3 rounded-2xl px-2.5 py-2 transition-colors',
        selected ? 'bg-accent-soft' : 'active:bg-surface-2',
      )}
    >
      <BrokerAvatar broker={account.broker} className={clsx('size-9 rounded-xl', selected && 'bg-surface')} />
      <span className="min-w-0 flex-1">
        <span className={clsx('block truncate text-sm font-medium', selected ? 'text-accent' : 'text-ink')}>{account.name}</span>
        <span className="block truncate text-xs text-ink-3">
          {account.account_type === 'tbsz' ? `TBSZ ${account.tbsz_year}` : `${account.currency} account`}
        </span>
      </span>
      <span className="tabular shrink-0 text-[13px] font-medium text-ink-2">
        <Sensitive>{formatMoney(account.value, currency)}</Sensitive>
      </span>
    </Link>
  )
}

/**
 * The phone sidebar, lying behind the app and always dark: switch account in the scrolling part; everything else
 * stays pinned below it. The strip of app still showing on the right closes it.
 */
export function MobileSidebar({ menu }: { menu: MobileMenu }) {
  const { baseCurrency } = usePreferences()
  const accounts = useAccounts(baseCurrency).data ?? []
  const selected = useSelectedAccount(accounts)
  const { pathname } = useLocation()
  const logout = useLogout()
  const closeButton = useRef<HTMLButtonElement>(null)
  const { menuOpen, close } = menu

  useEffect(() => {
    if (!menuOpen) return
    const previous = document.activeElement
    closeButton.current?.focus({ preventScroll: true })
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setTimeout(close)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      if (previous instanceof HTMLElement) previous.focus({ preventScroll: true })
    }
    // `close` only sets state; a new identity each render shouldn't move focus.
    // oxlint-disable-next-line react-hooks/exhaustive-deps
  }, [menuOpen])

  // On the transactions tab, switching account stays on that tab, like the tab bar itself would.
  const accountTarget = (id: number) => (pathname === '/transactions' ? `/transactions?account=${id}` : `/accounts/${id}`)
  const groups = groupByBroker(accounts)

  return (
    <>
      <aside
        aria-label="Menu"
        inert={!menuOpen}
        {...menu.touchHandlers}
        className={clsx('dark fixed inset-0 z-0 touch-pan-y bg-canvas text-ink', !menu.menuVisible && 'invisible')}
      >
        <div className={clsx('mobile-menu-panel flex h-full flex-col pb-[env(safe-area-inset-bottom)] pt-[env(safe-area-inset-top)]', menuOpen && 'mobile-menu-panel-open')}>
          <div className="flex items-center justify-between px-4 pb-2 pt-4">
            <Logo />
            <button
              ref={closeButton}
              type="button"
              onClick={close}
              aria-label="Close menu"
              className="grid size-9 place-items-center rounded-full text-ink-3 active:bg-surface-2"
            >
              <X className="size-5" aria-hidden />
            </button>
          </div>

          <div className="flex items-center justify-between px-4 pb-1 pt-3">
            <h2 className="text-[13px] font-semibold text-ink-3">Accounts</h2>
            <div className="flex items-center gap-1">
              <Link to="/accounts" onClick={close} className="rounded-full px-2.5 py-1.5 text-[13px] font-medium text-accent active:bg-surface-2">
                See all
              </Link>
              <Link
                to="/accounts?new=1"
                onClick={close}
                aria-label="New account"
                title="New account"
                className="grid size-8 place-items-center rounded-full text-accent active:bg-surface-2"
              >
                <Plus className="size-4" aria-hidden />
              </Link>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 pb-2">
            {accounts.length === 0 ? <p className="px-2.5 py-3 text-sm text-ink-3">No accounts yet.</p> : null}
            {groups.map(([broker, group]) => (
              <section key={broker} className="mt-2 first:mt-0">
                {groups.length > 1 ? <h3 className="px-2.5 pb-1 pt-1 text-xs font-medium text-ink-3">{broker}</h3> : null}
                <div className="flex flex-col gap-0.5">
                  {group.map((account) => (
                    <MenuAccount
                      key={account.id}
                      account={account}
                      selected={account.id === selected?.id}
                      currency={baseCurrency}
                      to={accountTarget(account.id)}
                      onSelect={close}
                    />
                  ))}
                </div>
              </section>
            ))}
          </div>

          <nav aria-label="More" className="flex shrink-0 flex-col gap-0.5 border-t border-line px-2 py-2">
            {MENU_LINKS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                onClick={close}
                className={({ isActive }) =>
                  clsx(
                    'flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm font-medium transition-colors',
                    isActive ? 'bg-accent-soft text-accent' : 'text-ink-2 active:bg-surface-2',
                  )
                }
              >
                <Icon className="size-[18px]" aria-hidden />
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="flex shrink-0 items-center justify-between gap-2 border-t border-line px-4 py-3">
            <ThemeSwitch />
            <button
              type="button"
              onClick={() => logout.mutate()}
              className="inline-flex h-9 items-center gap-2 rounded-full px-3 text-sm font-medium text-ink-2 active:bg-surface-2"
            >
              <LogOut className="size-4" aria-hidden /> Sign out
            </button>
          </div>
        </div>
      </aside>
      {menuOpen ? (
        <button
          type="button"
          tabIndex={-1}
          aria-hidden
          onClick={close}
          {...menu.touchHandlers}
          className="fixed inset-y-0 left-[var(--mobile-menu-width)] right-0 z-30 touch-pan-y"
        />
      ) : null}
    </>
  )
}

export function MobileTopBar({ menu }: { menu: MobileMenu }) {
  const { baseCurrency } = usePreferences()
  const accounts = useAccounts(baseCurrency).data ?? []
  const inUrl = useAccountIdInUrl()
  const title = accounts.find((account) => account.id === inUrl)?.name
  return (
    <header className="sticky top-0 z-20 flex items-center justify-between gap-2 border-b border-line bg-canvas/85 pl-2 pr-4 pb-2 pt-[calc(env(safe-area-inset-top)+0.5rem)] backdrop-blur">
      <button
        type="button"
        onClick={menu.open}
        aria-label={title ? `Menu, current account ${title}` : 'Menu'}
        aria-expanded={menu.menuOpen}
        className="flex min-w-0 items-center gap-1 rounded-full py-1.5 pl-2 pr-3 active:bg-surface-2"
      >
        <Menu className="size-5 shrink-0 text-ink-2" aria-hidden />
        {title ? null : <LogoMark className="ml-1.5 size-6 shrink-0" />}
        <span className="ml-1.5 truncate font-display font-bold">{title ?? 'Jacklyn'}</span>
      </button>
      <PrivacyToggle />
    </header>
  )
}

export function MobileTabs() {
  const { baseCurrency } = usePreferences()
  const accounts = useAccounts(baseCurrency).data ?? []
  const selected = useSelectedAccount(accounts)
  const { pathname } = useLocation()

  const tabs = [
    { to: '/', label: 'Overview', icon: LayoutDashboard, active: pathname === '/' || pathname === '/accounts' },
    { to: selected ? `/accounts/${selected.id}` : '/accounts', label: 'Account', icon: Wallet, active: pathname.startsWith('/accounts/') },
    {
      to: selected ? `/transactions?account=${selected.id}` : '/transactions',
      label: 'Transactions',
      icon: ReceiptText,
      active: pathname === '/transactions',
    },
  ]

  const activeIndex = tabs.findIndex((tab) => tab.active)

  return (
    <>
    <div aria-hidden className="tabbar-fade pointer-events-none fixed inset-x-0 bottom-0 z-10" />
    <nav
      aria-label="Main"
      className="glass-tabbar fixed inset-x-4 bottom-[max(env(safe-area-inset-bottom),0.75rem)] z-20 mx-auto grid max-w-md grid-cols-3 rounded-full p-1"
    >
      {/* Slides between the tabs; pages outside the three tabs (Income, Health...) have none lit. */}
      <span
        aria-hidden
        className={clsx('glass-tabbar-pill absolute inset-y-1 left-1 w-[calc((100%-0.5rem)/3)] rounded-full', activeIndex < 0 && 'opacity-0')}
        style={{ translate: `${Math.max(activeIndex, 0) * 100}% 0` }}
      />
      {tabs.map(({ to, label, icon: Icon, active }) => (
        <Link
          key={label}
          to={to}
          aria-current={active ? 'page' : undefined}
          className={clsx(
            'relative flex min-w-0 flex-col items-center gap-0.5 rounded-full py-2 text-[11px] font-medium transition-[color,scale] duration-200 active:scale-95',
            active ? 'text-accent' : 'text-ink-2',
          )}
        >
          <Icon className="size-5" aria-hidden />
          <span className="max-w-full truncate">{label}</span>
        </Link>
      ))}
    </nav>
    </>
  )
}
