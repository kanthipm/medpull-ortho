import { ArrowDown, ArrowUp, Download } from 'lucide-react'
import { useState, type CSSProperties, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useTeamDashboard, type RosterAthlete, type TeamDashboard } from '../../api/sports'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import { AnsweredDot, AvailabilityPill, FlagChip, MiniSpark, SignedBar, StaffGuardrail, StatusChip } from './SportsBits'
import TeamHead from './TeamHead'
import {
  BAND_WORD,
  DASH,
  compareNullable,
  fmt,
  pct,
  sd,
  signed,
  type SortDir,
} from './sportsFormat'

/** `/sports/teams/:teamId/data` — what is under the board, across the
 *  roster. The board shows who needs a word this morning; this is the whole
 *  table behind it, one family of readings at a time (overnight recovery,
 *  the morning answers, load, jumps), every column sortable, and the lot as
 *  a spreadsheet. The numbers are each athlete's own, set against their own
 *  baseline where the column says so; nothing here ranks one athlete
 *  against another. */

type Family = 'recovery' | 'wellness' | 'load' | 'jumps'

const FAMILIES: { key: Family; label: string }[] = [
  { key: 'recovery', label: 'Overnight recovery' },
  { key: 'wellness', label: 'Morning answers' },
  { key: 'load', label: 'Load' },
  { key: 'jumps', label: 'Jumps and tests' },
]

interface Column {
  key: string
  label: string
  /** What the column is, for its header's title and the caption. */
  hint: string
  /** The number the column sorts by; null sorts last. */
  value: (r: RosterAthlete) => number | null
  cell: (r: RosterAthlete) => ReactNode
  /** The same reading for the spreadsheet. */
  csv: (r: RosterAthlete) => string | number | null
}

const num = (v: number | null | undefined, dp = 0) => (v == null ? <span className="text-secondary">{DASH}</span> : fmt(v, dp))

