import { MoreHorizontal } from 'lucide-react'
import {
  cloneElement,
  isValidElement,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactElement,
  type ReactNode,
  type RefObject,
} from 'react'
import { createPortal } from 'react-dom'
import { FLOATING_GAP, useFloatingPosition, type Placement } from './floating'

/* ════════════════════════════════════════════════════════════════════════
   TOP-LAYER FLOATING PRIMITIVES (R5)

   Every menu, popover and tooltip opened from inside a card renders here:
   portalled to document.body and positioned `fixed` against its anchor, so
   a clipped `.card-group` / `.clip-surface` can never cut it off.

   Secondary text inside an overlay is --body, never --muted: dark's overlay
   panel is --n-700 #2A333D, where --muted is 3.655:1 (fails) and --body is
   4.955:1 (light: 7.222). OVERLAY_SCOPE flips `.meta` / `text-secondary`
   accordingly.
   ════════════════════════════════════════════════════════════════════════ */

export const OVERLAY_SCOPE = '[--text-secondary:var(--body)]'

export type { Placement }

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** A floating panel in the top layer.
 *
 *    const anchorRef = useRef<HTMLButtonElement>(null)
 *    <button ref={anchorRef} aria-expanded={open} aria-controls={id} …/>
 *    <Popover open={open} onClose={() => setOpen(false)} anchorRef={anchorRef}
 *             id={id} aria-label="Edit phone">…</Popover>
 *
 *  Closes on Escape (focus returns to the anchor) and on a pointer-down
 *  outside both the panel and the anchor. Moves focus into the panel on open
 *  unless `autoFocus` is false. */
export function Popover({
  open,
  onClose,
  anchorRef,
  children,
  placement = 'bottom-end',
  offset = FLOATING_GAP,
  variant = 'popover',
  role = 'dialog',
  id,
  className = '',
  style,
  autoFocus = true,
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledby,
  onKeyDown,
}: {
  open: boolean
  onClose: () => void
  anchorRef: RefObject<HTMLElement | null>
  children: ReactNode
  placement?: Placement
  offset?: number
  /** `popover` — 20px corners, 8px padding-less panel (set your own padding).
   *  `menu` — 12px corners, 6px padding. */
  variant?: 'popover' | 'menu'
  role?: 'dialog' | 'menu' | 'listbox' | 'tooltip'
  id?: string
  className?: string
  style?: CSSProperties
  autoFocus?: boolean
  'aria-label'?: string
  'aria-labelledby'?: string
  onKeyDown?: (e: ReactKeyboardEvent<HTMLDivElement>) => void
}) {
  const floatingRef = useRef<HTMLDivElement>(null)
  const pos = useFloatingPosition(open, anchorRef, floatingRef, placement, offset)
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        // Capture phase + preventDefault: an enclosing Modal sees the event
        // as handled and stays open.
        e.preventDefault()
        onCloseRef.current()
        anchorRef.current?.focus()
      }
    }
    const onPointer = (e: PointerEvent) => {
      const t = e.target as Node
      if (floatingRef.current?.contains(t) || anchorRef.current?.contains(t)) return
      onCloseRef.current()
    }
    document.addEventListener('keydown', onKey, true)
    document.addEventListener('pointerdown', onPointer, true)
    return () => {
      document.removeEventListener('keydown', onKey, true)
      document.removeEventListener('pointerdown', onPointer, true)
    }
  }, [open, anchorRef])

  useEffect(() => {
    if (!open || !autoFocus || role === 'tooltip') return
    const id = requestAnimationFrame(() => {
      const el = floatingRef.current
      if (!el || el.contains(document.activeElement)) return
      const first = el.querySelector<HTMLElement>(FOCUSABLE)
      ;(first ?? el).focus({ preventScroll: true })
    })
    return () => cancelAnimationFrame(id)
  }, [open, autoFocus, role])

  if (!open) return null

  return createPortal(
    <div
      ref={floatingRef}
      id={id}
      role={role}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledby}
      tabIndex={-1}
      onKeyDown={onKeyDown}
      className={`overlay glass-overlay ${variant === 'menu' ? 'overlay-menu p-1.5' : ''} ${OVERLAY_SCOPE} fixed z-[60] outline-0 [outline-style:none] ${
        pos ? 'animate-fadeIn' : ''
      } ${className}`}
      style={{
        top: pos?.top ?? 0,
        left: pos?.left ?? 0,
        visibility: pos ? 'visible' : 'hidden',
        transformOrigin: pos?.side === 'top' ? 'bottom' : 'top',
        ...style,
      }}
    >
      {children}
    </div>,
    document.body,
  )
}

