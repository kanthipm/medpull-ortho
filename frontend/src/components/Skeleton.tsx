/** Shimmer loading shapes — the app's only loading treatment. The shimmer
 *  stops under Reduce Motion (index.css) and stays a flat soft fill. */

export function SkeletonLine({ className = '' }: { className?: string }) {
  return <div aria-hidden className={`shimmer rounded-pill ${className}`} />
}

/** Mirrors SectionCard's surface (`.panel`, 20px corners, the small header
 *  line then body lines) so a card does not change shape when data lands.
 *  `rows` renders ListRow-shaped placeholders (tile + two lines) instead. */
export function SkeletonCard({
  lines = 3,
  rows,
  className = '',
}: {
  lines?: number
  rows?: number
  className?: string
}) {
  return (
    <div role="status" aria-label="Loading" className={`panel ${className}`}>
      <div className="px-5 pb-2 pt-5">
        <SkeletonLine className="h-3 w-28" />
      </div>
      {rows ? (
        <div className="pb-2">
          {Array.from({ length: rows }).map((_, i) => (
            <div key={i} className="flex min-h-[60px] items-center gap-3 px-4 py-3">
              <div aria-hidden className="shimmer h-7 w-7 shrink-0 rounded-tile" />
              <div className="flex-1 space-y-2">
                <SkeletonLine className={`h-3.5 ${i % 2 ? 'w-1/2' : 'w-2/3'}`} />
                <SkeletonLine className="h-3 w-1/3" />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-3 px-5 pb-5 pt-2">
          {Array.from({ length: lines }).map((_, i) => (
            <SkeletonLine
              key={i}
              className={`h-3.5 ${i === lines - 1 && lines > 1 ? 'w-2/3' : i % 2 ? 'w-5/6' : 'w-full'}`}
            />
          ))}
        </div>
      )}
    </div>
  )
}

/** Absolute overlay during a full refresh — opaque shimmer so nothing
 *  underneath shows. The parent must be `relative` (SectionCard is); the
 *  20px corners match the card. */
export function RefreshOverlay({ show }: { show: boolean }) {
  if (!show) return null
  return (
    <div aria-hidden className="absolute inset-0 z-20 animate-fadeIn">
      <div className="shimmer h-full w-full rounded-surface" />
    </div>
  )
}
