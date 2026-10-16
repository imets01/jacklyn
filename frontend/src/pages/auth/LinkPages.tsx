import { CircleAlert, Link2Off } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { useLinkInfo, useRegister, useResetPassword } from '../../api/auth'
import { Button, Field, Input, Notice, Spinner } from '../../components/ui/primitives'
import { formatDate } from '../../lib/format'
import { AuthLayout, PasswordHint } from './AuthLayout'

function InvalidLink({ message }: { message: string }) {
  return (
    <AuthLayout title="Link not valid" subtitle={message}>
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="grid size-12 place-items-center rounded-2xl bg-negative-soft text-negative">
          <Link2Off className="size-5" aria-hidden />
        </div>
        <p className="text-sm text-ink-3">Links work once and expire after a few days. Ask for a fresh one.</p>
        <Link to="/" className="text-sm font-medium text-accent hover:underline">
          Go to sign in
        </Link>
      </div>
    </AuthLayout>
  )
}

function NewPasswordFields({
  password,
  confirm,
  onPassword,
  onConfirm,
}: {
  password: string
  confirm: string
  onPassword: (value: string) => void
  onConfirm: (value: string) => void
}) {
  return (
    <>
      <Field label="Password" hint={<PasswordHint />}>
        <Input type="password" value={password} onChange={(event) => onPassword(event.target.value)} autoComplete="new-password" minLength={12} required />
      </Field>
      <Field label="Confirm password" hint={confirm && confirm !== password ? "Passwords don't match." : undefined}>
        <Input type="password" value={confirm} onChange={(event) => onConfirm(event.target.value)} autoComplete="new-password" required />
      </Field>
    </>
  )
}

export function InvitePage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const info = useLinkInfo(token, 'invite')
  const register = useRegister()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')

  if (info.isLoading) {
    return (
      <div className="grid min-h-dvh place-items-center bg-canvas">
        <Spinner />
      </div>
    )
  }
  if (info.error || !info.data) return <InvalidLink message={info.error?.message ?? 'This invite link is not valid.'} />

  const submit = (event: FormEvent) => {
    event.preventDefault()
    register.mutate({ token, display_name: name, email, password }, { onSuccess: () => void navigate('/', { replace: true }) })
  }

  return (
    <AuthLayout
      title="You're invited"
      subtitle={`Create your Jacklyn account${info.data.label ? `, ${info.data.label}` : ''}. Your portfolio is private - nobody else can see it.`}
      footer={`Invite valid until ${formatDate(info.data.expires_at, 'long')}.`}
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="Your name">
          <Input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" required autoFocus />
        </Field>
        <Field label="Email" hint="You sign in with this.">
          <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required />
        </Field>
        <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
        {register.error ? (
          <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
            {register.error.message}
          </Notice>
        ) : null}
        <Button variant="primary" type="submit" loading={register.isPending} disabled={!name || !email || password.length < 12 || password !== confirm}>
          Create account
        </Button>
      </form>
    </AuthLayout>
  )
}

export function ResetPage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const info = useLinkInfo(token, 'password_reset')
  const reset = useResetPassword()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')

  if (info.isLoading) {
    return (
      <div className="grid min-h-dvh place-items-center bg-canvas">
        <Spinner />
      </div>
    )
  }
  if (info.error || !info.data) return <InvalidLink message={info.error?.message ?? 'This reset link is not valid.'} />

  const submit = (event: FormEvent) => {
    event.preventDefault()
    reset.mutate({ token, password }, { onSuccess: () => void navigate('/', { replace: true }) })
  }

  return (
    <AuthLayout
      title="Choose a new password"
      subtitle={info.data.email ? `For ${info.data.email}.` : undefined}
      footer="This also turns off two-step verification and signs out your other devices."
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <NewPasswordFields password={password} confirm={confirm} onPassword={setPassword} onConfirm={setConfirm} />
        {reset.error ? (
          <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
            {reset.error.message}
          </Notice>
        ) : null}
        <Button variant="primary" type="submit" loading={reset.isPending} disabled={password.length < 12 || password !== confirm}>
          Save password and sign in
        </Button>
      </form>
    </AuthLayout>
  )
}
