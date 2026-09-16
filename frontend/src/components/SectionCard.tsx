import type { CSSProperties, ReactNode } from 'react'

/** Material elevated card — large corner radius, level-1 elevation, theme-aware.
 *  `sum` keeps a quiet blue wash for AI narrative panels. */
export default function SectionCard({
  spine,
  title,
  eyebrow,
  aside,
  sum = false,
  children,
  className = '',
  style,
}: {
  spine?: string
  title?: string
  eyebrow?: ReactNode
  aside?: ReactNode
  sum?: boolean
  children: ReactNode
  className?: string
  style?: CSSProperties
}) {
  const surface = sum
    ? 'bg-gradient-to-b from-panel to-[rgb(var(--sum-end))]'
    : 'bg-panel'
  return (
    <section
      style={style}
      className={`relative overflow-hidden rounded-card border border-line shadow-card ${surface} ${className}`}
    >
      {spine && <span aria-hidden className={`absolute inset-y-0 left-0 w-[4px] ${spine}`} />}
      <div className={`p-5 ${spine ? 'pl-[22px]' : ''}`}>
        {(title || eyebrow || aside) && (
          <div className="mb-3.5 flex items-baseline justify-between gap-3">
            <div>
              {eyebrow}
              {title && <h2 className="text-[16px] font-medium text-ink">{title}</h2>}
            </div>
            {aside}
          </div>
        )}
        {children}
      </div>
    </section>
  )
}
