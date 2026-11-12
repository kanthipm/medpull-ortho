import { CalendarDays, Check, CircleSlash, Moon, Stethoscope, TrendingUp, Users } from 'lucide-react'
import { useState } from 'react'
import { useCalendarMonth, type CalendarDay, type CalendarItem, type CalendarPatient } from '../../api/calendar'
import type { CalendarMark, CalendarVisit, LoadUnit } from '../../api/hep'
import { clockText } from '../../api/pt'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import { AdherenceChip } from './AdherenceChip'
import {
  changeText,
  dayOfMonth,
  longDay,
  mondayOf,
  monthDay,
  monthLabel,
  sameMonth,
  stateOf,
  tierKey,
  weekdayShort,
} from './scheduleCopy'
import { movedText } from './units'

/** Six weeks of the calendar at a glance.
 *
 *  On top, one strip per lifter: forty-two squares, one a day, saying how
 *  the day went (all done, some left, missed, still ahead, nothing on it).
 *  The strip is also the picker. Under it, the picked lifter's month as a
 *  calendar: each day lists what is on it with the same marks as the week
 *  grid, and opens that week for the full rows and the editing. A clinic
 *  visit and a rest day are named on their day, above the exercises.
 *
 *  Every square and every day carries its words (a title and a name), and
 *  the legend spells the five states out, so the fill is never the only
 *  thing saying it. */

const STRIP: Record<string, { cls: string; label: string }> = {
  none: { cls: 'bg-[rgb(var(--fill))]', label: 'Nothing on it' },
  done: { cls: 'bg-chart-s1', label: 'All done' },
  part: { cls: 'bg-chart-s1/45', label: 'Some done' },
  missed: { cls: 'bg-risk-med-ink', label: 'Missed' },
  ahead: { cls: 'bg-panel ring-1 ring-inset ring-line-strong', label: 'Still ahead' },
}

function stripKey(day: CalendarDay): keyof typeof STRIP {
  if (day.assigned === 0) return 'none'
  if (day.missed > 0) return 'missed'
  if (day.done >= day.assigned) return 'done'
  if (day.open > 0 && day.done === 0) return 'ahead'
  return 'part'
}

function dayWords(day: CalendarDay): string {
  if (day.assigned === 0) return 'nothing assigned'
  const parts = [`${day.done} of ${day.assigned} done`]
  if (day.missed > 0) parts.push(`${day.missed} missed`)
  if (day.skipped > 0) parts.push(`${day.skipped} skipped`)
  if (day.over > 0) parts.push(`${day.over} over the dose`)
  if (day.awaiting_review > 0) parts.push(`${day.awaiting_review} to review`)
  return parts.join(', ')
}

