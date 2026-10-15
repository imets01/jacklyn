import { FileSpreadsheet, UploadCloud, X } from "lucide-react";
import { useRef, useState } from "react";
import type { DragEvent } from "react";

import { cx } from "../ui/primitives";

const ACCEPT = ".csv,.txt,.tsv,text/csv,text/plain";

export function DropZone({
  file,
  onFile,
  onClear,
  maxBytes,
  disabled,
}: {
  file: File | null;
  onFile: (f: File) => void;
  onClear: () => void;
  maxBytes: number;
  disabled?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string>();

  function accept(f: File | undefined) {
    if (!f) return;
    if (f.size > maxBytes) {
      setError(`That file is ${(f.size / 1_048_576).toFixed(1)} MB; the limit is ${maxBytes / 1_048_576} MB.`);
      return;
    }
    setError(undefined);
    onFile(f);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (!disabled) accept(e.dataTransfer.files[0]);
  }

  if (file) {
    return (
      <div className="flex items-center gap-4 rounded-2xl border border-line bg-surface-2/60 p-4">
        <div className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand-strong">
          <FileSpreadsheet className="size-6" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-medium text-ink">{file.name}</p>
          <p className="text-xs text-muted">{(file.size / 1024).toFixed(1)} KB</p>
        </div>
        <button
          type="button"
          onClick={onClear}
          aria-label="Remove file"
          className="rounded-full p-2 text-muted hover:bg-surface-3 hover:text-ink"
        >
          <X className="size-5" aria-hidden />
        </button>
      </div>
    );
  }

  return (
    <div>
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cx(
          "flex w-full flex-col items-center justify-center gap-3 rounded-card border-2 border-dashed px-6 py-14 text-center transition-colors",
          "disabled:cursor-not-allowed disabled:opacity-60",
          dragging
            ? "border-brand bg-brand-soft/60"
            : "border-line bg-surface-2/40 hover:border-vein hover:bg-surface-2",
        )}
      >
        <div
          className={cx(
            "grid size-14 place-items-center rounded-full transition-transform",
            dragging ? "scale-110 bg-brand text-brand-contrast" : "bg-brand-soft text-brand-strong",
          )}
        >
          <UploadCloud className="size-7" aria-hidden />
        </div>
        <div>
          <p className="font-semibold text-ink">
            {dragging ? "Drop it here" : "Drag & drop a broker export"}
          </p>
          <p className="mt-1 text-sm text-muted">
            or <span className="font-medium text-brand">browse</span> · CSV from IBKR, Lightyear,
            Erste NetBroker or any bank
          </p>
        </div>
      </button>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          accept(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {error && <p className="mt-2 text-sm text-negative">{error}</p>}
    </div>
  );
}
