import type { Night } from '../../api/data'
import { shortDate } from '../../lib/format'
import { hoursText } from './dataFormat'

/** The nights as one bar each, oldest on the left, split into the four
 *  stages where the source sent them. Drawn in plain SVG: thirty bars need no
 *  chart runtime. The stage tones are four steps of the chart ramp, darkest
 *  for deep sleep, and the legend names them, so a stage never rests on hue
 *  alone. A night with a duration and no stages is one neutral bar. */

const STAGES = [
  { key: 'deep', label: 'Deep', fill: 'rgb(var(--chart-s1))', opacity: 1 },
  { key: 'rem', label: 'REM', fill: 'rgb(var(--chart-s2))', opacity: 0.95 },
  { key: 'light', label: 'Light', fill: 'rgb(var(--chart-s1))', opacity: 0.38 },
  { key: 'awake', label: 'Awake', fill: 'rgb(var(--risk-med-ink))', opacity: 0.55 },
] as const

const HEIGHT = 168
const TOP = 6
const BOTTOM = 22

export default function NightsChart({ nights }: { nights: Night[] }) {
  const ordered = [...nights].sort((a, b) => a.date.localeCompare(b.date))
  if (ordered.length === 0) return null
  const total = (n: Night) =>
    n.stages
      ? STAGES.reduce((sum, s) => sum + (n.stages?.[s.key] ?? 0), 0)
      : (n.duration_h ?? 0)
  const max = Math.max(8, ...ordered.map(total))
  const slot = 100 / ordered.length
  const width = Math.min(slot * 0.68, 5)
  const plot = HEIGHT - TOP - BOTTOM
  const y = (hours: number) => TOP + plot - (hours / max) * plot
  const labelEvery = Math.max(1, Math.ceil(ordered.length / 6))
  const staged = ordered.some((n) => n.stages)

  return (
    <div>
      {staged && (
        <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-label text-secondary">
          {STAGES.map((s) => (
            <span key={s.key} className="inline-flex items-center gap-el">
              <span
                aria-hidden
                className="h-2.5 w-2.5 rounded-[3px]"
                style={{ background: s.fill, opacity: s.opacity }}
              />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <svg
        viewBox={`0 0 100 ${HEIGHT}`}
        preserveAspectRatio="none"
        className="block w-full"
        style={{ height: HEIGHT }}
        role="img"
        aria-label={`Sleep over ${ordered.length} nights; the latest was ${hoursText(
          ordered[ordered.length - 1].duration_h,
        )}`}
      >
        {[4, 8].map((h) => (
          <line
            key={h}
            x1={0}
            x2={100}
            y1={y(h)}
            y2={y(h)}
            stroke="rgb(var(--chart-grid))"
            strokeWidth={1}
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {ordered.map((night, i) => {
          const x = i * slot + (slot - width) / 2
          let base = 0
          return (
            <g key={night.date}>
              <title>{`${shortDate(night.date)}: ${hoursText(night.duration_h)} asleep`}</title>
              {night.stages ? (
                STAGES.map((s) => {
                  const hours = night.stages?.[s.key] ?? 0
                  if (hours <= 0) return null
                  const top = y(base + hours)
                  const rect = (
                    <rect
                      key={s.key}
                      x={x}
                      y={top}
                      width={width}
                      height={Math.max(0, y(base) - top)}
                      fill={s.fill}
                      opacity={s.opacity}
                    />
                  )
                  base += hours
                  return rect
                })
              ) : (
                <rect
                  x={x}
                  y={y(night.duration_h ?? 0)}
                  width={width}
                  height={Math.max(0, y(0) - y(night.duration_h ?? 0))}
                  fill="rgb(var(--chart-s1))"
                  opacity={0.6}
                />
              )}
            </g>
          )
        })}
      </svg>
      <div className="relative -mt-5 h-5" aria-hidden>
        {ordered.map((night, i) =>
          i % labelEvery === 0 ? (
            <span
              key={night.date}
              className="absolute -translate-x-1/2 whitespace-nowrap text-[11px] text-secondary"
              style={{ left: `${i * slot + slot / 2}%` }}
            >
              {shortDate(night.date)}
            </span>
          ) : null,
        )}
      </div>
      <p className="meta mt-1">The two rules mark 4 and 8 hours.</p>
    </div>
  )
}
