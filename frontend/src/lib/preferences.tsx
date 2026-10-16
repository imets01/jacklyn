import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'

import { useMe, useUpdateMe } from '../api/hooks'
import { BASE_CURRENCIES, type BaseCurrency } from '../api/types'
import { PreferencesContext, type ThemePreference } from './preferences-context'

const THEME_KEY = 'jacklyn.theme'
const CURRENCY_KEY = 'jacklyn.baseCurrency'

function readStorage(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStorage(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // Private mode or blocked storage: the preference just won't persist.
  }
}

function isBaseCurrency(value: string | null | undefined): value is BaseCurrency {
  return BASE_CURRENCIES.some((currency) => currency === value)
}

export function PreferencesProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemePreference>(() => {
    const stored = readStorage(THEME_KEY)
    return stored === 'light' || stored === 'dark' ? stored : 'system'
  })
  const [systemDark, setSystemDark] = useState(() => window.matchMedia('(prefers-color-scheme: dark)').matches)
  // This browser's explicit choice wins; otherwise follow the server-side user preference.
  const [choice, setChoice] = useState<BaseCurrency | null>(() => {
    const stored = readStorage(CURRENCY_KEY)
    return isBaseCurrency(stored) ? stored : null
  })
  const me = useMe()
  const { mutate: saveMe } = useUpdateMe()
  const serverCurrency = me.data?.base_currency
  const baseCurrency: BaseCurrency = choice ?? (isBaseCurrency(serverCurrency) ? serverCurrency : 'CHF')

  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    media.addEventListener('change', onChange)
    return () => media.removeEventListener('change', onChange)
  }, [])

  const resolvedTheme = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme

  useEffect(() => {
    document.documentElement.classList.toggle('dark', resolvedTheme === 'dark')
  }, [resolvedTheme])

  const setTheme = useCallback((next: ThemePreference) => {
    setThemeState(next)
    writeStorage(THEME_KEY, next)
  }, [])

  const setBaseCurrency = useCallback(
    (currency: BaseCurrency) => {
      setChoice(currency)
      writeStorage(CURRENCY_KEY, currency)
      saveMe({ base_currency: currency })
    },
    [saveMe],
  )

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme, baseCurrency, setBaseCurrency }),
    [theme, resolvedTheme, setTheme, baseCurrency, setBaseCurrency],
  )
  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>
}
