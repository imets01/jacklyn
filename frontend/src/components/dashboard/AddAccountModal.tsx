import { useState } from "react";

import { api } from "@/lib/api";
import { INSTITUTION_META } from "@/lib/palette";
import type { AccountType, Institution } from "@/lib/types";

import { Modal } from "../ui/Modal";
import { Button, SegmentedControl } from "../ui/primitives";

const INSTITUTIONS = Object.keys(INSTITUTION_META) as Institution[];
const TYPES: { value: AccountType; label: string }[] = [
  { value: "standard", label: "Standard" },
  { value: "swiss", label: "Swiss" },
  { value: "tbsz", label: "TBSZ" },
];

export const inputClass =
  "h-10 w-full rounded-xl border border-line bg-surface px-3 text-sm text-ink outline-none transition-colors focus:border-brand";

export function AddAccountModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [institution, setInstitution] = useState<Institution>("ibkr");
  const [type, setType] = useState<AccountType>("standard");
  const [year, setYear] = useState(String(new Date().getFullYear()));
  const [currency, setCurrency] = useState("EUR");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();

  async function submit() {
    setSaving(true);
    setError(undefined);
    try {
      await api.createAccount({
        name: name.trim(),
        institution,
        account_type: type,
        tbsz_year: type === "tbsz" ? Number(year) : null,
        base_currency: currency,
      });
      setName("");
      onCreated();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add account"
      subtitle="Group transactions by broker account. TBSZ accounts track their lock-up."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={saving} disabled={!name.trim()} onClick={submit}>
            Create account
          </Button>
        </>
      }
    >
      <form
        className="grid gap-4"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <label className="grid gap-1.5 text-sm">
          <span className="font-medium">Name</span>
          <input
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Erste TBSZ 2026"
            autoFocus
          />
        </label>
        <div className="grid grid-cols-2 gap-4">
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Broker</span>
            <select
              className={inputClass}
              value={institution}
              onChange={(e) => setInstitution(e.target.value as Institution)}
            >
              {INSTITUTIONS.map((i) => (
                <option key={i} value={i}>
                  {INSTITUTION_META[i].label}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Currency</span>
            <select
              className={inputClass}
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
            >
              {["CHF", "EUR", "HUF", "USD", "GBP"].map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="grid gap-1.5 text-sm">
          <span className="font-medium">Account type</span>
          <SegmentedControl label="Account type" value={type} options={TYPES} onChange={setType} />
        </div>
        {type === "tbsz" && (
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Collection year</span>
            <input
              className={inputClass}
              type="number"
              min={1995}
              max={2100}
              value={year}
              onChange={(e) => setYear(e.target.value)}
            />
            <span className="text-xs text-muted">
              Deposits are allowed in this year only; gains become tax-free after 5 more years.
            </span>
          </label>
        )}
        {error && <p className="text-sm text-negative">{error}</p>}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
