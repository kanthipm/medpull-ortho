import { Database, Table2 } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { useWorkspaces } from '../../api/workspaces'
import EmptyState from '../../components/EmptyState'
import { SettingsHero } from '../settings/Switch'

/** `/sports/teams/:teamId/data` — the Sports version's Data tab: what is
 *  under the board, across the roster. The page head is in place; the tables
 *  arrive with the Sports stream (docs/dev/showcase.md, "Sports"). Until
 *  then it points at the board, where each athlete's page holds the same
 *  readings one person at a time. */
export default function TeamDataPage() {
  const { teamId = '' } = useParams()
  const team = useWorkspaces().data?.teams.find((t) => t.id === teamId)
  const name = team ? [team.org_name, team.name].filter(Boolean).join(' ') : null
  return (
    <div className="pb-10">
      <SettingsHero
        icon={<Database />}
        title="Data"
        badge={name && <span className="badge-ring">{name}</span>}
      >
        The roster’s data will be here side by side: overnight signals, wellness answers, tests,
        jumps and the devices they come from.
      </SettingsHero>

      <EmptyState
        className="rise mt-8"
        icon={<Table2 />}
        family="blue"
        title="For now, it is on each athlete’s page"
        action={
          <Link to={`/sports/teams/${encodeURIComponent(teamId)}`} className="btn-tinted">
            Open the board
          </Link>
        }
      >
        Open an athlete from the board for their signals, wellness, sessions and tests.
      </EmptyState>
    </div>
  )
}
