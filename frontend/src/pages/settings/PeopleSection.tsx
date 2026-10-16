import { clsx } from 'clsx'
import { Check, Copy, KeyRound, ShieldCheck, UserPlus } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import {
  useAdminUsers,
  useCreateInvite,
  useCreateResetLink,
  useInvites,
  useRevokeInvite,
  useUpdateUser,
  type CreatedLink,
  type Me,
} from '../../api/auth'
import { Badge, Button, Card, CardHeader, Field, Input, Notice, Select, Spinner } from '../../components/ui/primitives'
import { formatDate, formatRelativeTime } from '../../lib/format'

/** A freshly created invite/reset link. The token is never shown again, so make copying it obvious. */
function LinkReveal({ link, kind, onDone }: { link: CreatedLink; kind: 'invite' | 'reset'; onDone: () => void }) {
  const url = `${window.location.origin}${link.path}`
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }
  return (
    <Notice tone="accent" icon={<KeyRound className="size-4" />}>
      <p className="font-medium">
        {kind === 'invite' ? 'Invite link' : 'Password reset link'} - valid until {formatDate(link.expires_at, 'long')}, works once.
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <code className="min-w-0 flex-1 break-all rounded-lg bg-surface px-2.5 py-1.5 text-xs text-ink">{url}</code>
        <Button size="sm" onClick={() => void copy()}>
          {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
          {copied ? 'Copied' : 'Copy'}
        </Button>
        <Button size="sm" variant="ghost" onClick={onDone}>
          Done
        </Button>
      </div>
      <p className="mt-2 text-xs opacity-80">Send it privately (e.g. Signal). This is the only time it's shown.</p>
    </Notice>
  )
}

