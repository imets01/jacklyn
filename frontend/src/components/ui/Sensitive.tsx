import type { ReactNode } from 'react'

import { usePreferences } from '../../lib/preferences-context'

/** What every hidden figure shows behind the blur, so its length doesn't hint at its size. */
const PLACEHOLDER = '••••'

/**
 * Wraps a personal figure (money, quantity). In private mode it is replaced by the same placeholder number
 * everywhere and blurred, like a banking app; `reveal` keeps public figures (a share price change) as is.
 * The real value is not rendered at all while hidden.
 */
export function Sensitive({ children, reveal = false }: { children: ReactNode; reveal?: boolean }) {
  const { hideAmounts } = usePreferences()
  if (!hideAmounts || reveal) return <>{children}</>
  return (
    <span className="select-none blur-[0.32em]" aria-label="Hidden amount">
      {PLACEHOLDER}
    </span>
  )
}
