import { CalendarDays, CalendarRange } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useWorkspaces } from '../../api/workspaces'
import EmptyState from '../../components/EmptyState'
import { SettingsHero } from '../settings/Switch'

/** `/sports/teams/:teamId/calendar` — the Sports version's Calendar tab: the
 *  team's events with team load. The page head is in place; the calendar
 *  itself arrives with the Sports stream (docs/dev/showcase.md, "Sports").
 *  Until then it points at the board, whose week strip shows the next seven
 *  days. */
export default function TeamCalendarPage() {
  const { teamId = '' } = useParams()
  const team = useWorkspaces().data?.teams.find((t) => t.id === teamId)
  const name = team ? [team.org_name, team.name].filter(Boolean).join(' ') : null
  return (
    <div className="pb-10">
      <SettingsHero
        icon={<CalendarDays />}
        title="Calendar"
        badge={name && <span className="badge-ring">{name}</span>}
      >
        The team’s events will be here on one calendar, with the roster’s load beside them:
        practices, lifts, games and travel.
      </SettingsHero>

      <EmptyState
        className="rise mt-8"
        icon={<CalendarRange />}
        family="blue"
        title="For now, the week is on the board"
        action={
          <Link to={`/sports/teams/${encodeURIComponent(teamId)}`} className="btn-tinted">
            Open the board
          </Link>
        }
      >
        The board’s schedule strip shows the next seven days.
      </EmptyState>
    </div>
  )
}
