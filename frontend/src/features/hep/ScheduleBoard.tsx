import { CalendarDays, ChevronLeft, ChevronRight, Plus, Users } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { Assignment, SchedulePatient } from '../../api/hep'
import { todayIso, useSchedule } from '../../api/hep'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import AssignDialog from './AssignDialog'
import AssignmentChip from './AssignmentChip'
import AssignmentDialog from './AssignmentDialog'
import {
  addDays,
  assignable,
  dayOfMonth,
  longDay,
  mondayOf,
  rangeLabel,
  tierChip,
  tierKey,
  weekDays,
  weekdayShort,
} from './scheduleCopy'

/** The week on one grid: ← Today → over the dates, one row per clinic chart
 *  (avatar, name, pathway, tier), one column per day with today marked. A
 *  cell lists its assignments as chips and ends in a `+`; the chip opens
 *  AssignmentDialog, the `+` AssignDialog. A real table, so the dates are
 *  column headers and the names row headers.
 *
 *  `live` polls every 15 s (the demo screen, where a completion from the
 *  phone should land on the board by itself); `dense` tightens the columns
 *  for the demo's two-thirds pane; `aside` sits at the right of the week
 *  row (the demo-screen link). */
export default function ScheduleBoard({
  live = false,
  dense = false,
  anchor = 'monday',
  aside,
}: {
  live?: boolean
  dense?: boolean
  /** Where the seven days begin: the Monday of this week (the schedule
   *  page), or today itself (the demo screen, where the first column has to
   *  be the day the phone is showing). */
  anchor?: 'monday' | 'today'
  aside?: ReactNode
}) {
  const today = todayIso()
  const home = anchor === 'today' ? today : mondayOf(today)
  const [start, setStart] = useState(() => home)
  const schedule = useSchedule(start, 7, undefined, { live })
  const days = schedule.data?.days ?? weekDays(start)
  const thisWeek = start === home
  const [assign, setAssign] = useState<{ patientId: string; date: string } | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)
  const captionId = useId()

  const patients = schedule.data?.patients ?? []
  const assigning = assign ? patients.find((p) => p.id === assign.patientId) : undefined
  let opened: { a: Assignment; p: SchedulePatient } | undefined
  if (openId != null) {
    for (const p of patients) {
      const a = p.assignments.find((x) => x.id === openId)
      if (a) {
        opened = { a, p }
        break
      }
    }
  }
  const all = patients.flatMap((p) => p.assignments)
  const doneCount = all.filter((a) => a.status === 'done').length

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="glass inline-flex items-center gap-0.5 rounded-pill p-1" role="group" aria-label="Week">
          <button
            type="button"
            className="btn-icon btn-sm"
            aria-label="Previous week"
            onClick={() => setStart(addDays(start, -7))}
          >
            <ChevronLeft aria-hidden />
          </button>
          <button
            type="button"
            className="btn-plain btn-sm !px-3"
            disabled={thisWeek}
            onClick={() => setStart(home)}
          >
            Today
          </button>
          <button
            type="button"
            className="btn-icon btn-sm"
            aria-label="Next week"
            onClick={() => setStart(addDays(start, 7))}
          >
            <ChevronRight aria-hidden />
          </button>
        </div>
        <h2 id={captionId} className="text-subhead font-medium text-ink">
          {rangeLabel(days)}
        </h2>
        {schedule.data && (
          <span className="meta tabular-nums">
            {patients.length} patient{patients.length === 1 ? '' : 's'} · {all.length} exercise
            {all.length === 1 ? '' : 's'}
            {all.length > 0 && ` · ${doneCount} done`}
          </span>
        )}
        {aside && <div className="ml-auto flex items-center gap-2">{aside}</div>}
      </div>

      <div
        className={`mt-4 transition-opacity duration-state ease-apple ${
          schedule.isPlaceholderData ? 'opacity-60' : ''
        }`}
        aria-busy={schedule.isPlaceholderData || undefined}
      >
        {schedule.isLoading ? (
          <SkeletonCard rows={5} />
        ) : schedule.isError ? (
          <EmptyState
            title="The schedule couldn’t be loaded."
            icon={<CalendarDays />}
            action={
              <button type="button" className="btn-tinted" onClick={() => void schedule.refetch()}>
                Try again
              </button>
            }
          >
            {schedule.error instanceof Error && schedule.error.message
              ? schedule.error.message
              : 'Check that the API is running, then try again.'}
          </EmptyState>
        ) : patients.length === 0 ? (
          <EmptyState title="No patients on the schedule yet" icon={<Users />} family="teal">
            The clinic’s charts appear here as rows. Each day has a + to put an exercise on it.
          </EmptyState>
        ) : (
          <Grid
            patients={patients}
            days={days}
            today={today}
            dense={dense}
            captionId={captionId}
            onAssign={(patientId, date) => setAssign({ patientId, date })}
            onOpen={(a) => setOpenId(a.id)}
          />
        )}
      </div>

      {assign && assigning && (
        <AssignDialog
          key={`${assign.patientId}-${assign.date}`}
          patient={assigning}
          date={assign.date}
          days={days}
          assignments={assigning.assignments}
          careTeam={schedule.data?.care_team ?? []}
          onClose={() => setAssign(null)}
        />
      )}
      {opened && (
        <AssignmentDialog
          key={opened.a.id}
          assignment={opened.a}
          patientName={opened.p.name}
          days={days}
          careTeam={schedule.data?.care_team ?? []}
          onClose={() => setOpenId(null)}
        />
      )}
    </div>
  )
}

