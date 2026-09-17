import { X } from 'lucide-react'
import { useEffect, useId, useRef, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { OVERLAY_SCOPE } from './Menu'

export type ModalSize = 'sm' | 'md' | 'lg' | 'xl' | '2xl'

const WIDTH: Record<ModalSize, string> = {
  sm: 'max-w-sm', // 384
  md: 'max-w-md', // 448 — the old fixed Modal
  lg: 'max-w-lg', // 512
  xl: 'max-w-2xl', // 672 — PlanModal's 'xl' kept its 672px (R16)
  '2xl': 'max-w-3xl', // 768
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Dialog — a floating sheet in the top layer.
 *
 *  SURFACE. `.overlay`: 20px corners, opaque overlay panel, the soft layered
 *  --shadow-overlay; dark adds its 1px --overlay-border (the dark overlay
 *  panel is only 1.584:1 on its scrim). Secondary text inside is --body
 *  (dark --muted is 3.655:1 on the overlay panel; --body 4.955).
 *
 *  BACKDROP. The `.scrim` recipe: non-flipping black at .62 light / .70 dark
 *  with a 2px blur and its reduced-transparency / contrast / forced-colors /
 *  kill-switch degradations. Never --ink (it inverts to white in dark).
 *
 *  LAYOUT. Header (title 20/600 ink, optional eyebrow above it, a 32px close
 *  icon button), a scrolling body, and an optional pinned `footer` (a right-
 *  aligned button row; no rule). Height is capped at min(88vh, 860px).
 *
 *  BEHAVIOUR. Escape and a scrim click close it; focus moves into the dialog
 *  (first field, else first button after the close button), Tab is trapped,
 *  focus returns to the opener on close, and the page behind stops scrolling.
 *  Enter is a short rise (opacity + 8px) on the spring; Reduce Motion gets an
 *  opacity crossfade only (index.css). */
export default function Modal({
  title,
  eyebrow,
  onClose,
  children,
  footer,
  size = 'md',
  description,
  className = '',
  bodyClassName = '',
  initialFocus,
}: {
  title: string
  eyebrow?: ReactNode
  onClose: () => void
  children: ReactNode
  /** Pinned action row, e.g. <><button className="btn-plain">Cancel</button>
   *  <button className="btn-filled">Send</button></> */
  footer?: ReactNode
  size?: ModalSize
  /** One line of --body text under the title (aria-describedby). */
  description?: ReactNode
  className?: string
  bodyClassName?: string
  /** CSS selector inside the dialog to focus first. */
  initialFocus?: string
}) {
  const panelRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  const titleId = useId()
  const descId = useId()

  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    const panel = panelRef.current

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // A top-layer menu inside the dialog closes first.
        if (e.defaultPrevented) return
        onCloseRef.current()
        return
      }
      if (e.key !== 'Tab' || !panel) return
      const els = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      )
      if (els.length === 0) {
        e.preventDefault()
        panel.focus()
        return
      }
      const first = els[0]
      const last = els[els.length - 1]
      if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)

    const target =
      (initialFocus && panel?.querySelector<HTMLElement>(initialFocus)) ||
      panel?.querySelector<HTMLElement>('input:not([type="hidden"]), textarea, select') ||
      panel?.querySelector<HTMLElement>('[data-modal-body] button, [data-modal-footer] button') ||
      panel?.querySelector<HTMLElement>('button')
    ;(target ?? panel)?.focus({ preventScroll: true })

    const { overflow } = document.body.style
    document.body.style.overflow = 'hidden'

    return () => {
      window.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = overflow
      if (opener && document.contains(opener)) opener.focus({ preventScroll: true })
    }
    // Run once per mount; initialFocus is read on open only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-3 sm:items-center sm:p-6">
      <div aria-hidden className="scrim absolute inset-0 animate-fadeIn" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        tabIndex={-1}
        className={`overlay ${OVERLAY_SCOPE} relative flex max-h-[min(88vh,860px)] w-full ${WIDTH[size]} animate-modalIn flex-col outline-none ${className}`}
      >
        <div className="flex items-start justify-between gap-3 px-6 pb-3 pt-5">
          <div className="min-w-0">
            {eyebrow}
            <h2 id={titleId} className="text-subhead font-semibold text-ink">
              {title}
            </h2>
            {description && (
              <p id={descId} className="mt-1 text-copy text-secondary">
                {description}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="btn-icon btn-sm -mr-2 shrink-0"
          >
            <X aria-hidden />
          </button>
        </div>
        <div
          data-modal-body
          className={`min-h-0 flex-1 overflow-y-auto px-6 ${footer ? 'pb-2' : 'pb-6'} ${bodyClassName}`}
        >
          {children}
        </div>
        {footer && (
          <div data-modal-footer className="flex flex-wrap items-center justify-end gap-2 px-6 pb-5 pt-3 [&>*:only-child]:flex-1">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  )
}
