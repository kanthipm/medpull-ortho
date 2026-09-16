import type { ReadoutItem, ReadoutTone } from './MetricCluster'

/** Foreground risk = the `-ink` half of the pair. See MetricCluster. */
const TONE: Record<ReadoutTone, string> = {
  high: 'text-risk-high-ink',
  med: 'text-risk-med-ink',
  low: 'text-risk-low-ink',
  missing: 'text-risk-missing-ink',
}

/**
 * Single-baseline instrument strip — mono value glued to its label.
 * One left→right pass; no vertical hop between title and number.
 * The size tokens carry their own leading and tracking, so there is no paired
 * `leading-[…]`/`tracking-[…]` to translate.
 */
export default function InlineReadout({
  items,
  className = '',
}: {
  items: ReadoutItem[]
  className?: string
}) {
  return (
    <div role="list" className={`flex flex-wrap items-baseline gap-x-6 gap-y-2 ${className}`}>
      {items.map((item) => (
        <span key={item.key} role="listitem" className="inline-flex items-baseline gap-el">
          <span
            className={`font-mono text-title font-medium tabular-nums ${
              item.tone ? TONE[item.tone] : 'text-ink'
            }`}
          >
            {item.value}
          </span>
          <span className="text-copy font-medium text-muted">
            {item.label}
            {item.hint ? (
              <span className="ml-el text-label text-muted">{item.hint}</span>
            ) : null}
          </span>
        </span>
      ))}
    </div>
  )
}
