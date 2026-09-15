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
 *  idiom: one brand series, quiet gray bands and references, a warm marker
 *  for change-points, status carried by the card's chip rather than the line.
 *  `CareChart` is the h-28 card variant; `MiniChart` the 44px tile variant
 *  (no axes, no tooltip — the tile is a button). */

const BRAND = 'rgb(var(--brand))'
const CYAN = 'rgb(var(--brand-cyan))'
const LINE = 'rgb(var(--line))'
const FAINT = 'rgb(var(--faint))'
const MED = 'rgb(var(--risk-med))'
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
    <div className="rounded-btn border border-line bg-panel px-2.5 py-1.5 text-xs shadow-lift">
      <div className="text-[11px] font-medium text-faint">{xText(spec, row.x, row.label)}</div>
      {y != null && (
        <div className="font-mono font-medium tabular-nums text-ink">
          {fmtNum(y)} {spec.y_label}
        </div>
      )}
      {y2 != null && (
        <div className="font-mono font-medium tabular-nums text-muted">
          {fmtNum(y2)} {spec.y2_label}
        </div>
      )}
      {y == null && fit != null && (
        <div className="font-mono font-medium tabular-nums text-muted">fit {fmtNum(fit)}</div>
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
        stroke={BRAND}
        strokeWidth={2}
      />
    ) : (
      <g key={props.index} />
    )
  }
}

const GAUGE_TONE = {
  low: 'bg-risk-low/45',
  med: 'bg-risk-med/45',
  high: 'bg-risk-high/45',
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
        {segments.map((s) => (
          <span key={s.key} className={`h-full ${s.tone}`} style={{ width: `${s.w}%` }} />
        ))}
        <span
          aria-hidden
          className="absolute inset-y-0 w-[2px] -translate-x-1/2 rounded-full bg-ink"
          style={{ left: `${pct}%` }}
        />
      </div>
      {!thin && (
        <div className="mt-1.5 flex justify-between font-mono text-[10px] font-medium tabular-nums text-faint">
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

function heatDot(v: number | null | undefined, size: string): string {
  if (v == null) return `${size} rounded-full bg-transparent`
  if (v >= 1) return `${size} rounded-full bg-brand`
  if (v >= 0.5) return `${size} rounded-full bg-brand/35`
  return `${size} rounded-full border border-line bg-transparent`
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
        <div className="flex justify-between font-mono text-[10px] font-medium tabular-nums text-faint">
          <span>{xTick(spec, days[0])}</span>
          <span>{xTick(spec, days[days.length - 1])}</span>
        </div>
      </div>
      {rows.map((r) => (
        <div key={r} className="grid grid-cols-[minmax(0,7rem)_1fr] items-center gap-x-2">
          <span className="truncate text-[11px] font-medium text-muted" title={r}>
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
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5 text-[10.5px] font-medium text-faint">
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-brand" /> verified
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full bg-brand/35" /> self-attested
        </span>
        <span className="inline-flex items-center gap-1">
          <span className="h-1.5 w-1.5 rounded-full border border-line" /> missed
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
      className={`grid place-items-center rounded-[10px] border border-line bg-soft ${thin ? 'h-11' : 'h-28'}`}
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
        stroke={MED}
        strokeDasharray="4 3"
        label={{ value: 'Change', position: 'top', fontSize: 10, fontWeight: 500, fill: MED }}
      />
    ) : null
  const reference =
    spec.reference != null ? (
      <ReferenceLine y={spec.reference} stroke={FAINT} strokeDasharray="3 3" />
    ) : null
  const tooltip = (
    <Tooltip
      cursor={{ stroke: LINE, strokeWidth: 1 }}
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
              tick={{ fontSize: 10.5, fill: FAINT }}
              tickFormatter={(v: string | number) => (hasLabel ? String(v) : xTick(spec, v))}
              interval={hasLabel ? 0 : 'preserveStartEnd'}
            />
            <YAxis hide />
            {reference}
            <Bar dataKey="y" fill={BRAND} fillOpacity={0.85} radius={[3, 3, 0, 0]} maxBarSize={28} isAnimationActive={false} />
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
              tick={{ fontSize: 10.5, fill: FAINT }}
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
                stroke={FAINT}
                strokeWidth={1.2}
                strokeDasharray="4 3"
                dot={false}
                isAnimationActive={false}
                tooltipType="none"
              />
            )}
            <Scatter
              data={spec.series}
              dataKey="y"
              fill={BRAND}
              fillOpacity={0.7}
              isAnimationActive={false}
            />
            {marker}
            <Tooltip
              cursor={{ stroke: LINE, strokeWidth: 1, strokeDasharray: '3 3' }}
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

  return (
    <div>
      {dual && (
        <div className="mb-1.5 flex items-center gap-4 text-[11px] font-medium text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded bg-brand" /> {spec.y_label || 'Primary'}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded bg-brand-cyan" /> {spec.y2_label || 'Secondary'}
          </span>
        </div>
      )}
      <div className="h-28">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={margin}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0" stopColor={BRAND} stopOpacity=".18" />
                <stop offset="1" stopColor={BRAND} stopOpacity="0" />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="x"
              type={numericX ? 'number' : 'category'}
              domain={numericX ? ['dataMin', 'dataMax'] : undefined}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 10.5, fill: FAINT }}
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
                fill={LINE}
                fillOpacity={0.85}
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
              <ReferenceLine yAxisId="left" y={spec.reference} stroke={FAINT} strokeDasharray="3 3" />
            )}
            {spec.fit && spec.fit.length > 0 && (
              <Line
                yAxisId="left"
                dataKey="fit"
                stroke={FAINT}
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
              stroke={BRAND}
              strokeWidth={2}
              dot={lastDot(count)}
              isAnimationActive={false}
              connectNulls
            />
            {dual && (
              <Line
                yAxisId="right"
                dataKey="y2"
                stroke={CYAN}
                strokeWidth={1.6}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            )}
            {spec.marker_x != null && (
              <ReferenceLine
                yAxisId="left"
                x={spec.marker_x}
                stroke={MED}
                strokeDasharray="4 3"
                label={{ value: 'Change', position: 'top', fontSize: 10, fontWeight: 500, fill: MED }}
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
              <ReferenceLine y={spec.reference} stroke={LINE} strokeDasharray="3 3" />
            )}
            <Bar dataKey="y" fill={BRAND} fillOpacity={0.8} radius={[2, 2, 0, 0]} maxBarSize={12} isAnimationActive={false} />
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
              <Line data={spec.fit} dataKey="y" stroke={BRAND} strokeWidth={1.8} dot={false} isAnimationActive={false} />
            )}
            <Scatter data={spec.series} dataKey="y" fill={BRAND} fillOpacity={0.45} isAnimationActive={false} />
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
              <stop offset="0" stopColor={BRAND} stopOpacity=".22" />
              <stop offset="1" stopColor={BRAND} stopOpacity="0" />
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
            <Area dataKey="band" stroke="none" fill={LINE} fillOpacity={0.7} isAnimationActive={false} connectNulls />
          )}
          {spec.kind !== 'band' && (
            <Area dataKey="y" stroke="none" fill={`url(#${gradientId})`} isAnimationActive={false} connectNulls />
          )}
          {spec.reference != null && (
            <ReferenceLine y={spec.reference} stroke={LINE} strokeDasharray="3 3" />
          )}
          {spec.marker_x != null && (
            <ReferenceLine x={spec.marker_x} stroke={MED} strokeDasharray="3 3" />
          )}
          <Line
            dataKey="y"
            stroke={BRAND}
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
