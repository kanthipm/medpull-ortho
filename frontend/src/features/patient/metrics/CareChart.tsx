import { useId } from 'react'
import {
  Area,
  Bar,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import type { ChartPoint, ChartSpec, GaugeExtra } from '../../../api/care'
import { fmtNum } from './labels'

/** Every `ChartSpec.kind` the care engine emits, drawn in the app's chart
 *  idiom: quiet grid and references, a warm marker for change-points, status
 *  carried by the card's chip rather than the line. `CareChart` is the h-28
 *  card variant; `MiniChart` the 44px tile variant (no axes, no tooltip — the
 *  tile is a button).
 *
 *  COLOUR, all of it on the chart tokens now. The five strings this file used
 *  to hold were the brand FILL token (never a chart stroke), the old cyan
 *  chart stroke, the border token, the faint non-text tier and the bare risk
 *  alias — three of them aliases that die in the Cleanup phase. Recomputed on
 *  --panel, light / dark:
 *
 *    S1     --chart-s1          #1976D2 / #63A4FF   4.602 / 6.783
 *    S2     --chart-s2          #00707D / #5DDEF4   5.811 / 10.825
 *    AXIS   --chart-axis-label  #626B78 / #7F8A98   5.393 / 4.906
 *    REF    --chart-ref-line    #626B78 / #6B7480   5.393 / 3.631
 *    GRID   --chart-grid        #E0E5EC / #2A333D   1.266 / 1.342
 *    MARKER --risk-med-ink      #9A5300 / #FFB25C   5.815 / 9.641
 *
 *  CATEGORICAL IS CAPPED AT TWO, and S1/S2 are 1.263:1 apart in light and
 *  1.596:1 in dark — so on the `dual` kind the second series carries a 4-2 dash
 *  and a direct end-of-line label, and those are the accessibility mechanism
 *  rather than the hue. Anything with three or more levels (the `heat` grid)
 *  uses the single-hue sequential ramp instead of inventing a third category.
 *
 *  Every mark is a solid token: the `fillOpacity` washes this file used to put
 *  on bars, scatter points and the band are gone, because a wash's real ratio
 *  depends on whatever ground happens to show through it. */

const S1 = 'rgb(var(--chart-s1))'
const S2 = 'rgb(var(--chart-s2))'
const GRID = 'rgb(var(--chart-grid))'
const AXIS = 'rgb(var(--chart-axis-label))'
const REF = 'rgb(var(--chart-ref-line))'
const MARKER = 'rgb(var(--risk-med-ink))'
const PANEL = 'rgb(var(--panel))'

type Row = {
  x: number | string
  y: number | null
  y2: number | null
  fit: number | null
  band: [number, number] | null
  label?: string
}

/** Merge series / fit / band on x so one `data` array feeds every layer —
 *  the same shape `TrajectoryChart` builds, so lines connect across gaps
 *  the fit or band fill in. */
function mergeRows(spec: ChartSpec): Row[] {
  const rows = new Map<number | string, Row>()
  const at = (x: number | string): Row => {
    let row = rows.get(x)
    if (!row) {
      row = { x, y: null, y2: null, fit: null, band: null }
      rows.set(x, row)
    }
    return row
  }
  for (const p of spec.series) {
    const row = at(p.x)
    row.y = p.y ?? null
    row.y2 = p.y2 ?? null
    if (p.label) row.label = p.label
  }
  for (const f of spec.fit ?? []) at(f.x).fit = f.y
  for (const b of spec.band ?? []) at(b.x).band = [b.lo, b.hi]
  const out = [...rows.values()]
  if (out.every((r) => typeof r.x === 'number')) {
    out.sort((a, b) => (a.x as number) - (b.x as number))
  }
  return out
}

function xText(spec: ChartSpec, x: number | string, label?: string): string {
  if (label) return label
  if (typeof x === 'string') return x
  const axis = spec.x_label || 'Post-op day'
  return /^post-?op day$/i.test(axis) ? `Post-op day ${x}` : `${axis} ${x}`
}

function xTick(spec: ChartSpec, x: number | string): string {
  if (typeof x === 'string') return x
  const axis = spec.x_label || 'Post-op day'
  if (/^post-?op day$/i.test(axis)) return `D${x}`
  if (/^day/i.test(axis)) return `D${x}`
  if (/^hour/i.test(axis)) return `${x}h`
  if (/^minute/i.test(axis)) return `${x}m`
  return fmtNum(x)
}

function ChartTip({
  spec,
  active,
  payload,
}: {
  spec: ChartSpec
  active?: boolean
  payload?: { payload?: Row & ChartPoint }[]
}) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  if (!row) return null
  const y = row.y ?? null
  const y2 = row.y2 ?? null
  const fit = 'fit' in row ? row.fit : null
  return (
    // A tooltip IS a floating overlay, so it is one of the three surfaces the
    // ambient shadow is allowed on and `.overlay` carries it — along with
    // dark's own hairline and the forced-colors border. The retired
    // lift-shadow alias and the hairline border that double-drew the
    // edge beside it are both gone. 11px is axis labels only, so every line
    // here is on the 12px rung, and the x label moves off --faint (2.585:1,
    // non-text only) onto --muted (5.393:1).
    // The `border-overlay-border` is the ONE separation: light
    // --overlay-panel is #FFFFFF, the same as light --panel, so the fill
    // gives 1.000:1 and --shadow-overlay is a soft wash offset downward,
    // not an edge. See Sparkline.tsx for the full note and the exit
    // condition. In dark, `.dark .overlay` already sets this, so it is
    // a no-op there.
    <div className="overlay border border-overlay-border px-2.5 py-1.5">
      <div className="text-label font-medium text-muted">{xText(spec, row.x, row.label)}</div>
      {y != null && (
        <div className="text-label font-medium tabular-nums text-ink">
          {fmtNum(y)} {spec.y_label}
        </div>
      )}
      {y2 != null && (
        <div className="text-label font-medium tabular-nums text-muted">
          {fmtNum(y2)} {spec.y2_label}
        </div>
      )}
      {y == null && fit != null && (
        <div className="text-label font-medium tabular-nums text-muted">
          fit {fmtNum(fit)}
        </div>
      )}
    </div>
  )
}

