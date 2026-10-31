import { clsx } from 'clsx'
import { Eye, EyeOff, Monitor, Moon, Sun } from 'lucide-react'

import { usePreferences, type ThemePreference } from '../../lib/preferences-context'

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: 'light', label: 'Light', icon: Sun },
  { value: 'system', label: 'System', icon: Monitor },
  { value: 'dark', label: 'Dark', icon: Moon },
]

export function ThemeSwitch() {
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
            'grid h-7 flex-1 place-items-center rounded-full px-3 transition-all',
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
export function PrivacyToggle() {
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
