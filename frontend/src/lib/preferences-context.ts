import { createContext, useContext } from 'react'

import type { BaseCurrency } from '../api/types'

export type ThemePreference = 'light' | 'dark' | 'system'

export interface Preferences {
  theme: ThemePreference
  resolvedTheme: 'light' | 'dark'
  setTheme: (theme: ThemePreference) => void
  baseCurrency: BaseCurrency
  setBaseCurrency: (currency: BaseCurrency) => void
}

export const PreferencesContext = createContext<Preferences | null>(null)

export function usePreferences(): Preferences {
  const context = useContext(PreferencesContext)
  if (!context) throw new Error('usePreferences must be used inside <PreferencesProvider>')
  return context
}
