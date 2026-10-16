import { CircleAlert, CircleCheck, Laptop, ShieldCheck, ShieldOff } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import {
  useChangePassword,
  useRevokeSession,
  useSignInSessions,
  useTotpDisable,
  useTotpEnable,
  useTotpSetup,
  type Me,
} from '../../api/auth'
import { useUpdateMe } from '../../api/hooks'
import { Badge, Button, Card, CardHeader, Field, Input, Notice, Spinner } from '../../components/ui/primitives'
import { formatRelativeTime } from '../../lib/format'

function describeDevice(userAgent: string | null): string {
  if (!userAgent) return 'Unknown device'
  const browser = /Edg\//.test(userAgent)
    ? 'Edge'
    : /Firefox\//.test(userAgent)
      ? 'Firefox'
      : /Chrome\//.test(userAgent)
        ? 'Chrome'
        : /Safari\//.test(userAgent)
          ? 'Safari'
          : 'Browser'
  const os = /iPhone|iPad/.test(userAgent)
    ? 'iOS'
    : /Android/.test(userAgent)
      ? 'Android'
      : /Mac OS X/.test(userAgent)
        ? 'macOS'
        : /Windows/.test(userAgent)
          ? 'Windows'
          : /Linux/.test(userAgent)
            ? 'Linux'
            : ''
  return os ? `${browser} on ${os}` : browser
}

export function ProfileCard({ me }: { me: Me }) {
  const [name, setName] = useState(me.display_name)
  const update = useUpdateMe()
  return (
    <Card>
      <CardHeader title="Profile" subtitle={me.email} />
      <form
        className="flex flex-col gap-3 px-6 pb-6 pt-4 sm:flex-row sm:items-end"
        onSubmit={(event) => {
          event.preventDefault()
          update.mutate({ display_name: name })
        }}
      >
        <div className="flex-1">
          <Field label="Display name">
            <Input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} required />
          </Field>
        </div>
        <Button type="submit" loading={update.isPending} disabled={!name.trim() || name === me.display_name}>
          {update.isSuccess && name === update.data.display_name ? 'Saved' : 'Save'}
        </Button>
      </form>
    </Card>
  )
}

export function PasswordCard() {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const change = useChangePassword()

  const submit = (event: FormEvent) => {
    event.preventDefault()
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          setCurrent('')
          setNext('')
          setConfirm('')
        },
      },
    )
  }

  return (
    <Card>
      <CardHeader title="Password" subtitle="Changing it signs you out on every other device." />
      <form onSubmit={submit} className="grid gap-4 px-6 pb-6 pt-4 sm:grid-cols-3">
        <Field label="Current password">
          <Input type="password" value={current} onChange={(event) => setCurrent(event.target.value)} autoComplete="current-password" required />
        </Field>
        <Field label="New password" hint="At least 12 characters.">
          <Input type="password" value={next} onChange={(event) => setNext(event.target.value)} autoComplete="new-password" required />
        </Field>
        <Field label="Confirm new password" hint={confirm && confirm !== next ? "Doesn't match." : undefined}>
          <Input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} autoComplete="new-password" required />
        </Field>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-3">
          <Button type="submit" variant="primary" loading={change.isPending} disabled={!current || next.length < 12 || next !== confirm}>
            Change password
          </Button>
          {change.isSuccess ? (
            <span className="inline-flex items-center gap-1.5 text-sm text-positive">
              <CircleCheck className="size-4" aria-hidden /> Password changed
            </span>
          ) : null}
          {change.error ? <span className="text-sm text-negative">{change.error.message}</span> : null}
        </div>
      </form>
    </Card>
  )
}

