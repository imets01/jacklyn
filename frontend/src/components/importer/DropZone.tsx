import { clsx } from 'clsx'
import { CloudUpload } from 'lucide-react'
import { useRef, useState, type DragEvent } from 'react'

const ACCEPT = '.csv,.tsv,.txt,.xlsx,.xls,.xml'

export function DropZone({ onFile, busy }: { onFile: (file: File) => void; busy: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files[0]
    if (file) onFile(file)
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Upload a statement: drop a file here or press Enter to browse"
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
      onDrop={onDrop}
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
        <p className="font-semibold text-ink">{busy ? 'Reading your statement…' : 'Drop a statement here'}</p>
        <p className="mt-1 text-sm text-ink-3">
          or <span className="font-medium text-accent">browse files</span> · CSV, Excel (.xlsx / .xls), IBKR Flex XML
        </p>
      </div>
      <input
        ref={input}
        type="file"
        accept={ACCEPT}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) onFile(file)
          event.target.value = ''
        }}
      />
    </div>
  )
}
