import { useRef } from 'react'
import {
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { DailySeries } from '../../api/data'
import { CHART_TOOLTIP_WRAPPER, lineDomain } from '../../components/charts/chartScale'
import { ChartTooltip } from '../../components/charts/Sparkline'
import { shortDate } from '../../lib/format'
import { num, sourceName } from './dataFormat'

const S1 = 'rgb(var(--chart-s1))'
const S2 = 'rgb(var(--chart-s2))'
const GRID = 'rgb(var(--chart-grid))'
const AXIS = 'rgb(var(--chart-axis-label))'
const REF = 'rgb(var(--chart-ref-line))'

/** One metric's daily series as the engine reads it: the value (solid), the
 *  person's own baseline (a dashed line, with a quiet band one standard
 *  deviation either side of it) and, for a metric judged against the
 *  expected recovery curve, that curve (dashed second series). The y-axis
 *  follows the data, as every line chart in the console does; the latest
 *  value is always printed by the caller, never left to the tooltip. */
export default function SeriesChart({ series, height = 200 }: { series: DailySeries; height?: number }) {
  const hostRef = useRef<HTMLDivElement>(null)
  const points = series.points
  if (points.length === 0) {
    return (
      <div className="grid place-items-center rounded-control bg-soft" style={{ height }}>
        <span className="meta">No readings in this window</span>
      </div>
    )
  }
  const baseline = series.baseline
  const hasExpected = points.some((p) => p.expected != null)
  const band = baseline ? [baseline.mean - baseline.sd, baseline.mean + baseline.sd] : null
  const domain = lineDomain([
    ...points.map((p) => p.value),
    ...points.map((p) => p.expected),
    ...(band ?? []),
  ])
  const last = points[points.length - 1]
  const summary = `${series.label}: ${points.length} days, latest ${num(last.value)} ${series.unit} on ${shortDate(
    last.date,
  )}${baseline ? `, baseline ${num(baseline.mean)}` : ''}`

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-label text-secondary">
        <span className="inline-flex items-center gap-el">
          <span aria-hidden className="h-0.5 w-4 rounded-pill bg-chart-s1" /> Daily value
        </span>
        {baseline && (
          <span className="inline-flex items-center gap-el">
            <span aria-hidden className="h-2.5 w-4 rounded-[3px] bg-chart-grid" /> Own baseline ± 1 SD
          </span>
        )}
        {hasExpected && (
          <span className="inline-flex items-center gap-el">
            <span
              aria-hidden
              className="h-0 w-4 border-t-2 border-dashed"
              style={{ borderColor: S2 }}
            />{' '}
            Expected for this recovery
          </span>
        )}
      </div>
      <div ref={hostRef} style={{ height }} role="img" aria-label={summary}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: AXIS }}
              tickFormatter={(d: string) => shortDate(d)}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis
              domain={domain}
              tickLine={false}
              axisLine={false}
              width={40}
              tick={{ fontSize: 11, fill: AXIS }}
              tickFormatter={(v: number) => num(v)}
              tickCount={4}
            />
            {band && <ReferenceArea y1={band[0]} y2={band[1]} fill={GRID} fillOpacity={0.9} stroke="none" />}
            {baseline && <ReferenceLine y={baseline.mean} stroke={REF} strokeDasharray="4 3" />}
            {hasExpected && (
              <Line
                dataKey="expected"
                stroke={S2}
                strokeWidth={1.6}
                strokeDasharray="4 2"
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
            )}
            <Line
              dataKey="value"
              stroke={S1}
              strokeWidth={2}
              strokeLinecap="round"
              dot={points.length <= 31 ? { r: 2, fill: S1, strokeWidth: 0 } : false}
              isAnimationActive={false}
              connectNulls
            />
            <Tooltip
              wrapperStyle={CHART_TOOLTIP_WRAPPER}
              isAnimationActive={false}
              cursor={{ stroke: GRID, strokeWidth: 1 }}
              content={({ active, payload, coordinate }) => {
                if (!active || !payload?.length) return null
                const p = payload[0].payload as DailySeries['points'][number]
                return (
                  <ChartTooltip hostRef={hostRef} x={coordinate?.x} y={coordinate?.y}>
                    <div className="text-label text-secondary">
                      {shortDate(p.date)} · day {p.day}
                    </div>
                    <div className="text-copy font-medium tabular-nums text-ink">
                      {num(p.value)} {series.unit}
                    </div>
                    {p.expected != null && (
                      <div className="text-label tabular-nums text-secondary">
                        Expected {num(p.expected)}
                      </div>
                    )}
                    {p.z != null && (
                      <div className="text-label tabular-nums text-secondary">
                        {p.z > 0 ? '+' : '−'}
                        {Math.abs(p.z).toFixed(1)} SD from the reference
                      </div>
                    )}
                    {p.source && <div className="text-label text-secondary">From {sourceName(p.source)}</div>}
                  </ChartTooltip>
                )
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
