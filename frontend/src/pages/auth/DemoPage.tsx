import { ArrowRight, CircleAlert, Code2 } from 'lucide-react'

import { useDemoLogin, useSession } from '../../api/auth'
import { Button, Notice } from '../../components/ui/primitives'
import { AuthLayout } from './AuthLayout'

const POINTS = [
  'Statements from several brokers in one exact-decimal ledger',
  'Live valuation across CHF, EUR, USD and HUF',
  'Money- and time-weighted returns, dividends, portfolio health',
]

/** The sign-in screen of a public demo instance: no credentials, one button into the seeded portfolio. */
export function DemoPage() {
  const session = useSession()
  const demo = useDemoLogin()
  const source = session.data?.demo_source_url ?? null

  return (
    <AuthLayout
      title="Jacklyn"
      subtitle="A self-hosted wealth tracker. This is a live demo filled with invented data — look around, change anything."
      footer="The portfolio, the brokers and every number in here are made up."
    >
      <div className="flex flex-col gap-5">
        <ul className="flex flex-col gap-2 text-sm text-ink-2">
          {POINTS.map((point) => (
            <li key={point} className="flex gap-2.5">
              <ArrowRight className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden />
              {point}
            </li>
          ))}
        </ul>
        {demo.error ? (
          <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
            {demo.error.message}
          </Notice>
        ) : null}
        <Button variant="primary" onClick={() => demo.mutate()} loading={demo.isPending}>
          Open the demo
        </Button>
        {source ? (
          <a
            href={source}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center justify-center gap-2 text-sm text-ink-3 hover:text-ink"
          >
            <Code2 className="size-4" aria-hidden /> Read the code
          </a>
        ) : null}
      </div>
    </AuthLayout>
  )
}
