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

/** 14-day micro-trend inside a metric card. ONE series, so it takes --chart-s1
 *  and needs neither a dash pattern nor a direct label: those are the mechanism
 *  that separates s1 from s2, and there is no s2 here. Soft fading area fill,
 *  panel-cored dot on the latest reading. Status still lives in the card's
 *  pill, not the line.
 *
 *  Colours, recomputed on --panel: s1 4.602:1 light / 6.783:1 dark; the
 *  baseline --chart-ref-line 5.393 / 3.631; the tooltip cursor --chart-grid
 *  1.266 / 1.342, which is the gridline tier and deliberately quiet. The old
 *  strings were the raw brand and border tokens — the brand token is a FILL
 *  token and --line is a border token, and neither survives Cleanup as a chart
 *  colour. */
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
    // A fill OR a hairline, never both: an empty slot is a quiet fill.
    return <div className="h-10 rounded-surface bg-soft" />
  }
  return (
    <div className="h-10">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={series} margin={{ top: 4, right: 6, bottom: 2, left: 2 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="rgb(var(--chart-s1))" stopOpacity=".22" />
              <stop offset="1" stopColor="rgb(var(--chart-s1))" stopOpacity="0" />
            </linearGradient>
          </defs>
          {baseline != null && (
            <ReferenceLine
              y={baseline}
              stroke="rgb(var(--chart-ref-line))"
              strokeDasharray="3 3"
            />
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
            stroke="rgb(var(--chart-s1))"
            strokeWidth={2}
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
            cursor={{ stroke: 'rgb(var(--chart-grid))', strokeWidth: 1 }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const p = payload[0].payload as { date: string; value: number }
              return (
                // A tooltip IS a floating overlay, so it is one of the three
                // surfaces allowed the ambient shadow — `.overlay` carries it,
                // plus dark's own hairline and the forced-colors border. The
                // retired lift-shadow alias and the hairline border that
                // double-drew the edge next to it are both gone.
                // border-overlay-border is the ONE separation, because `.overlay`'s light fill
                // delivers none: light --overlay-panel is var(--n-0), the same
                // #FFFFFF as light --panel, so a tooltip over a card measured
                // 1.000:1 against it and the only other cue is --shadow-overlay,
                // a 0.08-alpha 120px wash offset 64px DOWN, which reads as a
                // smudge below the box rather than an edge around it. I
                // photographed exactly that before adding this. --overlay-border
                // is the token light declares for this job and consumes nowhere
                // (3.834:1 on the overlay panel light, 4.225:1 dark), and
                // `.dark .overlay` already applies it, so in dark this class is
                // a no-op and only the light edge is new. This is not the
                // forbidden hairline-AND-fill: in light there is no fill to
                // speak of. DELETE IT when index.css gives light --overlay-panel
                // a value of its own or puts the hairline on the recipe.
                <div className="overlay border border-overlay-border px-2 py-1">
                  {/* 11px is reserved for chart axis labels; a tooltip line is
                      UI text, so it starts at the 12px rung. */}
                  <span className="text-label font-medium text-muted">{shortDate(p.date)}</span>{' '}
                  <span className="font-mono text-label font-medium tabular-nums text-ink">
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
