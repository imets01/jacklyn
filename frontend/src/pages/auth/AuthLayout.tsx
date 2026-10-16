import type { ReactNode } from 'react'

import { LogoMark } from '../../components/ui/Logo'

export function AuthLayout({ title, subtitle, children, footer }: { title: string; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-canvas px-4 py-10">
      <div className="w-full max-w-[400px]">
        <div className="mb-8 flex flex-col items-center text-center">
          <LogoMark className="size-14" />
          <h1 className="mt-5 text-2xl font-bold text-ink">{title}</h1>
          {subtitle ? <div className="mt-2 text-sm text-ink-3">{subtitle}</div> : null}
        </div>
        <div className="rounded-3xl border border-line bg-surface p-6 shadow-[var(--shadow-card)] sm:p-7">{children}</div>
        {footer ? <div className="mt-6 text-center text-xs text-ink-3">{footer}</div> : null}
      </div>
    </div>
  )
}

export function PasswordHint() {
  return <>At least 12 characters. A short sentence is easy to remember and hard to guess.</>
}
