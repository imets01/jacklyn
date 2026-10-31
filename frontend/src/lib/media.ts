import { useCallback, useSyncExternalStore } from 'react'

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const media = window.matchMedia(query)
      media.addEventListener('change', onChange)
      return () => media.removeEventListener('change', onChange)
    },
    [query],
  )
  return useSyncExternalStore(subscribe, () => window.matchMedia(query).matches)
}

/** Tailwind's `lg`: the fixed sidebar replaces the drawer and tab bar. */
export const useIsDesktop = () => useMediaQuery('(min-width: 64rem)')

/** Below Tailwind's `md`: wide tables become lists and filters collapse. */
export const useIsCompact = () => useMediaQuery('(max-width: 47.999rem)')
