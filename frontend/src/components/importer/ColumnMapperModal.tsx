import { clsx } from 'clsx'
import { CircleAlert, Columns3, RefreshCw, WandSparkles } from 'lucide-react'
import { useMemo, useState } from 'react'

import {
  MAPPING_FIELDS,
  TRANSACTION_TYPES,
  type ColumnMappingConfig,
  type MappingField,
  type TablePreview,
  type TransactionType,
} from '../../api/types'
import { TRANSACTION_TYPE_LABELS } from '../../lib/format'
import { Modal } from '../ui/Modal'
import { Badge, Button, Field, Input, Notice, Select } from '../ui/primitives'
import { DATE_FORMATS, FIELD_META, missingRequirements, withColumn, withTypeMapping } from './mapping'

const CURRENCIES = ['CHF', 'EUR', 'USD', 'HUF', 'GBP']
const REQUIRED: readonly MappingField[] = ['date']

export interface MapperApply {
  config: ColumnMappingConfig
  presetName: string | null
}

export function ColumnMapperModal({
  open,
  onClose,
  table,
  initial,
  filename,
  applying,
  error,
  onApply,
  onReloadTable,
}: {
  open: boolean
  onClose: () => void
  table: TablePreview
  initial: ColumnMappingConfig
  filename: string
  applying: boolean
  error: string | null
  onApply: (result: MapperApply) => void
  onReloadTable: (config: ColumnMappingConfig) => Promise<TablePreview | null>
}) {
  const [config, setConfig] = useState<ColumnMappingConfig>(initial)
  const [currentTable, setCurrentTable] = useState<TablePreview>(table)
  const [savePreset, setSavePreset] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [reloading, setReloading] = useState(false)

  const headers = currentTable.headers
  const problems = missingRequirements(config)
  const fieldByHeader = useMemo(() => {
    const map = new Map<string, MappingField>()
    for (const [field, header] of Object.entries(config.columns)) if (header) map.set(header, field as MappingField)
    return map
  }, [config.columns])
  const typeHeader = config.columns.type
  const typeValues = typeHeader
    ? (currentTable.distinct_values[typeHeader] ??
      (typeHeader === table.suggested.columns.type ? currentTable.distinct_type_values : []))
    : []

  const reload = async (next: ColumnMappingConfig) => {
    setReloading(true)
    try {
      const fresh = await onReloadTable(next)
      if (fresh) {
        setCurrentTable(fresh)
        // Keep only assignments whose header still exists under the new header row/delimiter.
        const columns = Object.fromEntries(
          Object.entries(next.columns).filter(([, header]) => header && fresh.headers.includes(header)),
        )
        setConfig({ ...next, columns, header_row: fresh.header_row })
      }
    } finally {
      setReloading(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="xl"
      title="Map your columns"
      description={
        <span>
          <span className="font-medium text-ink-2">{filename}</span> isn’t a known broker format. Tell Jacklyn what each
          column means — once. Save it as a preset and the next upload maps itself.
        </span>
      }
      footer={
        <>
          {problems.length > 0 ? <p className="mr-auto text-sm text-warning">{problems[0]}</p> : null}
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            loading={applying}
            disabled={problems.length > 0 || (savePreset && !presetName.trim())}
            onClick={() => onApply({ config, presetName: savePreset ? presetName.trim() : null })}
          >
            <WandSparkles className="size-4" aria-hidden /> Preview transactions
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-6">
        {/* File preview */}
        <section>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
              <Columns3 className="size-4 text-ink-3" aria-hidden /> File preview
            </h3>
            <p className="text-xs text-ink-3">
              {currentTable.total_rows} data rows · header on row {currentTable.header_row + 1}
              {currentTable.delimiter ? ` · delimiter “${currentTable.delimiter === '\t' ? 'tab' : currentTable.delimiter}”` : ''}
              {currentTable.encoding ? ` · ${currentTable.encoding}` : ''}
              {currentTable.sheet_name ? ` · sheet “${currentTable.sheet_name}”` : ''}
            </p>
          </div>
          <div className={clsx('overflow-x-auto rounded-2xl border border-line', reloading && 'opacity-60')}>
            <table className="w-full text-xs">
              <thead className="bg-surface-2 text-left">
                <tr>
                  {headers.map((header) => {
                    const field = fieldByHeader.get(header)
                    return (
                      <th key={header} className="whitespace-nowrap px-3 py-2 align-top font-semibold text-ink">
                        {header}
                        <div className="mt-1 h-5">
                          {field ? <Badge tone="accent">→ {FIELD_META[field].label}</Badge> : <span className="text-[11px] font-normal text-ink-3">not used</span>}
                        </div>
                      </th>
                    )
                  })}
                </tr>
              </thead>
              <tbody className="tabular">
                {currentTable.sample_rows.map((row, index) => (
                  <tr key={index} className="border-t border-line">
                    {row.map((cell, cellIndex) => (
                      <td
                        key={cellIndex}
                        className={clsx(
                          'max-w-[220px] truncate whitespace-nowrap px-3 py-2',
                          fieldByHeader.has(headers[cellIndex] ?? '') ? 'text-ink' : 'text-ink-3',
                        )}
                      >
                        {cell || '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          {/* Column assignments */}
          <section>
            <h3 className="mb-3 text-sm font-semibold text-ink">Columns</h3>
            <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
              {MAPPING_FIELDS.map((field) => (
                <Field
                  key={field}
                  label={`${FIELD_META[field].label}${REQUIRED.includes(field) ? ' *' : ''}`}
                  hint={FIELD_META[field].hint}
                >
                  <Select
                    value={config.columns[field] ?? ''}
                    onChange={(event) => setConfig(withColumn(config, field, event.target.value || null))}
                  >
                    <option value="">— Not in this file —</option>
                    {headers.map((header) => (
                      <option key={header} value={header}>
                        {header}
                      </option>
                    ))}
                  </Select>
                </Field>
              ))}
            </div>
          </section>

          <div className="flex flex-col gap-6">
            {/* Formats */}
            <section>
              <h3 className="mb-3 text-sm font-semibold text-ink">Formats</h3>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Decimal format">
                  <Select
                    value={config.decimal_separator ?? ''}
                    onChange={(event) =>
                      setConfig({ ...config, decimal_separator: (event.target.value || null) as ColumnMappingConfig['decimal_separator'] })
                    }
                  >
                    <option value="">Auto ({currentTable.detected_decimal_separator === ',' ? '1.234,56' : '1,234.56'})</option>
                    <option value=".">1,234.56</option>
                    <option value=",">1.234,56</option>
                  </Select>
                </Field>
                <Field label="Date format">
                  <Select value={config.date_format ?? ''} onChange={(event) => setConfig({ ...config, date_format: event.target.value || null })}>
                    {DATE_FORMATS.map((format) => (
                      <option key={format.value} value={format.value}>
                        {format.value === '' && currentTable.detected_date_format
                          ? `Auto (${DATE_FORMATS.find((f) => f.value === currentTable.detected_date_format)?.label ?? currentTable.detected_date_format})`
                          : format.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Default currency" hint={config.columns.currency ? 'Used when a row has none' : 'Required without a currency column'}>
                  <Select value={config.default_currency ?? ''} onChange={(event) => setConfig({ ...config, default_currency: event.target.value || null })}>
                    <option value="">—</option>
                    {CURRENCIES.map((code) => (
                      <option key={code}>{code}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Default type" hint={config.columns.type ? 'Used for unmapped values' : 'Used for every row'}>
                  <Select
                    value={config.default_type ?? ''}
                    onChange={(event) => setConfig({ ...config, default_type: (event.target.value || null) as TransactionType | null })}
                  >
                    <option value="">—</option>
                    {TRANSACTION_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {TRANSACTION_TYPE_LABELS[type]}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Header row" hint="Skip title lines above the table">
                  <Input
                    type="number"
                    min={1}
                    value={(config.header_row ?? currentTable.header_row) + 1}
                    onChange={(event) => setConfig({ ...config, header_row: Math.max(0, Number(event.target.value) - 1) })}
                  />
                </Field>
                {currentTable.kind === 'csv' ? (
                  <Field label="Delimiter">
                    <Select value={config.delimiter ?? ''} onChange={(event) => setConfig({ ...config, delimiter: event.target.value || null })}>
                      <option value="">Auto</option>
                      <option value=",">Comma ,</option>
                      <option value=";">Semicolon ;</option>
                      <option value={'\t'}>Tab</option>
                      <option value="|">Pipe |</option>
                    </Select>
                  </Field>
                ) : null}
              </div>
              {(config.header_row ?? currentTable.header_row) !== currentTable.header_row ||
              (currentTable.kind === 'csv' && (config.delimiter ?? currentTable.delimiter) !== currentTable.delimiter) ? (
                <Button size="sm" className="mt-3" loading={reloading} onClick={() => void reload(config)}>
                  <RefreshCw className="size-3.5" aria-hidden /> Re-read file with these settings
                </Button>
              ) : null}
            </section>

            {/* Type values */}
            {typeHeader ? (
              <section>
                <h3 className="mb-1 text-sm font-semibold text-ink">Transaction types</h3>
                <p className="mb-3 text-xs text-ink-3">Values found in “{typeHeader}”. “Auto” lets Jacklyn recognise common words.</p>
                {typeValues.length === 0 ? (
                  <p className="text-sm text-ink-3">This column has too many distinct values to list.</p>
                ) : (
                  <div className="flex max-h-72 flex-col gap-2 overflow-y-auto pr-1">
                    {typeValues.map((raw) => (
                      <div key={raw} className="flex items-center gap-3">
                        <span className="min-w-0 flex-1 truncate rounded-lg bg-surface-2 px-2.5 py-1.5 text-xs font-medium text-ink" title={raw}>
                          {raw}
                        </span>
                        <div className="w-36 shrink-0">
                          <Select
                            className="h-8 text-xs"
                            aria-label={`Type for “${raw}”`}
                            value={config.type_map[raw] ?? ''}
                            onChange={(event) => setConfig(withTypeMapping(config, raw, (event.target.value || null) as TransactionType | null))}
                          >
                            <option value="">Auto</option>
                            {TRANSACTION_TYPES.map((type) => (
                              <option key={type} value={type}>
                                {TRANSACTION_TYPE_LABELS[type]}
                              </option>
                            ))}
                          </Select>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            ) : null}

            {/* Preset */}
            <section className="rounded-2xl bg-surface-2 p-4">
              <label className="flex items-start gap-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4 accent-[var(--accent)]"
                  checked={savePreset}
                  onChange={(event) => setSavePreset(event.target.checked)}
                />
                <span>
                  <span className="font-medium text-ink">Save as a preset</span>
                  <span className="block text-ink-3">Files with the same columns will map automatically next time.</span>
                </span>
              </label>
              {savePreset ? (
                <Input
                  className="mt-3"
                  value={presetName}
                  onChange={(event) => setPresetName(event.target.value)}
                  placeholder="e.g. Revolut Trading CSV"
                  aria-label="Preset name"
                />
              ) : null}
            </section>
          </div>
        </div>

        {error ? (
          <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
            {error}
          </Notice>
        ) : null}
      </div>
    </Modal>
  )
}