/** Sparkline's panel-cored dot on the newest reading. */
function lastDot(count: number) {
  return function Dot(props: { index?: number; cx?: number; cy?: number }) {
    return props.index === count - 1 && props.cx != null && props.cy != null ? (
      <circle
        key="last"
        cx={props.cx}
        cy={props.cy}
        r={3}
        fill={PANEL}
        stroke={S1}
        strokeWidth={2}
      />
    ) : (
      <g key={props.index} />
    )
  }
}

/** Direct end-of-line label for the SECOND series of a `dual` chart. S1 and S2
 *  are 1.263:1 apart in light, so the reader cannot be asked to tell them apart
 *  by hue — the 4-2 dash and this label are what do it.
 *
 *  Drawn through the `dot` renderer rather than as a right-hand axis label, so
 *  it costs the h-28 plot no horizontal room and cannot be clipped by the SVG
 *  viewport: it sits 6px above the last point, anchored back along the line,
 *  with a 3px --panel outline under it (paint-order) so it stays legible where
 *  it crosses the primary line's tail. */
function endLabel(text: string, fill: string, atIndex: number) {
  return function EndLabel(props: { index?: number; cx?: number; cy?: number }) {
    if (props.index !== atIndex || props.cx == null || props.cy == null || !text) {
      return <g key={props.index} />
    }
    return (
      <text
        key="end-label"
        x={props.cx - 4}
        y={props.cy - 6}
        textAnchor="end"
        fontSize={12}
        fontWeight={500}
        fill={fill}
        stroke={PANEL}
        strokeWidth={3}
        paintOrder="stroke"
      >
        {text}
      </text>
    )
  }
}

/** Gauge bands. These were 45% alpha washes over the track, which put the real
 *  ratio at the mercy of whatever showed through; they are solid risk `-ink`
 *  tokens now (5.369 / 5.815 / 5.622:1 on light panel, 9.035 / 9.641 / 7.563
 *  dark). The `-tint` pair cannot be used here: the three light tints are
 *  within 1.03:1 of each other and three adjacent bands would be one bar.
 *
 *  Even at full strength low and med are only 1.084:1 apart in luminance, so a
 *  band boundary is NOT left to colour — each segment after the first draws a
 *  1px --panel divider (5.4-9.6:1 against every band), and the numeric scale
 *  under the bar names each edge. */
const GAUGE_TONE = {
  low: 'bg-risk-low-ink',
  med: 'bg-risk-med-ink',
  high: 'bg-risk-high-ink',
} as const

