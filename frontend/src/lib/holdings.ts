import type { AssetClass, CashBalance, Holding } from '../api/types'
import { toNumber } from './format'

/** One asset across every account, as the dashboard lists it. */
export interface Position {
  assetId: number
  symbol: string
  name: string | null
  isin: string | null
  assetClass: AssetClass
  currency: string
  logoUrl: string | null
  quantity: number
  price: string | null
  avgCost: number | null
  value: number
  costBasis: number
  unrealizedPnl: number
  unrealizedPnlPct: number | null
  dayChange: number
  weight: number
  accounts: number
}

export function combinePositions(holdings: readonly Holding[]): Position[] {
  const byAsset = new Map<number, Position & { localCost: number }>()
  for (const holding of holdings) {
    const quantity = toNumber(holding.quantity)
    const localCost = holding.avg_cost === null ? 0 : toNumber(holding.avg_cost) * quantity
    const existing = byAsset.get(holding.asset_id)
    if (existing) {
      existing.quantity += quantity
      existing.localCost += localCost
      existing.value += toNumber(holding.value)
      existing.costBasis += toNumber(holding.cost_basis)
      existing.unrealizedPnl += toNumber(holding.unrealized_pnl)
      existing.dayChange += toNumber(holding.day_change)
      existing.weight += toNumber(holding.weight)
      existing.accounts += 1
      continue
    }
    byAsset.set(holding.asset_id, {
      assetId: holding.asset_id,
      symbol: holding.symbol,
      name: holding.name,
      isin: holding.isin,
      assetClass: holding.asset_class,
      currency: holding.currency,
      logoUrl: holding.logo_url,
      quantity,
      price: holding.price,
      avgCost: null,
      localCost,
      value: toNumber(holding.value),
      costBasis: toNumber(holding.cost_basis),
      unrealizedPnl: toNumber(holding.unrealized_pnl),
      unrealizedPnlPct: null,
      dayChange: toNumber(holding.day_change),
      weight: toNumber(holding.weight),
      accounts: 1,
    })
  }
  return [...byAsset.values()]
    .map(({ localCost, ...position }) => ({
      ...position,
      avgCost: position.quantity > 0 && localCost > 0 ? localCost / position.quantity : null,
      unrealizedPnlPct: position.costBasis > 0 ? position.unrealizedPnl / position.costBasis : null,
    }))
    .sort((a, b) => b.value - a.value)
}

export interface CashTotal {
  currency: string
  amount: number
  value: number
  logoUrl: string | null
}

export function combineCash(cash: readonly CashBalance[]): CashTotal[] {
  const byCurrency = new Map<string, CashTotal>()
  for (const balance of cash) {
    const total = byCurrency.get(balance.currency) ?? {
      currency: balance.currency,
      amount: 0,
      value: 0,
      logoUrl: balance.logo_url,
    }
    total.amount += toNumber(balance.amount)
    total.value += toNumber(balance.value)
    byCurrency.set(balance.currency, total)
  }
  return [...byCurrency.values()].filter((total) => Math.abs(total.amount) >= 0.005).sort((a, b) => b.value - a.value)
}

export function holdingTitle(holding: { name: string | null; symbol: string }): string {
  return holding.name ?? holding.symbol
}
