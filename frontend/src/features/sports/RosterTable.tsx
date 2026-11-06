import { ChevronRight, Users } from 'lucide-react'
import { useState, type MouseEvent, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { usePrefetchAthlete, type AthleteFlag, type RosterAthlete } from '../../api/sports'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import type { ReadoutTone } from '../../components/MetricCluster'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import DotLine from '../patient/DotLine'
import { AnsweredDot, AvailabilityPill, FlagChip } from './SportsBits'
import { BAND_WORD, DASH, TONE_TEXT, bandTone, fmt, loadTone, pct, sd, signed, statusTone } from './sportsFormat'

type Filter = 'all' | 'attention' | 'unavailable'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'attention', label: 'Attention' },
  { key: 'unavailable', label: 'Out & modified' },
]

function matches(r: RosterAthlete, f: Filter): boolean {
  if (f === 'attention') return r.severity >= 1 || r.availability !== 'available'
  if (f === 'unavailable') return r.availability !== 'available'
  return true
}

function flagOf(r: RosterAthlete, key: string): AthleteFlag | undefined {
  return r.flags.find((f) => f.key === key)
}

function toneClass(tone: ReadoutTone | undefined): string {
  return tone ? TONE_TEXT[tone] : 'text-ink'
}

function athleteHref(teamId: string, id: string): string {
  return `/sports/teams/${teamId}/athletes/${id}`
}

/** Every figure on a row, read once so the table and the cards agree.
 *  Tones come from the engine's own flags (sleep, hrv, resting_hr,
 *  wellness, neuromuscular), the load step from its published threshold. */
function figures(r: RosterAthlete) {
  return {
    band: bandTone(r.readiness_band),
    sleep: {
      text: r.sleep_hours == null ? DASH : `${fmt(r.sleep_hours, 1)} / ${fmt(r.sleep_need, 1)} h`,
      tone: statusTone(flagOf(r, 'sleep')?.status),
    },
    hrv: { text: sd(r.hrv_z), tone: statusTone(flagOf(r, 'hrv')?.status) },
    rhr: { text: signed(r.rhr_delta, 1, ' bpm'), tone: statusTone(flagOf(r, 'resting_hr')?.status) },
    wellness: { text: sd(r.wellness_z), tone: statusTone(flagOf(r, 'wellness')?.status) },
    load: {
      text: r.load_week == null ? DASH : `${fmt(r.load_week)} AU`,
      change: pct(r.load_change_pct),
      tone: loadTone(r.load_change_pct),
    },
    jumps: fmt(r.jumps_week),
    cmj: {
      text: r.cmj == null ? DASH : `${fmt(r.cmj, 1)} cm`,
      change: r.cmj_change_pct == null ? null : `${pct(r.cmj_change_pct)} vs baseline`,
      tone: statusTone(flagOf(r, 'neuromuscular')?.status),
    },
    flagsTone: (r.flags.some((f) => f.status === 'flag')
      ? 'high'
      : r.flags.length > 0
        ? 'med'
        : undefined) as ReadoutTone | undefined,
  }
}

/** The full roster, already sorted by severity by the API. A table from
 *  1024px (the lower-priority columns step in at 1120 and 1200), cards
 *  below it. The row navigates; the name is the real link. */
export default function RosterTable({ rows, teamId }: { rows: RosterAthlete[]; teamId: string }) {
  const [filter, setFilter] = useState<Filter>('all')
  const shown = rows.filter((r) => matches(r, filter))
  return (
    <SectionCard
      flush
      title="Roster"
      aside={rows.length > 0 ? `${shown.length} of ${rows.length}` : undefined}
      action={
        rows.length > 0 ? (
          <SegmentedControl
            size="sm"
            role="radiogroup"
            aria-label="Filter the roster"
            options={FILTERS}
            value={filter}
            onChange={setFilter}
          />
        ) : undefined
      }
    >
      {rows.length === 0 ? (
        <EmptyState variant="inline" icon={<Users />} title="No athletes linked yet">
          Athletes appear here once they join the team in the app.
        </EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState variant="inline" icon={<Users />} family="teal" title="Nobody matches this filter">
          Switch back to All to see the full roster.
        </EmptyState>
      ) : (
        <>
          <div className="hidden lg:block">
            <Table rows={shown} teamId={teamId} />
          </div>
          <ul className="divide-y divide-hairline lg:hidden" aria-label="Roster">
            {shown.map((r) => (
              <AthleteCard key={r.id} r={r} teamId={teamId} />
            ))}
          </ul>
        </>
      )}
    </SectionCard>
  )
}

