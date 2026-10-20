import './splash.css'

import { useEffect, type AnimationEvent } from 'react'

import { markGreeted } from '../../lib/welcome'
import { LEAF_BLADE, LEAF_TRANSFORM, LEAF_VEINS } from '../ui/leaf'

const STEM = 'M32.4 85 C 29.8 72, 35.3 50, 31.1 24.5'

/**
 * The welcome: a Jacklyn grows from a pot, its leaf unfurls and wiggles, then turns into the logo and the
 * app fades in underneath. About four seconds; a click or key press skips it.
 */
export function GrowingSplash({ onDone }: { onDone: () => void }) {
  useEffect(() => {
    markGreeted()
    window.addEventListener('keydown', onDone)
    return () => window.removeEventListener('keydown', onDone)
  }, [onDone])

  const finished = (event: AnimationEvent) => {
    if (event.target === event.currentTarget && event.animationName === 'splash-leave') onDone()
  }

  return (
    <div
      className="splash fixed inset-0 z-[100] grid cursor-pointer place-items-center bg-canvas"
      onClick={onDone}
      onAnimationEnd={finished}
      aria-hidden
    >
      <div className="flex flex-col items-center">
        <svg viewBox="0 0 64 102" className="splash-scene">
          <g className="splash-plant">
            <ellipse cx="32" cy="100.3" rx="10" ry="1.2" fill="var(--ink)" opacity=".07" />
            {/* The petiole, from the soil to where it joins the blade; faint darker flecks grow with it. */}
            <path className="splash-stem" d={STEM} fill="none" stroke="var(--splash-stem)" strokeWidth="1.7" strokeLinecap="round" />
            <path
              className="splash-stem"
              d={STEM}
              fill="none"
              stroke="var(--splash-mottle)"
              strokeOpacity=".45"
              strokeWidth="1"
              strokeLinecap="round"
              strokeDasharray="0.5 2.6 1.2 3.4"
            />
            <path
              className="splash-pot"
              d="M21.5 85 L42.5 85 C 42.5 92.5, 40.6 99.6, 36.4 99.6 L27.6 99.6 C 23.4 99.6, 21.5 92.5, 21.5 85 Z"
              fill="var(--splash-pot)"
            />
          </g>
          {/* Grows over the plant, so only the leaf stays in front of it. */}
          <rect className="splash-tile" width="64" height="64" rx="18" fill="var(--accent)" />
          <g className="splash-ride">
            <g transform={LEAF_TRANSFORM}>
              <g className="splash-turn">
                <g className="splash-lengthen">
                  <g className="splash-widen">
                    <g className="splash-wiggle">
                      <path className="splash-blade" d={LEAF_BLADE} />
                      <path className="splash-veins" d={LEAF_VEINS} pathLength={1} />
                    </g>
                  </g>
                </g>
              </g>
            </g>
          </g>
        </svg>
        <p className="splash-wordmark font-display text-4xl font-extrabold tracking-tight text-ink">Jacklyn</p>
      </div>
    </div>
  )
}
