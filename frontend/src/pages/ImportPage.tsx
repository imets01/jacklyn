import { CircleAlert, CircleCheck } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router'

import { useAccounts, useCommitImport, usePreviewImport, useSaveMapping } from '../api/hooks'
import type { ColumnMappingConfig, ImportCommitResult, ImportPreview, TablePreview } from '../api/types'
import { NewAccountModal } from '../components/accounts/NewAccountModal'
import { ColumnMapperModal, type MapperApply } from '../components/importer/ColumnMapperModal'
import { DropZone } from '../components/importer/DropZone'
import { ImportHistory, SavedPresets, SupportedFormats } from '../components/importer/ImportSidebar'
import { PreviewPanel } from '../components/importer/PreviewPanel'
import { PageHeader } from '../components/layout/PageHeader'
import { Button, Card, Notice } from '../components/ui/primitives'
import { usePreferences } from '../lib/preferences-context'

function defaultSelection(preview: ImportPreview): Set<number> {
  return new Set(preview.transactions.flatMap((row, index) => (row.duplicate ? [] : [index])))
}

export function ImportPage() {
  const { baseCurrency } = usePreferences()
  const accounts = useAccounts(baseCurrency)
  const previewMutation = usePreviewImport()
  const commitMutation = useCommitImport()
  const saveMapping = useSaveMapping()

  const [file, setFile] = useState<File | null>(null)
  const [accountId, setAccountId] = useState<number | null>(null)
  const [mapping, setMapping] = useState<ColumnMappingConfig | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [table, setTable] = useState<TablePreview | null>(null)
  const [mapperOpen, setMapperOpen] = useState(false)
  // Bumped on every open so the mapper starts from the latest mapping/table (fresh component state).
  const [mapperSession, setMapperSession] = useState(0)
  const [mapperError, setMapperError] = useState<string | null>(null)
  const [newAccountOpen, setNewAccountOpen] = useState(false)
  const [committed, setCommitted] = useState<{ result: ImportCommitResult; accountId: number } | null>(null)

  const runPreview = (
    nextFile: File,
    options: { accountId: number | null; mapping: ColumnMappingConfig | null; parserKey?: string },
    onDone?: (result: ImportPreview) => void,
  ) => {
    previewMutation.mutate(
      { file: nextFile, accountId: options.accountId, mapping: options.mapping, parserKey: options.parserKey ?? null },
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

  const onFile = (nextFile: File) => {
    setFile(nextFile)
    setMapping(null)
    setTable(null)
    setCommitted(null)
    setPreview(null)
    runPreview(nextFile, { accountId, mapping: null })
  }

  const onAccountChange = (id: number | null) => {
    setAccountId(id)
    // Duplicate flags depend on the target account: re-check them.
    if (file && preview?.status === 'parsed') runPreview(file, { accountId: id, mapping })
  }

  const onApplyMapping = ({ config, presetName }: MapperApply) => {
    if (!file) return
    setMapperError(null)
    const apply = () =>
      runPreview(file, { accountId, mapping: config }, (result) => {
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
    const result = await previewMutation.mutateAsync({ file, accountId, mapping: { ...config, columns: {} } })
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
        onSuccess: (result) => {
          setCommitted({ result, accountId })
          setPreview(null)
          setFile(null)
        },
      },
    )
  }

  const clear = () => {
    setFile(null)
    setPreview(null)
    setMapping(null)
    setTable(null)
  }

  const accountList = accounts.data ?? []
  const committedAccount = committed ? accountList.find((a) => a.id === committed.accountId) : undefined

  return (
    <>
      <PageHeader
        title="Import"
        subtitle="Statements from any broker become one clean ledger. Re-importing is always safe — duplicates are skipped."
        showMarket={false}
      />

      <div className="flex flex-col gap-5">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-4">
            {committed ? (
              <Card className="flex flex-wrap items-center gap-4 px-6 py-5">
                <div className="grid size-10 place-items-center rounded-2xl bg-positive-soft text-positive">
                  <CircleCheck className="size-5" aria-hidden />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-ink">
                    Imported {committed.result.imported} transaction{committed.result.imported === 1 ? '' : 's'}
                    {committedAccount ? ` into ${committedAccount.name}` : ''}
                  </p>
                  <p className="text-sm text-ink-3">
                    {committed.result.duplicates
                      ? `${committed.result.duplicates} already recorded and skipped.`
                      : 'No duplicates found.'}
                  </p>
                </div>
                <Link
                  to={`/accounts/${committed.accountId}`}
                  className="inline-flex h-10 items-center rounded-full border border-line px-4 text-sm font-medium hover:bg-surface-2"
                >
                  View account
                </Link>
              </Card>
            ) : null}
            <DropZone onFile={onFile} busy={previewMutation.isPending && !mapperOpen} />
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

        {preview && preview.status === 'parsed' ? (
          <PreviewPanel
            preview={preview}
            accounts={accountList}
            accountId={accountId}
            onAccountChange={onAccountChange}
            onNewAccount={() => setNewAccountOpen(true)}
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
      <NewAccountModal
        open={newAccountOpen}
        onClose={() => setNewAccountOpen(false)}
        defaultBroker={preview?.account_hint?.broker ?? preview?.detection?.broker ?? null}
        onCreated={(account) => onAccountChange(account.id)}
      />
    </>
  )
}
