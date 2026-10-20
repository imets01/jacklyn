const GREETED_KEY = 'jacklyn:greeted'

/** Whether the welcome already played in this browser session (a tab or window, until it closes). */
export function greetedThisSession(): boolean {
  try {
    return sessionStorage.getItem(GREETED_KEY) === '1'
  } catch {
    return false
  }
}

export function markGreeted(): void {
  try {
    sessionStorage.setItem(GREETED_KEY, '1')
  } catch {
    // Private mode or blocked storage: it may simply play again on the next visit.
  }
}
