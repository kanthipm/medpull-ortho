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

  return (
    <div>
      {/* Copy unchanged: the s2 line is identified at the line by its own end
          label, so it needs no legend row of its own and does not get one. */}
      <div className="mb-2 flex items-center gap-4 text-label font-medium text-muted">
        <span className="inline-flex items-center gap-el">
          <span className="h-0.5 w-4 bg-chart-s1" /> Actual
        </span>
        <span className="inline-flex items-center gap-el">
          <span className="h-2.5 w-4 bg-chart-grid" /> Expected range
        </span>
      </div>
      <div className="h-40">
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
            <YAxis hide domain={[0, (dataMax: number) => Math.min(1.1, dataMax * 1.2)]} />
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
              dot={false}
              isAnimationActive={false}
              connectNulls
            />
            {changePointDay != null && (
              <ReferenceLine
                x={changePointDay}
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
            <Tooltip
              cursor={{ stroke: GRID, strokeWidth: 1 }}
              content={({ active, payload, label }) => {
                if (!active || !payload?.length) return null
                const row = payload[0].payload as { actual: number | null; mid: number | null }
                return (
                  // A tooltip is a floating overlay: `.overlay` is the one place
                  // the ambient shadow is allowed. The retired lift-shadow
                  // alias and the hairline that double-drew next to it are gone.
                  // The `border-overlay-border` is the ONE separation: light
                  // --overlay-panel is #FFFFFF, the same as light --panel, so the fill
                  // gives 1.000:1 and --shadow-overlay is a soft wash offset downward,
                  // not an edge. See Sparkline.tsx for the full note and the exit
                  // condition. In dark, `.dark .overlay` already sets this, so it is
                  // a no-op there.
                  <div className="overlay border border-overlay-border px-2.5 py-1.5">
                    <div className="text-label font-medium text-muted">Post-op day {label}</div>
                    {row.actual != null && (
                      <div className="text-label font-medium tabular-nums text-ink">
                        Actual {Math.round(row.actual * 100)}%
                      </div>
                    )}
                    {row.mid != null && (
                      <div className="text-label font-medium tabular-nums text-muted">
                        Expected {Math.round(row.mid * 100)}%
                      </div>
                    )}
                  </div>
                )
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
