import { ArrowRight, Check, Wand2 } from "lucide-react";
import { useState } from "react";

import { TYPE_LABELS } from "@/lib/labels";
import type {
  CanonicalField,
  ColumnMapping,
  FieldSpec,
  ImportPreview,
  TransactionType,
} from "@/lib/types";

import { inputClass } from "../dashboard/AddAccountModal";
import { Modal } from "../ui/Modal";
import { Badge, Button, cx } from "../ui/primitives";

const DATE_FORMATS: { value: string; example: string }[] = [
  { value: "", example: "Auto-detect" },
  { value: "%Y-%m-%d", example: "2026-01-31" },
  { value: "%d.%m.%Y", example: "31.01.2026" },
  { value: "%d/%m/%Y", example: "31/01/2026" },
  { value: "%m/%d/%Y", example: "01/31/2026" },
  { value: "%Y.%m.%d.", example: "2026.01.31." },
  { value: "%d/%m/%Y %H:%M:%S", example: "31/01/2026 14:05:00" },
  { value: "%Y-%m-%d %H:%M:%S", example: "2026-01-31 14:05:00" },
];

export function emptyMapping(preview: ImportPreview): ColumnMapping {
  const s = preview.suggestion;
  const typeMap: Record<string, TransactionType> = {};
  for (const [raw, t] of Object.entries(s?.type_map ?? {})) if (t) typeMap[raw] = t;
  return {
    columns: { ...(s?.columns ?? {}) },
    date_format: s?.date_format ?? null,
    decimal_separator: s?.decimal_separator ?? ".",
    thousands_separator: null,
    delimiter: s?.delimiter ?? null,
    type_map: typeMap,
    default_currency: null,
    amount_sign: "infer",
  };
}

export function mappingProblems(m: ColumnMapping): string[] {
  const problems: string[] = [];
  if (!m.columns.trade_date) problems.push("Map a trade date column");
  if (!m.columns.type) problems.push("Map a transaction type column");
  if (!m.columns.amount && !(m.columns.quantity && m.columns.price))
    problems.push("Map an amount column (or both quantity and price)");
  if (!m.columns.currency && !m.default_currency)
    problems.push("Map a currency column or pick a default currency");
  return problems;
}

