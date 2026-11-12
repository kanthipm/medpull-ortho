import type { CSSProperties, ReactNode } from 'react'
import type { TeamDashboard } from '../../api/sports'
import DotLine from '../patient/DotLine'
import { longDateOf, words } from './sportsFormat'

/** The head of a team's Calendar and Data pages, in the shell's sky window:
 *  the school's badge in its own colours, the page's name over the team's,
 *  and the facts line. The board has its own, larger head with the roster
 *  tile; this is the same identity at the size of a sub-page. */
export default function TeamHead({
  d,
  title,
  children,
}: {
  d: TeamDashboard
  title: string
  /** One line under the title saying what the page is. */
  children?: ReactNode
}) {
  const { team, org } = d
  return (
    <header data-hero className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
      {org && (
        <span
          className="badge-ring max-w-full"
          style={
            org.colors
              ? ({ background: org.colors.primary, color: '#fff', borderColor: org.colors.primary } as CSSProperties)
              : undefined
          }
        >
          <span
            aria-hidden
            className="dot-lime"
            style={org.colors ? ({ backgroundColor: org.colors.secondary, boxShadow: 'none' } as CSSProperties) : undefined}
          />
          <span className="min-w-0 truncate">
            {org.short_name ?? org.name} · {team.name}
          </span>
        </span>
      )}
      <h1 className="display-title mt-3 text-section text-ink lg:text-display">{title}</h1>
      <DotLine
        as="p"
        className="mt-2 text-copy-lg text-body"
        parts={[team.sport_label, `${team.season} ${words(team.phase).toLowerCase()}`, longDateOf(d.as_of)]}
      />
      {children && <p className="mt-2 max-w-[60ch] text-copy text-body">{children}</p>}
    </header>
  )
}
