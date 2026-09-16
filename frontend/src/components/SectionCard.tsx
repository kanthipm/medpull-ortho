import type { CSSProperties, ReactNode } from 'react'

/** THE card surface for the console. Everything that is a card is this
 *  component, or `.panel` if it cannot be.
 *
 *  Separation is ONE mechanism: `.panel` is `rounded-surface border
 *  border-line bg-panel` — a 1px hairline and a fill, and nothing else. Never
 *  add a second edge alongside it (a ring or another border): that pair drew
 *  two 1px edges at 13 sites and read as a heavy rule. A card that is also a
 *  button adds `border-line-strong`, since its edge is then part of how it
 *  reads as pressable. No shadow on a card either; the ambient
 *  `shadow-overlay` belongs to floating surfaces only (Modal, Toast,
 *  NotificationsPopover), which use `.overlay`.
 *
 *  `sum` is the AI-narrative variant. It is a SOLID `bg-brand-tint`, not the
 *  old panel→--sum-end gradient: a wash's real contrast depends on which
 *  ground shows through it, so every tint in this system is a solid. Text on
 *  it measures --body 6.237:1 light / 5.514:1 dark and --ink 15.9 / 14.3. */
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
  return (
    <section
      style={style}
      className={`panel relative overflow-hidden ${sum ? 'bg-brand-tint' : ''} ${className}`}
    >
      {spine && <span aria-hidden className={`absolute inset-y-0 left-0 w-el ${spine}`} />}
      <div className={`p-block ${spine ? 'pl-region' : ''}`}>
        {(title || eyebrow || aside) && (
          <div className="mb-tight flex items-baseline justify-between gap-tight">
            <div>
              {eyebrow}
              {title && <h2 className="text-copy-lg font-medium text-ink">{title}</h2>}
            </div>
            {aside}
          </div>
        )}
        {children}
      </div>
    </section>
  )
}