export function ColumnMapperModal({
  open,
  preview,
  fields,
  transactionTypes,
  initial,
  saveAs,
  onClose,
  onApply,
}: {
  open: boolean;
  preview: ImportPreview;
  fields: FieldSpec[];
  transactionTypes: TransactionType[];
  initial: ColumnMapping;
  saveAs: string;
  onClose: () => void;
  onApply: (mapping: ColumnMapping, saveAs: string) => void;
}) {
  const [mapping, setMapping] = useState<ColumnMapping>(initial);
  const [name, setName] = useState(saveAs);
  const headers = preview.headers;
  const rows = preview.sample_rows;

  const columnValues = (header: string | undefined) => {
    if (!header) return [];
    const idx = headers.indexOf(header);
    return idx < 0 ? [] : rows.map((r) => r[idx] ?? "").filter((v) => v.trim() !== "");
  };

  const rawTypes = [...new Set(columnValues(mapping.columns.type).map((v) => v.trim()))];

  const problems = mappingProblems(mapping);
  const mappedHeaders = new Set(Object.values(mapping.columns));

  function setColumn(field: CanonicalField, header: string) {
    setMapping((m) => {
      const columns = { ...m.columns };
      if (header) columns[field] = header;
      else delete columns[field];
      return { ...m, columns };
    });
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      wide
      title="Universal Column Mapper"
      subtitle="Tell Jacklyn what each column means. Save it once and the same layout is recognised automatically next time."
      footer={
        <>
          <label className="mr-auto flex items-center gap-2 text-sm">
            <span className="whitespace-nowrap text-muted">Save as</span>
            <input
              className={cx(inputClass, "h-9 w-48")}
              placeholder="e.g. My bank export"
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={problems.length > 0}
            onClick={() => onApply(mapping, name)}
            icon={<Check className="size-4" aria-hidden />}
          >
            Apply mapping
          </Button>
        </>
      }
    >
      <div className="grid gap-8 lg:grid-cols-[1.4fr_1fr]">
        {/* Field ↔ column grid */}
        <section aria-label="Column mapping">
          <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <Wand2 className="size-4 text-brand" aria-hidden /> Columns
            {preview.suggestion?.is_complete && <Badge tone="positive">Auto-matched</Badge>}
          </h3>
          <ul className="divide-y divide-line rounded-2xl border border-line">
            {fields.map((f) => {
              const header = mapping.columns[f.key] ?? "";
              const sample = columnValues(header)[0];
              return (
                <li key={f.key} className="grid grid-cols-[1fr_auto_1.2fr] items-center gap-3 px-4 py-2.5">
                  <div className="min-w-0">
                    <div className="text-sm font-medium">
                      {f.label}
                      {f.required && <span className="text-negative"> *</span>}
                    </div>
                    <div className="truncate text-xs text-muted" title={f.help}>
                      {sample ? (
                        <span className="tabular text-ink/80">e.g. {sample}</span>
                      ) : (
                        f.help
                      )}
                    </div>
                  </div>
                  <ArrowRight className="size-4 text-subtle" aria-hidden />
                  <select
                    aria-label={`Column for ${f.label}`}
                    className={cx(inputClass, "h-9", !header && "text-muted")}
                    value={header}
                    onChange={(e) => setColumn(f.key, e.target.value)}
                  >
                    <option value="">— not mapped —</option>
                    {headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </li>
              );
            })}
          </ul>
        </section>

        <div className="grid content-start gap-6">
          {/* Number & date formats */}
          <section className="grid gap-3" aria-label="Formats">
            <h3 className="text-sm font-semibold">Formats</h3>
            <label className="grid gap-1 text-sm">
              <span className="text-muted">Date format</span>
              <select
                className={inputClass}
                value={mapping.date_format ?? ""}
                onChange={(e) => setMapping({ ...mapping, date_format: e.target.value || null })}
              >
                {DATE_FORMATS.map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.example}
                  </option>
                ))}
                {mapping.date_format &&
                  !DATE_FORMATS.some((d) => d.value === mapping.date_format) && (
                    <option value={mapping.date_format}>{mapping.date_format}</option>
                  )}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <label className="grid gap-1 text-sm">
                <span className="text-muted">Decimal mark</span>
                <select
                  className={inputClass}
                  value={mapping.decimal_separator}
                  onChange={(e) =>
                    setMapping({
                      ...mapping,
                      decimal_separator: e.target.value as ColumnMapping["decimal_separator"],
                    })
                  }
                >
                  <option value=".">1,234.56</option>
                  <option value=",">1.234,56</option>
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="text-muted">Default currency</span>
                <select
                  className={inputClass}
                  value={mapping.default_currency ?? ""}
                  onChange={(e) =>
                    setMapping({ ...mapping, default_currency: e.target.value || null })
                  }
                >
                  <option value="">From column</option>
                  {["CHF", "EUR", "HUF", "USD", "GBP"].map((c) => (
                    <option key={c}>{c}</option>
                  ))}
                </select>
              </label>
            </div>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 accent-[var(--brand)]"
                checked={mapping.amount_sign === "infer"}
                onChange={(e) =>
                  setMapping({ ...mapping, amount_sign: e.target.checked ? "infer" : "as_is" })
                }
              />
              <span>
                Derive +/− from the type
                <span className="block text-xs text-muted">
                  Untick if amounts in the file are already signed (buys negative).
                </span>
              </span>
            </label>
          </section>

          {/* Type values */}
          <section className="grid gap-2" aria-label="Transaction types">
            <h3 className="text-sm font-semibold">Transaction types</h3>
            {rawTypes.length === 0 ? (
              <p className="text-sm text-muted">Map the type column to see its values.</p>
            ) : (
              <ul className="grid gap-2">
                {rawTypes.map((raw) => (
                  <li key={raw} className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
                    <code className="truncate rounded-lg bg-surface-2 px-2 py-1.5 text-xs">{raw}</code>
                    <ArrowRight className="size-4 text-subtle" aria-hidden />
                    <select
                      aria-label={`Type for ${raw}`}
                      className={cx(inputClass, "h-9", !mapping.type_map[raw] && "border-warning")}
                      value={mapping.type_map[raw] ?? ""}
                      onChange={(e) => {
                        const type_map = { ...mapping.type_map };
                        if (e.target.value) type_map[raw] = e.target.value as TransactionType;
                        else delete type_map[raw];
                        setMapping({ ...mapping, type_map });
                      }}
                    >
                      <option value="">Auto-guess</option>
                      {transactionTypes.map((t) => (
                        <option key={t} value={t}>
                          {TYPE_LABELS[t]}
                        </option>
                      ))}
                    </select>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {problems.length > 0 && (
            <ul className="rounded-2xl bg-warning-soft p-3 text-sm text-warning">
              {problems.map((p) => (
                <li key={p}>• {p}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Raw file preview with mapped columns highlighted */}
      <section className="mt-8" aria-label="File sample">
        <h3 className="mb-3 text-sm font-semibold">File sample</h3>
        <div className="overflow-x-auto rounded-2xl border border-line">
          <table className="w-full text-xs">
            <thead>
              <tr>
                {headers.map((h) => (
                  <th
                    key={h}
                    className={cx(
                      "px-3 py-2 text-left font-medium whitespace-nowrap",
                      mappedHeaders.has(h) ? "bg-brand-soft text-brand-strong" : "bg-surface-2 text-muted",
                    )}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {rows.slice(0, 5).map((r, i) => (
                <tr key={i}>
                  {headers.map((h, j) => (
                    <td key={h} className="tabular px-3 py-2 whitespace-nowrap text-muted">
                      {r[j]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </Modal>
  );
}
