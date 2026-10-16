import { CircleAlert, ShieldCheck } from 'lucide-react'
import { useState, type FormEvent } from 'react'

import { useLogin } from '../../api/auth'
import { ApiError } from '../../api/client'
import { Button, Field, Input, Notice } from '../../components/ui/primitives'
import { AuthLayout } from './AuthLayout'

export function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code, setCode] = useState('')
  const [needsCode, setNeedsCode] = useState(false)
  const login = useLogin()

  const submit = (event: FormEvent) => {
    event.preventDefault()
    login.mutate(
      { email, password, totp_code: needsCode ? code : null },
      {
        onError: (error) => {
          if (error instanceof ApiError && error.code === 'totp_required') {
            setNeedsCode(true)
            setCode('')
          }
        },
      },
    )
  }

  const error = login.error
  const showError = error && !(error instanceof ApiError && error.code === 'totp_required' && !code)

  return (
    <AuthLayout
      title={needsCode ? 'Two-step verification' : 'Welcome back'}
      subtitle={needsCode ? 'Enter the 6-digit code from your authenticator app.' : 'Sign in to your Jacklyn.'}
      footer="Private instance · accounts are invite-only."
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        {needsCode ? (
          <Field label="Authentication code">
            <Input
              value={code}
              onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              autoComplete="one-time-code"
              placeholder="123456"
              autoFocus
              className="text-center text-lg tracking-[0.4em]"
            />
          </Field>
        ) : (
          <>
            <Field label="Email">
              <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required autoFocus />
            </Field>
            <Field label="Password">
              <Input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </Field>
          </>
        )}
        {showError ? (
          <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
            {error.message}
          </Notice>
        ) : null}
        <Button variant="primary" type="submit" loading={login.isPending} disabled={needsCode ? code.length !== 6 : !email || !password}>
          {needsCode ? (
            <>
              <ShieldCheck className="size-4" aria-hidden /> Verify
            </>
          ) : (
            'Sign in'
          )}
        </Button>
        {needsCode ? (
          <button type="button" className="text-sm text-ink-3 hover:text-ink" onClick={() => setNeedsCode(false)}>
            Use a different account
          </button>
        ) : (
          <p className="text-center text-xs text-ink-3">Forgot your password? Ask the person who invited you for a reset link.</p>
        )}
      </form>
    </AuthLayout>
  )
}
