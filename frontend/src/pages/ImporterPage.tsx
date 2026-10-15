import { AlertTriangle, CheckCircle2, FileCog, Sparkles, Table2 } from "lucide-react";
import { useEffect, useState } from "react";

import {
  ColumnMapperModal,
  emptyMapping,
} from "@/components/importer/ColumnMapperModal";
import { DropZone } from "@/components/importer/DropZone";
import { ImportHistory } from "@/components/importer/ImportHistory";
import { PreviewTable } from "@/components/importer/PreviewTable";
import { inputClass } from "@/components/dashboard/AddAccountModal";
import { Badge, Button, Card, CardHeader, ErrorState, Skeleton } from "@/components/ui/primitives";
import { api } from "@/lib/api";
import type { ColumnMapping, ImportCommit, ImportPreview } from "@/lib/types";
import { useAsync } from "@/lib/useAsync";

export function ImporterPage() {
  const setup = useAsync(
    () => Promise.all([api.accounts(), api.importOptions(), api.mappings()]),
    [],
  );
  const logs = useAsync(() => api.importLogs(), []);

  const [accountId, setAccountId] = useState<number | null>(null);
  const [parser, setParser] = useState("auto");
  const [file, setFile] = useState<File | null>(null);
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [mappingId, setMappingId] = useState<number | null>(null);
  const [saveAs, setSaveAs] = useState("");
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string>();
  const [result, setResult] = useState<ImportCommit | null>(null);
  const [mapperOpen, setMapperOpen] = useState(false);

  const [accounts, options, savedMappings] = setup.data ?? [[], null, []];

  useEffect(() => {
    if (accountId == null && accounts.length > 0) setAccountId(accounts[0]!.id);
  }, [accounts, accountId]);

  // Re-run the preview whenever the inputs that shape it change.
  useEffect(() => {
    if (!file || accountId == null) return;
    let active = true;
    setPreviewing(true);
    setError(undefined);
    api
      .preview({ file, accountId, parser, mapping, mappingId })
      .then((p) => {
        if (!active) return;
        setPreview(p);
        if (p.needs_mapping && !mapping) setMapperOpen(true);
      })
      .catch((e: unknown) => {
        if (!active) return;
        setPreview(null);
        setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => active && setPreviewing(false));
    return () => {
      active = false;
    };
  }, [file, accountId, parser, mapping, mappingId]);

  function reset() {
    setFile(null);
    setPreview(null);
    setMapping(null);
    setMappingId(null);
    setSaveAs("");
    setError(undefined);
  }

  async function commit() {
    if (!file || accountId == null || !preview) return;
    setCommitting(true);
    setError(undefined);
    try {
      const res = await api.commit({
        file,
        accountId,
        parser,
        mapping,
        mappingId,
        expectedSha256: preview.file_sha256,
        saveMappingAs: mapping ? saveAs : null,
      });
      setResult(res);
      reset();
      logs.reload();
      setup.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCommitting(false);
    }
  }

  if (setup.error) return <ErrorState error={setup.error} onRetry={setup.reload} />;
  if (!setup.data || !options) {
    return (
      <div className="grid grid-cols-1 gap-6">
        <Skeleton className="h-16 w-72" />
        <Skeleton className="h-80" />
      </div>
    );
  }

  const selectedAccount = accounts.find((a) => a.id === accountId);
  const canCommit = preview && !preview.needs_mapping && preview.counts.new > 0 && !previewing;

  return (
    <div className="grid grid-cols-1 gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Smart Importer</h1>
        <p className="mt-1 text-sm text-muted">
          Drop a statement. Jacklyn detects the broker, maps the columns and skips anything already
          imported.
        </p>
      </div>

      {result && (
        <div
          role="status"
          className="flex items-start gap-3 rounded-card border border-positive/30 bg-positive-soft p-4 text-sm"
        >
          <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-positive" aria-hidden />
          <div className="flex-1">
            <p className="font-semibold text-ink">
              Imported {result.rows_imported} transactions
            </p>
            <p className="text-muted">
              {result.rows_duplicate} duplicates skipped · {result.rows_failed} rows failed ·{" "}
              {result.assets_created} new assets
              {result.mapping_id && " · mapping saved"}
            </p>
          </div>
          <Button variant="ghost" onClick={() => setResult(null)}>
            Dismiss
          </Button>
        </div>
      )}

      <Card>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Import into</span>
            <select
              className={inputClass}
              value={accountId ?? ""}
              onChange={(e) => setAccountId(Number(e.target.value))}
            >
              {accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                  {a.tbsz_year ? ` (TBSZ ${a.tbsz_year})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="grid gap-1.5 text-sm">
            <span className="font-medium">Format</span>
            <select
              className={inputClass}
              value={mappingId != null ? `m:${mappingId}` : parser}
              onChange={(e) => {
                const v = e.target.value;
                setMapping(null);
                if (v.startsWith("m:")) {
                  setMappingId(Number(v.slice(2)));
                  setParser("auto");
                } else {
                  setMappingId(null);
                  setParser(v);
                }
              }}
            >
              <option value="auto">✨ Auto-detect</option>
              <optgroup label="Brokers">
                {options.parsers
                  .filter((p) => p.key !== "generic")
                  .map((p) => (
                    <option key={p.key} value={p.key}>
                      {p.label}
                      {p.is_stub ? " (beta)" : ""}
                    </option>
                  ))}
              </optgroup>
              {savedMappings.length > 0 && (
                <optgroup label="Saved mappings">
                  {savedMappings.map((m) => (
                    <option key={m.id} value={`m:${m.id}`}>
                      {m.name}
                    </option>
                  ))}
                </optgroup>
              )}
              <option value="generic">Custom CSV (map columns)</option>
            </select>
          </label>
        </div>

        <div className="mt-5">
          <DropZone
            file={file}
            onFile={(f) => {
              setResult(null);
              setMapping(null);
              setFile(f);
            }}
            onClear={reset}
            maxBytes={options.max_upload_bytes}
            disabled={!selectedAccount}
          />
        </div>

        {error && (
          <p className="mt-4 flex items-start gap-2 rounded-2xl bg-negative-soft p-3 text-sm text-negative">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
            {error}
          </p>
        )}
      </Card>

      {file && (previewing || preview) && (
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Table2 className="size-4 text-brand" aria-hidden /> Preview
              </span>
            }
            subtitle={
              preview?.needs_mapping
                ? "We couldn't recognise this layout. Map its columns to continue."
                : preview && (
                    <span className="flex flex-wrap items-center gap-2">
                      <Sparkles className="size-3.5 text-brand" aria-hidden />
                      {mapping
                        ? "Custom column mapping"
                        : preview.mapping_id
                          ? `Saved mapping: ${savedMappings.find((m) => m.id === preview.mapping_id)?.name ?? "custom"}`
                          : `${preview.parser_label}${parser === "auto" ? ` · ${Math.round(preview.confidence * 100)}% match` : ""}`}
                      {preview.is_stub && <Badge tone="warning">beta parser</Badge>}
                    </span>
                  )
            }
            action={
              preview && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    onClick={() => setMapperOpen(true)}
                    icon={<FileCog className="size-4" aria-hidden />}
                  >
                    {mapping || preview.needs_mapping ? "Edit mapping" : "Map columns manually"}
                  </Button>
                  <Button
                    variant="primary"
                    loading={committing}
                    disabled={!canCommit}
                    onClick={commit}
                  >
                    Import {preview.counts.new} transactions
                  </Button>
                </div>
              )
            }
          />

          {preview?.warnings.map((w) => (
            <p
              key={w}
              className="mb-3 flex items-start gap-2 rounded-2xl bg-warning-soft p-3 text-sm text-warning"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />
              {w}
            </p>
          ))}

          {previewing && !preview ? (
            <Skeleton className="h-64" />
          ) : preview && !preview.needs_mapping ? (
            <div className={previewing ? "opacity-60" : undefined}>
              <PreviewTable key={`${preview.file_sha256}-${preview.counts.total}`} preview={preview} />
            </div>
          ) : (
            preview && (
              <div className="flex flex-col items-center gap-3 rounded-2xl bg-surface-2/60 py-10 text-center">
                <FileCog className="size-7 text-brand" aria-hidden />
                <p className="max-w-sm text-sm text-muted">
                  Found {preview.headers.length} columns. Tell Jacklyn which is the date, type and
                  amount — it remembers the layout for next time.
                </p>
                <Button variant="primary" onClick={() => setMapperOpen(true)}>
                  Open column mapper
                </Button>
              </div>
            )
          )}
        </Card>
      )}

      {preview && mapperOpen && (
        <ColumnMapperModal
          open={mapperOpen}
          preview={preview}
          fields={options.fields}
          transactionTypes={options.transaction_types}
          initial={mapping ?? emptyMapping(preview)}
          saveAs={saveAs || preview.filename.replace(/\.[^.]+$/, "")}
          onClose={() => setMapperOpen(false)}
          onApply={(m, name) => {
            setMapping(m);
            setMappingId(null);
            setSaveAs(name);
            setMapperOpen(false);
          }}
        />
      )}

      {logs.data && <ImportHistory logs={logs.data} accounts={accounts} />}
    </div>
  );
}
