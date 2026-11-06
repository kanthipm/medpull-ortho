import { Check } from 'lucide-react'
import { STAFF_GUARDRAIL, type AthleteFlag, type Availability } from '../../api/sports'
import type { ReadoutTone } from '../../components/MetricCluster'
import { METRIC_STATUS, PRIORITY, type MetricStatus } from '../../lib/risk'

/* The small shared pieces of the team pages. Every state pill here carries
   its word (lib/risk.ts: colour never carries the state alone). */

/** Availability on the risk pill recipes: available is the calm green,
 *  modified the amber review tier, out the clay high tier. */
const AVAIL = {
  available: PRIORITY.low,
  modified: PRIORITY.medium,
  out: PRIORITY.high,
} as const satisfies Record<Availability, unknown>

export function AvailabilityPill({
  availability,
  label,
  className = '',
}: {
  availability: Availability
  label?: string
  className?: string
}) {
  const a = AVAIL[availability] ?? PRIORITY.missing_data
  return (
    <span className={`chip gap-1.5 ${a.pill} ${className}`}>
      <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-pill ${a.dot}`} />
      {label ?? availability}
    </span>
  )
}

/** An engine flag ("Spike", "Suppressed") on the metric-status recipe. */
export function FlagChip({ flag, className = '' }: { flag: AthleteFlag; className?: string }) {
  const s = METRIC_STATUS[flag.status] ?? METRIC_STATUS.nodata
  return <span className={`chip ${s.pill} ${className}`}>{flag.text}</span>
}

/** A panel's status, in the engine's own words when it has them. */
export function StatusChip({
  status,
  text,
  className = '',
}: {
  status: MetricStatus
  text?: string | null
  className?: string
}) {
  const s = METRIC_STATUS[status] ?? METRIC_STATUS.nodata
  return <span className={`chip ${s.pill} ${className}`}>{text || s.label}</span>
}

/** Evidence grade of a suggestion — a fact about the literature, not a risk,
 *  so it sits on the brand tint. */
export function EvidencePill({ grade }: { grade: string }) {
  return <span className="chip bg-brand-tint text-on-brand-tint">Evidence {grade}</span>
}

/** Answered the morning questions: a filled dot, or a hollow one when not —
 *  shape and the screen-reader text carry it, the hue is a second channel. */
export function AnsweredDot({ answered }: { answered: boolean }) {
  return (
    <span className="inline-flex items-center">
      <span
        aria-hidden
        className={`h-2 w-2 shrink-0 rounded-pill ${
          answered ? 'bg-risk-low-ink' : 'border-[1.5px] border-risk-missing-ink'
        }`}
      />
      <span className="sr-only">{answered ? 'Answered the morning questions' : 'Not answered today'}</span>
    </span>
  )
}

/** The 14-point readiness trend on a roster row: one series, --chart-s1,
 *  round caps and a panel-cored dot on the latest point, like the console's
 *  Sparkline, drawn inline so a list of rows costs no chart runtime. */
export function MiniSpark({
  values,
  width = 84,
  height = 28,
  label,
  className = '',
}: {
  values: (number | null | undefined)[]
  width?: number
  height?: number
  label?: string
  className?: string
}) {
  const nums = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (nums.length < 2) {
    return <span className="meta">No trend yet</span>
  }
  const pad = 3
  const lo = Math.min(...nums)
  const hi = Math.max(...nums)
  const span = hi - lo || 1
  const n = values.length
  const x = (i: number) => pad + (n > 1 ? (i / (n - 1)) * (width - 2 * pad) : 0)
  const y = (v: number) => height - pad - ((v - lo) / span) * (height - 2 * pad)
  let d = ''
  let pen = false
  let last: { x: number; y: number } | null = null
  values.forEach((v, i) => {
    if (typeof v !== 'number' || !Number.isFinite(v)) {
      pen = false
      return
    }
    const px = x(i)
    const py = y(v)
    d += `${pen ? 'L' : 'M'}${px.toFixed(1)},${py.toFixed(1)} `
    pen = true
    last = { x: px, y: py }
  })
  const end = last as { x: number; y: number } | null
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={`shrink-0 overflow-visible ${className}`}
      role="img"
      aria-label={`${label ? `${label}: ` : ''}${nums.length} days, latest ${Math.round(nums[nums.length - 1])}`}
    >
      <path
        d={d.trim()}
        fill="none"
        className="stroke-chart-s1"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {end && <circle cx={end.x} cy={end.y} r={2.5} className="fill-panel stroke-chart-s1" strokeWidth={1.75} />}
    </svg>
  )
}

/** A z-score as a bar from a centre mark: left and clay below baseline,
 *  right and sage above. Decorative — the figure beside it says the number. */
export function SignedBar({ z, max = 3, className = '' }: { z: number | null; max?: number; className?: string }) {
  const v = z == null ? 0 : Math.max(-max, Math.min(max, z))
  const half = (Math.abs(v) / max) * 50
  return (
    <span aria-hidden className={`relative block h-1.5 w-24 overflow-hidden rounded-pill bg-soft ${className}`}>
      <span className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
      <span
        className={`absolute inset-y-0 rounded-pill ${v < 0 ? 'bg-risk-high-ink' : 'bg-brand'}`}
        style={v < 0 ? { right: '50%', width: `${half}%` } : { left: '50%', width: `${half}%` }}
      />
    </span>
  )
}

/** The site's meter: a warm track and a grainy fill that grows in. */
export function Meter({
  pct,
  tone,
  className = '',
}: {
  pct: number | null | undefined
  tone?: ReadoutTone
  className?: string
}) {
  const w = Math.max(0, Math.min(100, pct ?? 0))
  return (
    <span aria-hidden className={`meter block ${className}`}>
      <span
        className={`meter-fill ${tone === 'med' ? 'is-watch' : tone === 'high' ? 'is-flag' : ''}`}
        style={{ width: `${w}%` }}
      />
    </span>
  )
}

/** A criterion's met / not-met mark, beside its label. */
export function CriterionMark({ met }: { met: boolean }) {
  return (
    <span
      className={`inline-grid h-5 w-5 shrink-0 place-items-center rounded-pill ${
        met ? 'bg-risk-low-tint text-risk-low-ink' : 'border border-line-strong text-faint'
      }`}
    >
      {met ? <Check aria-hidden size={12} strokeWidth={2.5} /> : null}
      <span className="sr-only">{met ? 'Met' : 'Not met'}</span>
    </span>
  )
}

/** The staff guardrail line, on the console's footnote recipe. */
export function StaffGuardrail({ text, className = '' }: { text?: string | null; className?: string }) {
  return <p className={`meta ${className}`}>{text || STAFF_GUARDRAIL}</p>
}
