import { useId, type CSSProperties, type ReactNode } from 'react'

/** THE card surface for the console, shaped like the app's cards: 20px
 *  corners, a 1px --line edge, an opaque --panel fill, and a small sentence-
 *  case header ("Your recovery", "Today") with an optional plain action on
 *  the right ("Details").
 *
 *  HEADER. Title 14/500 in the secondary colour (--muted 5.393 light / 4.906
 *  dark on panel; --body 6.237 / 5.513 on the brand tint, R8). An optional
 *  leading `icon` (a small Tile), an `aside` (.meta — timestamps, counts) and
 *  an `action` (render a `.btn-plain btn-sm`). No rule under the title.
 *
 *  VARIANTS.
 *    sum / tint  brand-tint card (briefing, recovery summary). Ink prose on
 *                it is 15.871 light / 14.255 dark; secondary text is --body.
 *    flush       no body padding and clipped corners, so a ListGroup
 *                (`embedded`) or a table bleeds to the edge.
 *    clip        clip children to the 20px curve without removing padding.
 *
 *  Not clipped by default: a menu or tooltip inside must still portal (R5),
 *  but an unported one is not cut off in the meantime.
 *
 *  NARROW. The header wraps: when the title and the aside do not fit on one
 *  line, the aside drops under the title instead of truncating it. */
export default function SectionCard({
  title,
  eyebrow,
  aside,
  action,
  icon,
  sum = false,
  tint = false,
  flush = false,
  clip = false,
  headingLevel = 2,
  children,
  className = '',
  bodyClassName = '',
  style,
  id,
  'aria-label': ariaLabel,
}: {
  title?: ReactNode
  eyebrow?: ReactNode
  /** Right-aligned secondary info (timestamp, count). Rendered as .meta when
   *  it is a string. */
  aside?: ReactNode
  /** Right-aligned header action; pass a `.btn-plain btn-sm` button/link. */
  action?: ReactNode
  /** Leading glyph for the header, e.g. <Tile size="sm" family="teal" …/>. */
  icon?: ReactNode
  /** Brand-tint AI-narrative card. Same as `tint`. */
  sum?: boolean
  tint?: boolean
  flush?: boolean
  clip?: boolean
  headingLevel?: 2 | 3
  children: ReactNode
  className?: string
  bodyClassName?: string
  style?: CSSProperties
  id?: string
  'aria-label'?: string
}) {
  const headingId = useId()
  const tinted = sum || tint
  const hasHeader = Boolean(title || eyebrow || aside || action)
  const H = headingLevel === 3 ? 'h3' : 'h2'
  const surface = tinted ? 'card-tint' : 'panel'
  const clipped = flush || clip ? 'clip-surface' : ''

  return (
    <section
      id={id}
      style={style}
      aria-labelledby={title && !ariaLabel ? headingId : undefined}
      aria-label={ariaLabel}
      className={`${surface} ${clipped} relative ${className}`}
    >
      {hasHeader && (
        <div
          className={`flex min-h-[44px] flex-wrap items-center justify-between gap-x-3 gap-y-1 px-5 pt-4 ${
            flush ? 'pb-2' : 'pb-1'
          }`}
        >
          <div className="flex min-w-0 items-center gap-2">
            {icon}
            <div className="min-w-0">
              {eyebrow}
              {title && (
                <H id={headingId} className="truncate text-copy font-medium text-secondary">
                  {title}
                </H>
              )}
            </div>
          </div>
          {(aside || action) && (
            <div className="flex shrink-0 items-center gap-3">
              {aside && (typeof aside === 'string' ? <span className="meta">{aside}</span> : aside)}
              {action}
            </div>
          )}
        </div>
      )}
      <div
        className={`${flush ? '' : hasHeader ? 'px-5 pb-5 pt-2' : 'p-5'} ${bodyClassName}`}
      >
        {children}
      </div>
    </section>
  )
}
