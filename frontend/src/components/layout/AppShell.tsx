import { LayoutDashboard, Moon, Sun, UploadCloud } from "lucide-react";
import type { ReactNode } from "react";

import { usePreferences } from "@/lib/preferences";
import { hrefFor, type Route } from "@/lib/router";
import { BASE_CURRENCIES } from "@/lib/types";

import { SegmentedControl, cx } from "../ui/primitives";
import { Logo } from "./Logo";

const NAV: { route: Route; label: string; icon: typeof LayoutDashboard }[] = [
  { route: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { route: "import", label: "Import", icon: UploadCloud },
];

export function AppShell({ route, children }: { route: Route; children: ReactNode }) {
  const { theme, toggleTheme, baseCurrency, setBaseCurrency } = usePreferences();

  return (
    <div className="min-h-screen lg:pl-64">
      {/* Sidebar (desktop) */}
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r border-line bg-surface/70 px-5 py-6 backdrop-blur lg:flex">
        <Logo />
        <nav className="mt-10 flex flex-col gap-1" aria-label="Main">
          {NAV.map(({ route: r, label, icon: Icon }) => (
            <a
              key={r}
              href={hrefFor(r)}
              aria-current={route === r ? "page" : undefined}
              className={cx(
                "flex items-center gap-3 rounded-2xl px-3.5 py-2.5 text-sm font-medium transition-colors",
                route === r
                  ? "bg-brand-soft text-brand-strong"
                  : "text-muted hover:bg-surface-2 hover:text-ink",
              )}
            >
              <Icon className="size-[18px]" aria-hidden />
              {label}
            </a>
          ))}
        </nav>
        <div className="mt-auto rounded-2xl bg-surface-2 p-4 text-xs leading-relaxed text-muted">
          <p className="font-medium text-ink">Phase 1 · local data</p>
          FX uses a static rate table. Prices come from your latest trades.
        </div>
      </aside>

      {/* Top bar */}
      <header className="sticky top-0 z-20 border-b border-line bg-bg/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-3 px-4 sm:px-6 lg:px-10">
          <div className="lg:hidden">
            <Logo compact />
          </div>
          <div className="hidden text-sm text-muted lg:block">
            {route === "dashboard" ? "Overview" : "Smart Importer"}
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <SegmentedControl
              label="Base currency"
              value={baseCurrency}
              options={BASE_CURRENCIES}
              onChange={setBaseCurrency}
              size="sm"
            />
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
              className="grid size-9 place-items-center rounded-full border border-line bg-surface text-muted transition-colors hover:text-ink"
            >
              {theme === "dark" ? (
                <Sun className="size-4" aria-hidden />
              ) : (
                <Moon className="size-4" aria-hidden />
              )}
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 pt-6 pb-28 sm:px-6 lg:px-10 lg:pt-10 lg:pb-16">
        {children}
      </main>

      {/* Bottom nav (mobile) */}
      <nav
        aria-label="Main"
        className="fixed inset-x-4 bottom-4 z-20 flex justify-around rounded-full border border-line bg-surface/90 p-1.5 shadow-card backdrop-blur lg:hidden"
      >
        {NAV.map(({ route: r, label, icon: Icon }) => (
          <a
            key={r}
            href={hrefFor(r)}
            aria-current={route === r ? "page" : undefined}
            className={cx(
              "flex flex-1 items-center justify-center gap-2 rounded-full py-2.5 text-sm font-medium",
              route === r ? "bg-brand-soft text-brand-strong" : "text-muted",
            )}
          >
            <Icon className="size-[18px]" aria-hidden />
            {label}
          </a>
        ))}
      </nav>
    </div>
  );
}
