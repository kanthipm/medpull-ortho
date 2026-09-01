import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

export default function Modal({
  title,
  onClose,
  children,
}: {
  title: string
  onClose: () => void
  children: ReactNode
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

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        aria-hidden
        className="absolute inset-0 animate-fadeIn bg-ink/35 backdrop-blur-[2px]"
        onClick={onClose}
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="relative w-full max-w-md animate-modalIn rounded-card border border-line bg-panel p-5 shadow-glass"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-[15px] font-semibold tracking-[-.01em] text-ink">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid h-8 w-8 cursor-pointer place-items-center rounded-btn border border-line bg-panel text-muted transition-colors duration-150 hover:bg-soft hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
          >
            <X size={16} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  )
}
