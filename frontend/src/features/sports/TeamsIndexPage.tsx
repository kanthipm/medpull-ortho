import { ChevronRight, Users } from 'lucide-react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { useSportsTeams, type SportsOrg } from '../../api/sports'
import EmptyState from '../../components/EmptyState'
import ListRow, { ListGroup } from '../../components/ListRow'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import Tile, { type TileFamily } from '../../components/Tile'
import { longDate } from '../../lib/format'
import DotLine from '../patient/DotLine'
import { StaffGuardrail } from './SportsBits'
import { words } from './sportsFormat'

/** The demo opens on this team. */
const DEFAULT_TEAM = { org: 'rice', team: 'rice-mbb' }

const SPORT_FAMILY: Record<string, TileFamily> = {
  basketball: 'teal',
  soccer: 'blue',
  tennis: 'violet',
}

/** Every organisation as a grouped list of its teams, straight into a
 *  team's board. */
export default function TeamsIndexPage() {
  const { data, isLoading, isError } = useSportsTeams()
  // Rice first (the demo), then the rest in the API's order.
  const orgs = [...(data?.orgs ?? [])].sort(
    (a, b) => Number(b.id === DEFAULT_TEAM.org) - Number(a.id === DEFAULT_TEAM.org),
  )
  const teams = orgs.reduce((n, o) => n + o.teams.length, 0)
  const start = orgs.flatMap((o) => o.teams).find((t) => t.id === DEFAULT_TEAM.team) ?? null

  return (
    <div className="pb-4 pt-8">
      <header data-hero className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <p className="micro">Teams</p>
        <h1 className="display-title mt-2 text-section text-ink lg:text-display">Team boards</h1>
        {data ? (
          <DotLine
            as="p"
            className="mt-3 text-copy-lg text-body"
            parts={[
              longDate(),
              `${orgs.length} ${orgs.length === 1 ? 'organisation' : 'organisations'}`,
              `${teams} ${teams === 1 ? 'team' : 'teams'}`,
            ]}
          />
        ) : (
          <SkeletonLine className="mt-4 h-4 w-72 max-w-full" />
        )}
        {start && (
          <div className="mt-6">
            <Link to={`/sports/teams/${start.id}`} className="btn-filled">
              <span aria-hidden className="dot-lime" />
              Open {orgs[0].short_name} {start.name}
              <ChevronRight aria-hidden size={16} />
            </Link>
          </div>
        )}
      </header>

      {isLoading && (
        <div className="mt-10 space-y-stack" role="status" aria-label="Loading teams">
          <SkeletonCard rows={4} />
          <SkeletonCard rows={2} />
        </div>
      )}
      {(isError || (data && orgs.length === 0)) && (
        <div className="mt-10">
          <EmptyState icon={<Users />} title={isError ? 'Teams couldn’t be loaded' : 'No teams yet'}>
            {isError
              ? 'Check that the API is running, then reload this page.'
              : 'Organisations and teams appear here once they are set up.'}
          </EmptyState>
        </div>
      )}
      {orgs.length > 0 && (
        <div className="mt-10 space-y-stack">
          {orgs.map((org, i) => (
            <OrgCard key={org.id} org={org} index={i + 1} />
          ))}
        </div>
      )}

      <StaffGuardrail className="mt-8" />
    </div>
  )
}

function OrgCard({ org, index }: { org: SportsOrg; index: number }) {
  return (
    <SectionCard
      flush
      title={org.name}
      className="rise"
      style={{ '--rise-delay': `${index * 55}ms` } as CSSProperties}
      aside={
        <DotLine
          className="meta"
          parts={[org.level_label, org.conference, [org.city, org.state].filter(Boolean).join(', ')]}
        />
      }
    >
      {org.colors && (
        <div aria-hidden className="mx-4 mb-1 mt-3 flex h-1.5 w-20 overflow-hidden rounded-full">
          <span className="flex-1" style={{ backgroundColor: org.colors.primary }} />
          <span className="flex-1" style={{ backgroundColor: org.colors.secondary }} />
        </div>
      )}
      <ListGroup embedded inset="tile" aria-label={`${org.name} teams`}>
        {org.teams.map((t) => {
          const n = t.roster ?? 0
          return (
            <ListRow
              key={t.id}
              to={`/sports/teams/${t.id}`}
              leading={<Tile family={SPORT_FAMILY[t.sport] ?? 'teal'} icon={<Users />} />}
              title={t.name}
              subtitle={<DotLine parts={[t.sport_label, t.season, words(t.phase).toLowerCase()]} />}
              aside={n === 0 ? 'No athletes linked' : `${n} ${n === 1 ? 'athlete' : 'athletes'}`}
            />
          )
        })}
      </ListGroup>
    </SectionCard>
  )
}
