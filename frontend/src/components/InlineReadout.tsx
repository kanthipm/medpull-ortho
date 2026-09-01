import type { ReadoutItem, ReadoutTone } from './MetricCluster'

const TONE: Record<ReadoutTone, string> = {
  high: 'text-risk-high',
  med: 'text-risk-med',
  low: 'text-risk-low',
  missing: 'text-risk-missing',
}

/**
 * Single-baseline instrument strip — mono value glued to its label.
 * One left→right pass; no vertical hop between title and number.
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
        <span key={item.key} role="listitem" className="inline-flex items-baseline gap-1.5">
          <span
            className={`font-mono text-[22px] font-medium leading-none tabular-nums tracking-[-.02em] ${
              item.tone ? TONE[item.tone] : 'text-ink'
            }`}
          >
            {item.value}
          </span>
          <span className="text-[12.5px] font-medium text-muted">
            {item.label}
            {item.hint ? (
              <span className="ml-1 text-[10.5px] uppercase tracking-[.04em] text-faint">
                {item.hint}
              </span>
            ) : null}
          </span>
        </span>
      ))}
    </div>
  )
}