export default function MonthBoard({
  month,
  unit,
  onOpenWeek,
}: {
  /** The first day of the month on show. */
  month: string
  unit: LoadUnit
  /** A day was opened: show its week on the grid. */
  onOpenWeek: (day: string) => void
}) {
  const calendar = useCalendarMonth(mondayOf(month))
  const [picked, setPicked] = useState<string | null>(null)
  const patients = calendar.data?.patients ?? []
  const days = calendar.data?.days ?? []
  const today = calendar.data?.today ?? ''
  const chosen = patients.find((p) => p.id === picked) ?? patients[0]

  if (calendar.isLoading) return <SkeletonCard rows={6} />
  if (calendar.isError) {
    return (
      <EmptyState
        title="The month couldn’t be loaded."
        icon={<CalendarDays />}
        action={
          <button type="button" className="btn-tinted" onClick={() => void calendar.refetch()}>
            Try again
          </button>
        }
      >
        Check that the API is running, then try again.
      </EmptyState>
    )
  }
  if (patients.length === 0) {
    return (
      <EmptyState title="No patients on the calendar yet" icon={<Users />} family="teal">
        The clinic’s charts appear here once they have exercises on a day.
      </EmptyState>
    )
  }

  const weeks = Array.from({ length: Math.ceil(days.length / 7) }, (_, i) => days.slice(i * 7, i * 7 + 7))

  return (
    <div
      className={`space-y-stack transition-opacity duration-state ease-apple ${
        calendar.isPlaceholderData ? 'opacity-60' : ''
      }`}
      aria-busy={calendar.isPlaceholderData || undefined}
    >
      <section aria-label="Six weeks, one strip per patient" className="card-group">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left">
            <caption className="sr-only">
              {monthLabel(month)}: one row per patient, one square per day, saying how the day went
            </caption>
            <thead>
              <tr>
                <th scope="col" className="w-[260px] px-4 py-2.5 text-label font-medium tracking-label text-secondary">
                  Patient
                </th>
                {weeks.map((week) => (
                  <th key={week[0]} scope="col" className="px-1.5 py-2.5 text-label font-medium tabular-nums text-secondary">
                    {monthDay(week[0])}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {patients.map((p) => (
                <StripRow
                  key={p.id}
                  patient={p}
                  weeks={weeks}
                  today={today}
                  selected={p.id === chosen?.id}
                  onPick={() => setPicked(p.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
        <ul className="flex flex-wrap gap-x-4 gap-y-1 border-t border-hairline px-4 py-2.5">
          {(['done', 'part', 'missed', 'ahead', 'none'] as const).map((key) => (
            <li key={key} className="meta inline-flex items-center gap-1.5">
              <span aria-hidden className={`h-3 w-3 rounded-[3px] ${STRIP[key].cls}`} />
              {STRIP[key].label}
            </li>
          ))}
        </ul>
      </section>

      {chosen && (
        <MonthGrid
          patient={chosen}
          month={month}
          weeks={weeks}
          today={today}
          unit={unit}
          onOpenWeek={onOpenWeek}
          visits={(calendar.data?.visits ?? []).filter((v) => v.patient_id === chosen.id)}
          marks={(calendar.data?.marks ?? []).filter((m) => m.patient_id === chosen.id)}
        />
      )}
    </div>
  )
}

function StripRow({
  patient: p,
  weeks,
  today,
  selected,
  onPick,
}: {
  patient: CalendarPatient
  weeks: string[][]
  today: string
  selected: boolean
  onPick: () => void
}) {
  const byDate = new Map(p.days.map((d) => [d.date, d]))
  const adherence = p.adherence
  return (
    <tr className={selected ? 'bg-brand-tint/40' : ''}>
      <th scope="row" className="border-t border-hairline py-2 pl-4 pr-2 text-left font-normal">
        <button
          type="button"
          onClick={onPick}
          aria-pressed={selected}
          className="flex w-full items-center gap-3 rounded-control-sm py-1 text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          <Avatar name={p.name} tier={tierKey(p.risk_tier)} size="sm" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-copy font-medium text-ink">{p.name}</span>
            {adherence && adherence.assigned > 0 ? (
              <AdherenceChip done={adherence.done} assigned={adherence.assigned} pct={adherence.pct} className="mt-0.5" />
            ) : (
              <span className="meta block">Nothing assigned this week</span>
            )}
          </span>
        </button>
      </th>
      {weeks.map((week) => (
        <td key={week[0]} className="border-t border-hairline px-1.5 py-2 align-middle">
          <div className="grid grid-cols-7 gap-px">
            {week.map((date) => {
              const day = byDate.get(date)
              const key = day ? stripKey(day) : 'none'
              return (
                <span
                  key={date}
                  title={`${weekdayShort(date)} ${monthDay(date)}: ${day ? dayWords(day) : 'nothing assigned'}`}
                  className={`h-5 rounded-[3px] ${STRIP[key].cls} ${
                    date === today ? 'outline outline-2 outline-offset-1 outline-ink' : ''
                  }`}
                >
                  <span className="sr-only">
                    {longDay(date)}: {day ? dayWords(day) : 'nothing assigned'}.
                  </span>
                </span>
              )
            })}
          </div>
        </td>
      ))}
    </tr>
  )
}

function ItemLine({ item }: { item: CalendarItem }) {
  const state = stateOf(item)
  const quiet = state === 'skipped' || state === 'missed'
  return (
    <span className={`flex items-center gap-1 text-micro leading-tight ${quiet ? 'text-secondary' : 'text-ink'}`}>
      {state === 'done' ? (
        <Check aria-hidden size={10} className="shrink-0 text-risk-low-ink" />
      ) : state === 'skipped' ? (
        <CircleSlash aria-hidden size={10} className="shrink-0" />
      ) : (
        <span
          aria-hidden
          className={`h-1.5 w-1.5 shrink-0 rounded-pill ${
            state === 'missed' ? 'bg-risk-med-ink' : state === 'in_progress' ? 'bg-brand-ink' : 'bg-line-strong'
          }`}
        />
      )}
      <span className="min-w-0 truncate">{item.title}</span>
      {item.over && <TrendingUp aria-hidden size={10} className="ml-auto shrink-0 text-risk-med-ink" />}
    </span>
  )
}

const SHOWN = 4

function MonthGrid({
  patient: p,
  month,
  weeks,
  today,
  unit,
  onOpenWeek,
  visits,
  marks,
}: {
  patient: CalendarPatient
  month: string
  weeks: string[][]
  today: string
  unit: LoadUnit
  onOpenWeek: (day: string) => void
  visits: CalendarVisit[]
  marks: CalendarMark[]
}) {
  const byDate = new Map(p.days.map((d) => [d.date, d]))
  const inMonth = p.days.filter((d) => sameMonth(d.date, month))
  const assigned = inMonth.reduce((n, d) => n + d.assigned, 0)
  const done = inMonth.reduce((n, d) => n + d.done, 0)
  const missed = inMonth.reduce((n, d) => n + d.missed, 0)
  const over = inMonth.reduce((n, d) => n + d.over, 0)
  const load = p.load_week
  const planned = changeText(load?.planned_change_pct)
  return (
    <section aria-label={`${p.name}, ${monthLabel(month)}`} className="card-group">
      <header className="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 pb-2 pt-3">
        <h3 className="text-copy-lg font-medium text-ink">{p.name}</h3>
        {p.pathway && <span className="meta">{p.pathway}</span>}
        <span className="meta ml-auto tabular-nums">
          {assigned === 0
            ? 'Nothing assigned this month'
            : `${done} of ${assigned} done${missed > 0 ? ` · ${missed} missed` : ''}${over > 0 ? ` · ${over} over the dose` : ''}`}
          {load?.planned_next_week != null && load.planned_next_week > 0 && (
            <>
              {' · '}next week {movedText(load.planned_next_week, unit)} written{planned ? `, ${planned}` : ''}
            </>
          )}
        </span>
      </header>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] table-fixed border-separate border-spacing-0 text-left">
          <caption className="sr-only">
            {p.name}’s exercises in {monthLabel(month)}. Each day opens its week.
          </caption>
          <thead>
            <tr>
              {weeks[0].map((d) => (
                <th key={d} scope="col" className="border-t border-hairline px-2 py-1.5 text-label font-medium tracking-label text-secondary">
                  {weekdayShort(d)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {weeks.map((week) => (
              <tr key={week[0]}>
                {week.map((date) => {
                  const day = byDate.get(date)
                  const items = day?.items ?? []
                  const outside = !sameMonth(date, month)
                  const isToday = date === today
                  const visit = visits.find((v) => v.on === date)
                  const rest = marks.find((m) => m.day === date && m.kind === 'rest')
                  const also = [
                    visit ? `${visit.kind_label}${visit.at ? ` at ${clockText(visit.at)}` : ''}` : '',
                    rest ? 'a rest day' : '',
                  ]
                    .filter(Boolean)
                    .join(', ')
                  return (
                    <td
                      key={date}
                      className={`border-l border-t border-hairline p-0 align-top first:border-l-0 ${
                        isToday ? 'bg-brand-tint/40' : ''
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => onOpenWeek(date)}
                        aria-label={`${longDay(date)}: ${also ? `${also}; ` : ''}${day ? dayWords(day) : 'nothing assigned'}. Open the week.`}
                        className={`flex min-h-[104px] w-full flex-col gap-1 p-2 text-left transition-colors duration-state ease-apple hover:bg-soft focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus ${
                          outside ? 'opacity-55' : ''
                        }`}
                      >
                        <span className="flex items-center gap-1.5 text-label font-medium tabular-nums text-ink">
                          {dayOfMonth(date) === '1' ? monthDay(date) : dayOfMonth(date)}
                          {isToday && <span className="dot-lime" aria-hidden />}
                          {day && day.assigned > 0 && (
                            <span className="ml-auto text-micro font-normal text-secondary">
                              {day.done}/{day.assigned}
                            </span>
                          )}
                        </span>
                        {visit && (
                          <span className="flex items-center gap-1 text-micro font-medium leading-tight text-cat-violet-ink">
                            <Stethoscope aria-hidden size={10} className="shrink-0" />
                            <span className="min-w-0 truncate">
                              {visit.kind_label}
                              {visit.at ? ` ${clockText(visit.at)}` : ''}
                            </span>
                          </span>
                        )}
                        {rest && (
                          <span className="flex items-center gap-1 text-micro leading-tight text-secondary">
                            <Moon aria-hidden size={10} className="shrink-0" />
                            Rest day
                          </span>
                        )}
                        {items.slice(0, SHOWN).map((item) => (
                          <ItemLine key={item.id} item={item} />
                        ))}
                        {items.length > SHOWN && (
                          <span className="text-micro text-secondary">+{items.length - SHOWN} more</span>
                        )}
                      </button>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
