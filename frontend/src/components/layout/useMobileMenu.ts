import { clsx } from 'clsx'
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type TouchEvent } from 'react'
import { useLocation } from 'react-router'

/** How far the screen has to be dragged back before letting go closes the menu. */
const SWIPE_CLOSE_PX = 72
/** Matches the slide in index.css; the screen stays frozen until it has landed. */
const SLIDE_MS = 280

/**
 * The phone menu lies behind the app, and opening it slides the whole screen aside. The page normally scrolls
 * the window, and a moved element can't keep its scroll position, so while the menu is showing the screen is
 * frozen to the size of the viewport with its content offset by the scroll position, which is restored on close.
 */
export function useMobileMenu(desktop: boolean) {
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [frozen, setFrozen] = useState<{ scrollY: number; locationKey: string } | null>(null)
  const [dragX, setDragX] = useState(0)
  const touch = useRef<{ x: number; y: number; axis: 'x' | 'y' | null } | null>(null)
  const restoreScroll = useRef<number | null>(null)

  if (desktop && menuOpen) setMenuOpen(false)

  // Going somewhere from the menu lands at the top of the new page, not at the old page's position.
  const offset = frozen?.locationKey === location.key ? frozen.scrollY : 0

  useEffect(() => {
    if (menuOpen || !frozen) return
    const timer = setTimeout(() => {
      restoreScroll.current = offset
      setFrozen(null)
    }, SLIDE_MS)
    return () => clearTimeout(timer)
  }, [menuOpen, frozen, offset])

  useLayoutEffect(() => {
    if (frozen || restoreScroll.current === null) return
    window.scrollTo({ top: restoreScroll.current })
    restoreScroll.current = null
  }, [frozen])

  const open = () => {
    // Reopened mid-close, the screen is still frozen at the position that counts.
    setFrozen((current) => current ?? { scrollY: window.scrollY, locationKey: location.key })
    setMenuOpen(true)
  }
  const close = () => setMenuOpen(false)

  const touchHandlers = {
    onTouchStart: (event: TouchEvent) => {
      const point = event.touches[0]
      if (point) touch.current = { x: point.clientX, y: point.clientY, axis: null }
    },
    onTouchMove: (event: TouchEvent) => {
      const start = touch.current
      const point = event.touches[0]
      if (!start || !point) return
      const dx = point.clientX - start.x
      const dy = point.clientY - start.y
      // Decide once per gesture, so scrolling the account list never drags the screen.
      if (!start.axis && Math.hypot(dx, dy) > 8) start.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
      if (start.axis === 'x') setDragX(Math.min(0, dx))
    },
    onTouchEnd: () => {
      if (dragX < -SWIPE_CLOSE_PX) close()
      setDragX(0)
      touch.current = null
    },
  }

  const screenStyle: CSSProperties | undefined = dragX
    ? { translate: `calc(var(--mobile-menu-width) + ${dragX}px) 0`, transition: 'none' }
    : undefined

  return {
    menuOpen,
    /** The menu has to be painted: open, or still being covered by the returning screen. */
    menuVisible: frozen !== null,
    open,
    close,
    touchHandlers,
    screenClass: clsx(!desktop && 'mobile-screen', frozen && 'mobile-screen-frozen', menuOpen && 'mobile-screen-open'),
    screenStyle,
    mainStyle: frozen ? { marginTop: -offset } : undefined,
  }
}
