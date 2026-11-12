import {
  ArrowUpRight,
  CalendarCheck,
  CalendarRange,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  CopyPlus,
  Dumbbell,
  TrendingUp,
} from 'lucide-react'
import { useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { useWeekReview, type WeekEntry } from '../../api/calendar'
import type { CareTeamMember, LoadUnit } from '../../api/hep'
import { todayIso, useHepOptions } from '../../api/hep'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { relativeTime } from '../../lib/format'
import { SettingsHero } from '../settings/Switch'
import { ReviewDot } from './AdherenceChip'
import ApplyProgramDialog from './ApplyProgramDialog'
import CopyWeekDialog from './CopyWeekDialog'
import ExercisesNav from './ExercisesNav'
import { CALENDAR } from './paths'
import {
  addDays,
  changeText,
  mondayOf,
  monthDay,
  painChipClass,
  rangeLabel,
  shortDay,
  tierChip,
  tierKey,
  weekDays,
  weekdayShort,
} from './scheduleCopy'
import { movedText, unitOf } from './units'

/** `/calendar/week` — the week in review, one card per lifter, those with
 *  something to look at first. Each card is the Monday-morning read: what
 *  was done against what was written, pain before and after, effort against
 *  the target, the load moved against the load written and against the
 *  week before, the days that went over the dose, what waits for a look,
 *  and whether next week is on the calendar yet — with the two ways to set
 *  it (copy this week forward, or apply a program).
 *
 *  Every number here describes what happened. Nothing on the page tells
 *  the therapist what the next dose should be. */

const ATTENTION: Record<string, string> = {
  over: 'Went over the dose',
  review: 'Waiting for your look',
  missed: 'Missed days',
}

function fixed(n: number | null | undefined): string {
  return n == null ? '—' : String(Number(n.toFixed(1)))
}

export default function WeekReviewPage() {
  const today = todayIso()
  const home = mondayOf(today)
  const [start, setStart] = useState(home)
  const week = useWeekReview(start)
  const options = useHepOptions()
  const days = week.data?.days ?? weekDays(start)
  const unit = unitOf(week.data?.clinic)
  const careTeam = options.data?.care_team ?? []
  const [action, setAction] = useState<{ kind: 'copy' | 'apply'; entry: WeekEntry } | null>(null)
  const entries = week.data?.patients ?? []
  const looking = entries.filter((e) => e.attention.length > 0).length

  return (
    <div className="pb-10">
      <SettingsHero
        nav={<ExercisesNav />}
        icon={<CalendarRange />}
        title="Week"
        decor={[<CalendarRange key="c" />, <Dumbbell key="d" />, <CalendarCheck key="k" />]}
      >
        Each lifter’s week in review: what was done against what was written, pain and effort, the
        load, and whether next week is set.
      </SettingsHero>

      <div
        className="rise mt-8 flex flex-wrap items-center gap-x-4 gap-y-3"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        <div className="glass inline-flex items-center gap-0.5 rounded-pill p-1" role="group" aria-label="Week">
          <button type="button" className="btn-icon btn-sm" aria-label="Previous week" onClick={() => setStart(addDays(start, -7))}>
            <ChevronLeft aria-hidden />
          </button>
          <button type="button" className="btn-plain btn-sm !px-3" disabled={start === home} onClick={() => setStart(home)}>
            This week
          </button>
          <button type="button" className="btn-icon btn-sm" aria-label="Next week" onClick={() => setStart(addDays(start, 7))}>
            <ChevronRight aria-hidden />
          </button>
        </div>
        <h2 className="text-subhead font-medium text-ink">{rangeLabel(days)}</h2>
        {week.data && (
          <span className="meta tabular-nums">
            {week.data.clinic && <>{week.data.clinic.name} · </>}
            {entries.length} lifter{entries.length === 1 ? '' : 's'}
            {looking > 0 ? ` · ${looking} with something to look at` : entries.length > 0 ? ' · nothing waiting' : ''}
          </span>
        )}
      </div>

      <div
        className={`rise mt-6 space-y-stack transition-opacity duration-state ease-apple ${
          week.isPlaceholderData ? 'opacity-60' : ''
        }`}
        style={{ '--rise-delay': '100ms' } as CSSProperties}
        aria-busy={week.isPlaceholderData || undefined}
      >
        {week.isLoading ? (
          <SkeletonCard rows={5} />
        ) : week.isError ? (
          <EmptyState
            title="The week couldn’t be loaded."
            icon={<CalendarRange />}
            action={
              <button type="button" className="btn-tinted" onClick={() => void week.refetch()}>
                Try again
              </button>
            }
          >
            Check that the API is running, then try again.
          </EmptyState>
        ) : entries.length === 0 ? (
          <EmptyState
            title="No one is on the calendar yet"
            icon={<CalendarCheck />}
            family="teal"
            action={
              <Link to={CALENDAR.schedule} className="btn-tinted">
                Open the schedule
              </Link>
            }
          >
            A lifter’s week shows here once exercises are on their days.
          </EmptyState>
        ) : (
          entries.map((entry) => (
            <WeekCard
              key={entry.patient.id}
              entry={entry}
              days={days}
              today={today}
              unit={unit}
              onAction={(kind) => setAction({ kind, entry })}
            />
          ))
        )}
      </div>

      {action?.kind === 'copy' && (
        <CopyWeekDialog
          patient={action.entry.patient}
          toStart={action.entry.next_week.start}
          careTeam={careTeam as CareTeamMember[]}
          title="Copy this week onto next week?"
          onClose={() => setAction(null)}
        />
      )}
      {action?.kind === 'apply' && (
        <ApplyProgramDialog
          patient={action.entry.patient}
          defaultStart={action.entry.next_week.start}
          careTeam={careTeam as CareTeamMember[]}
          onClose={() => setAction(null)}
        />
      )}
    </div>
  )
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-label font-medium tracking-label text-secondary">{label}</dt>
      <dd className="mt-0.5">
        <span className="big-num text-[1.5rem] text-ink">{value}</span>
        {hint && <span className="meta block">{hint}</span>}
      </dd>
    </div>
  )
}

