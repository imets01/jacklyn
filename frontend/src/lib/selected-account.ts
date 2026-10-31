import { useEffect, useState } from 'react'
import { useLocation, useMatch } from 'react-router'

import type { AccountSummary } from '../api/types'

const SELECTED_KEY = 'jacklyn.selectedAccount'

function positiveId(value: string | null | undefined): number | null {
  const id = Number(value)
  return value && Number.isInteger(id) && id > 0 ? id : null
}

function readStored(): number | null {
  try {
    return positiveId(localStorage.getItem(SELECTED_KEY))
  } catch {
    return null
  }
}

/** The account the current page is about, if any. */
export function useAccountIdInUrl(): number | null {
  const detail = useMatch('/accounts/:accountId')
  const transactions = useMatch('/transactions')
  const { search } = useLocation()
  if (detail) return positiveId(detail.params.accountId)
  if (transactions) return positiveId(new URLSearchParams(search).get('account'))
  return null
}

/**
 * The phone tab bar's current account: the one on screen, else the last one looked at, else the first.
 * The last-used id can name a deleted account or another user's, so it only counts if it's in the list.
 */
export function useSelectedAccount(accounts: AccountSummary[]): AccountSummary | null {
  const inUrl = useAccountIdInUrl()
  const [remembered, setRemembered] = useState(readStored)
  if (inUrl !== null && inUrl !== remembered) setRemembered(inUrl)

  useEffect(() => {
    if (remembered === null) return
    try {
      localStorage.setItem(SELECTED_KEY, String(remembered))
    } catch {
      // Private mode or blocked storage: the selection just won't persist.
    }
  }, [remembered])

  return accounts.find((account) => account.id === (inUrl ?? remembered)) ?? accounts[0] ?? null
}