const TH = 'meta whitespace-nowrap px-2.5 pb-2 pt-1 text-left font-medium'
const TD = 'px-2.5 py-2.5 align-middle'
const NUM = 'whitespace-nowrap text-copy tabular-nums'
const AT_1120 = 'hidden min-[1120px]:table-cell'
const AT_1200 = 'hidden min-[1200px]:table-cell'

function Table({ rows, teamId }: { rows: RosterAthlete[]; teamId: string }) {
  const navigate = useNavigate()
  const prefetch = usePrefetchAthlete(teamId)
  const open = (e: MouseEvent<HTMLTableRowElement>, id: string) => {
    // The name is a real link; a click on it navigates on its own.
    if ((e.target as HTMLElement).closest('a, button')) return
    navigate(athleteHref(teamId, id))
  }
  return (
    <table className="w-full border-collapse">
      <thead>
        <tr>
          <th scope="col" className={`${TH} pl-5`}>Athlete</th>
          <th scope="col" className={TH}>Availability</th>
          <th scope="col" className={`${TH} text-right`}>Readiness</th>
          <th scope="col" className={`${TH} text-right`}>Sleep / need</th>
          <th scope="col" className={`${TH} text-right`}>HRV</th>
          <th scope="col" className={`${TH} ${AT_1120} text-right`}>Resting HR</th>
          <th scope="col" className={`${TH} ${AT_1120} text-right`}>Wellness</th>
          <th scope="col" className={`${TH} text-right`}>Load, week</th>
          <th scope="col" className={`${TH} ${AT_1200} text-right`}>Jumps</th>
          <th scope="col" className={`${TH} ${AT_1200} text-right`}>CMJ</th>
          <th scope="col" className={`${TH} text-right`}>Flags</th>
          <th scope="col" className={`${TH} pr-5`}>
            <span className="sr-only">Open</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const f = figures(r)
          return (
            <tr
              key={r.id}
              className="card-row is-interactive cursor-pointer border-t border-hairline"
              onClick={(e) => open(e, r.id)}
              onPointerEnter={() => prefetch(r.id)}
            >
              <td className={`${TD} pl-5`}>
                <div className="flex items-center gap-2.5">
                  <Avatar name={r.name} size="sm" tier={r.severity >= 2 ? 'high' : undefined} />
                  <div className="min-w-0">
                    <Link
                      to={athleteHref(teamId, r.id)}
                      onFocus={() => prefetch(r.id)}
                      className="block truncate text-copy font-medium text-ink"
                    >
                      {r.name}
                    </Link>
                    <DotLine
                      as="p"
                      className="meta truncate"
                      parts={[r.position, r.jersey ? `#${r.jersey}` : null, r.class_year]}
                    />
                  </div>
                </div>
              </td>
              <td className={TD}>
                <AvailabilityPill availability={r.availability} label={r.availability_label} />
              </td>
              <td className={`${TD} text-right`}>
                <span className={`text-copy-lg font-medium tabular-nums ${toneClass(f.band)}`}>
                  {fmt(r.readiness)}
                </span>
                {r.readiness_band && <span className="sr-only">, {BAND_WORD[r.readiness_band]}</span>}
              </td>
              <td className={`${TD} text-right`}>
                <span className={`${NUM} ${toneClass(f.sleep.tone)}`}>{f.sleep.text}</span>
              </td>
              <td className={`${TD} text-right`}>
                <span className={`${NUM} ${toneClass(f.hrv.tone)}`}>{f.hrv.text}</span>
              </td>
              <td className={`${TD} ${AT_1120} text-right`}>
                <span className={`${NUM} ${toneClass(f.rhr.tone)}`}>{f.rhr.text}</span>
              </td>
              <td className={`${TD} ${AT_1120} text-right`}>
                <span className="inline-flex items-center gap-2">
                  <span className={`${NUM} ${toneClass(f.wellness.tone)}`}>{f.wellness.text}</span>
                  <AnsweredDot answered={r.wellness_answered_today} />
                </span>
              </td>
              <td className={`${TD} text-right`}>
                <span className={`${NUM} block text-ink`}>{f.load.text}</span>
                <span className={`meta block whitespace-nowrap tabular-nums ${f.load.tone ? TONE_TEXT[f.load.tone] : ''}`}>
                  {f.load.change}
                </span>
              </td>
              <td className={`${TD} ${AT_1200} text-right`}>
                <span className={`${NUM} text-ink`}>{f.jumps}</span>
              </td>
              <td className={`${TD} ${AT_1200} text-right`}>
                <span className={`${NUM} block ${toneClass(f.cmj.tone)}`}>{f.cmj.text}</span>
                {f.cmj.change && <span className="meta block whitespace-nowrap tabular-nums">{f.cmj.change}</span>}
              </td>
              <td className={`${TD} text-right`}>
                <span
                  className={`${NUM} ${f.flagsTone ? TONE_TEXT[f.flagsTone] : 'text-secondary'}`}
                  title={r.flags.map((x) => x.text).join(' · ') || undefined}
                >
                  {r.flags.length}
                </span>
                {r.flags.length > 0 && (
                  <span className="sr-only">: {r.flags.map((x) => x.text).join(', ')}</span>
                )}
              </td>
              <td className={`${TD} pr-5`}>
                <ChevronRight aria-hidden size={16} className="text-faint" />
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

function Cell({ label, value, tone }: { label: string; value: ReactNode; tone?: ReadoutTone }) {
  return (
    <div className="min-w-0">
      <dt className="meta truncate">{label}</dt>
      <dd className={`truncate text-copy tabular-nums ${toneClass(tone)}`}>{value}</dd>
    </div>
  )
}

/** The same row as a card, under 1024px. */
function AthleteCard({ r, teamId }: { r: RosterAthlete; teamId: string }) {
  const f = figures(r)
  return (
    <li className="card-row is-interactive">
      <div className="flex items-center gap-3">
        <Avatar name={r.name} tier={r.severity >= 2 ? 'high' : undefined} />
        <div className="min-w-0 flex-1">
          <Link
            to={athleteHref(teamId, r.id)}
            className="stretched-link block truncate text-copy-lg font-medium text-ink"
          >
            {r.name}
          </Link>
          <DotLine
            as="p"
            className="meta truncate"
            parts={[r.position, r.jersey ? `#${r.jersey}` : null, r.class_year]}
          />
        </div>
        <AvailabilityPill availability={r.availability} label={r.availability_label} />
        <span className={`text-title font-medium tabular-nums ${toneClass(f.band)}`}>
          {fmt(r.readiness)}
          <span className="sr-only">
            {' '}
            readiness{r.readiness_band ? `, ${BAND_WORD[r.readiness_band]}` : ''}
          </span>
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-2 sm:grid-cols-4 md:grid-cols-7">
        <Cell label="Sleep / need" value={f.sleep.text} tone={f.sleep.tone} />
        <Cell label="HRV" value={f.hrv.text} tone={f.hrv.tone} />
        <Cell label="Resting HR" value={f.rhr.text} tone={f.rhr.tone} />
        <Cell
          label="Wellness"
          value={
            <span className="inline-flex items-center gap-1.5">
              {f.wellness.text}
              <AnsweredDot answered={r.wellness_answered_today} />
            </span>
          }
          tone={f.wellness.tone}
        />
        <Cell
          label="Load, week"
          value={
            <>
              {f.load.text}{' '}
              <span className={`text-label ${f.load.tone ? TONE_TEXT[f.load.tone] : 'text-secondary'}`}>
                {f.load.change}
              </span>
            </>
          }
        />
        <Cell label="Jumps" value={f.jumps} />
        <Cell
          label="CMJ"
          value={
            <>
              {f.cmj.text}
              {f.cmj.change && <span className="text-label text-secondary"> {pct(r.cmj_change_pct)}</span>}
            </>
          }
          tone={f.cmj.tone}
        />
      </dl>
      {r.flags.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {r.flags.map((x, i) => (
            <FlagChip key={`${x.key}-${i}`} flag={x} />
          ))}
        </div>
      )}
    </li>
  )
}
