import { useQuery } from '@tanstack/react-query'
import { Users } from 'lucide-react'
import type { CSSProperties } from 'react'
import { Navigate } from 'react-router-dom'
import { fetchSportsTeams, sportsKeys, type SportsOrg } from '../../api/sports'
import { useWorkspaces } from '../../api/workspaces'
import EmptyState from '../../components/EmptyState'
import { landingSubject } from '../../components/layout/workspaceRows'
import ListRow, { ListGroup } from '../../components/ListRow'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import Tile, { type TileFamily } from '../../components/Tile'
import { longDate } from '../../lib/format'
import DotLine from '../patient/DotLine'
import { StaffGuardrail } from './SportsBits'
import { words } from './sportsFormat'

const SPORT_FAMILY: Record<string, TileFamily> = {
  basketball: 'teal',
  soccer: 'blue',
  tennis: 'violet',
}

/** `/sports` — names no team, so it forwards to the team that was open
 *  last on this browser, else the first one the workspace menu lists (a team
 *  with a roster). Sports is one team at a time, picked from that menu.
 *
 *  Only where the menu has no team to offer does this page show itself:
 *  every organisation this console can see as a grouped list of its teams,
 *  each straight into its board, or one line saying there are none. */
export default function TeamsIndexPage() {
  const workspaces = useWorkspaces()
  const landing = workspaces.data ? landingSubject(workspaces.data, 'sports') : null
  // The index is read only once it is known there is no team to forward to.
  const settled = workspaces.data != null || workspaces.isError
  const { data, isLoading, isError } = useQuery({
    queryKey: sportsKeys.teams,
    queryFn: fetchSportsTeams,
    enabled: settled && !landing,
  })

  if (landing) return <Navigate to={`/sports/teams/${encodeURIComponent(landing)}`} replace />
  if (!settled) {
    return (
      <div className="space-y-stack pb-4 pt-8" role="status" aria-label="Loading">
        <SkeletonCard lines={3} />
      </div>
    )
  }

  const orgs = data?.orgs ?? []
  const teams = orgs.reduce((n, o) => n + o.teams.length, 0)

  return (
    <div className="pb-4 pt-8">
      <header data-hero className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <p className="micro">Sports</p>
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
          !isError && <SkeletonLine className="mt-4 h-4 w-72 max-w-full" />
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
          <EmptyState
            icon={<Users />}
            title={isError ? 'Teams couldn’t be loaded' : 'No teams to show on this deployment'}
          >
            {isError
              ? 'Check that the API is running, then reload this page.'
              : 'Sports is the version for a team’s performance and medical staff: the board, the calendar and the roster’s data. No team is set up here.'}
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
