import { useCallback, useLayoutEffect, useState, type RefObject } from 'react'

/* Top-layer positioning for Menu.tsx's Popover / Menu / Tooltip, and for any
   custom fixed-position floating UI (chart tooltips). Lives outside Menu.tsx
   so that file exports components only (react-refresh). */

export type Placement =
  | 'bottom-start'
  | 'bottom-end'
  | 'bottom'
  | 'top-start'
  | 'top-end'
  | 'top'

export const FLOATING_GAP = 8
const EDGE = 8

function computePosition(
  anchor: DOMRect,
  floating: { width: number; height: number },
  placement: Placement,
  offset: number,
): { top: number; left: number; side: 'top' | 'bottom' } {
  const vw = window.innerWidth
  const vh = window.innerHeight
  let side: 'top' | 'bottom' = placement.startsWith('top') ? 'top' : 'bottom'
  const below = anchor.bottom + offset
  const above = anchor.top - offset - floating.height
  if (side === 'bottom' && below + floating.height > vh - EDGE && above >= EDGE) side = 'top'
  else if (side === 'top' && above < EDGE && below + floating.height <= vh - EDGE) side = 'bottom'
  const top = side === 'bottom' ? below : above

  const align = placement.endsWith('-start') ? 'start' : placement.endsWith('-end') ? 'end' : 'center'
  let left =
    align === 'start'
      ? anchor.left
      : align === 'end'
        ? anchor.right - floating.width
        : anchor.left + anchor.width / 2 - floating.width / 2
  left = Math.max(EDGE, Math.min(left, vw - floating.width - EDGE))
  return { top: Math.max(EDGE, top), left, side }
}

/** Keeps a fixed-position floating element glued to its anchor through
 *  scrolling (any scroll container) and resizing. */
export function useFloatingPosition(
  open: boolean,
  anchorRef: RefObject<HTMLElement | null>,
  floatingRef: RefObject<HTMLElement | null>,
  placement: Placement = 'bottom-end',
  offset = FLOATING_GAP,
) {
  const [pos, setPos] = useState<{ top: number; left: number; side: 'top' | 'bottom' } | null>(
    null,
  )

  const update = useCallback(() => {
    const a = anchorRef.current
    const f = floatingRef.current
    if (!a || !f) return
    const next = computePosition(
      a.getBoundingClientRect(),
      { width: f.offsetWidth, height: f.offsetHeight },
      placement,
      offset,
    )
    setPos((p) =>
      p && p.top === next.top && p.left === next.left && p.side === next.side ? p : next,
    )
  }, [anchorRef, floatingRef, placement, offset])

  useLayoutEffect(() => {
    if (!open) return
    update()
    window.addEventListener('scroll', update, true)
    window.addEventListener('resize', update)
    let ro: ResizeObserver | undefined
    if (typeof ResizeObserver !== 'undefined' && floatingRef.current) {
      ro = new ResizeObserver(update)
      ro.observe(floatingRef.current)
    }
    return () => {
      window.removeEventListener('scroll', update, true)
      window.removeEventListener('resize', update)
      ro?.disconnect()
    }
  }, [open, update, floatingRef])

  return open ? pos : null
}
