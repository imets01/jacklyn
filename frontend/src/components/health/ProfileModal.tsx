import { useState, type FormEvent } from 'react'

import { useSaveInvestorProfile } from '../../api/hooks'
import { BASE_CURRENCIES, HEALTH_CATEGORIES, RISK_LEVELS, type HealthCategory, type InvestorProfile, type RiskLevel } from '../../api/types'
import { CATEGORY_LABELS, RISK_LABELS } from '../../lib/health'
import { usePreferences } from '../../lib/preferences-context'
import { Modal } from '../ui/Modal'
import { Button, Field, Input, Notice, Select } from '../ui/primitives'

const GOALS = ['Retirement', 'Wealth building', 'House', 'Education', 'Other']
const COUNTRIES = ['Switzerland', 'Germany', 'Hungary', 'United Kingdom', 'France', 'United States', 'Japan', 'Canada']

function percentString(value: string | null | undefined): string {
  return value ? String(Math.round(Number(value) * 1000) / 10) : ''
}

function ProfileForm({ profile, onClose }: { profile: InvestorProfile | null; onClose: () => void }) {
  const save = useSaveInvestorProfile()
  const [birthYear, setBirthYear] = useState(profile?.birth_year ? String(profile.birth_year) : '')
  const [horizon, setHorizon] = useState(profile?.horizon_years != null ? String(profile.horizon_years) : '')
  const [risk, setRisk] = useState<RiskLevel>(profile?.risk_tolerance ?? 'balanced')
  const [goal, setGoal] = useState(profile?.goal ?? 'Wealth building')
  const [home, setHome] = useState(profile?.home_country ?? 'Switzerland')
  const { baseCurrency } = usePreferences()
  const [currency, setCurrency] = useState(profile?.currency ?? baseCurrency)
  const [emergency, setEmergency] = useState(profile?.emergency_fund ?? '')
  const [monthly, setMonthly] = useState(profile?.monthly_contribution ?? '')
  const [minOrder, setMinOrder] = useState(profile && Number(profile.min_order) ? profile.min_order : '')
  const [fractional, setFractional] = useState(profile?.fractional_shares ?? true)
  const [manual, setManual] = useState(Boolean(profile?.target_overrides))
  const [targets, setTargets] = useState<Record<HealthCategory, string>>(() => {
    const raw = profile?.target_overrides ?? {}
    return Object.fromEntries(HEALTH_CATEGORIES.map((key) => [key, percentString(raw[key])])) as Record<HealthCategory, string>
  })

  const targetSum = HEALTH_CATEGORIES.reduce((sum, key) => sum + (Number(targets[key]) || 0), 0)
  const targetsValid = !manual || Math.abs(targetSum - 100) < 0.05
  const horizonValid = horizon !== '' || birthYear !== ''

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!targetsValid || !horizonValid) return
    const overrides = manual
      ? Object.fromEntries(
          HEALTH_CATEGORIES.filter((key) => Number(targets[key]) > 0).map((key) => [key, String(Number(targets[key]) / 100)]),
        )
      : null
    save.mutate(
      {
        birth_year: birthYear ? Number(birthYear) : null,
        horizon_years: horizon !== '' ? Number(horizon) : null,
        risk_tolerance: risk,
        goal,
        home_country: home,
        currency,
        emergency_fund: emergency || null,
        monthly_contribution: monthly || null,
        min_order: minOrder || '0',
        fractional_shares: fractional,
        target_overrides: overrides,
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Your investor profile"
      description="Used to suggest a target allocation and to judge your portfolio against it. Stored only in Jacklyn."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" type="submit" form="investor-profile" loading={save.isPending} disabled={!targetsValid || !horizonValid}>
            Save profile
          </Button>
        </>
      }
    >
      <form id="investor-profile" onSubmit={submit} className="grid gap-4 sm:grid-cols-2">
        <Field label="Birth year">
          <Input type="number" min={1900} max={2100} value={birthYear} onChange={(e) => setBirthYear(e.target.value)} placeholder="1995" />
        </Field>
        <Field label="Years until you need the money" hint="Leave empty to use years until age 65.">
          <Input type="number" min={-40} max={80} value={horizon} onChange={(e) => setHorizon(e.target.value)} placeholder="30" />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Risk tolerance" hint={RISK_LABELS[risk].hint}>
            <Select value={risk} onChange={(e) => setRisk(e.target.value as RiskLevel)}>
              {RISK_LEVELS.map((level) => (
                <option key={level} value={level}>
                  {RISK_LABELS[level].label}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Goal">
          <Select value={goal} onChange={(e) => setGoal(e.target.value)}>
            {GOALS.map((option) => (
              <option key={option}>{option}</option>
            ))}
          </Select>
        </Field>
        <Field label="Home country" hint="Used for the home-bias check.">
          <Select value={home} onChange={(e) => setHome(e.target.value)}>
            {(COUNTRIES.includes(home) ? COUNTRIES : [home, ...COUNTRIES]).map((option) => (
              <option key={option}>{option}</option>
            ))}
          </Select>
        </Field>
        <Field label="Currency of the amounts below" hint="Converted automatically when you view another currency.">
          <Select value={currency} onChange={(e) => setCurrency(e.target.value)}>
            {(BASE_CURRENCIES as readonly string[]).includes(currency)
              ? BASE_CURRENCIES.map((code) => <option key={code}>{code}</option>)
              : [currency, ...BASE_CURRENCIES].map((code) => <option key={code}>{code}</option>)}
          </Select>
        </Field>
        <Field label={`Emergency fund (${currency})`} hint="Cash kept aside; not counted as idle.">
          <Input type="number" min={0} step="any" value={emergency} onChange={(e) => setEmergency(e.target.value)} placeholder="0" />
        </Field>
        <Field label={`Monthly contribution (${currency})`} hint="Used by the rebalancing assistant.">
          <Input type="number" min={0} step="any" value={monthly} onChange={(e) => setMonthly(e.target.value)} placeholder="0" />
        </Field>
        <Field label={`Minimum order size (${currency})`} hint="Smaller orders are skipped.">
          <Input type="number" min={0} step="any" value={minOrder} onChange={(e) => setMinOrder(e.target.value)} placeholder="0" />
        </Field>
        <label className="flex items-center gap-3 self-end rounded-2xl bg-surface-2 px-4 py-3 text-sm">
          <input type="checkbox" className="size-4 accent-[var(--accent)]" checked={fractional} onChange={(e) => setFractional(e.target.checked)} />
          <span className="font-medium text-ink">My broker allows fractional shares</span>
        </label>
        <div className="flex flex-col gap-3 rounded-2xl border border-line p-4 sm:col-span-2">
          <label className="flex items-start gap-3 text-sm">
            <input type="checkbox" className="mt-0.5 size-4 accent-[var(--accent)]" checked={manual} onChange={(e) => setManual(e.target.checked)} />
            <span>
              <span className="font-medium text-ink">Set my own target allocation</span>
              <span className="block text-ink-3">Otherwise Jacklyn suggests one from your horizon and risk tolerance.</span>
            </span>
          </label>
          {manual ? (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {HEALTH_CATEGORIES.map((key) => (
                  <Field key={key} label={`${CATEGORY_LABELS[key]} %`}>
                    <Input
                      type="number"
                      min={0}
                      max={100}
                      step="any"
                      value={targets[key]}
                      onChange={(e) => setTargets((current) => ({ ...current, [key]: e.target.value }))}
                      placeholder="0"
                    />
                  </Field>
                ))}
              </div>
              <p className={targetsValid ? 'text-xs text-ink-3' : 'text-xs font-medium text-negative'}>
                Total {Math.round(targetSum * 10) / 10}% {targetsValid ? '' : '— must be 100%'}
              </p>
            </>
          ) : null}
        </div>
        {!horizonValid ? (
          <div className="sm:col-span-2">
            <Notice>Enter a birth year or the years until you need the money.</Notice>
          </div>
        ) : null}
        {save.error ? (
          <div className="sm:col-span-2">
            <Notice tone="negative">{save.error.message}</Notice>
          </div>
        ) : null}
      </form>
    </Modal>
  )
}

export function ProfileModal({ open, profile, onClose }: { open: boolean; profile: InvestorProfile | null; onClose: () => void }) {
  return open ? <ProfileForm profile={profile} onClose={onClose} /> : null
}
