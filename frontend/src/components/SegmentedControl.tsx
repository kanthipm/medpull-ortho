import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import { Link, useLocation } from 'react-router-dom'

export type SegmentOption<T extends string = string> = {
  key: T
  label: ReactNode
  /** When set, this option is a route link instead of a button. */
  to?: string
  end?: boolean
  /** Custom active matcher for route segments (pathname → boolean). */
  match?: (pathname: string) => boolean
  /** Plain-text label, used for the no-jitter width reservation on the
   *  `primary` tone and as the accessible name when `label` is not a string. */
  text?: string
  disabled?: boolean
}

/** Visual tone.
 *  - `default` — the Apple segmented control: a --soft track with a
 *    BRAND-FILLED thumb that slides on the spring. Idle labels ink 400
 *    (16.202 on the light track) / body 400 (6.211 dark); the selected label
 *    is white 500 on #1976D2 (4.602). The thumb clears 1.4.11 on its own
 *    (4.057 light / 3.490 dark against the track). R9: the selected segment
 *    keeps a visible focus ring — a 2px --focus ring outside plus a white
 *    inset ring on the thumb (index.css `.seg-item`).
 *  - `primary` — the underline tab strip (in-page tabs and the top nav):
 *    ink 400 idle, ink 600 selected, and the 2px `.nav-rule` under it. */
export type SegmentTone = 'default' | 'primary'

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

function textOf(opt: SegmentOption): string | undefined {
  if (opt.text) return opt.text
  return typeof opt.label === 'string' ? opt.label : undefined
}

/** Segmented control / tab strip. Button options select with click and with
 *  the arrow, Home and End keys (roving tabindex); link options navigate. */
export default function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className = '',
  tone = 'default',
  size = 'md',
  fullWidth = false,
  role = 'tablist',
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledby,
}: {
  options: SegmentOption<T>[]
  value: T | undefined
  onChange?: (key: T) => void
  className?: string
  tone?: SegmentTone
  /** `sm` — 28px items for dense card headers (default tone only). */
  size?: 'md' | 'sm'
  /** Stretch the track to its container and share the width equally. */
  fullWidth?: boolean
  /** `tablist` (default, items are tabs with aria-selected) or `radiogroup`
   *  (a filter; items are radios with aria-checked). */
  role?: 'tablist' | 'radiogroup'
  'aria-label'?: string
  'aria-labelledby'?: string
}) {
  const primary = tone === 'primary'
  const { trackRef, style } = useSlidingIndicator(value, options.length, primary ? 12 : 0)
  const itemRole = role === 'radiogroup' ? 'radio' : 'tab'

  const onKeyDown = (e: KeyboardEvent<HTMLElement>, index: number) => {
    const keys = ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End']
    if (!keys.includes(e.key)) return
    const enabled = options
      .map((o, i) => ({ o, i }))
      .filter(({ o }) => !o.disabled)
    const pos = enabled.findIndex(({ i }) => i === index)
    if (pos < 0 || enabled.length === 0) return
    let next: number
    if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = enabled.length - 1
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp')
      next = (pos - 1 + enabled.length) % enabled.length
    else next = (pos + 1) % enabled.length
    e.preventDefault()
    const target = enabled[next]
    const el = trackRef.current?.querySelector<HTMLElement>(`[data-segment-index="${target.i}"]`)
    el?.focus()
    if (!target.o.to) onChange?.(target.o.key)
  }

  const trackClass = primary
    ? `relative inline-flex items-stretch gap-1 ${fullWidth ? 'flex w-full' : ''}`
    : `seg-track ${fullWidth ? 'flex w-full' : ''}`

  return (
    <div
      ref={trackRef}
      role={options.some((o) => o.to) ? undefined : role}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledby}
      className={`${trackClass} ${className}`}
    >
      {primary ? (
        <span aria-hidden className="nav-rule" style={style} />
      ) : (
        <span aria-hidden className="seg-thumb" style={style} />
      )}
      {options.map((opt, i) => {
        const active = opt.key === value
        const label = textOf(opt)
        const cls = primary
          ? `appbar-link ${active ? 'on' : ''} ${fullWidth ? 'flex-1' : ''} min-h-10`
          : `seg-item ${active ? 'on' : ''} ${fullWidth ? 'flex-1' : ''} ${size === 'sm' ? '!min-h-7 !px-3' : ''} ${
              opt.disabled ? 'pointer-events-none opacity-50' : ''
            }`
        const common = {
          'data-segment-active': active ? 'true' : undefined,
          'data-segment-index': i,
          'data-label': primary ? label : undefined,
          className: cls,
        }

        if (opt.to) {
          return (
            <Link
              key={opt.key}
              to={opt.to}
              aria-current={active ? 'page' : undefined}
              {...common}
            >
              {opt.label}
            </Link>
          )
        }

        return (
          <button
            key={opt.key}
            type="button"
            role={itemRole}
            aria-selected={itemRole === 'tab' ? active : undefined}
            aria-checked={itemRole === 'radio' ? active : undefined}
            aria-disabled={opt.disabled || undefined}
            tabIndex={active || (value === undefined && i === 0) ? 0 : -1}
            onClick={() => !opt.disabled && onChange?.(opt.key)}
            onKeyDown={(e) => onKeyDown(e, i)}
            {...common}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
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
