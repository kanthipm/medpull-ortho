import { PRIORITY, type Priority } from '../lib/risk'

/** Risk pill — a 24px capsule on its own opaque tint, a dot AND the word, so
 *  the tier never rests on colour. Pairs (light / dark): high 4.835 / 5.701,
 *  medium 5.165 / 6.890, low 4.731 / 6.484, missing 6.367 / 5.093.
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
      <span aria-hidden className={`h-1.5 w-1.5 shrink-0 rounded-pill ${p.dot}`} />
      {p.label}
    </span>
  )
}
