import type { ReactNode } from 'react'

export default function EmptyState({
  title,
  children,
}: {
  title: string
  children?: ReactNode
}) {
  return (
    <div className="rounded-card border border-line bg-panel px-6 py-10 text-center">
      <p className="text-[13.5px] font-semibold tracking-[-.01em] text-ink">{title}</p>
      {children && <div className="mt-1.5 text-[13px] font-medium text-faint">{children}</div>}
    </div>
  )
}
