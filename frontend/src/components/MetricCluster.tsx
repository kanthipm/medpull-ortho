import type { ReactNode } from 'react'

export type ReadoutTone = 'high' | 'med' | 'low' | 'missing'

/** Risk as TEXT takes the `-ink` half of each pair. On the --soft tile
 *  (light / dark): high 4.956 / 7.064, med 5.127 / 9.005, low 4.733 / 8.439,
 *  missing 6.367 / 6.211. A toned value must still say its state in words
 *  somewhere nearby (a hint or the label); the hue is a second channel. */
const TONE: Record<ReadoutTone, string> = {
  high: 'text-risk-high-ink',
  med: 'text-risk-med-ink',
  low: 'text-risk-low-ink',
  missing: 'text-risk-missing-ink',
}

export type ReadoutItem = {
  key: string
  label: string
  value: ReactNode
  tone?: ReadoutTone
  hint?: string
}

/**
 * Metric tiles, like the app's portfolio grid: each value is its own
 * rounded --soft tile (12px corners) with the label above and the figure
 * below. Label 14/400 secondary (--muted on soft 4.755 light / 4.582 dark),
 * value 26/500 ink with tabular digits (16.202 / 16.060), hint 12/400.
 * Tiles are OPAQUE, so a clinical number never sits on a wash or a tint.
 *
 * `framed` (default) wraps the grid in its own `.panel` with 12px padding;
 * pass `framed={false}` inside a SectionCard or the recovery card.
 */
export default function MetricCluster({
  items,
  className = '',
  columns,
  framed = true,
}: {
  items: ReadoutItem[]
  className?: string
  /** Override auto column count (defaults to item count, capped at 4). */
  columns?: number
  framed?: boolean
}) {
  const n = columns ?? items.length
  const colClass =
    n <= 1
      ? 'grid-cols-1'
      : n === 2
        ? 'grid-cols-2'
        : n === 3
          ? 'grid-cols-2 sm:grid-cols-3'
          : 'grid-cols-2 sm:grid-cols-4'

  return (
    <div className={`${framed ? 'panel p-3' : ''} grid gap-2 ${colClass} ${className}`}>
      {items.map((item) => (
        <div key={item.key} className="min-w-0 rounded-control bg-soft px-3.5 py-3">
          <span className="block truncate text-copy text-secondary">{item.label}</span>
          <span
            className={`mt-1 flex flex-wrap items-baseline gap-x-1.5 text-title font-medium tabular-nums ${
              item.tone ? TONE[item.tone] : 'text-ink'
            }`}
          >
            {item.value}
            {item.hint && (
              <span className="max-w-[10rem] truncate text-label font-normal text-secondary">
                {item.hint}
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}