export type MenuItem =
  | {
      key: string
      label: ReactNode
      onSelect: () => void
      icon?: ReactNode
      /** One line of --body text under the label. */
      description?: ReactNode
      /** Risk-ink label (escalate, disconnect). The word must still say it. */
      danger?: boolean
      disabled?: boolean
    }
  | { key: string; separator: true }

export type MenuTriggerProps = {
  ref: (el: HTMLButtonElement | null) => void
  onClick: (e: ReactMouseEvent<HTMLElement>) => void
  'aria-haspopup': 'menu'
  'aria-expanded': boolean
  'aria-controls': string | undefined
}

/** An action menu (the "…" menu).
 *
 *    <Menu label="More actions for Marcus Reyes" items={[
 *      { key: 'send', label: 'Send now', onSelect: send },
 *    ]} />
 *
 *  The default trigger is a 32px `.btn-icon.btn-sm.above-stretch` with a
 *  MoreHorizontal glyph (safe inside a stretched-link row, R4). Pass
 *  `renderTrigger` for a custom one; spread the props it receives onto a
 *  <button>. Keyboard: Enter/Space/ArrowDown open and focus the first item;
 *  ArrowUp/Down, Home/End move; Escape closes and returns focus; Tab closes. */
export function Menu({
  items,
  label,
  placement = 'bottom-end',
  renderTrigger,
  triggerClassName = 'btn-icon btn-sm above-stretch',
  icon,
  className = '',
  minWidth = 200,
}: {
  items: MenuItem[]
  /** Accessible name of the trigger and the menu. Required. */
  label: string
  placement?: Placement
  renderTrigger?: (props: MenuTriggerProps) => ReactNode
  triggerClassName?: string
  icon?: ReactNode
  className?: string
  minWidth?: number
}) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement | null>(null)
  const setTrigger = useCallback((el: HTMLButtonElement | null) => {
    triggerRef.current = el
  }, [])
  const menuId = useId()

  const itemEls = () =>
    Array.from(
      document.getElementById(menuId)?.querySelectorAll<HTMLElement>(
        '[role="menuitem"]:not([aria-disabled="true"])',
      ) ?? [],
    )

  const focusItem = (which: 'first' | 'last' | 'next' | 'prev') => {
    const els = itemEls()
    if (!els.length) return
    const i = els.indexOf(document.activeElement as HTMLElement)
    const n =
      which === 'first'
        ? 0
        : which === 'last'
          ? els.length - 1
          : which === 'next'
            ? (i + 1) % els.length
            : (i - 1 + els.length) % els.length
    els[n].focus()
  }

  const onMenuKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      focusItem('next')
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      focusItem('prev')
    } else if (e.key === 'Home') {
      e.preventDefault()
      focusItem('first')
    } else if (e.key === 'End') {
      e.preventDefault()
      focusItem('last')
    } else if (e.key === 'Tab') {
      setOpen(false)
    }
  }

  const triggerProps: MenuTriggerProps = {
    ref: setTrigger,
    onClick: (e) => {
      e.stopPropagation()
      e.preventDefault()
      setOpen((o) => !o)
    },
    'aria-haspopup': 'menu',
    'aria-expanded': open,
    'aria-controls': open ? menuId : undefined,
  }

  return (
    <>
      {renderTrigger ? (
        // The props hold a callback ref and handlers; nothing reads a ref
        // during render.
        // eslint-disable-next-line react-hooks/refs
        renderTrigger(triggerProps)
      ) : (
        <button
          type="button"
          {...triggerProps}
          aria-label={label}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown' && !open) {
              e.preventDefault()
              setOpen(true)
            }
          }}
          className={triggerClassName}
        >
          {icon ?? <MoreHorizontal aria-hidden />}
        </button>
      )}
      <Popover
        open={open}
        onClose={() => setOpen(false)}
        anchorRef={triggerRef}
        placement={placement}
        variant="menu"
        role="menu"
        id={menuId}
        aria-label={label}
        onKeyDown={onMenuKey}
        className={className}
        style={{ minWidth }}
      >
        <div className="flex flex-col">
          {items.map((item) =>
            'separator' in item ? (
              <div key={item.key} role="separator" className="my-1 h-px bg-hairline" />
            ) : (
              <button
                key={item.key}
                type="button"
                role="menuitem"
                tabIndex={-1}
                aria-disabled={item.disabled || undefined}
                onClick={(e) => {
                  e.stopPropagation()
                  if (item.disabled) return
                  setOpen(false)
                  triggerRef.current?.focus()
                  item.onSelect()
                }}
                className={`flex min-h-9 w-full cursor-pointer items-start gap-2.5 rounded-control-sm px-2.5 py-2 text-left text-copy transition-colors duration-state ease-apple hover:bg-soft focus-visible:bg-soft focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus aria-disabled:cursor-default aria-disabled:text-disabled-ink aria-disabled:hover:bg-transparent ${
                  item.danger ? 'text-risk-high-ink' : 'text-ink'
                }`}
              >
                {item.icon && (
                  <span aria-hidden className="mt-0.5 shrink-0 [&_svg]:h-4 [&_svg]:w-4">
                    {item.icon}
                  </span>
                )}
                <span className="min-w-0">
                  <span className="block font-medium">{item.label}</span>
                  {item.description && (
                    <span className="meta mt-0.5 block">{item.description}</span>
                  )}
                </span>
              </button>
            ),
          )}
        </div>
      </Popover>
    </>
  )
}

