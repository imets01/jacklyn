import type { AccountSummary } from '../api/types'

/** Accounts grouped by institution, preserving the API's order. */
export function groupByBroker(accounts: AccountSummary[]): [string, AccountSummary[]][] {
  const groups = new Map<string, AccountSummary[]>()
  for (const account of accounts) {
    const list = groups.get(account.broker) ?? []
    list.push(account)
    groups.set(account.broker, list)
  }
  return [...groups.entries()]
}
