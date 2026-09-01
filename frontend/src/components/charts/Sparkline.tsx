import { useId } from 'react'
import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'
import { shortDate } from '../../lib/format'

/** 14-day micro-trend inside a metric card, in the demo sparkline style:
 *  brand-purple stroke with a soft fading area fill and a panel-cored dot marking
 *  the latest reading. Status still lives in the card's pill, not the line. */
export default function Sparkline({
  series,
  baseline,
  unit,
}: {
  series: { date: string; value: number }[]
  baseline?: number | null
  unit: string
}) {
  // A metric grid renders one of these per card; a shared gradient id would
  // make every card paint from whichever <defs> the document happened to
  // parse first. Strip the punctuation React wraps the id in so the fragment
  // reference stays a plain SVG name.
  const gradientId = `spark-fade-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}`

  if (series.length === 0) {
    return <div className="h-10 rounded-[10px] border border-line bg-soft" />
  }
  return (
    <div className="h-10">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={series} margin={{ top: 4, right: 6, bottom: 2, left: 2 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="rgb(var(--brand))" stopOpacity=".22" />
              <stop offset="1" stopColor="rgb(var(--brand))" stopOpacity="0" />
            </linearGradient>
          </defs>
          {baseline != null && (
            <ReferenceLine y={baseline} stroke="rgb(var(--line))" strokeDasharray="3 3" />
          )}
          <Area
            type="monotone"
            dataKey="value"
            stroke="none"
            fill={`url(#${gradientId})`}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="rgb(var(--brand))"
            strokeWidth={2.2}
            isAnimationActive={false}
            dot={(props: { index?: number; cx?: number; cy?: number }) =>
              props.index === series.length - 1 ? (
                <circle
                  key="last"
                  cx={props.cx}
                  cy={props.cy}
                  r={3}
                  fill="rgb(var(--panel))"
                  stroke="rgb(var(--brand))"
                  strokeWidth={2}
                />
              ) : (
                <g key={props.index} />
              )
            }
          />
          <Tooltip
            cursor={{ stroke: 'rgb(var(--line))', strokeWidth: 1 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as { date: string; value: number }
              return (
                <div className="rounded-btn border border-line bg-panel px-2 py-1 text-xs shadow-lift">
                  <span className="text-[11px] font-medium text-faint">{shortDate(p.date)}</span>{' '}
                  <span className="font-mono font-medium tabular-nums text-ink">
                    {Math.round(p.value * 10) / 10} {unit}
                  </span>
                </div>
              )
            }}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
