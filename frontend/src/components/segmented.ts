import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import type { SegmentOption } from './SegmentedControl'

/* The hooks behind SegmentedControl and the app-bar nav. Kept out of
   SegmentedControl.tsx so that file exports components only (react-refresh). */

type Indicator = { left: number; width: number; ready: boolean; animate: boolean }

/** Measures the element marked `data-segment-active="true"` inside
 *  `trackRef` and returns its left/width. `inset` shrinks the width on both
 *  sides (the nav rule sits under the text, not under the padding).
 *  The first measurement lands with transitions off, so the indicator
 *  appears in place instead of sliding in from 0. */
export function useSlidingIndicator(activeKey: string | undefined, optionCount: number, inset = 0) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [indicator, setIndicator] = useState<Indicator>({
    left: 0,
    width: 0,
    ready: false,
    animate: false,
  })

  const measure = useCallback(() => {
    const track = trackRef.current
    if (!track) return
    const active = track.querySelector<HTMLElement>('[data-segment-active="true"]')
    if (!active) {
      setIndicator((i) => (i.ready ? { ...i, ready: false } : i))
      return
    }
    const left = active.offsetLeft + inset
    const width = Math.max(0, active.offsetWidth - inset * 2)
    setIndicator((i) =>
      i.ready && i.left === left && i.width === width ? i : { ...i, left, width, ready: true },
    )
  }, [inset])

  useLayoutEffect(() => {
    measure()
  }, [measure, activeKey, optionCount])

  // Turn transitions on one frame after the first placement.
  useEffect(() => {
    if (!indicator.ready || indicator.animate) return
    const id = requestAnimationFrame(() => setIndicator((i) => ({ ...i, animate: true })))
    return () => cancelAnimationFrame(id)
  }, [indicator.ready, indicator.animate])

  useLayoutEffect(() => {
    const track = trackRef.current
    if (!track) return
    window.addEventListener('resize', measure)
    // Web fonts change label widths after first paint.
    document.fonts?.ready.then(measure).catch(() => {})
    if (typeof ResizeObserver === 'undefined') {
      return () => window.removeEventListener('resize', measure)
    }
    const ro = new ResizeObserver(() => measure())
    ro.observe(track)
    for (const el of Array.from(track.children)) ro.observe(el)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [measure, optionCount])

  const style = {
    left: indicator.left,
    width: indicator.width,
    opacity: indicator.ready ? 1 : 0,
    ...(indicator.animate ? {} : { transition: 'none' }),
  }

  return { trackRef, indicator, style, measure }
}

/** The key of the option whose route matches the current location. */
export function useActiveRoute<T extends string>(
  options: (SegmentOption<T> & { to: string })[],
): T | undefined {
  const { pathname } = useLocation()
  return options.find((o) =>
    o.match
      ? o.match(pathname)
      : o.end
        ? pathname === o.to
        : pathname === o.to || pathname.startsWith(`${o.to}/`),
  )?.key
}
