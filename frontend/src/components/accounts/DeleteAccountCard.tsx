import { CircleAlert, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { useDeleteAccount } from '../../api/hooks'
import type { AccountSummary } from '../../api/types'
import { Modal } from '../ui/Modal'
import { Button, Card, CardHeader, Field, Input, Notice } from '../ui/primitives'

export function DeleteAccountCard({ account }: { account: AccountSummary }) {
  const [open, setOpen] = useState(false)
  const [typed, setTyped] = useState('')
  const remove = useDeleteAccount()
  const navigate = useNavigate()
  const matches = typed.trim() === account.name

  const close = () => {
    setOpen(false)
    setTyped('')
    remove.reset()
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    remove.mutate(
      { id: account.id, confirm: typed.trim() },
      { onSuccess: () => void navigate('/accounts', { replace: true }) },
    )
  }

  return (
    <Card className="border-negative/30">
      <CardHeader
        title="Delete this account"
        subtitle="Removes the account with all its transactions and import history. This can't be undone."
        action={
          <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
            <Trash2 className="size-3.5" aria-hidden /> Delete account
          </Button>
        }
      />
      <div className="pb-5" />
      <Modal
        open={open}
        onClose={close}
        title={`Delete ${account.name}?`}
        description="This can't be undone. Your other accounts aren't affected."
        footer={
          <>
            <Button variant="ghost" onClick={close}>
              Cancel
            </Button>
            <Button variant="danger" type="submit" form="delete-account" loading={remove.isPending} disabled={!matches}>
              Delete permanently
            </Button>
          </>
        }
      >
        <form id="delete-account" onSubmit={submit} className="flex flex-col gap-4">
          <ul className="list-disc pl-5 text-sm text-ink-2">
            <li>
              {account.transaction_count} transaction{account.transaction_count === 1 ? '' : 's'}
            </li>
            <li>
              {account.holdings_count} holding{account.holdings_count === 1 ? '' : 's'} and the account's cash balances
            </li>
            <li>its import history (re-importing the same files later works fine)</li>
          </ul>
          <Field label={`Type "${account.name}" to confirm`}>
            <Input value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" autoFocus />
          </Field>
          {remove.error ? (
            <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
              {remove.error.message}
            </Notice>
          ) : null}
        </form>
      </Modal>
    </Card>
  )
}
