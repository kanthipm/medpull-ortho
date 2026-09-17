import { ChevronRight } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router-dom'

/** The app's list anatomy on the web: a grouped card whose rows are
 *  separated by INSET hairlines that start where the text column starts.
 *
 *    <ListGroup aria-label="Next steps" inset="tile">
 *      <ListRow leading={<Tile family="blue" icon={<Phone />} />}
 *               title="Call the patient today"
 *               subtitle="Several signals are off baseline together"
 *               trailing={<button className="btn-tinted btn-sm">Log call</button>} />
 *    </ListGroup>
 *
 *  `inset`: 'tile' = 56px (16 + 28 + 12), 'avatar' = 60px (16 + 32 + 12),
 *  'none' = 16px, or a number. `embedded` drops the group's own border,
 *  fill and corners, for a list that sits inside a SectionCard with `flush`
 *  (the card then supplies the edge and the clipping). */
export function ListGroup({
  children,
  inset = 'tile',
  embedded = false,
  as: As = 'ul',
  className = '',
  style,
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledby,
}: {
  children: ReactNode
  inset?: 'tile' | 'avatar' | 'none' | number
  embedded?: boolean
  as?: 'ul' | 'ol' | 'div'
  className?: string
  style?: CSSProperties
  'aria-label'?: string
  'aria-labelledby'?: string
}) {
  const px =
    typeof inset === 'number' ? inset : inset === 'avatar' ? 60 : inset === 'none' ? 16 : 56
  return (
    <As
      role={As === 'div' ? 'list' : undefined}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledby}
      className={`card-group ${embedded ? '!rounded-none !border-0 !bg-transparent' : ''} ${className}`}
      style={{ ['--row-inset' as string]: `${px}px`, ...style }}
    >
      {children}
    </As>
  )
}

export type ListRowTint = 'none' | 'risk-high' | 'brand'

/** One list row: leading tile/avatar, title over subtitle, trailing content.
 *
 *  INTERACTION (R4). The row itself is an <li>/<div>, never a link. If `to`
 *  (router link), `href` (plain link) or `onClick` is given, the TITLE is the
 *  one interactive element and it carries `.stretched-link`, whose ::after
 *  covers the whole row (and draws the focus ring). Everything in `trailing`
 *  is lifted above that overlay (`.above-stretch`), so buttons stay separate
 *  controls — never nest a control inside the link.
 *
 *  TEXT. Title 16/500 ink (14/500 with `compact`). Subtitle 14/400 in the
 *  secondary colour: --muted on panel (5.393 light / 4.906 dark), --body on a
 *  tinted row (R8). `meta` is a 12/400 third line.
 *
 *  TINT. `risk-high` is the high-risk row (R1: put `.btn-on-tint` /
 *  `.btn-danger-on-tint` in `trailing`, and an Avatar with tier="high").
 *  `brand` is a brand-tint row with the on-tint text scope. */
