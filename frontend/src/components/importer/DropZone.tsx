import { clsx } from 'clsx'
import { CloudUpload } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xls,.xml'
// Inside a folder, only statement-like files are sent (a folder of downloads may hold PDFs and images too).
const STATEMENT_FILE = /\.(csv|tsv|txt|xlsx|xls|xml)$/i

function readEntries(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise((resolve, reject) => {
    const entries: FileSystemEntry[] = []
    const next = () =>
      reader.readEntries((batch) => {
        if (batch.length === 0) resolve(entries)
        else {
          entries.push(...batch)
          next() // directories hand out their entries in batches
        }
      }, reject)
    next()
  })
}

async function filesIn(entry: FileSystemEntry): Promise<{ files: File[]; ignored: number }> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject))
    return { files: [file], ignored: 0 }
  }
  if (!entry.isDirectory) return { files: [], ignored: 0 }
  const children = await readEntries((entry as FileSystemDirectoryEntry).createReader())
  const nested = await Promise.all(children.map(filesIn))
  const files = nested.flatMap((part) => part.files)
  const kept = files.filter((file) => STATEMENT_FILE.test(file.name))
  return { files: kept, ignored: files.length - kept.length + nested.reduce((sum, part) => sum + part.ignored, 0) }
}

const byName = (a: File, b: File) => a.name.localeCompare(b.name, undefined, { numeric: true })

/** One statement, several, or a whole folder of them (dropped, or picked with "choose a folder"). */
export function DropZone({ onFiles, busy }: { onFiles: (files: File[], ignored: number) => void; busy: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const onDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    // Entries must be taken synchronously: the drop's item list is emptied after the first await.
    const entries = Array.from(event.dataTransfer.items)
      .map((item) => item.webkitGetAsEntry())
      .filter((entry): entry is FileSystemEntry => entry !== null)
    const plainFiles = Array.from(event.dataTransfer.files)
    if (entries.length === 0) {
      if (plainFiles.length) onFiles(plainFiles.sort(byName), 0)
      return
    }
    const parts = await Promise.all(entries.map(filesIn))
    const files = parts.flatMap((part) => part.files).sort(byName)
    if (files.length) onFiles(files, parts.reduce((sum, part) => sum + part.ignored, 0))
  }

  const fromInput = (list: FileList | null, folder: boolean) => {
    const files = Array.from(list ?? [])
    const kept = folder ? files.filter((file) => STATEMENT_FILE.test(file.name)) : files
    if (kept.length) onFiles(kept.sort(byName), files.length - kept.length)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload statements: drop files or a folder here, or press Enter to browse"
      aria-busy={busy}
      onClick={() => input.current?.click()}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          input.current?.click()
        }
      }}
      onDragOver={(event) => {
        event.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => void onDrop(event)}
      className={clsx(
        'flex cursor-pointer flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed px-6 py-12 text-center transition-colors',
        dragging ? 'border-accent bg-accent-soft' : 'border-line-strong bg-surface-2/50 hover:border-accent/60 hover:bg-accent-soft/40',
        busy && 'pointer-events-none opacity-60',
      )}
    >
      <div className="grid size-14 place-items-center rounded-2xl bg-surface text-accent shadow-[var(--shadow-card)]">
        <CloudUpload className={clsx('size-6', busy && 'animate-pulse')} aria-hidden />
      </div>
      <div>
        <p className="font-semibold text-ink">{busy ? 'Reading your statements…' : 'Drop statements or a folder here'}</p>
        <p className="mt-1 text-sm text-ink-3">
          or <span className="font-medium text-accent">browse files</span> ·{' '}
          <button
            type="button"
            className="font-medium text-accent hover:underline"
            onClick={(event) => {
              event.stopPropagation()
              folderInput.current?.click()
            }}
          >
            choose a folder
          </button>{' '}
          · CSV, Excel (.xlsx / .xls), IBKR Flex XML
        </p>
      </div>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        multiple
        className="hidden"
        onChange={(event) => {
          fromInput(event.target.files, false)
          event.target.value = ''
        }}
      />
      <input
        // React has no typed prop for folder picking; the attribute is standard in every current browser.
        ref={(element) => {
          folderInput.current = element
          element?.setAttribute('webkitdirectory', '')
        }}
        type="file"
        multiple
        className="hidden"
        onClick={(event) => event.stopPropagation()}
        onChange={(event) => {
          fromInput(event.target.files, true)
          event.target.value = ''
        }}
      />
    </div>
  )
}
