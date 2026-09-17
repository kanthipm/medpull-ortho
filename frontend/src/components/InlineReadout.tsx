import type { ReadoutItem, ReadoutTone } from './MetricCluster'

/** Foreground risk = the `-ink` half of the pair. See MetricCluster. */
const TONE: Record<ReadoutTone, string> = {
  high: 'text-risk-high-ink',
  med: 'text-risk-med-ink',
  low: 'text-risk-low-ink',
  missing: 'text-risk-missing-ink',
}

/**
 * Single-baseline stat strip — the figure glued to its label ("3 active
 * tasks · 82% verified"). One left-to-right pass; no vertical hop.
 * Value 26/500 with tabular digits; label 14/400 in the secondary colour
 * (--muted 5.393 / 4.906 on panel, --body 6.237 / 5.513 inside a tint card);
 * hint 12/400. Opaque surfaces only, never the ambient wash.
 */
export default function InlineReadout({
  items,
  className = '',
}: {
  items: ReadoutItem[]
  className?: string
}) {
  return (
    <div role="list" className={`flex flex-wrap items-baseline gap-x-8 gap-y-2 ${className}`}>
      {items.map((item) => (
        <span key={item.key} role="listitem" className="inline-flex items-baseline gap-1.5">
          <span
            className={`text-title font-medium tabular-nums ${
              item.tone ? TONE[item.tone] : 'text-ink'
            }`}
          >
            {item.value}
          </span>
          <span className="text-copy text-secondary">
            {item.label}
            {item.hint ? <span className="ml-1 text-label">{item.hint}</span> : null}
          </span>
        </span>
      ))}
    </div>
  )
}
