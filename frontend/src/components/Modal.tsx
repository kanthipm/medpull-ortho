import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

/** Dialog. The backdrop is the `.scrim` RECIPE, not a utility pair: it carries
 *  the non-flipping black at 0.62 light / 0.70 dark, the 2px blur (the console's
 *  only blurred surface) and the three degradation blocks —
 *  prefers-reduced-transparency, prefers-contrast and forced-colors — plus the
 *  [data-glass="off"] escape hatch. The old pair — --ink at 35% plus a bare
 *  2px blur utility — carried none of that and was a real defect: --ink inverts to #FFFFFF in dark, so the
 *  backdrop BRIGHTENED the page behind the dialog, at 0.35 rather than 0.62.
 *  The panel is `.overlay` — modal/popover/toast are the only surfaces allowed
 *  the ambient shadow, and it brings dark's own hairline and the forced-colors
 *  border with it. */
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
      <div aria-hidden className="scrim absolute inset-0 animate-fadeIn" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="overlay relative w-full max-w-md animate-modalIn p-6"
      >
        <div className="mb-block flex items-center justify-between">
          <h2 className="text-subhead font-normal text-ink">{title}</h2>
          {/* --body, not --muted: dark's overlay panel is --n-700, where --muted
              is only 3.655:1. --body is 4.955:1 on it and 7.222:1 on light. */}
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="grid h-10 w-10 cursor-pointer place-items-center rounded-control text-body transition-colors duration-150 hover:bg-soft hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>,
    document.body,
  )
}