function WeekCard({
  entry: e,
  days,
  today,
  unit,
  onAction,
}: {
  entry: WeekEntry
  days: string[]
  today: string
  unit: LoadUnit
  onAction: (kind: 'copy' | 'apply') => void
}) {
  const p = e.patient
  const tier = tierChip(p.risk_tier)
  const w = e.week
  const first = p.name.split(' ')[0]
  const painBy = new Map(e.pain.by_day.map((d) => [d.date, d]))
  const loadChange = changeText(e.load.change_pct)
  const nextChange = e.next_week.change_pct
  const past = days[days.length - 1] < today

  // A percent of the whole week reads as a shortfall while days are still
  // ahead, so it is printed once the week is over; until then the line says
  // what was missed (or that nothing was) and what is left.
  const doneHint = [
    w.open === 0 && w.assigned > 0 ? `${Math.round(w.pct)}%` : '',
    w.missed > 0 ? `${w.missed} missed` : '',
    w.skipped > 0 ? `${w.skipped} skipped` : '',
    w.open > 0 && w.missed === 0 && w.skipped === 0 ? 'nothing missed' : '',
    w.open > 0 ? `${w.open} still ahead` : '',
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <article className="panel p-5" aria-label={`${p.name}: the week`}>
      <header className="flex flex-wrap items-start gap-3">
        <Avatar name={p.name} tier={tierKey(p.risk_tier)} size="md" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 className="text-lede font-semibold text-ink">{p.name}</h3>
            {tier && <span className={`chip ${tier.pill}`}>{tier.label}</span>}
            {e.attention.map((key) => (
              <span key={key} className="chip bg-risk-med-tint normal-case text-risk-med-ink">
                {key === 'review' && <ReviewDot />}
                {key === 'over' && <TrendingUp aria-hidden size={12} />}
                {ATTENTION[key] ?? key}
              </span>
            ))}
          </div>
          <p className="meta mt-0.5">
            {[p.pathway, p.assigned_provider_name].filter(Boolean).join(' · ')}
            {e.last_patient_message_at && ` · last wrote ${relativeTime(e.last_patient_message_at)}`}
          </p>
        </div>
        <Link to={`/patients/${encodeURIComponent(p.id)}`} className="btn-plain btn-sm -mr-2">
          Chart <ArrowUpRight aria-hidden size={14} />
        </Link>
      </header>

      {w.assigned === 0 ? (
        <p className="mt-4 text-copy text-secondary">Nothing was on {first}’s calendar this week.</p>
      ) : (
        <>
          <dl className="mt-5 grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Done" value={`${w.done} of ${w.assigned}`} hint={doneHint} />
            <Stat
              label="Pain after"
              value={e.pain.after_avg == null ? '—' : `${fixed(e.pain.after_avg)}`}
              hint={
                e.pain.after_avg == null
                  ? 'no scores yet'
                  : `on average · ${e.pain.after_max} at most${
                      e.pain.before_avg != null ? ` · ${fixed(e.pain.before_avg)} before` : ''
                    }`
              }
            />
            <Stat
              label="Effort"
              value={e.effort.avg == null ? '—' : `${fixed(e.effort.avg)}`}
              hint={
                e.effort.avg == null
                  ? 'not reported'
                  : e.effort.target_avg != null
                    ? `target ${fixed(e.effort.target_avg)}${
                        e.effort.days_over_target > 0
                          ? ` · over it on ${e.effort.days_over_target} day${e.effort.days_over_target === 1 ? '' : 's'}`
                          : ''
                      }`
                    : 'no target written'
              }
            />
            <Stat
              label="Load moved"
              value={e.load.done > 0 || e.load.planned > 0 ? movedText(e.load.done, unit) : '—'}
              hint={
                e.load.planned > 0 || e.load.done > 0
                  ? [`${movedText(e.load.planned, unit)} written`, loadChange].filter(Boolean).join(' · ')
                  : 'no loaded exercises'
              }
            />
          </dl>

          <div className="mt-5">
            <h4 className="text-label font-medium tracking-label text-secondary">Pain after, by day</h4>
            <ol className="mt-1.5 grid grid-cols-7 gap-1.5" aria-label="Pain after the exercises, by day">
              {days.map((d) => {
                const day = painBy.get(d)
                const pain = day?.after_max ?? null
                return (
                  <li
                    key={d}
                    aria-current={d === today ? 'date' : undefined}
                    className={`rounded-control-sm px-2 py-1.5 text-center ${d === today ? 'bg-brand-tint/40' : 'bg-soft/70'}`}
                  >
                    <span className="block text-micro text-secondary">{weekdayShort(d)}</span>
                    {pain != null ? (
                      <span className={`mt-0.5 inline-block rounded-pill px-2 text-copy font-medium tabular-nums ${painChipClass(pain)}`}>
                        {pain}
                      </span>
                    ) : (
                      <span className="mt-0.5 block text-copy text-secondary">
                        <span aria-hidden>{day && day.done > 0 ? '·' : '—'}</span>
                        <span className="sr-only">{day && day.done > 0 ? 'done, no score' : 'nothing done'}</span>
                      </span>
                    )}
                  </li>
                )
              })}
            </ol>
          </div>
        </>
      )}

      {e.over.length > 0 && (
        <div className="mt-5">
          <h4 className="text-label font-medium tracking-label text-secondary">Over the dose</h4>
          <ul className="mt-1.5 divide-y divide-hairline">
            {e.over.map((o) => (
              <li key={o.assignment_id} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-2 first:pt-0">
                <span className="text-copy text-ink">
                  <span className="tabular-nums text-secondary">{shortDay(o.day)}</span> · {o.title}: {o.line}
                </span>
                {o.reviewed ? (
                  <span className="meta inline-flex items-center gap-1">
                    <Check aria-hidden size={12} /> Looked at
                  </span>
                ) : (
                  <Link to={CALENDAR.review} className="text-label text-risk-med-ink hover:underline">
                    Waiting for your look
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      <footer className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-hairline pt-4">
        <p className="min-w-0 flex-1 text-copy text-ink">
          <span className="font-medium">Next week</span>{' '}
          <span className="text-secondary">({monthDay(e.next_week.start)} on)</span>:{' '}
          {e.next_week.set ? (
            <>
              {e.next_week.assigned} exercise{e.next_week.assigned === 1 ? '' : 's'} set
              {e.next_week.planned_load > 0 && (
                <>
                  {' · '}
                  {movedText(e.next_week.planned_load, unit)} written
                  {nextChange != null && nextChange !== 0 && (
                    <>, {nextChange > 0 ? '+' : '−'}{Math.abs(Math.round(nextChange))}% against this week</>
                  )}
                </>
              )}
            </>
          ) : (
            <span className="text-risk-med-ink">not set yet</span>
          )}
        </p>
        {!past && (
          <span className="flex flex-wrap gap-2">
            <button type="button" className="btn-gray btn-sm" onClick={() => onAction('copy')}>
              <CopyPlus size={14} aria-hidden /> Copy this week forward
            </button>
            <button type="button" className="btn-plain btn-sm" onClick={() => onAction('apply')}>
              <ClipboardList size={14} aria-hidden /> Apply a program
            </button>
          </span>
        )}
      </footer>
    </article>
  )
}
