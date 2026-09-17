import { PRIORITY, type Priority } from '../lib/risk'

/** Risk pill — the site's status pill: a capsule on its own opaque tint, a
 *  dot AND the word, so the tier never rests on colour. Missing data gets a
 *  hollow dot, like the site. Pairs (light / dark): high 4.73 / 6.12,
 *  medium 5.38 / 7.49, low 4.90 / 7.41, missing 5.93 / 6.22.
 *  Show it ONCE per view for a given patient (R7). */
export default function PriorityBadge({
  priority,
  className = '',
}: {
  priority: Priority
  className?: string
}) {
  const p = PRIORITY[priority]
  return (
    <span className={`chip gap-1.5 ${p.pill} ${className}`}>
      <span
        aria-hidden
        className={`h-1.5 w-1.5 shrink-0 rounded-pill ${
          priority === 'missing_data' ? 'border-[1.5px] border-current' : p.dot
        }`}
      />
      {p.label}
    </span>
  )
}
