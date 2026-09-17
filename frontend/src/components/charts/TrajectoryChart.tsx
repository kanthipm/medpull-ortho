import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useRef } from 'react'
import { CHART_TOOLTIP_WRAPPER, lineDomain, markerSide } from './chartScale'
import { ChangeLabel, ChartTooltip } from './Sparkline'

interface Props {
  actual: { day: number; v: number }[]
  expected: { day: number; lo: number; mid: number; hi: number }[]
  changePointDay?: number | null
}

const S1 = 'rgb(var(--chart-s1))'
const S2 = 'rgb(var(--chart-s2))'
const GRID = 'rgb(var(--chart-grid))'
const AXIS = 'rgb(var(--chart-axis-label))'
const MARKER = 'rgb(var(--risk-med-ink))'
const PANEL = 'rgb(var(--panel))'

/** Direct end-of-line label for the second series. s1 and s2 are only 1.263:1
 *  apart in light and 1.596:1 in dark, so hue cannot be what tells them apart —
 *  the 4-2 dash and this label are the accessibility mechanism, not decoration.
 *
 *  It is drawn through the `dot` renderer so it needs no extra right margin
 *  (which would shrink the plot): it sits 6px above the last point, anchored
 *  back along the line, with a 3px --panel outline under it via paint-order so
 *  it stays legible where it crosses the band or the line's own tail. */
function endLabel(text: string, fill: string, atIndex: number) {
  return function EndLabel(props: { index?: number; cx?: number; cy?: number }) {
    if (props.index !== atIndex || props.cx == null || props.cy == null) {
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

/** Functional recovery index vs the expected band for this procedure.
 *
 *  Sits on an opaque --panel (a SectionCard body), which is where every ratio
 *  below was measured. The tooltip renders in the top layer (ChartTooltip).
 *  Y-domain: a line/band chart, so it follows the data rather than pinning
 *  zero; the "Expected" label and the band keep the gap readable.
 *
 *  TWO categorical series, which is the cap: `actual` is s1 solid, `expected`
 *  (the band's midline) is s2 on a 4-2 dash with a direct end-of-line label.
 *  The lo..hi band behind them is not a third series — it is a --chart-grid
 *  fill, the quiet structural tier, and the number a clinician reads off it is
 *  carried by the labelled s2 line rather than by the wash. That is why the
 *  band getting quieter here (--line 1.553:1 -> --chart-grid 1.266:1 on light
 *  panel) is an improvement overall: the midline went from an unlabelled
 *  --faint stroke at 2.585:1 to a labelled s2 at 5.811:1.
 *
 *  Axis ticks moved off --muted onto --chart-axis-label (5.393:1 light /
 *  4.906:1 dark) at the 11px chart-axis rung, which is the one place 11px is
 *  allowed. */
export default function TrajectoryChart({ actual, expected, changePointDay }: Props) {
  const hostRef = useRef<HTMLDivElement>(null)
  const byDay = new Map<number, Record<string, number | number[] | null>>()
  for (const e of expected) {
    byDay.set(e.day, { day: e.day, band: [e.lo, e.hi], mid: e.mid, actual: null })
  }
  for (const a of actual) {
    const row = byDay.get(a.day) ?? { day: a.day, band: null, mid: null, actual: null }
    row.actual = a.v
    byDay.set(a.day, row)
  }
  const data = [...byDay.values()].sort((a, b) => (a.day as number) - (b.day as number))
  // The label belongs on the last point that HAS a midline, not on the last
  // row: `connectNulls` draws across gaps but the dot renderer does not.
  const lastMid = data.reduce((last, r, i) => (r.mid != null ? i : last), -1)
  // Line/band chart: the y-domain follows the data (HIG), it does not pin 0.
  const domain = lineDomain([
    ...actual.map((a) => a.v),
    ...expected.flatMap((e) => [e.lo, e.hi]),
  ])
  const lastActual = actual.length ? actual[actual.length - 1] : null
  const lastExpected = lastActual ? expected.find((e) => e.day === lastActual.day) : undefined
  const summary = lastActual
    ? `Recovery index: day ${lastActual.day}, actual ${Math.round(lastActual.v * 100)}%${
        lastExpected ? `, expected ${Math.round(lastExpected.mid * 100)}%` : ''
      }${changePointDay != null ? `, change at day ${changePointDay}` : ''}`
    : 'Recovery index: no readings yet'

  return (
    <div>
      {/* Copy unchanged: the s2 line is identified at the line by its own end
          label, so it needs no legend row of its own and does not get one. */}
      <div className="mb-2 flex items-center gap-4 text-label text-secondary">
        <span className="inline-flex items-center gap-el">
          <span aria-hidden className="h-0.5 w-4 rounded-pill bg-chart-s1" /> Actual
        </span>
        <span className="inline-flex items-center gap-el">
          <span aria-hidden className="h-2.5 w-4 rounded-[3px] bg-chart-grid" /> Expected range
        </span>
      </div>
      <div ref={hostRef} className="h-40" role="img" aria-label={summary}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 16, right: 8, bottom: 0, left: 8 }}>
            <XAxis
              dataKey="day"
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 11, fill: AXIS }}
              tickFormatter={(d: number) => `Day ${d}`}
              interval="preserveStartEnd"
            />
            <YAxis hide domain={domain} />
            <Area
              dataKey="band"
              stroke="none"
              fill={GRID}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              dataKey="mid"
              stroke={S2}
              strokeWidth={1.6}
              strokeDasharray="4 2"
              dot={endLabel('Expected', S2, lastMid)}
              isAnimationActive={false}
              connectNulls
            />
            <Line
              dataKey="actual"
              stroke={S1}
              strokeWidth={2}
              strokeLinecap="round"
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            {changePointDay != null && (
              <ReferenceLine
                x={changePointDay}
                stroke={MARKER}
                strokeDasharray="4 3"
                label={
                  <ChangeLabel
                    side={markerSide(
                      changePointDay,
                      data.map((r) => r.day as number),
                    )}
                  />
                }
              />
            )}
            <Tooltip
              wrapperStyle={CHART_TOOLTIP_WRAPPER}
              isAnimationActive={false}
              cursor={{ stroke: GRID, strokeWidth: 1 }}
              content={({ active, payload, label, coordinate }) => {
                if (!active || !payload?.length) return null
                const row = payload[0].payload as { actual: number | null; mid: number | null }
                return (
                  <ChartTooltip hostRef={hostRef} x={coordinate?.x} y={coordinate?.y}>
                    <div className="text-label text-secondary">Post-op day {label}</div>
                    {row.actual != null && (
                      <div className="text-copy font-medium tabular-nums text-ink">
                        Actual {Math.round(row.actual * 100)}%
                      </div>
                    )}
                    {row.mid != null && (
                      <div className="text-label tabular-nums text-secondary">
                        Expected {Math.round(row.mid * 100)}%
                      </div>
                    )}
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
