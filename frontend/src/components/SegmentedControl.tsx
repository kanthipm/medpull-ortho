import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { NavLink, useLocation } from 'react-router-dom'

export type SegmentOption<T extends string = string> = {
  key: T
  label: ReactNode
  /** When set, this option is a route link instead of a button. */
  to?: string
  end?: boolean
  /** Custom active matcher for route segments (pathname → boolean). */
  match?: (pathname: string) => boolean
}

type Pill = { left: number; width: number; ready: boolean }

function useSlidingPill(activeKey: string, optionCount: number) {
  const trackRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<(HTMLElement | null)[]>([])
  const [pill, setPill] = useState<Pill>({ left: 0, width: 0, ready: false })

  const measure = useCallback(() => {
    const track = trackRef.current
    if (!track) return
    const active = track.querySelector<HTMLElement>('[data-segment-active="true"]')
    if (!active) return

    setPill({
      left: active.offsetLeft,
      width: active.offsetWidth,
      ready: true,
    })
  }, [])

  useLayoutEffect(() => {
    measure()
  }, [measure, activeKey, optionCount])

  useLayoutEffect(() => {
    const track = trackRef.current
    if (!track || typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(() => measure())
    ro.observe(track)
    for (const el of itemRefs.current) {
      if (el) ro.observe(el)
    }
    window.addEventListener('resize', measure)
    return () => {
      ro.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [measure, optionCount])

  return { trackRef, itemRefs, pill }
}

/** Sliding-pill segmented control — shared by header nav, filters, and future toggles. */
export default function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className = '',
  'aria-label': ariaLabel,
}: {
  options: SegmentOption<T>[]
  value: T
  onChange?: (key: T) => void
  className?: string
  'aria-label'?: string
}) {
  const { trackRef, itemRefs, pill } = useSlidingPill(value, options.length)

  return (
    <div
      ref={trackRef}
      role="tablist"
      aria-label={ariaLabel}
      className={`relative inline-flex rounded-[9px] bg-track p-[3px] ${className}`}
    >
      <span
        aria-hidden
        className="pointer-events-none absolute top-[3px] z-0 h-[calc(100%-6px)] rounded-[7px] bg-panel shadow-segment motion-safe:transition-[transform,width] motion-safe:duration-300 motion-safe:ease-[cubic-bezier(.22,.61,.36,1)]"
        style={{
          width: pill.width,
          transform: `translateX(${pill.left}px)`,
          opacity: pill.ready ? 1 : 0,
        }}
      />
      {options.map((opt, i) => {
        const active = opt.key === value
        const cls = `relative z-10 cursor-pointer whitespace-nowrap rounded-[7px] px-3 py-1.5 text-[13px] font-medium transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand ${
          active ? 'text-ink' : 'text-muted hover:text-ink'
        }`

        if (opt.to) {
          return (
            <NavLink
              key={opt.key}
              to={opt.to}
              end={opt.end}
              role="tab"
              aria-selected={active}
              data-segment-active={active ? 'true' : undefined}
              ref={(el) => {
                itemRefs.current[i] = el
              }}
              className={cls}
            >
              {opt.label}
            </NavLink>
          )
        }

        return (
          <button
            key={opt.key}
            type="button"
            role="tab"
            aria-selected={active}
            data-segment-active={active ? 'true' : undefined}
            ref={(el) => {
              itemRefs.current[i] = el
            }}
            onClick={() => onChange?.(opt.key)}
            className={cls}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}

/** Header nav — active route drives the sliding pill. */
export function NavSegmentedControl({
  options,
  className = '',
}: {
  options: (SegmentOption & { to: string })[]
  className?: string
}) {
  const { pathname } = useLocation()
  const active =
    options.find((o) =>
      o.match
        ? o.match(pathname)
        : o.end
          ? pathname === o.to
          : pathname === o.to || pathname.startsWith(`${o.to}/`),
    )?.key ?? options[0]?.key

  return (
    <SegmentedControl
      options={options}
      value={active}
      className={`min-w-0 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${className}`}
      aria-label="Primary"
    />
  )
}
