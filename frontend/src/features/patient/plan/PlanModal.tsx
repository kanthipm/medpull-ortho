import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/** The shared `Modal` is a fixed `max-w-md` panel with no size or footer
 *  slot, and `components/*` is not this track's to edit. The builder needs
 *  a wide, scrolling body with a pinned footer, so this mirrors `Modal`'s
 *  structure, tokens and motion and adds exactly those two things. */
export default function PlanModal({
  title,
  eyebrow,
  onClose,
  children,
  footer,
  size = 'md',
}: {
  title: string
  eyebrow?: ReactNode
  onClose: () => void
  children: ReactNode
  footer?: ReactNode
  size?: 'md' | 'lg' | 'xl'
}) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    panelRef.current?.querySelector<HTMLElement>('input, textarea, button')?.focus()
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const width = size === 'xl' ? 'max-w-2xl' : size === 'lg' ? 'max-w-lg' : 'max-w-md'

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        aria-hidden
        className="scrim absolute inset-0 animate-fadeIn"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`overlay relative flex max-h-[min(88vh,860px)] w-full ${width} animate-modalIn flex-col`}
      >
        <div className="flex items-start justify-between gap-3 px-5 pb-3 pt-5">
          <div className="min-w-0">
            {eyebrow}
            <h2 className="text-copy-lg font-medium text-ink">{title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid h-8 w-8 shrink-0 cursor-pointer place-items-center rounded-control text-muted transition-colors duration-150 hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
          >
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 pb-5">{children}</div>
        {footer && (
          <div className="border-t border-line px-5 py-3.5">{footer}</div>
        )}
      </div>
    </div>,
    document.body,
  )
}
