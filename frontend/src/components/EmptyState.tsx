import type { ReactNode } from 'react'

export default function EmptyState({
  title,
  children,
}: {
  title: string
  children?: ReactNode
}) {
  return (
    <div className="rounded-card border border-line bg-panel px-6 py-12 text-center shadow-card">
      <p className="text-[16px] font-medium text-ink">{title}</p>
      {children && <div className="mt-2 text-[14px] text-muted">{children}</div>}
    </div>
  )
}
