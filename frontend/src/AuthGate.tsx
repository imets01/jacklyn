import { useQueryClient } from '@tanstack/react-query'
import { CircleAlert } from 'lucide-react'
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Route, Routes } from 'react-router'

import { authKeys, useSession } from './api/auth'
import { UNAUTHORIZED_EVENT } from './api/client'
import { AppShell } from './components/layout/AppShell'
import { GrowingSplash } from './components/splash/GrowingSplash'
import { LogoMark } from './components/ui/Logo'
import { Button, Spinner } from './components/ui/primitives'
import { PreferencesProvider } from './lib/preferences'
import { greetedThisSession } from './lib/welcome'
import { AccountDetailPage } from './pages/AccountDetailPage'
import { AccountsPage } from './pages/AccountsPage'
import { InvitePage, ResetPage } from './pages/auth/LinkPages'
import { LoginPage } from './pages/auth/LoginPage'
import { SetupPage } from './pages/auth/SetupPage'
import { DashboardPage } from './pages/DashboardPage'
import { HealthPage } from './pages/HealthPage'
import { HoldingDetailPage } from './pages/HoldingDetailPage'
import { ImportPage } from './pages/ImportPage'
import { NotFound } from './pages/NotFound'
import { SettingsPage } from './pages/settings/SettingsPage'
import { TransactionsPage } from './pages/TransactionsPage'

function Splash({ error, onRetry }: { error?: string; onRetry?: () => void }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-5 bg-canvas px-4 text-center">
      <LogoMark className="size-12" />
      {error ? (
        <>
          <p className="inline-flex items-center gap-2 text-sm text-ink-2">
            <CircleAlert className="size-4 text-negative" aria-hidden /> {error}
          </p>
          {onRetry ? <Button onClick={onRetry}>Try again</Button> : null}
        </>
      ) : (
        <Spinner />
      )}
    </div>
  )
}

/** Decides between first-run setup, the sign-in screens and the app. The server enforces all of it too. */
export function AuthGate() {
  const session = useSession()
  const client = useQueryClient()
  const authenticated = session.data?.authenticated

  // The welcome plays on the first visit in a browser session and right after signing in. Signed out, it waits
  // for the sign-in instead of playing twice in a row.
  const [welcome, setWelcome] = useState(() => !greetedThisSession())
  const [wasAuthenticated, setWasAuthenticated] = useState(authenticated)
  if (authenticated !== wasAuthenticated) {
    setWasAuthenticated(authenticated)
    if (wasAuthenticated === false && authenticated) setWelcome(true)
  }
  const welcomeDone = useCallback(() => setWelcome(false), [])
  const playing = welcome && authenticated === true

  useEffect(() => {
    const onUnauthorized = () => {
      client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth' })
      void client.invalidateQueries({ queryKey: authKeys.session })
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [client])

  // A plain canvas while the welcome is about to start, instead of a flash of the loading screen.
  if (session.isLoading) return welcome ? <div className="min-h-dvh bg-canvas" /> : <Splash />
  if (session.error || !session.data) {
    return <Splash error="Can't reach the Jacklyn server." onRetry={() => void session.refetch()} />
  }
  if (session.data.needs_setup) return <SetupPage />

  const linkRoutes = (
    <>
      <Route path="invite/:token" element={<InvitePage />} />
      <Route path="reset/:token" element={<ResetPage />} />
    </>
  )

  if (!session.data.authenticated) {
    return (
      <Routes>
        {linkRoutes}
        <Route path="*" element={<LoginPage />} />
      </Routes>
    )
  }

  return withWelcome(
    <PreferencesProvider>
      <Routes>
        {linkRoutes}
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="accounts" element={<AccountsPage />} />
          <Route path="accounts/:accountId" element={<AccountDetailPage />} />
          <Route path="holdings/:assetId" element={<HoldingDetailPage />} />
          <Route path="transactions" element={<TransactionsPage />} />
          <Route path="health" element={<HealthPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </PreferencesProvider>,
  )

  function withWelcome(app: ReactNode) {
    return (
      <>
        {app}
        {playing ? <GrowingSplash onDone={welcomeDone} /> : null}
      </>
    )
  }
}
