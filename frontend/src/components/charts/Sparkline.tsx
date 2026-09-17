import {
  useEffect,
  useId,
  useLayoutEffect,
  useReducer,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react'
import { createPortal } from 'react-dom'
import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  YAxis,
} from 'recharts'
import { OVERLAY_SCOPE } from '../Menu'
import { shortDate } from '../../lib/format'

/* ════════════════════════════════════════════════════════════════════════
   CHART TOOLTIP IN THE TOP LAYER (R5)

   Recharts draws its tooltip inside the chart wrapper, so a clipped card
   (`.card-group`, `.clip-surface`, a scrolling table) can cut it off. Every
   chart in the console instead hides Recharts' own wrapper
   (`wrapperStyle={CHART_TOOLTIP_WRAPPER}`) and renders its content through
   <ChartTooltip>, which portals to document.body at `position: fixed`,
   placed next to the hovered point, flipped and clamped to the viewport.

   Surface: `.overlay.overlay-menu` (opaque overlay panel, 12px corners,
   --shadow-overlay; dark adds its hairline). Secondary lines are --body via
   OVERLAY_SCOPE, because dark --muted on the overlay panel is 3.655:1:
     ink  18.377 light / 12.810 dark
     body  7.222 light /  4.955 dark
   Numbers sit on that opaque fill and are never only in the tooltip — every
   card states its value in the header.
   ════════════════════════════════════════════════════════════════════════ */

/** Pass as `wrapperStyle` on a Recharts <Tooltip> that renders <ChartTooltip>. */
export const CHART_TOOLTIP_WRAPPER = { display: 'none' } as const

const EDGE = 8
const GAP = 12

