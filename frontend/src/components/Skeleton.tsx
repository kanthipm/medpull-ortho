/** Shimmer loading bars — the app's only loading treatment. */

export function SkeletonLine({ className = '' }: { className?: string }) {
  return <div className={`shimmer rounded-control ${className}`} />
}

/** Mirrors SectionCard's surface exactly (`.panel`, one edge, no shadow) so a
 *  card does not change shape when its data lands. */
export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="panel p-block">
      <div className="space-y-tight">
        {Array.from({ length: lines }).map((_, i) => (
          <SkeletonLine key={i} className={`h-3.5 ${i === 0 ? 'w-1/4' : i % 2 ? 'w-full' : 'w-2/3'}`} />
        ))}
      </div>
    </div>
  )
}

/** Absolute overlay during a full refresh — opaque shimmer so nothing underneath shows. */
export function RefreshOverlay({ show }: { show: boolean }) {
  if (!show) return null
  return (
    <div aria-hidden className="absolute inset-0 z-20 animate-fadeIn">
      <div className="shimmer h-full w-full rounded-surface" />
    </div>
  )
}
