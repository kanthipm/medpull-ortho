import { ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'
import { usePrefetchAthlete, type RosterAthlete } from '../../api/sports'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import { ListGroup } from '../../components/ListRow'
import SectionCard from '../../components/SectionCard'
import DotLine from '../patient/DotLine'
import { AvailabilityPill, FlagChip, MiniSpark } from './SportsBits'
import { BAND_WORD, TONE_TEXT, bandTone, fmt } from './sportsFormat'

/** Row grid (R4). At ≥1024px six fixed columns so names, pills, scores,
 *  flags and the staff action each share one x:
 *
 *    [avatar 36] [name 196] [availability 104] [readiness 156] [flags 1fr] [action 200]
 *
 *  Narrower, the score, flags and action wrap under the name. The row is an
 *  <li>; the athlete's name is its only link, stretched over the row. */
const ROW_GRID = [
  'grid items-center gap-x-3 gap-y-2',
  "grid-cols-[36px_minmax(0,1fr)_auto] [grid-template-areas:'av_id_st'_'._rd_rd'_'._fl_fl'_'._ac_ac']",
  "lg:grid-cols-[36px_196px_104px_156px_minmax(0,1fr)_200px] lg:[grid-template-areas:'av_id_st_rd_fl_ac']",
].join(' ')

const MAX_CHIPS = 3

export default function AttentionList({ rows, teamId }: { rows: RosterAthlete[]; teamId: string }) {
  const prefetch = usePrefetchAthlete(teamId)
  return (
    <SectionCard
      flush
      title="Needs attention"
      aside={rows.length > 0 ? `${rows.length} ${rows.length === 1 ? 'athlete' : 'athletes'}` : undefined}
    >
      {rows.length === 0 ? (
        <EmptyState variant="inline" icon={<ShieldCheck />} family="teal" title="Nobody needs a look this morning">
          Flags and availability changes land here.
        </EmptyState>
      ) : (
        <ListGroup embedded inset="avatar" aria-label="Athletes needing attention">
          {rows.map((r) => (
            <AttentionRow key={r.id} r={r} teamId={teamId} onWarm={prefetch} />
          ))}
        </ListGroup>
      )}
    </SectionCard>
  )
}

function AttentionRow({
  r,
  teamId,
  onWarm,
}: {
  r: RosterAthlete
  teamId: string
  onWarm: (id: string) => void
}) {
  const tone = bandTone(r.readiness_band)
  const extra = r.flags.length - MAX_CHIPS
  const action = r.staff_action ?? r.status_note
  const flagged = r.severity >= 2
  return (
    <li
      className={`card-row ${ROW_GRID}`}
      onPointerEnter={() => onWarm(r.id)}
      onFocus={() => onWarm(r.id)}
    >
      <span className="flex [grid-area:av]">
        <Avatar name={r.name} tier={flagged ? 'high' : undefined} />
      </span>

      <div className="min-w-0 [grid-area:id]">
        <Link
          to={`/sports/teams/${teamId}/athletes/${r.id}`}
          className="stretched-link block truncate text-copy-lg font-medium text-ink"
        >
          {r.name}
          {flagged && <span className="sr-only">, flagged</span>}
        </Link>
        <DotLine
          as="p"
          className="meta mt-0.5 truncate"
          parts={[r.position, r.jersey ? `#${r.jersey}` : null, r.class_year]}
        />
      </div>

      <div className="[grid-area:st]">
        <AvailabilityPill availability={r.availability} label={r.availability_label} />
      </div>

      <div className="flex items-center gap-2.5 [grid-area:rd]">
        <span
          className={`w-9 shrink-0 text-right text-copy-lg font-medium tabular-nums ${
            tone ? TONE_TEXT[tone] : 'text-ink'
          }`}
        >
          {fmt(r.readiness)}
          <span className="sr-only">
            {' '}
            readiness{r.readiness_band ? `, ${BAND_WORD[r.readiness_band]}` : ''}
          </span>
        </span>
        <MiniSpark values={r.readiness_series} label="Readiness, 14 days" />
      </div>

      <div className="flex min-w-0 flex-wrap items-center gap-1.5 [grid-area:fl]">
        {r.flags.length === 0 ? (
          <span className="meta">No flags</span>
        ) : (
          r.flags.slice(0, MAX_CHIPS).map((f, i) => <FlagChip key={`${f.key}-${i}`} flag={f} />)
        )}
        {extra > 0 && <span className="meta">+{extra} more</span>}
      </div>

      <div className="min-w-0 [grid-area:ac]">
        {action ? (
          <p className="line-clamp-2 text-copy text-ink" title={action}>
            {action}
          </p>
        ) : (
          <p className="meta">No action suggested</p>
        )}
      </div>
    </li>
  )
}
