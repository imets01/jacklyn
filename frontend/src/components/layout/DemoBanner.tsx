import { Code2, FlaskConical } from 'lucide-react'

import { useSession } from '../../api/auth'

/** On a public demo, says so on every page: nothing in here is anyone's real money. */
export function DemoBanner() {
  const session = useSession()
  if (!session.data?.demo) return null
  const source = session.data.demo_source_url
  return (
    <div className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-2xl border border-line bg-accent-soft px-4 py-2.5 text-sm text-ink-2">
      <span className="inline-flex items-center gap-2 font-medium text-accent">
        <FlaskConical className="size-4" aria-hidden /> Demo
      </span>
      <span>Every account, trade and price in here is invented, and the data resets regularly.</span>
      {source ? (
        <a href={source} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 font-medium text-accent hover:underline">
          <Code2 className="size-4" aria-hidden /> Read the code
        </a>
      ) : null}
    </div>
  )
}