const COLUMNS: Record<Family, Column[]> = {
  recovery: [
    {
      key: 'readiness',
      label: 'Readiness',
      hint: '0 to 100 against the athlete’s own 28-day baselines; 50 is their normal',
      value: (r) => r.readiness,
      cell: (r) => (
        <span className="flex items-center gap-3">
          <span className="w-8 tabular-nums">{num(r.readiness)}</span>
          <MiniSpark values={r.readiness_series} label={`${r.first_name}’s readiness`} />
          {r.readiness_band && <span className="meta hidden xl:inline">{BAND_WORD[r.readiness_band]}</span>}
        </span>
      ),
      csv: (r) => r.readiness,
    },
    {
      key: 'sleep',
      label: 'Sleep',
      hint: 'Last night, in hours, with their own need',
      value: (r) => r.sleep_hours,
      cell: (r) =>
        r.sleep_hours == null ? (
          <span className="text-secondary">{DASH}</span>
        ) : (
          <>
            {fmt(r.sleep_hours, 1)} h <span className="text-secondary">of {fmt(r.sleep_need, 1)}</span>
          </>
        ),
      csv: (r) => r.sleep_hours,
    },
    {
      key: 'debt',
      label: 'Sleep debt',
      hint: 'The last seven nights’ shortfall against need, in hours',
      value: (r) => r.sleep_debt,
      cell: (r) => (r.sleep_debt == null ? num(null) : `${fmt(r.sleep_debt, 1)} h`),
      csv: (r) => r.sleep_debt,
    },
    {
      key: 'hrv',
      label: 'HRV',
      hint: 'Last night against their own baseline, in ms and in standard deviations',
      value: (r) => r.hrv_z,
      cell: (r) => (
        <span className="flex items-center gap-2.5">
          <span className="w-20 tabular-nums">
            {r.hrv_latest == null ? DASH : `${fmt(r.hrv_latest)} ms`}
            <span className="meta block">{r.hrv_baseline == null ? '' : `usual ${fmt(r.hrv_baseline)}`}</span>
          </span>
          <SignedBar z={r.hrv_z} />
          <span className="w-14 text-right tabular-nums text-secondary">{sd(r.hrv_z)}</span>
        </span>
      ),
      csv: (r) => r.hrv_latest,
    },
    {
      key: 'rhr',
      label: 'Resting HR',
      hint: 'Last night, and the change against their own baseline',
      value: (r) => r.rhr_delta,
      cell: (r) =>
        r.rhr_latest == null ? (
          num(null)
        ) : (
          <>
            {fmt(r.rhr_latest)} bpm <span className="text-secondary">{signed(r.rhr_delta, 1)}</span>
          </>
        ),
      csv: (r) => r.rhr_latest,
    },
    {
      key: 'days',
      label: 'Days on file',
      hint: 'Days with any reading: a baseline needs about four weeks',
      value: (r) => r.days_with_data,
      cell: (r) => num(r.days_with_data),
      csv: (r) => r.days_with_data,
    },
  ],
  wellness: [
    {
      key: 'answered',
      label: 'Today',
      hint: 'Whether the morning questions were answered today',
      value: (r) => (r.wellness_answered_today ? 1 : 0),
      cell: (r) => (
        <span className="inline-flex items-center gap-2">
          <AnsweredDot answered={r.wellness_answered_today} />
          <span className={r.wellness_answered_today ? 'text-ink' : 'text-secondary'}>
            {r.wellness_answered_today ? 'Answered' : 'Not yet'}
          </span>
        </span>
      ),
      csv: (r) => (r.wellness_answered_today ? 'yes' : 'no'),
    },
    {
      key: 'hooper',
      label: 'Hooper index',
      hint: 'Sleep, stress, fatigue and soreness, each 1 to 7, summed: lower is fresher',
      value: (r) => r.hooper,
      cell: (r) => num(r.hooper),
      csv: (r) => r.hooper,
    },
    {
      key: 'wellness_z',
      label: 'Against their usual',
      hint: 'Today’s answers against the athlete’s own average, in standard deviations',
      value: (r) => r.wellness_z,
      cell: (r) => (
        <span className="flex items-center gap-2.5">
          <SignedBar z={r.wellness_z} />
          <span className="tabular-nums text-secondary">{sd(r.wellness_z)}</span>
        </span>
      ),
      csv: (r) => r.wellness_z,
    },
    {
      key: 'soreness',
      label: 'Soreness',
      hint: 'This morning, 1 to 7',
      value: (r) => r.soreness,
      cell: (r) => (r.soreness == null ? num(null) : `${fmt(r.soreness)} of 7`),
      csv: (r) => r.soreness,
    },
    {
      key: 'flags',
      label: 'What the engine marked',
      hint: 'The engine’s own marks on this athlete today',
      value: (r) => r.flags.length,
      cell: (r) =>
        r.flags.length === 0 ? (
          <span className="text-secondary">Nothing</span>
        ) : (
          <span className="flex flex-wrap gap-1">
            {r.flags.slice(0, 3).map((f) => (
              <FlagChip key={f.key} flag={f} />
            ))}
            {r.flags.length > 3 && <span className="meta">+{r.flags.length - 3}</span>}
          </span>
        ),
      csv: (r) => r.flags.map((f) => f.text).join('; '),
    },
  ],
  load: [
    {
      key: 'load_week',
      label: 'This week',
      hint: 'Session load over the last seven days, in arbitrary units (effort × minutes)',
      value: (r) => r.load_week,
      cell: (r) => (r.load_week == null ? num(null) : `${fmt(r.load_week)} AU`),
      csv: (r) => r.load_week,
    },
    {
      key: 'load_change',
      label: 'Week on week',
      hint: 'This week’s load against the week before',
      value: (r) => r.load_change_pct,
      cell: (r) => (r.load_change_pct == null ? num(null) : pct(r.load_change_pct)),
      csv: (r) => r.load_change_pct,
    },
    {
      key: 'acwr',
      label: 'Acute:chronic',
      hint: 'The last 7 days against the last 28, as a ratio. A description of the week, not a forecast',
      value: (r) => r.acwr,
      cell: (r) => (r.acwr == null ? num(null) : fmt(r.acwr, 2)),
      csv: (r) => r.acwr,
    },
    {
      key: 'monotony',
      label: 'Monotony',
      hint: 'The week’s mean daily load over its spread: high when every day is the same',
      value: (r) => r.monotony,
      cell: (r) => (r.monotony == null ? num(null) : fmt(r.monotony, 1)),
      csv: (r) => r.monotony,
    },
    {
      key: 'availability',
      label: 'Status',
      hint: 'What the staff have set for today',
      value: (r) => (r.availability === 'available' ? 0 : r.availability === 'modified' ? 1 : 2),
      cell: (r) => (
        <span className="flex flex-wrap items-center gap-2">
          <AvailabilityPill availability={r.availability} label={r.availability_label} />
          {r.status_note && <span className="meta">{r.status_note}</span>}
        </span>
      ),
      csv: (r) => r.availability_label,
    },
  ],
  jumps: [
    {
      key: 'jumps_week',
      label: 'Jumps this week',
      hint: 'Counted by the wearable over the last seven days',
      value: (r) => r.jumps_week,
      cell: (r) => num(r.jumps_week),
      csv: (r) => r.jumps_week,
    },
    {
      key: 'cmj',
      label: 'Countermovement jump',
      hint: 'The latest test, in centimetres',
      value: (r) => r.cmj,
      cell: (r) => (r.cmj == null ? num(null) : `${fmt(r.cmj, 1)} cm`),
      csv: (r) => r.cmj,
    },
    {
      key: 'cmj_change',
      label: 'Against their baseline',
      hint: 'The latest jump against the athlete’s own baseline',
      value: (r) => r.cmj_change_pct,
      cell: (r) => (r.cmj_change_pct == null ? num(null) : pct(r.cmj_change_pct)),
      csv: (r) => r.cmj_change_pct,
    },
    {
      key: 'neuromuscular',
      label: 'Neuromuscular read',
      hint: 'The engine’s read of the jump trend',
      value: (r) => (r.neuromuscular === 'flag' ? 2 : r.neuromuscular === 'watch' ? 1 : r.neuromuscular === 'ok' ? 0 : null),
      cell: (r) => <StatusChip status={r.neuromuscular} />,
      csv: (r) => r.neuromuscular,
    },
    {
      key: 'injuries',
      label: 'In rehab',
      hint: 'An injury the athlete is being brought back from',
      value: (r) => r.injuries.length,
      cell: (r) =>
        r.injuries.length === 0 ? (
          <span className="text-secondary">No</span>
        ) : (
          r.injuries.map((i) => i.label).join(', ')
        ),
      csv: (r) => r.injuries.map((i) => i.label).join('; '),
    },
  ],
}

