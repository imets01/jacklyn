import { CircleAlert, Info } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'

import { useAccounts, useCommitImport, usePreviewImport, useSaveMapping } from '../api/hooks'
import type { ColumnMappingConfig, ImportPreview, PreviewGroup, TablePreview } from '../api/types'
import { AccountFormModal, type AccountDefaults } from '../components/accounts/AccountFormModal'
import { ColumnMapperModal, type MapperApply } from '../components/importer/ColumnMapperModal'
import { DropZone } from '../components/importer/DropZone'
import { GroupedPreview } from '../components/importer/GroupedPreview'
import { IbkrSyncCard } from '../components/importer/IbkrSyncCard'
import { ImportHistory, SavedPresets, SupportedFormats } from '../components/importer/ImportSidebar'
import { PreviewPanel } from '../components/importer/PreviewPanel'
import { PageHeader } from '../components/layout/PageHeader'
import { Button, Card, Notice } from '../components/ui/primitives'
import { importedState } from '../lib/imported'
import { usePreferences } from '../lib/preferences-context'

function defaultSelection(preview: ImportPreview): Set<number> {
  return new Set(preview.transactions.flatMap((row, index) => (row.duplicate ? [] : [index])))
}

/** A new account for a preview group, prefilled from what the statement says (e.g. "Erste TBSZ 2024"). */
function accountDefaults(preview: ImportPreview | null, group: PreviewGroup | null): AccountDefaults {
  const hint = group?.account_hint ?? preview?.account_hint ?? null
  const broker = hint?.broker ?? preview?.detection?.broker ?? undefined
  return {
    name: group ? [broker?.split(' ')[0], hint?.name ?? group.label].filter(Boolean).join(' ') : undefined,
    broker,
    account_type: hint?.tbsz_year ? 'tbsz' : undefined,
    tbsz_year: hint?.tbsz_year ?? undefined,
    currency: hint?.currency ?? undefined,
    external_account_id: hint?.external_account_id ?? undefined,
  }
}

