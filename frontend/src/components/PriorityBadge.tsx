import { PRIORITY, type Priority } from '../lib/risk'

/** Risk chip — tinted container + dot. */
export default function PriorityBadge({ priority, className = '' }: { priority: Priority; className?: string }) {
  const p = PRIORITY[priority]
  return (
    <span
      className={`chip gap-1.5 ${p.pill} ${className}`}
    >
      <span className={`h-2 w-2 rounded-full ${p.dot}`} />
      {p.label}
    </span>
  )
}
