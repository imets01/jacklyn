import { CircleCheck, X } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'

import { readImportedState } from '../../lib/imported'

/** Confirms an import or sync that just landed in this account (passed along as router state). */
export function ImportedBanner() {
  const location = useLocation()
  const navigate = useNavigate()
  const imported = readImportedState(location.state)
  if (!imported) return null
  return (
    <div role="status" className="mb-5 flex items-center gap-3 rounded-2xl bg-positive-soft px-4 py-3 text-positive">
      <CircleCheck className="size-5 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold">{imported.title}</p>
        <p className="opacity-80">{imported.detail}</p>
      </div>
      <button
        type="button"
        className="grid size-8 shrink-0 place-items-center rounded-full hover:bg-positive/10"
        aria-label="Dismiss"
        onClick={() => navigate(location.pathname + location.search, { replace: true, state: null })}
      >
        <X className="size-4" aria-hidden />
      </button>
    </div>
  )
}