function csvCell(v: string | number | null): string {
  if (v == null) return ''
  const text = String(v)
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/** The whole roster, every column of every family, as one spreadsheet. */
function downloadCsv(d: TeamDashboard) {
  const columns = FAMILIES.flatMap((f) => COLUMNS[f.key])
  const head = ['Athlete', 'Position', 'Jersey', ...columns.map((c) => c.label)]
  const lines = d.roster.map((r) =>
    [r.name, r.position, r.jersey, ...columns.map((c) => c.csv(r))].map((v) => csvCell(v ?? null)).join(','),
  )
  const blob = new Blob([[head.map(csvCell).join(','), ...lines].join('\n')], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${d.team.id}-roster-${d.as_of}.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function TeamDataPage() {
  const { teamId = '' } = useParams()
  const board = useTeamDashboard(teamId)
  const [family, setFamily] = useState<Family>('recovery')
  const [sort, setSort] = useState<{ key: string; dir: SortDir } | null>(null)

  if (board.isLoading) {
    return (
      <div className="pb-4 pt-8">
        <header data-hero className="pt-3">
          <SkeletonLine className="h-4 w-40" />
          <SkeletonLine className="mt-6 h-11 w-72 max-w-full" />
        </header>
        <div className="mt-10" role="status" aria-label="Loading the roster’s data">
          <SkeletonCard rows={8} />
        </div>
      </div>
    )
  }
  if (board.isError || !board.data) {
    return (
      <EmptyState
        className="mt-10"
        title="This team couldn’t be loaded"
        action={
          <Link to="/sports" className="btn-tinted">
            Open a team
          </Link>
        }
      >
        Check the link, or pick a team from the menu at the top right.
      </EmptyState>
    )
  }

  const d = board.data
  const s = d.summary
  const columns = COLUMNS[family]
  const active = sort && columns.some((c) => c.key === sort.key) ? sort : null
  const sortBy = active ? columns.find((c) => c.key === active.key) : undefined
  const rows = sortBy
    ? [...d.roster].sort((a, b) => compareNullable(sortBy.value(a), sortBy.value(b), active!.dir) || a.name.localeCompare(b.name))
    : d.roster
  const days = d.roster.map((r) => r.days_with_data)
  const answered = d.roster.filter((r) => r.wellness_answered_today).length

  const onSort = (key: string) =>
    setSort((prev) => (prev?.key === key ? { key, dir: prev.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: 'desc' }))

  return (
    <div className="pb-10 pt-8">
      <TeamHead d={d} title="Data">
        The whole roster’s readings side by side: each athlete against their own baseline, never
        against each other.
      </TeamHead>

      <dl
        className="rise mt-8 grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-4"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        {[
          { label: 'On the roster', value: fmt(s.roster), hint: `${s.available} available · ${s.modified} modified · ${s.out} out` },
          { label: 'Mean readiness', value: s.mean_readiness == null ? DASH : fmt(s.mean_readiness), hint: '50 is each athlete’s own normal' },
          { label: 'Answered this morning', value: `${answered} of ${s.roster}`, hint: 'the four morning questions' },
          {
            label: 'Days on file',
            value: !days.length
              ? DASH
              : Math.min(...days) === Math.max(...days)
                ? fmt(days[0])
                : `${Math.min(...days)}–${Math.max(...days)}`,
            hint: days.length && Math.min(...days) === Math.max(...days) ? 'every athlete' : 'fewest to most, per athlete',
          },
        ].map((fact) => (
          <div key={fact.label} className="panel px-5 py-4">
            <dt className="text-label font-medium tracking-label text-secondary">{fact.label}</dt>
            <dd className="mt-1">
              <span className="big-num text-[1.75rem] text-ink">{fact.value}</span>
              <span className="meta block">{fact.hint}</span>
            </dd>
          </div>
        ))}
      </dl>

      <SectionCard
        className="rise mt-stack"
        style={{ '--rise-delay': '100ms' } as CSSProperties}
        title="The roster"
        aside={`${rows.length} athletes${sortBy ? ` · by ${sortBy.label.toLowerCase()}` : ' · the board’s order'}`}
        action={
          <button type="button" className="btn-plain btn-sm" onClick={() => downloadCsv(d)}>
            <Download aria-hidden size={16} /> Export CSV
          </button>
        }
        flush
      >
        <div className="px-5 pb-3">
          <SegmentedControl<Family>
            options={FAMILIES}
            value={family}
            onChange={setFamily}
            size="sm"
            role="radiogroup"
            aria-label="Which readings to show"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] border-separate border-spacing-0 text-left">
            <caption className="sr-only">
              The roster’s {FAMILIES.find((f) => f.key === family)?.label.toLowerCase()}: one row per athlete. A column
              header sorts by that column.
            </caption>
            <thead>
              <tr>
                <th scope="col" className="px-5 pb-2 text-label font-medium text-secondary">
                  Athlete
                </th>
                {columns.map((c) => {
                  const on = active?.key === c.key
                  return (
                    <th
                      key={c.key}
                      scope="col"
                      aria-sort={on ? (active!.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                      className="px-3 pb-2 text-label font-medium text-secondary"
                    >
                      <button
                        type="button"
                        title={c.hint}
                        onClick={() => onSort(c.key)}
                        className={`inline-flex items-center gap-1 rounded-[6px] hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${on ? 'text-ink' : ''}`}
                      >
                        {c.label}
                        {on && (active!.dir === 'asc' ? <ArrowUp aria-hidden size={12} /> : <ArrowDown aria-hidden size={12} />)}
                      </button>
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <th scope="row" className="border-t border-hairline py-2.5 pl-5 pr-3 text-left font-normal">
                    <Link
                      to={`/sports/teams/${encodeURIComponent(teamId)}/athletes/${encodeURIComponent(r.id)}`}
                      className="flex items-center gap-3 rounded-control-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                    >
                      <Avatar name={r.name} size="sm" />
                      <span className="min-w-0">
                        <span className="block truncate text-copy font-medium text-ink hover:underline">{r.name}</span>
                        <span className="meta block truncate">
                          {[r.position, r.jersey ? `#${r.jersey}` : null, r.class_year].filter(Boolean).join(' · ')}
                        </span>
                      </span>
                    </Link>
                  </th>
                  {columns.map((c) => (
                    <td key={c.key} className="border-t border-hairline px-3 py-2.5 text-copy tabular-nums text-ink">
                      {c.cell(r)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <ul className="space-y-0.5 border-t border-hairline px-5 py-3">
          {columns.map((c) => (
            <li key={c.key} className="meta">
              <span className="text-body">{c.label}:</span> {c.hint}.
            </li>
          ))}
        </ul>
      </SectionCard>

      <StaffGuardrail text={d.guardrail} className="mt-8 px-1" />
    </div>
  )
}