function readGauge(spec: ChartSpec): GaugeExtra | null {
  const e = spec.extra as Partial<GaugeExtra>
  if (typeof e.value !== 'number') return null
  const min = typeof e.min === 'number' ? e.min : 0
  const max = typeof e.max === 'number' ? e.max : 100
  const bands = Array.isArray(e.bands) ? e.bands : [{ to: max, tone: 'low' as const }]
  return { value: e.value, min, max, bands }
}

function Gauge({ spec, thin }: { spec: ChartSpec; thin: boolean }) {
  const g = readGauge(spec)
  if (!g) return <Empty thin={thin} />
  const span = Math.max(g.max - g.min, 1e-9)
  const pct = Math.min(100, Math.max(0, ((g.value - g.min) / span) * 100))
  const edges = g.bands.map((b) => Math.min(b.to, g.max))
  const segments = g.bands.map((b, i) => {
    const from = i === 0 ? g.min : edges[i - 1]
    const w = Math.max(0, ((edges[i] - from) / span) * 100)
    return { key: i, w, tone: GAUGE_TONE[b.tone] ?? GAUGE_TONE.low }
  })
  return (
    <div className={thin ? 'py-[18px]' : 'py-2'}>
      <div
        className={`relative flex w-full overflow-hidden rounded-full bg-line ${thin ? 'h-1.5' : 'h-2.5'}`}
        role="img"
        aria-label={`${fmtNum(g.value)} of ${fmtNum(g.max)}`}
      >
        {segments.map((s, i) => (
          <span
            key={s.key}
            className={`h-full box-border ${i === 0 ? '' : 'border-l border-panel'} ${s.tone}`}
            style={{ width: `${s.w}%` }}
          />
        ))}
        {/* The value marker has to read on a green, an amber, a red band AND on
            the bare track, so it is a --panel core (5.4-9.6:1 on every band)
            inside an --ink hairline (18.377:1 light / 17.194:1 dark on that
            core) rather than a flat --ink bar, which was 1.5:1 on the red. */}
        <span
          aria-hidden
          className="absolute inset-y-0 w-[3px] -translate-x-1/2 rounded-full bg-panel outline outline-1 outline-ink"
          style={{ left: `${pct}%` }}
        />
      </div>
      {/* The gauge's own axis: the 11px chart-axis rung (was 10px, under the
          floor) on --chart-axis-label (5.393:1, was --faint at 2.585:1). */}
      {!thin && (
        <div className="mt-1.5 flex justify-between text-micro font-medium tabular-nums text-chart-axis-label">
          <span>{fmtNum(g.min)}</span>
          {g.bands.slice(0, -1).map((b, i) => (
            <span key={i}>{fmtNum(b.to)}</span>
          ))}
          <span>{fmtNum(g.max)}</span>
        </div>
      )}
    </div>
  )
}

/** Adherence has THREE levels plus "not scheduled", which is more than the
 *  two-series categorical cap, so it takes the single-hue sequential ramp
 *  rather than a third hue. `bg-brand/35` was a 35% wash of a FILL token — an
 *  invented step whose ratio depended on the ground; --chart-seq-3 is the
 *  declared step. On --panel, light / dark: seq-5 8.631 / 14.087, seq-3
 *  3.343 / 5.144, and 2.582 / 2.739 between the two. The "missed" ring moves
 *  from --line (1.553:1, a border token) to --line-strong (3.834 / 5.671),
 *  which is the 1.4.11 boundary tier. Every cell also carries the state as a
 *  word in its `title`, so none of this is colour alone.
 *
 *  The ring is `border-2`, not `border`. Measured off a screenshot: a 1px ring
 *  on an 8px circle antialiases so hard that its strongest pixel came back
 *  #8F97A2 = 2.951:1 on light panel, i.e. the declared 3.834 never reaches the
 *  screen and the ring lands under the 1.4.11 floor anyway. At 2px the token
 *  value survives the rasteriser. */
function heatDot(v: number | null | undefined, size: string): string {
  if (v == null) return `${size} rounded-full bg-transparent`
  if (v >= 1) return `${size} rounded-full bg-chart-seq-5`
  if (v >= 0.5) return `${size} rounded-full bg-chart-seq-3`
  return `${size} rounded-full border-2 border-line-strong bg-transparent`
}

