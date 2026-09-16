import { PRIORITY, type Priority } from '../lib/risk'

/** Risk chip — tinted container + dot. */
export default function PriorityBadge({ priority, className = '' }: { priority: Priority; className?: string }) {
  const p = PRIORITY[priority]
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-btn px-2.5 py-[4px] text-[12px] font-medium leading-none ${p.pill} ${className}`}
    >
      <span className={`h-2 w-2 rounded-full ${p.dot}`} />
      {p.label}
    </span>
  )
}
