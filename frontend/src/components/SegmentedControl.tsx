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

/** Visual tone: `default` sits on a light surface with a blue underline;
 *  `primary` sits on the blue app bar with a white underline. */
export type SegmentTone = 'default' | 'primary'

type Indicator = { left: number; width: number; ready: boolean }

function useSlidingIndicator(activeKey: string, optionCount: number) {
  const trackRef = useRef<HTMLDivElement>(null)
  const itemRefs = useRef<(HTMLElement | null)[]>([])
  const [indicator, setIndicator] = useState<Indicator>({ left: 0, width: 0, ready: false })

  const measure = useCallback(() => {
    const track = trackRef.current
    if (!track) return
    const active = track.querySelector<HTMLElement>('[data-segment-active="true"]')
    if (!active) return

    setIndicator({
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

  return { trackRef, itemRefs, indicator }
}

const TONE = {
  default: {
    track: 'border-b border-line',
    bar: 'bg-brand',
    active: 'text-brand',
    idle: 'text-muted hover:text-ink',
    focus: 'focus-visible:outline-brand',
  },
  primary: {
    track: '',
    bar: 'bg-white',
    active: 'text-white',
    idle: 'text-white/75 hover:text-white',
    focus: 'focus-visible:outline-white',
  },
} as const satisfies Record<SegmentTone, unknown>

/** Underline tab strip — a sliding indicator marks the selected tab.
 *  Shared by header nav, filters, and future toggles. */
export default function SegmentedControl<T extends string>({
  options,
  value,
  onChange,
  className = '',
  tone = 'default',
  'aria-label': ariaLabel,
}: {
  options: SegmentOption<T>[]
  value: T
  onChange?: (key: T) => void
  className?: string
  tone?: SegmentTone
  'aria-label'?: string
}) {
  const { trackRef, itemRefs, indicator } = useSlidingIndicator(value, options.length)
  const t = TONE[tone]

  return (
    <div
      ref={trackRef}
      role="tablist"
      aria-label={ariaLabel}
      className={`relative inline-flex ${t.track} ${className}`}
    >
      <span
        aria-hidden
        className={`pointer-events-none absolute bottom-0 z-0 h-[3px] ${t.bar} motion-safe:transition-[transform,width] motion-safe:duration-300 motion-safe:ease-[cubic-bezier(.22,.61,.36,1)]`}
        style={{
          width: indicator.width,
          transform: `translateX(${indicator.left}px)`,
          opacity: indicator.ready ? 1 : 0,
        }}
      />
      {options.map((opt, i) => {
        const active = opt.key === value
        const cls = `relative z-10 inline-flex h-full cursor-pointer items-center whitespace-nowrap px-4 py-3 text-[14px] font-medium transition-colors duration-200 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 ${t.focus} ${
          active ? t.active : t.idle
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

/** Header nav — active route drives the sliding underline. */
export function NavSegmentedControl({
  options,
  className = '',
  tone = 'default',
}: {
  options: (SegmentOption & { to: string })[]
  className?: string
  tone?: SegmentTone
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
      tone={tone}
      className={`min-w-0 self-stretch overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden ${className}`}
      aria-label="Primary"
    />
  )
}
