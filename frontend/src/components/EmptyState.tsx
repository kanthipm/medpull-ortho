import { Inbox } from 'lucide-react'
import type { ReactNode } from 'react'
import Tile, { type TileFamily } from './Tile'

/** A friendly empty or error state: a centred large tile, a 16/600 ink title
 *  in plain words ("You're all caught up"), one line of secondary detail
 *  (--muted 5.393 light / 4.906 dark on panel; --body on tints) and an
 *  optional action (`.btn-tinted`). No dashed border.
 *
 *    <EmptyState title="No high-risk patients right now"
 *                icon={<ShieldCheck />} family="teal"
 *                action={<button className="btn-tinted">Show everyone</button>}>
 *      Anyone who needs you will show up here.
 *    </EmptyState>
 *
 *  `variant`: 'card' (default) sits in its own `.panel`; 'inline' has no
 *  surface, for use inside a SectionCard or a modal. */
export default function EmptyState({
  title,
  children,
  icon,
  family = 'blue',
  action,
  variant = 'card',
  className = '',
}: {
  title: string
  children?: ReactNode
  icon?: ReactNode
  family?: TileFamily
  action?: ReactNode
  variant?: 'card' | 'inline'
  className?: string
}) {
  return (
    <div
      className={`${variant === 'card' ? 'panel px-6 py-12' : 'px-4 py-8'} flex flex-col items-center text-center ${className}`}
    >
      <Tile family={family} size="lg" icon={icon ?? <Inbox />} />
      <p className="mt-4 text-copy-lg font-semibold text-ink">{title}</p>
      {children && (
        <div className="mt-1 max-w-[40ch] text-copy text-secondary">{children}</div>
      )}
      {action && <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  )
}