export default function ListRow({
  leading,
  title,
  subtitle,
  meta,
  trailing,
  aside,
  children,
  to,
  href,
  onClick,
  linkState,
  chevron,
  tint = 'none',
  compact = false,
  subtitleLines = 1,
  wrapTitle = false,
  as: As = 'li',
  titleAs: TitleAs = 'span',
  className = '',
  titleClassName = '',
  'aria-current': ariaCurrent,
  linkLabel,
}: {
  leading?: ReactNode
  title: ReactNode
  subtitle?: ReactNode
  meta?: ReactNode
  /** Right-hand content: one button, a time, a status chip. */
  trailing?: ReactNode
  /** Non-interactive right-hand text (a time, a count), right-aligned and
   *  left UNDER the stretched link so clicking it still opens the row. */
  aside?: ReactNode
  /** Extra content under the text column (e.g. an inline editor). */
  children?: ReactNode
  to?: string
  href?: string
  onClick?: () => void
  linkState?: unknown
  /** Decorative chevron at the far right. Defaults to on when the row
   *  navigates (`to`/`href`) and has no `trailing`. */
  chevron?: boolean
  tint?: ListRowTint
  compact?: boolean
  /** Subtitle lines before truncating (1 = single-line ellipsis). */
  subtitleLines?: 1 | 2 | 3
  /** Let the title wrap instead of truncating, and below the `sm`
   *  breakpoint drop the trailing controls under the text column so the
   *  title keeps the row's width (step titles at phone width). */
  wrapTitle?: boolean
  as?: 'li' | 'div'
  /** Use 'h3' etc. when the row title is a heading in the outline. */
  titleAs?: 'span' | 'h3' | 'h4' | 'p'
  className?: string
  titleClassName?: string
  'aria-current'?: 'page' | 'true'
  /** Accessible name for the stretched link when `title` is not plain text. */
  linkLabel?: string
}) {
  const interactive = Boolean(to || href || onClick)
  const showChevron = chevron ?? (Boolean(to || href) && !trailing)
  const tintClass =
    tint === 'risk-high' ? 'row-risk-high' : tint === 'brand' ? 'on-tint bg-brand-tint' : ''
  const titleText = `${compact ? 'text-copy' : 'text-copy-lg'} font-medium text-ink ${titleClassName}`
  const linkClass = `stretched-link text-left outline-none ${titleText}`

  let titleNode: ReactNode = title
  if (to) {
    titleNode = (
      <Link to={to} state={linkState} className={linkClass} aria-label={linkLabel} aria-current={ariaCurrent}>
        {title}
      </Link>
    )
  } else if (href) {
    titleNode = (
      <a href={href} className={linkClass} aria-label={linkLabel} aria-current={ariaCurrent}>
        {title}
      </a>
    )
  } else if (onClick) {
    titleNode = (
      <button type="button" onClick={onClick} className={`${linkClass} cursor-pointer`} aria-label={linkLabel}>
        {title}
      </button>
    )
  }

  return (
    <As
      role={As === 'div' ? 'listitem' : undefined}
      className={`card-row ${interactive ? 'is-interactive' : ''} ${tintClass} ${
        compact ? '!min-h-[52px] !py-2.5' : ''
      } grid ${
        leading ? 'grid-cols-[auto_minmax(0,1fr)_auto]' : 'grid-cols-[minmax(0,1fr)_auto]'
      } items-center gap-x-3 ${className}`}
    >
      {leading && (
        <span className={`flex shrink-0 items-center ${wrapTitle ? 'max-sm:self-start max-sm:pt-0.5' : ''}`}>
          {leading}
        </span>
      )}
      <div className="min-w-0">
        <TitleAs className={`block ${wrapTitle ? 'text-pretty' : 'truncate'} ${titleText}`}>{titleNode}</TitleAs>
        {subtitle && (
          <div className={`${compact ? 'text-label' : 'text-copy'} mt-0.5 text-secondary ${
              subtitleLines === 1 ? 'truncate' : subtitleLines === 2 ? 'line-clamp-2' : 'line-clamp-3'
            }`}>
            {subtitle}
          </div>
        )}
        {meta && <div className="meta mt-0.5">{meta}</div>}
        {children && <div className="above-stretch mt-2">{children}</div>}
      </div>
      {/* Only real controls are lifted above the stretched link; the
          decorative chevron stays under it so clicking it still navigates. */}
      <div
        className={`flex shrink-0 items-center gap-3 ${
          wrapTitle
            ? `max-sm:mt-2 max-sm:justify-self-start max-sm:row-start-2 ${leading ? 'max-sm:col-start-2' : 'max-sm:col-start-1'}`
            : ''
        }`}
      >
        {aside && <div className="meta text-right tabular-nums">{aside}</div>}
        {trailing && <div className="above-stretch flex items-center gap-2">{trailing}</div>}
        {showChevron && <ChevronRight aria-hidden size={16} className="text-faint" />}
      </div>
    </As>
  )
}
