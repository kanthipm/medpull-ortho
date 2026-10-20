import { useRef } from 'react'
import { Bar, BarChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { ChartTooltip } from '../../components/charts/Sparkline'
import { CHART_TOOLTIP_WRAPPER } from '../../components/charts/chartScale'
import { shortDate } from '../../lib/format'
import { addDays } from './sportsFormat'

const S1 = 'rgb(var(--chart-s1))'
const GRID = 'rgb(var(--chart-grid))'
const AXIS = 'rgb(var(--chart-axis-label))'
const REF = 'rgb(var(--chart-ref-line))'

/** Daily load as bars over a fixed window ending on `asOf`. Rest days are
 *  drawn as empty days, so the week's rhythm reads along the axis. ONE series
 *  on --chart-s1; the dashed reference is the window's mean (the caller
 *  states it in words under the chart — see `meanPerDay`). Bar totals keep
 *  zero (chartScale.ts), and the tooltip renders in the top layer. */
export default function LoadBars({
  data,
  asOf,
  unit,
  label,
  days = 28,
  className = 'h-40',
}: {
  data: { date: string; value: number | null }[]
  asOf: string
  unit: string
  /** Accessible name of the plot. */
  label: string
  days?: number
  className?: string
}) {
  const hostRef = useRef<HTMLDivElement>(null)
  const byDate = new Map(data.map((p) => [p.date, p.value ?? 0]))
  const start = addDays(asOf, -(days - 1))
  const rows = Array.from({ length: days }, (_, i) => {
    const date = addDays(start, i)
    return { date, value: byDate.get(date) ?? 0 }
  })
  const values = rows.map((r) => r.value)
  const mean = values.reduce((a, b) => a + b, 0) / Math.max(1, values.length)
  const peak = Math.max(...values, 0)
  const last = [...rows].reverse().find((r) => r.value > 0)
  const summary = last
    ? `${label}: ${days} days, mean ${Math.round(mean)} ${unit}, latest ${Math.round(last.value)} ${unit} on ${shortDate(last.date)}`
    : `${label}: no sessions in the last ${days} days`

  if (peak === 0) {
    return (
      <div className={`grid place-items-center ${className}`}>
        <span className="meta">No sessions logged in the last {days} days</span>
      </div>
    )
  }

  return (
    <div ref={hostRef} className={className} role="img" aria-label={summary}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ top: 12, right: 6, bottom: 0, left: 6 }} barCategoryGap="30%">
          <XAxis
            dataKey="date"
            tickLine={false}
            axisLine={false}
            tick={{ fontSize: 11, fill: AXIS }}
            tickFormatter={(d: string) => shortDate(d)}
            interval="preserveStartEnd"
            minTickGap={28}
          />
          <YAxis hide domain={[0, Math.ceil(peak * 1.08)]} />
          <ReferenceLine y={mean} stroke={REF} strokeDasharray="3 3" />
          <Bar dataKey="value" fill={S1} radius={[3, 3, 0, 0]} maxBarSize={22} isAnimationActive={false} />
          <Tooltip
            wrapperStyle={CHART_TOOLTIP_WRAPPER}
            isAnimationActive={false}
            cursor={{ fill: GRID }}
            content={({ active, payload, coordinate }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as { date: string; value: number }
              return (
                <ChartTooltip hostRef={hostRef} x={coordinate?.x} y={coordinate?.y}>
                  <div className="text-label text-secondary">{shortDate(p.date)}</div>
                  <div className="text-copy font-medium tabular-nums text-ink">
                    {Math.round(p.value).toLocaleString()}{' '}
                    <span className="text-label font-normal text-secondary">{unit}</span>
                  </div>
                </ChartTooltip>
              )
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
