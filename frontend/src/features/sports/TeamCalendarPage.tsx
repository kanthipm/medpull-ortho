import { CalendarDays, ChevronLeft, ChevronRight, MapPin, Plus, Trash2 } from 'lucide-react'
import { useState, type CSSProperties, type FormEvent } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../../api/client'
import {
  useAddTeamEvent,
  useDeleteTeamEvent,
  useTeamDashboard,
  useTeamEvents,
  type TeamEvent,
  type TeamLoadPoint,
} from '../../api/sports'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'
import { StaffGuardrail } from './SportsBits'
import TeamHead from './TeamHead'
import TeamLoadChart from './TeamLoadChart'
import {
  addDays,
  dayNumber,
  daysBetween,
  eventKind,
  fmt,
  inMonth,
  isGame,
  longDateOf,
  monthName,
  monthStart,
  nextGame,
  opponentLine,
  timeLabel,
  toIso,
  weekStart,
  weekday,
} from './sportsFormat'

/** `/sports/teams/:teamId/calendar` — the team's calendar with its load
 *  under it. A month at a time: each day lists what is on it (games,
 *  practices, lifts, travel, days off), and a day that has passed carries a
 *  bar for the roster's session load that day, so a heavy week before a
 *  game is something the staff can see on one page. Picking a day opens it
 *  beside the month: its entries in full, the load, and a form to put
 *  something on it. An entry the staff added is theirs to remove; the
 *  schedule that came with the team is not edited from here. */
