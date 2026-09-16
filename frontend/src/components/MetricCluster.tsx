import type { ReactNode } from 'react'

export type ReadoutTone = 'high' | 'med' | 'low' | 'missing'

/** Risk as TEXT takes the `-ink` half of each pair (4.7–6.4:1 on panel in both
 *  modes). The bare `text-risk-*` aliases still resolve, but they are the fill
 *  names and this is a foreground. */
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
 * Compact instrument cluster — label stacked over mono value.
 * Hairlines come from a 1px gap grid so wrapping never leaves empty midspans:
 * the container's `bg-line` shows through the `gap-px`. That fill IS the
 * internal separation, and `.panel`'s hairline ring is the single outer edge —
 * the old `border border-line shadow-card` drew that edge twice.
 */
export default function MetricCluster({
  items,
  className = '',
  columns,
}: {
  items: ReadoutItem[]
  className?: string
  /** Override auto column count (defaults to item count, capped at 4 on lg). */
  columns?: number
}) {
  const n = columns ?? items.length
  const colClass =
    n <= 2
      ? 'grid-cols-2'
      : n === 3
        ? 'grid-cols-2 sm:grid-cols-3'
        : 'grid-cols-2 sm:grid-cols-4'

  return (
    <div
      className={`panel grid overflow-hidden bg-line ${colClass} gap-px ${className}`}
    >
      {items.map((item) => (
        <div key={item.key} className="bg-panel px-snug py-tight">
          <span className="block whitespace-nowrap text-label font-medium text-muted">
            {item.label}
          </span>
          <span
            className={`mt-el flex items-baseline gap-el font-mono text-title font-medium tabular-nums ${
              item.tone ? TONE[item.tone] : 'text-ink'
            }`}
          >
            {item.value}
            {item.hint && (
              <span className="max-w-[9rem] truncate font-sans text-label font-medium text-muted">
                {item.hint}
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}