export function ChartTooltip({
  hostRef,
  x,
  y,
  children,
}: {
  /** The element that wraps the ResponsiveContainer; Recharts' coordinate is
   *  relative to it. */
  hostRef: RefObject<HTMLElement | null>
  x?: number
  y?: number
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const [tick, bump] = useReducer((n: number) => n + 1, 0)

  // Re-measure after every render (the pointer moved) and whenever anything
  // scrolls under a stationary pointer. setPos bails out on equal values.
  useLayoutEffect(() => {
    const host = hostRef.current
    const el = ref.current
    if (!host || !el || x == null || y == null) return
    const r = host.getBoundingClientRect()
    const w = el.offsetWidth
    const h = el.offsetHeight
    const ax = r.left + x
    const ay = r.top + y
    let left = ax + GAP
    if (left + w > window.innerWidth - EDGE) left = ax - GAP - w
    left = Math.max(EDGE, left)
    let top = ay - h - GAP
    if (top < EDGE) top = ay + GAP
    top = Math.max(EDGE, Math.min(top, window.innerHeight - h - EDGE))
    setPos((p) => (p && p.top === top && p.left === left ? p : { top, left }))
  }, [hostRef, x, y, children, tick])

  useEffect(() => {
    window.addEventListener('scroll', bump, true)
    window.addEventListener('resize', bump)
    return () => {
      window.removeEventListener('scroll', bump, true)
      window.removeEventListener('resize', bump)
    }
  }, [])

  if (typeof document === 'undefined') return null
  return createPortal(
    <div
      ref={ref}
      aria-hidden
      className={`overlay overlay-menu ${OVERLAY_SCOPE} pointer-events-none fixed z-[60] max-w-[16rem] px-3 py-2`}
      style={{
        top: pos?.top ?? 0,
        left: pos?.left ?? 0,
        visibility: pos ? 'visible' : 'hidden',
      }}
    >
      {children}
    </div>,
    document.body,
  )
}

/** The "Change" label on a change-point reference line. Recharts' `top`
 *  position centres the word on the line, so a marker near either end of the
 *  axis loses half the word to the SVG edge. This anchors the word to the
 *  line and runs it INTO the plot: rightward for a marker in the left half,
 *  leftward otherwise. Colour is --risk-med-ink (5.815 light / 9.641 dark on
 *  --panel) with a 3px --panel halo where it crosses a line. */
export function ChangeLabel({
  viewBox,
  side,
}: {
  viewBox?: { x?: number; y?: number }
  side: 'start' | 'end'
}) {
  if (viewBox?.x == null || viewBox?.y == null) return null
  return (
    <text
      x={viewBox.x + (side === 'start' ? 4 : -4)}
      y={viewBox.y - 5}
      textAnchor={side}
      fontSize={11}
      fontWeight={500}
      fill="rgb(var(--risk-med-ink))"
      stroke="rgb(var(--panel))"
      strokeWidth={3}
      paintOrder="stroke"
    >
      Change
    </text>
  )
}

/** Which way a marker's label should run: into the plot. */
export function markerSide(x: number, xs: (number | string)[]): 'start' | 'end' {
  const nums = xs.filter((v): v is number => typeof v === 'number')
  if (nums.length === 0) return 'start'
  const mid = (Math.min(...nums) + Math.max(...nums)) / 2
  return x <= mid ? 'start' : 'end'
}

/** Y domain for LINE-like marks (HIG Charts: a line's lower bound need not be
 *  zero — a resting HR of 60–66 on a 0–75 axis is a flat line). Pads the data
 *  span by 12% each side; a flat series gets a small symmetric pad. Bar totals
 *  do NOT use this: they keep zero. */
export function lineDomain(values: (number | null | undefined)[]): [number, number] | ['auto', 'auto'] {
  const nums = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (nums.length === 0) return ['auto', 'auto']
  const lo = Math.min(...nums)
  const hi = Math.max(...nums)
  const span = hi - lo
  const pad = span > 0 ? span * 0.12 : Math.max(Math.abs(hi) * 0.05, 1e-3)
  return [lo - pad, hi + pad]
}

/** One decimal, true minus (U+2212) for negative readings (R19). */
function oneDp(v: number): string {
  return String(Math.round(v * 10) / 10).replace('-', '\u2212')
}

/** 14-day micro-trend inside a signal card. ONE series, so it takes
 *  --chart-s1 and needs neither a dash pattern nor a direct label. Soft
 *  fading area fill, panel-cored dot on the latest reading, baseline as a
 *  dashed reference. Status lives in the card's pill, not the line.
 *
 *  It is drawn on an opaque --panel well (the caller's), which is where these
 *  ratios hold: s1 4.602:1 light / 6.783:1 dark; baseline --chart-ref-line
 *  5.393 / 3.631; cursor --chart-grid (quiet by design). On the grey tile
 *  itself dark --chart-ref-line would fall to 3.392 and light s1 to 4.057,
 *  which is why the well exists. */
export default function Sparkline({
  series,
  baseline,
  unit,
  label,
}: {
  series: { date: string; value: number }[]
  baseline?: number | null
  unit: string
  /** Accessible name of the plot (the metric name). */
  label?: string
}) {
  // A metric grid renders one of these per card; a shared gradient id would
  // make every card paint from whichever <defs> the document parsed first.
  const gradientId = `spark-fade-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  const hostRef = useRef<HTMLDivElement>(null)

  if (series.length === 0) {
    return (
      <div className="grid h-12 place-items-center">
        <span className="meta">No readings yet</span>
      </div>
    )
  }
  const last = series[series.length - 1]
  const domain = lineDomain([...series.map((p) => p.value), baseline])
  return (
    <div
      ref={hostRef}
      className="h-12"
      role="img"
      aria-label={`${label ? `${label}: ` : ''}${series.length} days, latest ${oneDp(last.value)} ${unit} on ${shortDate(
        last.date,
      )}${baseline != null ? `, baseline ${oneDp(baseline)}` : ''}`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={series} margin={{ top: 5, right: 6, bottom: 3, left: 2 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="rgb(var(--chart-s1))" stopOpacity=".22" />
              <stop offset="1" stopColor="rgb(var(--chart-s1))" stopOpacity="0" />
            </linearGradient>
          </defs>
          <YAxis hide domain={domain} />
          {baseline != null && (
            <ReferenceLine y={baseline} stroke="rgb(var(--chart-ref-line))" strokeDasharray="3 3" />
          )}
          <Area
            type="monotone"
            dataKey="value"
            stroke="none"
            fill={`url(#${gradientId})`}
            baseValue="dataMin"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="rgb(var(--chart-s1))"
            strokeWidth={2}
            strokeLinecap="round"
            isAnimationActive={false}
            dot={(props: { index?: number; cx?: number; cy?: number }) =>
              props.index === series.length - 1 ? (
                <circle
                  key="last"
                  cx={props.cx}
                  cy={props.cy}
                  r={3}
                  fill="rgb(var(--panel))"
                  stroke="rgb(var(--chart-s1))"
                  strokeWidth={2}
                />
              ) : (
                <g key={props.index} />
              )
            }
          />
          <Tooltip
            wrapperStyle={CHART_TOOLTIP_WRAPPER}
            isAnimationActive={false}
            cursor={{ stroke: 'rgb(var(--chart-grid))', strokeWidth: 1 }}
            content={({ active, payload, coordinate }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as { date: string; value: number }
              return (
                <ChartTooltip hostRef={hostRef} x={coordinate?.x} y={coordinate?.y}>
                  <div className="text-label text-secondary">{shortDate(p.date)}</div>
                  <div className="text-copy font-medium tabular-nums text-ink">
                    {oneDp(p.value)}{' '}
                    <span className="text-label font-normal text-secondary">{unit}</span>
                  </div>
                </ChartTooltip>
              )
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