export function TwoFactorCard({ me }: { me: Me }) {
  const setup = useTotpSetup()
  const enable = useTotpEnable()
  const disable = useTotpDisable()
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [disabling, setDisabling] = useState(false)

  return (
    <Card>
      <CardHeader
        title="Two-step verification"
        subtitle="Ask for a code from an authenticator app (1Password, Google Authenticator, Aegis...) at sign-in."
        action={me.totp_enabled ? <Badge tone="positive">On</Badge> : <Badge>Off</Badge>}
      />
      <div className="px-6 pb-6 pt-4">
        {me.totp_enabled ? (
          disabling ? (
            <form
              className="flex flex-col gap-3 sm:flex-row sm:items-end"
              onSubmit={(event) => {
                event.preventDefault()
                disable.mutate(password, { onSuccess: () => setDisabling(false) })
              }}
            >
              <div className="flex-1">
                <Field label="Confirm with your password">
                  <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" autoFocus />
                </Field>
              </div>
              <Button variant="danger" type="submit" loading={disable.isPending} disabled={!password}>
                Turn off
              </Button>
              <Button variant="ghost" onClick={() => setDisabling(false)}>
                Cancel
              </Button>
              {disable.error ? <p className="text-sm text-negative">{disable.error.message}</p> : null}
            </form>
          ) : (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="inline-flex items-center gap-2 text-sm text-ink-2">
                <ShieldCheck className="size-4 text-positive" aria-hidden /> Your account asks for a code at every sign-in.
              </p>
              <Button onClick={() => setDisabling(true)}>
                <ShieldOff className="size-4" aria-hidden /> Turn off
              </Button>
            </div>
          )
        ) : setup.data ? (
          <form
            className="grid gap-6 sm:grid-cols-[auto_1fr]"
            onSubmit={(event) => {
              event.preventDefault()
              enable.mutate(code, { onSuccess: () => setup.reset() })
            }}
          >
            <img src={setup.data.qr_data_url} alt="QR code for your authenticator app" className="size-44 rounded-2xl border border-line bg-white p-1" />
            <div className="flex flex-col gap-3">
              <p className="text-sm text-ink-2">
                1. Scan the QR code with your authenticator app, or enter this key manually:
              </p>
              <code className="break-all rounded-xl bg-surface-2 px-3 py-2 text-xs tracking-wider text-ink">{setup.data.secret}</code>
              <Field label="2. Enter the 6-digit code it shows">
                <Input
                  value={code}
                  onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  className="max-w-40 tracking-[0.3em]"
                  autoFocus
                />
              </Field>
              {enable.error ? (
                <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
                  {enable.error.message}
                </Notice>
              ) : null}
              <div className="flex gap-2">
                <Button variant="primary" type="submit" loading={enable.isPending} disabled={code.length !== 6}>
                  Turn on
                </Button>
                <Button variant="ghost" onClick={() => setup.reset()}>
                  Cancel
                </Button>
              </div>
            </div>
          </form>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-ink-3">Recommended - especially if your Jacklyn is reachable from the internet.</p>
            <Button variant="primary" loading={setup.isPending} onClick={() => setup.mutate()}>
              <ShieldCheck className="size-4" aria-hidden /> Set up
            </Button>
          </div>
        )}
      </div>
    </Card>
  )
}

export function SessionsCard() {
  const sessions = useSignInSessions()
  const revoke = useRevokeSession()
  const others = (sessions.data ?? []).filter((session) => !session.current).length
  return (
    <Card>
      <CardHeader
        title="Signed-in devices"
        subtitle="Sessions last 30 days. Sign out anything you don't recognize."
        action={
          others > 0 ? (
            <Button size="sm" onClick={() => revoke.mutate('others')} loading={revoke.isPending && revoke.variables === 'others'}>
              Sign out others
            </Button>
          ) : undefined
        }
      />
      <ul className="px-3 pb-4 pt-3">
        {sessions.isLoading ? <Spinner className="m-4" /> : null}
        {(sessions.data ?? []).map((session) => (
          <li key={session.id} className="flex items-center gap-3 rounded-xl px-3 py-2.5">
            <Laptop className="size-4 shrink-0 text-ink-3" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm text-ink">
                {describeDevice(session.user_agent)} {session.current ? <Badge tone="accent">This device</Badge> : null}
              </p>
              <p className="truncate text-xs text-ink-3">
                {session.ip_address ?? 'unknown address'} · active {formatRelativeTime(session.last_seen_at)}
              </p>
            </div>
            {!session.current ? (
              <Button size="sm" variant="ghost" onClick={() => revoke.mutate(session.id)}>
                Sign out
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </Card>
  )
}