export function ImportPage() {
  const { baseCurrency } = usePreferences()
  const accounts = useAccounts(baseCurrency)
  const previewMutation = usePreviewImport()
  const commitMutation = useCommitImport()
  const saveMapping = useSaveMapping()

  const [files, setFiles] = useState<File[]>([])
  const [ignoredFiles, setIgnoredFiles] = useState(0)
  const [accountId, setAccountId] = useState<number | null>(null)
  const [groupAccounts, setGroupAccounts] = useState<Record<string, number | null>>({})
  const [mapping, setMapping] = useState<ColumnMappingConfig | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [table, setTable] = useState<TablePreview | null>(null)
  const [mapperOpen, setMapperOpen] = useState(false)
  // Bumped on every open so the mapper starts from the latest mapping/table (fresh component state).
  const [mapperSession, setMapperSession] = useState(0)
  const [mapperError, setMapperError] = useState<string | null>(null)
  // Open with null for the single-account preview, or with the group a new account is for.
  const [newAccountFor, setNewAccountFor] = useState<{ group: PreviewGroup | null } | null>(null)
  const [committingGroups, setCommittingGroups] = useState(false)
  const navigate = useNavigate()
  // The column mapper and per-row selection only apply to a single statement going into one account.
  const file = files.length === 1 ? files[0] : null
  const grouped = preview !== null && preview.groups.length > 0

  const runPreview = (
    nextFiles: File[],
    options: {
      accountId: number | null
      mapping: ColumnMappingConfig | null
      parserKey?: string
      groupAccounts?: Record<string, number | null>
    },
    onDone?: (result: ImportPreview) => void,
  ) => {
    previewMutation.mutate(
      {
        files: nextFiles,
        accountId: options.accountId,
        mapping: options.mapping,
        parserKey: options.parserKey ?? null,
        groupAccounts: options.groupAccounts,
      },
      {
        onSuccess: (result) => {
          setPreview(result)
          setSelected(defaultSelection(result))
          if (result.table) setTable(result.table)
          if (options.accountId === null && result.suggested_account_id) setAccountId(result.suggested_account_id)
          if (result.status === 'needs_mapping' && result.table) {
            setMapperError(null)
            setMapperSession((n) => n + 1)
            setMapperOpen(true)
          }
          onDone?.(result)
        },
      },
    )
  }

  const onFiles = (nextFiles: File[], ignored: number) => {
    setFiles(nextFiles)
    setIgnoredFiles(ignored)
    setMapping(null)
    setTable(null)
    setPreview(null)
    setGroupAccounts({})
    runPreview(nextFiles, { accountId: nextFiles.length === 1 ? accountId : null, mapping: null })
  }

  const onAccountChange = (id: number | null) => {
    setAccountId(id)
    // Duplicate flags depend on the target account: re-check them.
    if (file && preview?.status === 'parsed') runPreview([file], { accountId: id, mapping })
  }

  const onGroupAccountChange = (group: PreviewGroup, id: number | null) => {
    const next = { ...groupAccounts, [group.key]: id }
    setGroupAccounts(next)
    runPreview(files, { accountId: null, mapping: null, groupAccounts: next })
  }

  const onApplyMapping = ({ config, presetName }: MapperApply) => {
    if (!file) return
    setMapperError(null)
    const apply = () =>
      runPreview([file], { accountId, mapping: config }, (result) => {
        setMapping(config)
        if (result.status === 'parsed' && result.summary.total > 0) setMapperOpen(false)
        else setMapperError(result.message ?? result.errors[0]?.message ?? 'No transactions could be read with this mapping.')
      })
    const signature = table?.header_signature
    if (presetName && signature) {
      saveMapping.mutate({ name: presetName, header_signature: signature, config }, { onSuccess: apply, onError: (e) => setMapperError(e.message) })
    } else {
      apply()
    }
  }

  const reloadTable = async (config: ColumnMappingConfig): Promise<TablePreview | null> => {
    if (!file) return null
    const result = await previewMutation.mutateAsync({ files: [file], accountId, mapping: { ...config, columns: {} } })
    return result.table
  }

  const openMapper = () => {
    setMapperError(null)
    setMapperSession((n) => n + 1)
    setMapperOpen(true)
  }

  const commit = () => {
    if (!preview || !accountId) return
    const transactions = preview.transactions.filter((_, index) => selected.has(index)).map((row) => row.transaction)
    commitMutation.mutate(
      {
        account_id: accountId,
        transactions,
        parser_key: preview.detection?.parser_key ?? (preview.mapping_used ? `mapping:${preview.mapping_used.id}` : 'generic_csv'),
        filename: preview.filename,
        file_sha256: preview.file_sha256,
      },
      {
        onSuccess: (result) =>
          navigate(`/accounts/${accountId}`, {
            state: importedState(preview.filename, result.imported, result.duplicates),
          }),
      },
    )
  }

  /** One commit per account; each is idempotent, so a retry after a failure only adds what is missing. */
  const commitGroups = async () => {
    if (!preview) return
    const parts = preview.groups.flatMap((group) => {
      if (group.suggested_account_id === null) return []
      const rows = preview.transactions.filter((row) => row.group === group.key && !row.duplicate)
      return [{ group, accountId: group.suggested_account_id, transactions: rows.map((row) => row.transaction) }]
    })
    const names = new Map((accounts.data ?? []).map((account) => [account.id, account.name]))
    const results: { accountId: number; imported: number; duplicates: number }[] = []
    setCommittingGroups(true)
    try {
      for (const part of parts) {
        if (part.transactions.length === 0) {
          results.push({ accountId: part.accountId, imported: 0, duplicates: part.group.summary.duplicates })
          continue
        }
        const result = await commitMutation.mutateAsync({
          account_id: part.accountId,
          transactions: part.transactions,
          parser_key: part.group.parser_key,
          filename: preview.file_count > 1 ? `${preview.filename} · ${part.group.label}` : preview.filename,
          file_sha256: null,
        })
        results.push({ accountId: part.accountId, imported: result.imported, duplicates: result.duplicates + part.group.summary.duplicates })
      }
    } catch {
      return // shown below the preview; already committed accounts keep their rows, and a retry skips them
    } finally {
      setCommittingGroups(false)
    }
    const [target, ...others] = [...results].sort((a, b) => b.imported - a.imported)
    if (!target) return
    navigate(`/accounts/${target.accountId}`, {
      state: importedState(
        preview.filename,
        target.imported,
        target.duplicates,
        others.filter((other) => other.imported).map((other) => ({ name: names.get(other.accountId) ?? 'another account', imported: other.imported })),
      ),
    })
  }

  const clear = () => {
    setFiles([])
    setPreview(null)
    setMapping(null)
    setTable(null)
    setGroupAccounts({})
  }

  const accountList = accounts.data ?? []

  return (
    <>
      <PageHeader
        title="Import"
        subtitle="Statements from any broker become one clean ledger. Re-importing is always safe — duplicates are skipped."
        showMarket={false}
        showCurrency={false}
      />

      <div className="flex flex-col gap-5">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-4">
            <IbkrSyncCard accounts={accountList} />
            <DropZone onFiles={onFiles} busy={previewMutation.isPending && !mapperOpen && !grouped} />
            {ignoredFiles > 0 ? (
              <Notice tone="neutral" icon={<Info className="size-4" />}>
                {ignoredFiles} file{ignoredFiles === 1 ? ' was' : 's were'} left out of the folder: only CSV, Excel and XML
                files are read.
              </Notice>
            ) : null}
            {previewMutation.error && !mapperOpen ? (
              <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
                {previewMutation.error.message}
              </Notice>
            ) : null}
            {preview && preview.status === 'unsupported' ? (
              <Notice icon={<CircleAlert className="size-4" />}>{preview.message}</Notice>
            ) : null}
            {preview && preview.status === 'needs_mapping' && !mapperOpen && table ? (
              <Card className="flex flex-wrap items-center justify-between gap-3 px-6 py-5">
                <div>
                  <p className="font-semibold text-ink">{preview.filename}</p>
                  <p className="text-sm text-ink-3">{preview.message}</p>
                </div>
                <Button variant="primary" onClick={openMapper}>
                  Map columns
                </Button>
              </Card>
            ) : null}
          </div>
          <div className="flex flex-col gap-4">
            <SupportedFormats />
            <SavedPresets />
          </div>
        </div>

        {preview && grouped ? (
          <GroupedPreview
            preview={preview}
            accounts={accountList}
            onGroupAccountChange={onGroupAccountChange}
            onNewAccount={(group) => setNewAccountFor({ group })}
            onCommit={() => void commitGroups()}
            committing={committingGroups}
            busy={previewMutation.isPending}
            onClear={clear}
          />
        ) : preview && preview.status === 'parsed' ? (
          <PreviewPanel
            preview={preview}
            accounts={accountList}
            accountId={accountId}
            onAccountChange={onAccountChange}
            onNewAccount={() => setNewAccountFor({ group: null })}
            selected={selected}
            onSelectedChange={setSelected}
            onCommit={commit}
            committing={commitMutation.isPending}
            onOpenMapper={table ? openMapper : null}
            onClear={clear}
          />
        ) : null}
        {commitMutation.error ? (
          <Notice tone="negative" icon={<CircleAlert className="size-4" />}>
            {commitMutation.error.message}
          </Notice>
        ) : null}

        <ImportHistory accounts={accountList} />
      </div>

      {table && file ? (
        <ColumnMapperModal
          key={mapperSession}
          open={mapperOpen}
          onClose={() => setMapperOpen(false)}
          table={table}
          initial={mapping ?? table.suggested}
          filename={file.name}
          applying={previewMutation.isPending || saveMapping.isPending}
          error={mapperError}
          onApply={onApplyMapping}
          onReloadTable={reloadTable}
        />
      ) : null}
      <AccountFormModal
        open={newAccountFor !== null}
        onClose={() => setNewAccountFor(null)}
        defaults={accountDefaults(preview, newAccountFor?.group ?? null)}
        onSaved={(account) => {
          const group = newAccountFor?.group
          if (group) onGroupAccountChange(group, account.id)
          else onAccountChange(account.id)
        }}
      />
    </>
  )
}
