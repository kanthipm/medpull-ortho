import type { ReactNode } from 'react'

/** Empty card. One edge only — `.panel`'s hairline ring; the old
 *  `border border-line shadow-card` pair drew two. */
export default function EmptyState({
  title,
  children,
}: {
  title: string
  children?: ReactNode
}) {
  return (
    <div className="panel px-region py-12 text-center">
      <p className="text-copy-lg font-medium text-ink">{title}</p>
      {children && <div className="mt-seam text-copy text-muted">{children}</div>}
    </div>
  )
}
