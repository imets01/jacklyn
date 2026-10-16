import { CircleAlert, KeyRound } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { useSetup } from '../../api/auth'
import { Button, Field, Input, Notice } from '../../components/ui/primitives'
import { AuthLayout, PasswordHint } from './AuthLayout'

export function SetupPage() {
  const [token, setToken] = useState('')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [keepDemo, setKeepDemo] = useState(false)
  const setup = useSetup()
  const mismatch = confirm.length > 0 && confirm !== password

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setup.mutate({ setup_token: token.trim(), display_name: name, email, password, keep_demo_data: keepDemo })
  }

  return (
    <AuthLayout
      title="Set up Jacklyn"
      subtitle="Create the admin account. You'll invite everyone else from Settings."
      footer="The setup token proves you run this server - nobody else can claim it."
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Notice tone="accent" icon={<KeyRound className="size-4" />}>
          Find the <strong>setup token</strong> in the server log, or in <code className="text-xs">data/setup-token.txt</code>:
          <code className="mt-1 block text-xs">docker compose logs backend | grep -A2 "setup token"</code>
        </Notice>
        <Field label="Setup token">
          <Input value={token} onChange={(event) => setToken(event.target.value)} autoComplete="off" spellCheck={false} required autoFocus />
        </Field>
        <Field label="Your name">
          <Input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" required />
        </Field>
        <Field label="Email" hint="You sign in with this. It never leaves your server.">
          <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required />
        </Field>
        <Field label="Password" hint={<PasswordHint />}>
          <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={12} required />
        </Field>
        <Field label="Confirm password" hint={mismatch ? "Passwords don't match." : undefined}>
          <Input type="password" value={confirm} onChange={(event) => setConfirm(event.target.value)} autoComplete="new-password" required />
        </Field>
        <label className="flex items-start gap-3 rounded-2xl bg-surface-2 px-4 py-3 text-sm">
          <input type="checkbox" className="mt-0.5 size-4 accent-[var(--accent)]" checked={keepDemo} onChange={(event) => setKeepDemo(event.target.checked)} />
          <span>
            <span className="font-medium text-ink">Keep the demo portfolio</span>
            <span className="block text-ink-3">Handy for a tour. Leave off to start with your real accounts.</span>
          </span>
        </label>
        {setup.error ? (
          <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
            {setup.error.message}
          </Notice>
        ) : null}
        <Button variant="primary" type="submit" loading={setup.isPending} disabled={!token || !name || !email || password.length < 12 || password !== confirm}>
          Create admin account
        </Button>
      </form>
    </AuthLayout>
  )
}
