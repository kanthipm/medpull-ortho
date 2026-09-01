import { PRIORITY, type Priority } from '../lib/risk'

/** Quiet risk chip — color + label only, no glow ring. */
export default function PriorityBadge({ priority, className = '' }: { priority: Priority; className?: string }) {
  const p = PRIORITY[priority]
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-2 py-[3px] text-[11px] font-medium leading-none ${p.pill} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${p.dot}`} />
      {p.label}
    </span>
  )
}