function InviteCard() {
  const invites = useInvites(true)
  const create = useCreateInvite()
  const revoke = useRevokeInvite()
  const [label, setLabel] = useState('')
  const [days, setDays] = useState(7)
  const [grantsAdmin, setGrantsAdmin] = useState(false)
  const [created, setCreated] = useState<CreatedLink | null>(null)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate(
      { label: label.trim() || null, grants_admin: grantsAdmin, days },
      {
        onSuccess: (link) => {
          setCreated(link)
          setLabel('')
          setGrantsAdmin(false)
        },
      },
    )
  }

  return (
    <Card>
      <CardHeader title="Invite someone" subtitle="There's no public sign-up. Each invite link creates exactly one account." />
      <div className="flex flex-col gap-4 px-6 pb-6 pt-4">
        <form onSubmit={submit} className="grid gap-3 sm:grid-cols-[1fr_140px_auto] sm:items-end">
          <Field label="Who is it for?" hint="Only you see this.">
            <Input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="e.g. Anna" maxLength={120} />
          </Field>
          <Field label="Expires after">
            <Select value={days} onChange={(event) => setDays(Number(event.target.value))}>
              {[1, 3, 7, 14, 30].map((value) => (
                <option key={value} value={value}>
                  {value} day{value === 1 ? '' : 's'}
                </option>
              ))}
            </Select>
          </Field>
          <Button type="submit" variant="primary" loading={create.isPending}>
            <UserPlus className="size-4" aria-hidden /> Create link
          </Button>
          <label className="flex items-center gap-2 text-sm text-ink-2 sm:col-span-3">
            <input type="checkbox" className="size-4 accent-[var(--accent)]" checked={grantsAdmin} onChange={(event) => setGrantsAdmin(event.target.checked)} />
            Make them an admin (can invite and manage people - rarely needed)
          </label>
        </form>
        {created ? <LinkReveal link={created} kind="invite" onDone={() => setCreated(null)} /> : null}
        {create.error ? <p className="text-sm text-negative">{create.error.message}</p> : null}
        {invites.data && invites.data.length > 0 ? (
          <ul className="flex flex-col divide-y divide-line rounded-2xl border border-line">
            {invites.data.slice(0, 10).map((invite) => (
              <li key={invite.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <span className="min-w-0 flex-1 truncate text-ink">
                  {invite.label ?? 'Unnamed invite'} {invite.grants_admin ? <Badge tone="accent">admin</Badge> : null}
                </span>
                <span className="text-xs text-ink-3">
                  {invite.state === 'used'
                    ? `joined as ${invite.used_by ?? 'someone'}`
                    : invite.state === 'pending'
                      ? `expires ${formatDate(invite.expires_at, 'short')}`
                      : invite.state}
                </span>
                {invite.state === 'pending' ? (
                  <Button size="sm" variant="ghost" onClick={() => revoke.mutate(invite.id)}>
                    Revoke
                  </Button>
                ) : (
                  <Badge tone={invite.state === 'used' ? 'positive' : 'neutral'}>{invite.state}</Badge>
                )}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </Card>
  )
}

function UsersCard({ me }: { me: Me }) {
  const users = useAdminUsers(true)
  const update = useUpdateUser()
  const resetLink = useCreateResetLink()
  const [reset, setReset] = useState<{ userId: number; link: CreatedLink } | null>(null)

  return (
    <Card>
      <CardHeader title="People" subtitle="Everyone's portfolio is private to them - admins can manage accounts, not see data." />
      <div className="px-3 pb-4 pt-3">
        {users.isLoading ? <Spinner className="m-4" /> : null}
        <ul className="flex flex-col">
          {(users.data ?? []).map((user) => (
            <li key={user.id} className="rounded-2xl px-3 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={clsx(
                    'grid size-9 shrink-0 place-items-center rounded-xl font-display text-sm font-bold',
                    user.is_active ? 'bg-accent-soft text-accent' : 'bg-surface-2 text-ink-3',
                  )}
                  aria-hidden
                >
                  {user.display_name.slice(0, 1).toUpperCase()}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-1.5 text-sm font-medium text-ink">
                    {user.display_name}
                    {user.id === me.id ? <Badge tone="accent">you</Badge> : null}
                    {user.is_admin ? <Badge>admin</Badge> : null}
                    {user.totp_enabled ? (
                      <Badge tone="positive">
                        <ShieldCheck className="size-3" aria-hidden /> 2-step
                      </Badge>
                    ) : null}
                    {!user.is_active ? <Badge tone="negative">deactivated</Badge> : null}
                  </p>
                  <p className="truncate text-xs text-ink-3">
                    {user.email} · {user.account_count} accounts · last sign-in {user.last_login_at ? formatRelativeTime(user.last_login_at) : 'never'}
                  </p>
                </div>
                {user.id !== me.id ? (
                  <div className="flex flex-wrap gap-1">
                    {user.is_active ? (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => resetLink.mutate(user.id, { onSuccess: (link) => setReset({ userId: user.id, link }) })}
                      >
                        Reset link
                      </Button>
                    ) : null}
                    <Button size="sm" variant="ghost" onClick={() => update.mutate({ id: user.id, is_admin: !user.is_admin })}>
                      {user.is_admin ? 'Remove admin' : 'Make admin'}
                    </Button>
                    <Button size="sm" variant={user.is_active ? 'ghost' : 'secondary'} onClick={() => update.mutate({ id: user.id, is_active: !user.is_active })}>
                      {user.is_active ? 'Deactivate' : 'Reactivate'}
                    </Button>
                  </div>
                ) : null}
              </div>
              {reset && reset.userId === user.id ? (
                <div className="mt-3">
                  <LinkReveal link={reset.link} kind="reset" onDone={() => setReset(null)} />
                </div>
              ) : null}
            </li>
          ))}
        </ul>
        {update.error ? <p className="px-3 text-sm text-negative">{update.error.message}</p> : null}
        <p className="px-3 pt-2 text-xs text-ink-3">
          Deactivating signs someone out immediately and blocks sign-in; their data is kept. A reset link lets them choose a new
          password and turns off their two-step verification (for a lost phone).
        </p>
      </div>
    </Card>
  )
}

export function PeopleSection({ me }: { me: Me }) {
  return (
    <section className="flex flex-col gap-5">
      <h2 className="text-lg font-semibold text-ink">People</h2>
      <InviteCard />
      <UsersCard me={me} />
    </section>
  )
}
