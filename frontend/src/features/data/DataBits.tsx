import { Loader2 } from 'lucide-react'
import type { ReactNode } from 'react'
import type { MetricTier } from '../../api/data'
import EmptyState from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { TIER_CLASS, TIER_LABEL } from './dataFormat'

/** Small shared pieces of the Data tab. */

/** Days with data in a window, as a quiet bar with the count beside it. The
 *  number is always printed: the bar is a second channel, never the only one. */
export function DaysMeter({ days, of, label }: { days: number; of: number; label?: string }) {
  const share = of > 0 ? Math.min(1, days / of) : 0
  return (
    <span className="inline-flex items-center gap-2" title={label}>
      <span aria-hidden className="h-1.5 w-12 overflow-hidden rounded-pill bg-[rgb(var(--fill))]">
        <span
          className="block h-full rounded-pill bg-chart-s1"
          style={{ width: `${Math.max(share * 100, days > 0 ? 8 : 0)}%` }}
        />
      </span>
      <span className="tabular-nums text-copy text-ink">{days}</span>
    </span>
  )
}

export function TierChip({ tier }: { tier: MetricTier }) {
  return <span className={`chip normal-case tracking-label ${TIER_CLASS[tier]}`}>{TIER_LABEL[tier]}</span>
}

/** A view's three states in one place: loading, failed (with a way to try
 *  again), and loaded. */
export function ViewState({
  loading,
  error,
  onRetry,
  what,
  children,
}: {
  loading: boolean
  error: boolean
  onRetry: () => void
  /** What failed to load, as the object of "… could not be loaded". */
  what: string
  children: ReactNode
}) {
  if (loading) {
    return (
      <div className="space-y-stack" role="status" aria-label="Loading">
        <SkeletonCard lines={3} />
        <SkeletonCard rows={4} />
      </div>
    )
  }
  if (error) {
    return (
      <EmptyState
        title={`${what} could not be loaded`}
        action={
          <button type="button" className="btn-tinted" onClick={onRetry}>
            Try again
          </button>
        }
      >
        Check that the API is running, then try again.
      </EmptyState>
    )
  }
  return <>{children}</>
}

/** A labelled figure in a row of facts under a view's title. */
export function Fact({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-copy text-secondary">{label}</dt>
      <dd className="mt-0.5 flex items-baseline gap-1.5">
        <span className="big-num text-[1.75rem] text-ink">{value}</span>
        {hint && <span className="text-copy text-secondary">{hint}</span>}
      </dd>
    </div>
  )
}

export function Facts({ children }: { children: ReactNode }) {
  return <dl className="flex flex-wrap gap-x-10 gap-y-4">{children}</dl>
}

export function Busy({ show }: { show: boolean }) {
  if (!show) return null
  return <Loader2 aria-hidden size={14} className="animate-spin text-secondary" />
}
