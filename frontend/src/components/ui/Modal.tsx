import { clsx } from 'clsx'
import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'

/** Accessible dialog on top of the native <dialog> element (focus trap + Esc for free). */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: {
  open: boolean
  onClose: () => void
  title: string
  description?: ReactNode
  children: ReactNode
  footer?: ReactNode
  size?: 'md' | 'xl'
}) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClick={(event) => {
        if (event.target === ref.current) onClose()
      }}
      className={clsx(
        'm-auto max-h-[min(92vh,900px)] w-[calc(100vw-2rem)] overflow-hidden rounded-3xl border border-line bg-surface p-0 text-ink shadow-[var(--shadow-pop)] backdrop:bg-black/40 backdrop:backdrop-blur-[2px]',
        size === 'md' ? 'max-w-lg' : 'max-w-6xl',
      )}
    >
      {open ? (
        <div className="flex max-h-[min(92vh,900px)] flex-col">
          <header className="flex items-start justify-between gap-4 border-b border-line px-6 py-5">
            <div>
              <h2 className="text-lg font-semibold">{title}</h2>
              {description ? <div className="mt-1 text-sm text-ink-3">{description}</div> : null}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="grid size-8 place-items-center rounded-full text-ink-3 hover:bg-surface-2 hover:text-ink"
              aria-label="Close"
            >
              <X className="size-4" />
            </button>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">{children}</div>
          {footer ? <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line px-6 py-4">{footer}</footer> : null}
        </div>
      ) : null}
    </dialog>
  )
}