function heatGrid(spec: ChartSpec) {
  const rowsOrder: string[] = []
  const cols = new Set<number | string>()
  const cell = new Map<string, number | null>()
  for (const p of spec.series) {
    const r = p.row ?? ''
    if (!rowsOrder.includes(r)) rowsOrder.push(r)
    cols.add(p.x)
    cell.set(`${r}|${p.x}`, p.v ?? null)
  }
  const days = [...cols]
  if (days.every((d) => typeof d === 'number')) days.sort((a, b) => (a as number) - (b as number))
  return { rows: rowsOrder, days, cell }
}

function Heat({ spec }: { spec: ChartSpec }) {
  const { rows, days, cell } = heatGrid(spec)
  if (rows.length === 0 || days.length === 0) return <Empty thin={false} />
  const colStyle = { gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }
  return (
    <div className="space-y-1.5">
      <div className="grid grid-cols-[minmax(0,7rem)_1fr] items-center gap-x-2">
        <span />
        <div className="flex justify-between text-micro font-medium tabular-nums text-chart-axis-label">
          <span>{xTick(spec, days[0])}</span>
          <span>{xTick(spec, days[days.length - 1])}</span>
        </div>
      </div>
      {rows.map((r) => (
        <div key={r} className="grid grid-cols-[minmax(0,7rem)_1fr] items-center gap-x-2">
          <span className="truncate text-label font-medium text-muted" title={r}>
            {r}
          </span>
          <div className="grid" style={colStyle}>
            {days.map((d) => {
              const v = cell.get(`${r}|${d}`)
              return (
                <span key={String(d)} className="grid place-items-center">
                  <span
                    className={heatDot(v, 'h-2 w-2')}
                    title={`${xText(spec, d)} · ${v == null ? 'not scheduled' : v >= 1 ? 'verified' : v >= 0.5 ? 'self-attested' : 'missed'}`}
                  />
                </span>
              )
            })}
          </div>
        </div>
      ))}
      {/* Legend swatches track heatDot exactly. 10.5px on --faint (2.279:1) was
          a half-pixel size below the floor on the non-text tier; this is the
          12px rung on --muted (5.393:1). */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5 text-label font-medium text-muted">
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-chart-seq-5" /> verified
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-chart-seq-3" /> self-attested
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full border-2 border-line-strong" /> missed
        </span>
      </div>
    </div>
  )
}

/** Tile strip: one dot per day, tone = that day's mean across tasks. */
function HeatStrip({ spec }: { spec: ChartSpec }) {
  const { rows, days, cell } = heatGrid(spec)
  if (rows.length === 0 || days.length === 0) return <Empty thin />
  const perDay = days.map((d) => {
    const vals = rows
      .map((r) => cell.get(`${r}|${d}`))
      .filter((v): v is number => typeof v === 'number')
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
  })
  return (
    <div
      className="grid h-11 items-center"
      style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}
    >
      {perDay.map((v, i) => (
        <span key={i} className="grid place-items-center">
          <span className={heatDot(v, 'h-1.5 w-1.5')} />
        </span>
      ))}
    </div>
  )
}

function Empty({ thin }: { thin: boolean }) {
  return (
    <div
      // A fill OR a hairline, never both: an empty slot is a quiet fill.
      className={`grid place-items-center rounded-surface bg-soft ${thin ? 'h-11' : 'h-28'}`}
    >
      {!thin && <span className="micro">No chart data</span>}
    </div>
  )
}

function hasPoints(spec: ChartSpec): boolean {
  return spec.series.length > 0 || (spec.fit?.length ?? 0) > 0
}

