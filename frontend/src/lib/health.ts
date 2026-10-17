import type { HealthCategory, RiskLevel } from '../api/types'

export const RISK_LABELS: Record<RiskLevel, { label: string; hint: string }> = {
  conservative: { label: 'Conservative', hint: 'A 20% fall would make me sell.' },
  balanced: { label: 'Balanced', hint: 'I can sit through a 30% fall, uncomfortably.' },
  growth: { label: 'Growth', hint: 'I can hold through a 40% fall.' },
  aggressive: { label: 'Aggressive', hint: 'A 50% fall would not change my plan.' },
}

export const CATEGORY_LABELS: Record<HealthCategory, string> = {
  equity: 'Stocks',
  bonds: 'Bonds',
  commodities: 'Gold & commodities',
  crypto: 'Crypto',
  other: 'Other',
  cash: 'Cash (beyond emergency fund)',
}