function Grid({
  patients,
  days,
  today,
  dense,
  captionId,
  onAssign,
  onOpen,
}: {
  patients: SchedulePatient[]
  days: string[]
  today: string
  dense: boolean
  captionId: string
  onAssign: (patientId: string, date: string) => void
  onOpen: (a: Assignment) => void
}) {
  const colMin = dense ? 'min-w-[92px]' : 'min-w-[128px]'
  return (
    <div className="card-group">
      <div className="overflow-x-auto" role="region" aria-labelledby={captionId} tabIndex={0}>
        {/* Fixed layout: the day columns share the width equally and a long
            title truncates in its chip, instead of the longest one widening
            its column until Sunday scrolls off the edge. */}
        <table className={`w-full table-fixed text-left text-copy ${dense ? 'min-w-[820px]' : 'min-w-[1080px]'}`}>
          <caption className="sr-only">
            Exercise schedule, {rangeLabel(days)}: one row per patient, one column per day
          </caption>
          <thead>
            <tr>
              <th
                scope="col"
                className={`${dense ? 'w-[168px]' : 'w-[220px]'} px-4 py-3 align-bottom text-label font-medium tracking-label text-secondary`}
              >
                Patient
              </th>
              {days.map((d) => {
                const isToday = d === today
                return (
                  <th
                    key={d}
                    scope="col"
                    aria-current={isToday ? 'date' : undefined}
                    className={`${colMin} border-l border-hairline px-2 py-2.5 align-bottom font-normal ${
                      isToday ? 'bg-brand-tint/40' : ''
                    }`}
                  >
                    <span className="block text-label font-medium tracking-label text-secondary">
                      {weekdayShort(d)}
                    </span>
                    <span className="flex items-center gap-1.5 text-copy-lg font-medium tabular-nums text-ink">
                      {dayOfMonth(d)}
                      {isToday && (
                        <>
                          <span className="dot-lime" aria-hidden />
                          <span className="sr-only">today</span>
                        </>
                      )}
                    </span>
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {patients.map((p) => {
              const tier = tierChip(p.risk_tier)
              return (
                <tr key={p.id}>
                  <th scope="row" className="border-t border-hairline px-4 py-3 align-top text-left font-normal">
                    <div className="flex items-start gap-3">
                      <Avatar name={p.name} tier={tierKey(p.risk_tier)} size="sm" className="mt-0.5" />
                      <div className="min-w-0">
                        <Link
                          to={`/patients/${p.id}`}
                          className="block truncate rounded-[6px] text-copy font-medium text-ink hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                        >
                          {p.name}
                        </Link>
                        {p.pathway && <span className="meta block truncate">{p.pathway}</span>}
                        {tier && <span className={`chip mt-1.5 ${tier.pill}`}>{tier.label}</span>}
                      </div>
                    </div>
                  </th>
                  {days.map((d) => (
                    <Cell key={d} patient={p} date={d} today={today} dense={dense} onAssign={onAssign} onOpen={onOpen} />
                  ))}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Cell({
  patient: p,
  date: d,
  today,
  dense,
  onAssign,
  onOpen,
}: {
  patient: SchedulePatient
  date: string
  today: string
  dense: boolean
  onAssign: (patientId: string, date: string) => void
  onOpen: (a: Assignment) => void
}) {
  const items = p.assignments
    .filter((a) => a.scheduled_for === d)
    .sort((x, y) => x.sort_order - y.sort_order || x.id - y.id)
  const isToday = d === today
  const canAdd = assignable(d, today)
  return (
    <td
      className={`border-l border-t border-hairline align-top ${dense ? 'p-1' : 'p-1.5'} ${
        isToday ? 'bg-brand-tint/40' : ''
      }`}
    >
      <div className={`group/cell flex flex-col gap-1 ${dense ? 'min-h-[72px]' : 'min-h-[96px]'}`}>
        {items.map((a) => (
          <AssignmentChip key={a.id} assignment={a} onOpen={onOpen} />
        ))}
        {canAdd && (
          <button
            type="button"
            onClick={() => onAssign(p.id, d)}
            aria-label={`Add an exercise for ${p.name} on ${longDay(d)}`}
            className={`mt-auto inline-flex h-7 w-7 items-center justify-center self-start rounded-pill text-secondary transition-[opacity,background-color,color] duration-state ease-apple hover:bg-soft hover:text-ink focus-visible:opacity-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus ${
              items.length === 0 ? 'opacity-80' : 'opacity-40 group-hover/cell:opacity-100'
            }`}
          >
            <Plus aria-hidden size={14} />
          </button>
        )}
      </div>
    </td>
  )
}