/** A hover/focus tooltip in the top layer. Wraps ONE focusable element and
 *  describes it (aria-describedby). Text only; ink on the overlay panel
 *  (17+ light / 12.810 dark). Never put a clinical number only in a tooltip.
 *
 *    <Tooltip content="Refresh analysis"><button className="btn-icon" …/></Tooltip> */
export function Tooltip({
  content,
  children,
  placement = 'top',
  delay = 400,
}: {
  content: ReactNode
  children: ReactElement<Record<string, unknown>>
  placement?: Placement
  delay?: number
}) {
  const [open, setOpen] = useState(false)
  const anchorRef = useRef<HTMLElement | null>(null)
  const setAnchor = useCallback((el: HTMLElement | null) => {
    anchorRef.current = el
  }, [])
  const timer = useRef<number | undefined>(undefined)
  const id = useId()

  useEffect(() => () => window.clearTimeout(timer.current), [])

  if (!isValidElement(children)) return children

  const show = (immediate: boolean) => {
    window.clearTimeout(timer.current)
    if (immediate) setOpen(true)
    else timer.current = window.setTimeout(() => setOpen(true), delay)
  }
  const hide = () => {
    window.clearTimeout(timer.current)
    setOpen(false)
  }

  const p = children.props as Record<string, ((e: unknown) => void) | undefined>
  // Handlers and a callback ref only; no ref is read during render.
  // eslint-disable-next-line react-hooks/refs
  const child = cloneElement(children, {
    ref: setAnchor,
    'aria-describedby': open ? id : undefined,
    onPointerEnter: (e: unknown) => {
      p.onPointerEnter?.(e)
      show(false)
    },
    onPointerLeave: (e: unknown) => {
      p.onPointerLeave?.(e)
      hide()
    },
    onFocus: (e: unknown) => {
      p.onFocus?.(e)
      show(true)
    },
    onBlur: (e: unknown) => {
      p.onBlur?.(e)
      hide()
    },
  })

  return (
    <>
      {child}
      <Popover
        open={open}
        onClose={hide}
        anchorRef={anchorRef}
        placement={placement}
        offset={6}
        variant="menu"
        role="tooltip"
        id={id}
        autoFocus={false}
        className="pointer-events-none max-w-[16rem] !px-2.5 !py-1.5 text-label font-medium text-ink"
      >
        {content}
      </Popover>
    </>
  )
}

export default Menu
