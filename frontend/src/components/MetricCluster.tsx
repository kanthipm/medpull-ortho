import type { ReactNode } from 'react'

export type ReadoutTone = 'high' | 'med' | 'low' | 'missing'

const TONE: Record<ReadoutTone, string> = {
  high: 'text-risk-high',
  med: 'text-risk-med',
  low: 'text-risk-low',
  missing: 'text-risk-missing',
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
 * Hairlines come from a 1px gap grid so wrapping never leaves empty midspans.
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
      className={`grid overflow-hidden rounded-card border border-line bg-line ${colClass} gap-px ${className}`}
    >
      {items.map((item) => (
        <div key={item.key} className="bg-panel px-3.5 py-3">
          <span className="block whitespace-nowrap text-[10.5px] font-medium uppercase tracking-[.08em] text-faint">
            {item.label}
          </span>
          <span
            className={`mt-1.5 flex items-baseline gap-1.5 font-mono text-[20px] font-medium leading-none tabular-nums tracking-[-.02em] ${
              item.tone ? TONE[item.tone] : 'text-ink'
            }`}
          >
            {item.value}
            {item.hint && (
              <span className="max-w-[9rem] truncate font-sans text-[10px] font-medium uppercase tracking-[.04em] text-faint">
                {item.hint}
              </span>
            )}
          </span>
        </div>
      ))}
    </div>
  )
}