/** Card-size chart (h-28) with axes, tooltip, legend for dual series. */
export default function CareChart({ spec }: { spec: ChartSpec | null }) {
  const gradientId = `care-fade-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  if (!spec) return <Empty thin={false} />
  if (spec.kind === 'gauge') return <Gauge spec={spec} thin={false} />
  if (spec.kind === 'heat') return <Heat spec={spec} />
  if (!hasPoints(spec)) return <Empty thin={false} />

  // the change-point label sits above the plot, so leave it headroom
  const margin = { top: spec.marker_x != null ? 16 : 6, right: 8, bottom: 0, left: 8 }
  const marker =
    spec.marker_x != null ? (
      <ReferenceLine
        x={spec.marker_x}
        stroke={MARKER}
        strokeDasharray="4 3"
        label={{ value: 'Change', position: 'top', fontSize: 11, fontWeight: 500, fill: MARKER }}
      />
    ) : null
  const reference =
    spec.reference != null ? (
      <ReferenceLine y={spec.reference} stroke={REF} strokeDasharray="3 3" />
    ) : null
  const tooltip = (
    <Tooltip
      cursor={{ stroke: GRID, strokeWidth: 1 }}
      content={(props) => <ChartTip spec={spec} {...(props as object)} />}
    />
  )

  if (spec.kind === 'bars') {
    const hasLabel = spec.series.some((p) => p.label)
    const data = spec.series.map((p) => ({ x: p.x, y: p.y ?? null, label: p.label }))
    return (
      <div className="h-28">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={margin}>
            <XAxis
              dataKey={hasLabel ? 'label' : 'x'}
              type="category"
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: AXIS }}
              tickFormatter={(v: string | number) => (hasLabel ? String(v) : xTick(spec, v))}
              interval={hasLabel ? 0 : 'preserveStartEnd'}
            />
            <YAxis hide />
            {reference}
            <Bar
              dataKey="y"
              fill={S1}
              radius={[3, 3, 0, 0]}
              maxBarSize={28}
              isAnimationActive={false}
            />
            {!hasLabel && marker}
            {tooltip}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (spec.kind === 'scatter') {
    return (
      <div className="h-28">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={margin}>
            <XAxis
              dataKey="x"
              type="number"
              domain={['dataMin', 'dataMax']}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: AXIS }}
              tickFormatter={(v: number) => xTick(spec, v)}
              interval="preserveStartEnd"
            />
            <YAxis dataKey="y" hide />
            <ZAxis range={[36, 36]} />
            {reference}
            {spec.fit && spec.fit.length > 0 && (
              <Line
                data={spec.fit}
                dataKey="y"
                stroke={REF}
                strokeWidth={1.2}
                strokeDasharray="4 3"
                dot={false}
                isAnimationActive={false}
                tooltipType="none"
              />
            )}
            <Scatter data={spec.series} dataKey="y" fill={S1} isAnimationActive={false} />
            {marker}
            <Tooltip
              cursor={{ stroke: GRID, strokeWidth: 1, strokeDasharray: '3 3' }}
              content={(props) => <ChartTip spec={spec} {...(props as object)} />}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    )
  }

  const rows = mergeRows(spec)
  const numericX = rows.every((r) => typeof r.x === 'number')
  const dual = spec.kind === 'dual'
  const count = rows.length
  // The end label goes on the last row that HAS a y2: `connectNulls` draws
  // across gaps but the dot renderer is not called for a null point.
  const lastY2 = rows.reduce((last, r, i) => (r.y2 != null ? i : last), -1)
  const y2Label = spec.y2_label || 'Secondary'

  return (
    <div>
      {dual && (
        // Two series is the cap. The swatches say what is actually drawn — a
        // solid rule for S1, a 4-2 dashed one for S2 — because the two colours
        // are 1.263:1 apart in light and a pair of identical bars in two
        // near-identical blues would be the legend lying about the plot.
        <div className="mb-1.5 flex items-center gap-4 text-label font-medium text-muted">
          <span className="inline-flex items-center gap-el">
            <span aria-hidden className="h-0.5 w-4 bg-chart-s1" /> {spec.y_label || 'Primary'}
          </span>
          <span className="inline-flex items-center gap-el">
            <span
              aria-hidden
              className="h-0.5 w-4"
              style={{
                backgroundImage: `repeating-linear-gradient(to right, ${S2} 0 4px, transparent 4px 6px)`,
              }}
            />{' '}
            {y2Label}
          </span>
        </div>
      )}
      <div className="h-28">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={margin}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={S1} stopOpacity=".18" />
                <stop offset="1" stopColor={S1} stopOpacity="0" />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="x"
              type={numericX ? 'number' : 'category'}
              domain={numericX ? ['dataMin', 'dataMax'] : undefined}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: AXIS }}
              tickFormatter={(v: number | string) => xTick(spec, v)}
              interval="preserveStartEnd"
            />
            <YAxis yAxisId="left" hide domain={['auto', 'auto']} />
            {dual && <YAxis yAxisId="right" orientation="right" hide domain={['auto', 'auto']} />}
            {spec.kind === 'band' && (
              <Area
                yAxisId="left"
                dataKey="band"
                stroke="none"
                fill={GRID}
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
            )}
            {spec.kind === 'line' && (
              <Area
                yAxisId="left"
                dataKey="y"
                stroke="none"
                fill={`url(#${gradientId})`}
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
            )}
            {spec.reference != null && (
              <ReferenceLine yAxisId="left" y={spec.reference} stroke={REF} strokeDasharray="3 3" />
            )}
            {spec.fit && spec.fit.length > 0 && (
              <Line
                yAxisId="left"
                dataKey="fit"
                stroke={REF}
                strokeWidth={1.2}
                strokeDasharray="4 3"
                dot={false}
                isAnimationActive={false}
                connectNulls
                tooltipType="none"
              />
            )}
            <Line
              yAxisId="left"
              dataKey="y"
              stroke={S1}
              strokeWidth={2}
              dot={lastDot(count)}
              isAnimationActive={false}
              connectNulls
            />
            {dual && (
              <Line
                yAxisId="right"
                dataKey="y2"
                stroke={S2}
                strokeWidth={1.6}
                strokeDasharray="4 2"
                dot={endLabel(y2Label, S2, lastY2)}
                isAnimationActive={false}
                connectNulls
              />
            )}
            {spec.marker_x != null && (
              <ReferenceLine
                yAxisId="left"
                x={spec.marker_x}
                stroke={MARKER}
                strokeDasharray="4 3"
                label={{
                  value: 'Change',
                  position: 'top',
                  fontSize: 11,
                  fontWeight: 500,
                  fill: MARKER,
                }}
              />
            )}
            {tooltip}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