export default function TeamCalendarPage() {
  const { teamId = '' } = useParams()
  const board = useTeamDashboard(teamId)
  const today = toIso(new Date())
  const [month, setMonth] = useState(() => monthStart(today))
  const [picked, setPicked] = useState(today)
  const start = weekStart(month)
  const end = addDays(start, 41)
  const events = useTeamEvents(teamId, start, end)

  if (board.isLoading) {
    return (
      <div className="pb-4 pt-8">
        <header data-hero className="pt-3">
          <SkeletonLine className="h-4 w-40" />
          <SkeletonLine className="mt-6 h-11 w-72 max-w-full" />
        </header>
        <div className="mt-10" role="status" aria-label="Loading the calendar">
          <SkeletonCard rows={6} />
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
  const all = events.data?.events ?? []
  const kinds = events.data?.kinds ?? []
  const days = Array.from({ length: 42 }, (_, i) => addDays(start, i))
  const weeks = Array.from({ length: 6 }, (_, i) => days.slice(i * 7, i * 7 + 7))
  const loadBy = new Map(d.load.map((p) => [p.date, p]))
  const peak = Math.max(1, ...d.load.map((p) => p.load_per_athlete))
  const inThisMonth = all.filter((e) => inMonth(e.date, month))
  const games = inThisMonth.filter(isGame).length
  const off = inThisMonth.filter((e) => e.kind === 'off').length
  const sessions = inThisMonth.length - games - off
  const game = nextGame(d.events, d.as_of)
  const thisMonth = month === monthStart(today)

  const go = (n: number) => {
    const next = monthStart(month, n)
    setMonth(next)
    // Keep the open day inside the month on show.
    setPicked(inMonth(today, next) ? today : next)
  }

  return (
    <div className="pb-10 pt-8">
      <TeamHead d={d} title="Calendar">
        Everything on the team’s schedule, with the roster’s session load under the days it has
        already played.
      </TeamHead>

      <div
        className="rise mt-8 flex flex-wrap items-center gap-x-4 gap-y-3"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        <div className="glass inline-flex items-center gap-0.5 rounded-pill p-1" role="group" aria-label="Month">
          <button type="button" className="btn-icon btn-sm" aria-label="Previous month" onClick={() => go(-1)}>
            <ChevronLeft aria-hidden />
          </button>
          <button
            type="button"
            className="btn-plain btn-sm !px-3"
            disabled={thisMonth && picked === today}
            onClick={() => {
              setMonth(monthStart(today))
              setPicked(today)
            }}
          >
            Today
          </button>
          <button type="button" className="btn-icon btn-sm" aria-label="Next month" onClick={() => go(1)}>
            <ChevronRight aria-hidden />
          </button>
        </div>
        <h2 className="text-subhead font-medium text-ink">{monthName(month)}</h2>
        <span className="meta tabular-nums">
          {games} game{games === 1 ? '' : 's'} · {sessions} session{sessions === 1 ? '' : 's'}
          {off > 0 ? ` · ${off} day${off === 1 ? '' : 's'} off` : ''}
          {game &&
            ` · next game ${
              game.date === d.as_of ? 'today' : `in ${daysBetween(d.as_of, game.date)} day${daysBetween(d.as_of, game.date) === 1 ? '' : 's'}`
            }, ${opponentLine(game)}`}
        </span>
      </div>

      <div
        className="rise mt-4 grid gap-stack lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start"
        style={{ '--rise-delay': '100ms' } as CSSProperties}
      >
        <section
          aria-label={monthName(month)}
          className={`card-group transition-opacity duration-state ease-apple ${events.isPlaceholderData ? 'opacity-60' : ''}`}
          aria-busy={events.isPlaceholderData || undefined}
        >
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] table-fixed border-separate border-spacing-0 text-left">
              <caption className="sr-only">
                {monthName(month)}: the team’s events by day. A day that has passed also carries the roster’s session
                load. Pick a day to open it.
              </caption>
              <thead>
                <tr>
                  {weeks[0].map((day) => (
                    <th key={day} scope="col" className="px-2 py-2 text-label font-medium tracking-label text-secondary">
                      {weekday(day)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {weeks.map((week) => (
                  <tr key={week[0]}>
                    {week.map((day) => (
                      <DayCell
                        key={day}
                        day={day}
                        month={month}
                        today={today}
                        picked={picked === day}
                        events={all.filter((e) => e.date === day)}
                        load={loadBy.get(day)}
                        peak={peak}
                        onPick={() => setPicked(day)}
                      />
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="flex flex-wrap gap-x-4 gap-y-1 border-t border-hairline px-4 py-2.5">
            {(['game', 'practice', 'lift', 'recovery', 'off'] as const).map((kind) => (
              <li key={kind} className="meta inline-flex items-center gap-1.5">
                <span aria-hidden className={`h-2 w-2 rounded-pill ${eventKind(kind).dot}`} />
                {kind === 'practice' ? 'Practice and training' : kind === 'recovery' ? 'Shootaround, recovery, travel' : eventKind(kind).label}
              </li>
            ))}
            <li className="meta inline-flex items-center gap-1.5">
              <span aria-hidden className="h-1.5 w-5 rounded-pill bg-chart-s1" />
              Session load per athlete, that day
            </li>
          </ul>
        </section>

        <DayPanel
          teamId={teamId}
          day={picked}
          today={today}
          events={all.filter((e) => e.date === picked)}
          load={loadBy.get(picked)}
          kinds={kinds}
        />
      </div>

      <div className="mt-stack">
        <TeamLoadChart load={d.load} asOf={d.as_of} />
      </div>
      <StaffGuardrail text={d.guardrail} className="mt-8 px-1" />
    </div>
  )
}

function DayCell({
  day,
  month,
  today,
  picked,
  events,
  load,
  peak,
  onPick,
}: {
  day: string
  month: string
  today: string
  picked: boolean
  events: TeamEvent[]
  load: TeamLoadPoint | undefined
  peak: number
  onPick: () => void
}) {
  const outside = !inMonth(day, month)
  const isToday = day === today
  const sorted = [...events].sort((a, b) => (a.start_time ?? '').localeCompare(b.start_time ?? ''))
  const words =
    sorted.length === 0
      ? 'nothing scheduled'
      : sorted.map((e) => `${eventKind(e.kind).label}${e.opponent ? ` ${opponentLine(e)}` : ''}`).join(', ')
  return (
    <td className={`border-l border-t border-hairline p-0 align-top first:border-l-0 ${isToday ? 'bg-brand-tint/40' : ''}`}>
      <button
        type="button"
        onClick={onPick}
        aria-pressed={picked}
        aria-label={`${longDateOf(day)}: ${words}${load ? `; team load ${fmt(load.load_per_athlete)} per athlete` : ''}`}
        className={`flex min-h-[108px] w-full flex-col gap-1 p-2 text-left transition-colors duration-state ease-apple hover:bg-soft focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus ${
          picked ? 'shadow-[inset_0_0_0_2px_rgb(var(--focus))]' : ''
        } ${outside ? 'opacity-55' : ''}`}
      >
        <span className="flex items-center gap-1.5 text-label font-medium tabular-nums text-ink">
          {dayNumber(day)}
          {isToday && <span className="dot-lime" aria-hidden />}
        </span>
        {sorted.slice(0, 3).map((e) => {
          const kind = eventKind(e.kind)
          return (
            <span key={e.id} className="flex items-start gap-1.5 text-micro leading-tight text-ink">
              <span aria-hidden className={`mt-[3px] h-1.5 w-1.5 shrink-0 rounded-pill ${kind.dot}`} />
              <span className={`min-w-0 ${isGame(e) ? 'font-medium' : ''}`}>
                <span className="line-clamp-2">{e.opponent ? opponentLine(e) : e.title}</span>
                {e.start_time && <span className="block text-secondary">{timeLabel(e.start_time)}</span>}
              </span>
            </span>
          )
        })}
        {sorted.length > 3 && <span className="text-micro text-secondary">+{sorted.length - 3} more</span>}
        {load && load.load_per_athlete > 0 && (
          <span className="mt-auto block w-full" aria-hidden>
            <span className="block h-1.5 w-full overflow-hidden rounded-pill bg-[rgb(var(--fill))]">
              <span
                className="block h-full rounded-pill bg-chart-s1"
                style={{ width: `${Math.max(6, (load.load_per_athlete / peak) * 100)}%` }}
              />
            </span>
          </span>
        )}
      </button>
    </td>
  )
}

const DEFAULT_KIND = 'practice'

/** The picked day, beside the month: what is on it, the roster's load if
 *  the day has passed, and the form that puts something on it. */
function DayPanel({
  teamId,
  day,
  today,
  events,
  load,
  kinds,
}: {
  teamId: string
  day: string
  today: string
  events: TeamEvent[]
  load: TeamLoadPoint | undefined
  kinds: string[]
}) {
  const toast = useToast()
  const add = useAddTeamEvent(teamId)
  const remove = useDeleteTeamEvent(teamId)
  const [adding, setAdding] = useState(false)
  const [kind, setKind] = useState(DEFAULT_KIND)
  const [title, setTitle] = useState('')
  const [time, setTime] = useState('')
  const [opponent, setOpponent] = useState('')
  const [home, setHome] = useState<'home' | 'away'>('home')
  const [location, setLocation] = useState('')
  const [note, setNote] = useState('')
  const sorted = [...events].sort((a, b) => (a.start_time ?? '').localeCompare(b.start_time ?? ''))
  const game = kind === 'game' || kind === 'match'
  const options = kinds.length > 0 ? kinds : [DEFAULT_KIND]

  const reset = () => {
    setAdding(false)
    setTitle('')
    setTime('')
    setOpponent('')
    setLocation('')
    setNote('')
    setKind(DEFAULT_KIND)
    setHome('home')
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const name = title.trim() || eventKind(kind).label
    add.mutate(
      {
        date: day,
        kind,
        title: name,
        start_time: time || null,
        opponent: game ? opponent.trim() || null : null,
        home: game ? home === 'home' : null,
        location: location.trim() || null,
        note: note.trim() || null,
      },
      {
        onSuccess: () => {
          toast(`${name} is on ${weekday(day, 'long')}`, 'success')
          reset()
        },
        onError: (err) => toast(err instanceof ApiError && err.message ? err.message : 'Could not add it', 'warning'),
      },
    )
  }

  const onRemove = (e: TeamEvent) =>
    remove.mutate(e.id, {
      onSuccess: () => toast(`${e.title} removed`, 'info'),
      onError: (err) => toast(err instanceof ApiError && err.message ? err.message : 'Could not remove it', 'warning'),
    })

  return (
    <SectionCard
      title={day === today ? 'Today' : weekday(day, 'long')}
      icon={<Tile size="sm" family="teal" icon={<CalendarDays />} />}
      aside={longDateOf(day).replace(/^[A-Za-z]+, /, '')}
      className="lg:sticky lg:top-[calc(var(--bar-height)+var(--bar-inset)+16px)]"
    >
      {sorted.length === 0 ? (
        <p className="text-copy text-secondary">Nothing is on the schedule.</p>
      ) : (
        <ul className="divide-y divide-hairline">
          {sorted.map((e) => {
            const k = eventKind(e.kind)
            const mine = e.source === 'staff'
            return (
              <li key={e.id} className="py-2.5 first:pt-0 last:pb-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 text-copy text-ink">
                    <span className="inline-flex items-center gap-1.5 font-medium">
                      <span aria-hidden className={`h-2 w-2 shrink-0 rounded-pill ${k.dot}`} />
                      {e.opponent ? `${k.label} ${opponentLine(e)}` : e.title}
                    </span>
                    {/* The kind is said once: under the title only when the title is something else. */}
                    {!e.opponent && e.title.toLowerCase() !== k.label.toLowerCase() && (
                      <span className="meta block">{k.label}</span>
                    )}
                  </p>
                  {mine && (
                    <button
                      type="button"
                      className="btn-icon btn-sm -mr-1 -mt-1 shrink-0"
                      aria-label={`Remove ${e.title}`}
                      disabled={remove.isPending}
                      onClick={() => onRemove(e)}
                    >
                      <Trash2 aria-hidden />
                    </button>
                  )}
                </div>
                <p className="meta mt-0.5">
                  {[timeLabel(e.start_time), e.opponent ? e.title : null, e.home == null ? null : e.home ? 'Home' : 'Away']
                    .filter(Boolean)
                    .join(' · ') || 'No time set'}
                </p>
                {e.location && (
                  <p className="meta mt-0.5 inline-flex items-center gap-1">
                    <MapPin aria-hidden size={11} /> {e.location}
                  </p>
                )}
                {e.note && <p className="mt-1 text-copy text-body">{e.note}</p>}
                {mine && <p className="meta mt-1">Added by staff</p>}
              </li>
            )
          })}
        </ul>
      )}

      {load && (
        <dl className="mt-4 flex gap-x-8 border-t border-hairline pt-3">
          <div>
            <dt className="text-label text-secondary">Session load</dt>
            <dd className="text-copy font-medium tabular-nums text-ink">
              {fmt(load.load_per_athlete)} <span className="font-normal text-secondary">AU per athlete</span>
            </dd>
          </div>
          <div>
            <dt className="text-label text-secondary">Jumps</dt>
            <dd className="text-copy font-medium tabular-nums text-ink">
              {fmt(load.jumps_per_athlete)} <span className="font-normal text-secondary">per athlete</span>
            </dd>
          </div>
        </dl>
      )}

      {adding ? (
        <form onSubmit={submit} className="mt-4 space-y-3 border-t border-hairline pt-4">
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block px-1 text-label font-medium text-secondary">Kind</span>
              <select className="field cursor-pointer" value={kind} onChange={(e) => setKind(e.target.value)}>
                {options.map((k) => (
                  <option key={k} value={k}>
                    {eventKind(k).label}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1 block px-1 text-label font-medium text-secondary">Start</span>
              <input type="time" className="field tabular-nums" value={time} onChange={(e) => setTime(e.target.value)} />
            </label>
          </div>
          <label className="block">
            <span className="mb-1 block px-1 text-label font-medium text-secondary">Title</span>
            <input
              className="field"
              value={title}
              maxLength={120}
              placeholder={eventKind(kind).label}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          {game && (
            <div className="grid grid-cols-[minmax(0,1fr)_auto] gap-2">
              <label className="block">
                <span className="mb-1 block px-1 text-label font-medium text-secondary">Opponent</span>
                <input className="field" value={opponent} maxLength={80} onChange={(e) => setOpponent(e.target.value)} />
              </label>
              <label className="block">
                <span className="mb-1 block px-1 text-label font-medium text-secondary">Where</span>
                <select className="field cursor-pointer" value={home} onChange={(e) => setHome(e.target.value as 'home' | 'away')}>
                  <option value="home">Home</option>
                  <option value="away">Away</option>
                </select>
              </label>
            </div>
          )}
          <label className="block">
            <span className="mb-1 block px-1 text-label font-medium text-secondary">
              Location <span className="font-normal">optional</span>
            </span>
            <input className="field" value={location} maxLength={120} onChange={(e) => setLocation(e.target.value)} />
          </label>
          <label className="block">
            <span className="mb-1 block px-1 text-label font-medium text-secondary">
              Note <span className="font-normal">optional</span>
            </span>
            <input className="field" value={note} maxLength={200} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="flex justify-end gap-2">
            <button type="button" className="btn-plain-muted btn-sm" onClick={reset}>
              Cancel
            </button>
            <button type="submit" className="btn-filled btn-sm" disabled={add.isPending}>
              {add.isPending ? 'Adding…' : 'Add to the calendar'}
            </button>
          </div>
        </form>
      ) : (
        <button type="button" className="btn-tinted btn-sm mt-4" onClick={() => setAdding(true)}>
          <Plus aria-hidden size={14} /> Add to this day
        </button>
      )}
    </SectionCard>
  )
}
