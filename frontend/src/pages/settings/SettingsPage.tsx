import { LogOut } from 'lucide-react'

import { useLogout, useSession } from '../../api/auth'
import { PageHeader } from '../../components/layout/PageHeader'
import { Button, Spinner } from '../../components/ui/primitives'
import { PeopleSection } from './PeopleSection'
import { PasswordCard, ProfileCard, SessionsCard, TwoFactorCard } from './SecuritySection'

export function SettingsPage() {
  const session = useSession()
  const logout = useLogout()
  const me = session.data?.user
  if (!me) {
    return (
      <div className="grid h-80 place-items-center">
        <Spinner />
      </div>
    )
  }
  return (
    <>
      <PageHeader
        title="Settings"
        subtitle="Your account, security and the people you share Jacklyn with."
        showMarket={false}
        actions={
          <Button onClick={() => logout.mutate()} loading={logout.isPending}>
            <LogOut className="size-4" aria-hidden /> Sign out
          </Button>
        }
      />
      <div className="flex max-w-4xl flex-col gap-8">
        <section className="flex flex-col gap-5">
          <h2 className="text-lg font-semibold text-ink">Account & security</h2>
          <ProfileCard me={me} />
          <PasswordCard />
          <TwoFactorCard me={me} />
          <SessionsCard />
        </section>
        {me.is_admin ? <PeopleSection me={me} /> : null}
        <p className="text-xs text-ink-3">
          Market data from Yahoo Finance; fund country mixes and holdings from{' '}
          <a href="https://eulerpool.com" target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
            Eulerpool
          </a>{' '}
          (when configured). Stock, fund, commodity and currency logos by{' '}
          <a href="https://elbstream.com" target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
            Elbstream
          </a>
          ; logos are trademarks of their owners.
        </p>
      </div>
    </>
  )
}