/** 44px tile variant: line/band/scatter/bars reduced to the primary series
 *  with no axes; gauge → thin meter; heat → per-day dot strip; dual →
 *  primary series only. */
export function MiniChart({ spec }: { spec: ChartSpec | null }) {
  const gradientId = `care-mini-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`
  if (!spec) return <Empty thin />
  if (spec.kind === 'gauge') return <Gauge spec={spec} thin />
  if (spec.kind === 'heat') return <HeatStrip spec={spec} />
  if (!hasPoints(spec)) return <Empty thin />

  const margin = { top: 4, right: 4, bottom: 2, left: 2 }

  if (spec.kind === 'bars') {
    const hasLabel = spec.series.some((p) => p.label)
    const data = spec.series.map((p) => ({ x: p.x, y: p.y ?? null, label: p.label }))
    return (
      <div className="h-11">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={margin}>
            <XAxis dataKey={hasLabel ? 'label' : 'x'} type="category" hide />
            <YAxis hide />
            {spec.reference != null && (
              <ReferenceLine y={spec.reference} stroke={REF} strokeDasharray="3 3" />
            )}
            <Bar
              dataKey="y"
              fill={S1}
              radius={[2, 2, 0, 0]}
              maxBarSize={12}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (spec.kind === 'scatter') {
    return (
      <div className="h-11">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={margin}>
            <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} hide />
            <YAxis dataKey="y" hide />
            <ZAxis range={[14, 14]} />
            {spec.fit && spec.fit.length > 0 && (
              <Line
                data={spec.fit}
                dataKey="y"
                stroke={S1}
                strokeWidth={1.8}
                dot={false}
                isAnimationActive={false}
              />
            )}
            <Scatter data={spec.series} dataKey="y" fill={S1} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    )
  }

  const rows = mergeRows(spec)
  const numericX = rows.every((r) => typeof r.x === 'number')
  return (
    <div className="h-11">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={rows} margin={margin}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor={S1} stopOpacity=".22" />
              <stop offset="1" stopColor={S1} stopOpacity="0" />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="x"
            type={numericX ? 'number' : 'category'}
            domain={numericX ? ['dataMin', 'dataMax'] : undefined}
            hide
          />
          <YAxis hide domain={['auto', 'auto']} />
          {spec.kind === 'band' && (
            <Area dataKey="band" stroke="none" fill={GRID} isAnimationActive={false} connectNulls />
          )}
          {spec.kind !== 'band' && (
            <Area dataKey="y" stroke="none" fill={`url(#${gradientId})`} isAnimationActive={false} connectNulls />
          )}
          {spec.reference != null && (
            <ReferenceLine y={spec.reference} stroke={REF} strokeDasharray="3 3" />
          )}
          {spec.marker_x != null && (
            <ReferenceLine x={spec.marker_x} stroke={MARKER} strokeDasharray="3 3" />
          )}
          <Line
            dataKey="y"
            stroke={S1}
            strokeWidth={2}
            dot={lastDot(rows.length)}
            isAnimationActive={false}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
