import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  CopyPlus,
  MessageSquareText,
  Plus,
  Users,
} from 'lucide-react'
import { useId, useState, type DragEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useSetLoadUnit, useDuplicateAssignment, useTextToday } from '../../api/calendar'
import { ApiError } from '../../api/client'
import type { Assignment, LoadUnit, SchedulePatient } from '../../api/hep'
import { todayIso, useSchedule, useUpdateAssignment } from '../../api/hep'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import { Menu } from '../../components/Menu'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { AdherenceChip, AwaitingReview, LoadTrendChip } from './AdherenceChip'
import ApplyProgramDialog from './ApplyProgramDialog'
import AssignDialog from './AssignDialog'
import AssignmentChip from './AssignmentChip'
import AssignmentDialog from './AssignmentDialog'
import CopyWeekDialog from './CopyWeekDialog'
import MonthBoard from './MonthBoard'
import { CALENDAR } from './paths'
import {
  DRAG_TYPE,
  addDays,
  addMonths,
  assignable,
  dayOfMonth,
  firstOfMonth,
  longDay,
  mondayOf,
  monthLabel,
  rangeLabel,
  readDragged,
  shortDay,
  tierChip,
  tierKey,
  weekDays,
  weekdayShort,
} from './scheduleCopy'
import { unitOf } from './units'

type View = 'week' | 'month'

/** The week on one grid: ← Today → over the dates, one row per clinic chart
 *  (avatar, name, pathway, tier, the week's adherence and load trend, a
 *  menu), one column per day with today marked. A cell lists its
 *  assignments as chips and ends in a `+`; the chip opens AssignmentDialog,
 *  the `+` AssignDialog. The row menu copies last week forward or applies a
 *  program, and texts the lifter today's plan. A real table, so the dates
 *  are column headers and the names row headers.
 *
 *  A chip that is still open can be dragged to another day of its own row
 *  to move it, or with Option held to copy it; a done day can only be
 *  copied. The dialog's "Move" and "Copy to" do the same from the keyboard.
 *
 *  Week or Month: the month is six weeks at a glance, one strip per lifter
 *  and the picked lifter's calendar under them (MonthBoard); a day there
 *  opens its week here. The head also names the clinic whose calendar this
 *  is and switches the unit it reads loads in.
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
  const toast = useToast()
  const today = todayIso()
  const home = anchor === 'today' ? today : mondayOf(today)
  const [start, setStart] = useState(() => home)
  // The month view is the full page's; the demo screen keeps to its week.
  const [view, setView] = useState<View>('week')
  const [month, setMonth] = useState(() => firstOfMonth(today))
  const schedule = useSchedule(start, 7, undefined, { live })
  const days = schedule.data?.days ?? weekDays(start)
  const thisWeek = start === home
  const thisMonth = month === firstOfMonth(today)
  const [assign, setAssign] = useState<{ patientId: string; date: string } | null>(null)
  const [openId, setOpenId] = useState<number | null>(null)
  const [rowAction, setRowAction] = useState<{ kind: 'copy' | 'apply'; patientId: string } | null>(null)
  const captionId = useId()
  const move = useUpdateAssignment()
  const duplicate = useDuplicateAssignment()
  const textToday = useTextToday()
  const setUnit = useSetLoadUnit()
  const clinic = schedule.data?.clinic ?? null
  const unit = unitOf(clinic)

  const said = (fallback: string) => (e: unknown) =>
    toast(e instanceof ApiError && e.message ? e.message : fallback, 'warning')

  /** A chip dropped on another day of its row: moved, or copied when Option
   *  was held or the day was already done. */
  const onDropChip = (id: number, title: string, date: string, copy: boolean) => {
    if (copy) {
      duplicate.mutate(
        { id, dates: [date] },
        { onSuccess: () => toast(`${title} copied to ${shortDay(date)}`, 'success'), onError: said('Could not copy it') },
      )
    } else {
      move.mutate(
        { id, scheduled_for: date },
        { onSuccess: () => toast(`${title} moved to ${shortDay(date)}`, 'success'), onError: said('Could not move it') },
      )
    }
  }

  const onTextToday = (p: SchedulePatient) =>
    textToday.mutate(
      { patientId: p.id, by: p.assigned_provider_id ?? undefined },
      {
        onSuccess: (r) =>
          toast(
            r.sent
              ? `Texted ${p.name.split(' ')[0]} today’s plan, with a link that opens it`
              : `The text to ${p.name.split(' ')[0]} did not go: ${r.detail || r.status}`,
            r.sent ? 'success' : 'warning',
          ),
        onError: said('Could not text the plan'),
      },
    )

  const onUnit = (next: LoadUnit) => {
    if (next === unit) return
    setUnit.mutate(next, {
      onSuccess: () => toast(`Loads now read in ${next === 'lb' ? 'pounds' : 'kilograms'}`, 'success'),
      onError: said('Could not change the unit'),
    })
  }

  const patients = schedule.data?.patients ?? []
  const careTeam = schedule.data?.care_team ?? []
  const assigning = assign ? patients.find((p) => p.id === assign.patientId) : undefined
  const acting = rowAction ? patients.find((p) => p.id === rowAction.patientId) : undefined
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
  const waiting = patients.reduce((n, p) => n + (p.awaiting_review ?? 0), 0)

  const monthly = view === 'month' && !dense
  const step = (n: number) => (monthly ? setMonth(addMonths(month, n)) : setStart(addDays(start, n * 7)))
  const goHome = () => (monthly ? setMonth(firstOfMonth(today)) : setStart(home))

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div
          className="glass inline-flex items-center gap-0.5 rounded-pill p-1"
          role="group"
          aria-label={monthly ? 'Month' : 'Week'}
        >
          <button
            type="button"
            className="btn-icon btn-sm"
            aria-label={monthly ? 'Previous month' : 'Previous week'}
            onClick={() => step(-1)}
          >
            <ChevronLeft aria-hidden />
          </button>
          <button
            type="button"
            className="btn-plain btn-sm !px-3"
            disabled={monthly ? thisMonth : thisWeek}
            onClick={goHome}
          >
            Today
          </button>
          <button
            type="button"
            className="btn-icon btn-sm"
            aria-label={monthly ? 'Next month' : 'Next week'}
            onClick={() => step(1)}
          >
            <ChevronRight aria-hidden />
          </button>
        </div>
        <h2 id={captionId} className="text-subhead font-medium text-ink">
          {monthly ? monthLabel(month) : rangeLabel(days)}
        </h2>
        {schedule.data && (
          <span className="meta tabular-nums">
            {clinic && !dense && <>{clinic.name} · </>}
            {patients.length} patient{patients.length === 1 ? '' : 's'}
            {!monthly && (
              <>
                {' · '}
                {all.length} exercise{all.length === 1 ? '' : 's'}
                {all.length > 0 && ` · ${doneCount} done`}
              </>
            )}
            {waiting > 0 && (
              <>
                {' · '}
                <Link to={CALENDAR.review} className="text-risk-med-ink hover:underline">
                  {waiting} to review
                </Link>
              </>
            )}
          </span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {!dense && (
            <>
              {/* The unit is the clinic's: shown once the clinic is known, so
                  it never opens on one unit and settles on the other. */}
              {clinic && (
              <SegmentedControl<LoadUnit>
                options={[
                  { key: 'lb', label: 'lb', text: 'Pounds' },
                  { key: 'kg', label: 'kg', text: 'Kilograms' },
                ]}
                value={unit}
                onChange={onUnit}
                size="sm"
                tone="glass"
                role="radiogroup"
                aria-label="Unit loads are read in"
              />
              )}
              <SegmentedControl<View>
                options={[
                  { key: 'week', label: 'Week' },
                  { key: 'month', label: 'Month' },
                ]}
                value={view}
                onChange={setView}
                size="sm"
                tone="glass"
                role="radiogroup"
                aria-label="How much of the calendar to show"
              />
            </>
          )}
          {aside}
        </div>
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
        ) : monthly ? (
          <MonthBoard
            month={month}
            unit={unit}
            onOpenWeek={(day) => {
              setStart(mondayOf(day))
              setView('week')
            }}
          />
        ) : (
          <>
            <Grid
              patients={patients}
              days={days}
              today={today}
              dense={dense}
              captionId={captionId}
              onAssign={(patientId, date) => setAssign({ patientId, date })}
              onOpen={(a) => setOpenId(a.id)}
              onRowAction={(kind, patientId) => setRowAction({ kind, patientId })}
              onDropChip={onDropChip}
              onTextToday={onTextToday}
            />
            {!dense && (
              <p className="meta mt-3 px-1">
                Drag an exercise to another day of the same row to move it; hold Option to copy
                it. A day that is done stays where it is and can only be copied.
              </p>
            )}
          </>
        )}
      </div>

      {assign && assigning && (
        <AssignDialog
          key={`${assign.patientId}-${assign.date}`}
          patient={assigning}
          date={assign.date}
          days={days}
          assignments={assigning.assignments}
          careTeam={careTeam}
          unit={unit}
          onClose={() => setAssign(null)}
        />
      )}
      {opened && (
        <AssignmentDialog
          key={opened.a.id}
          assignment={opened.a}
          patientName={opened.p.name}
          days={days}
          careTeam={careTeam}
          unit={unit}
          onClose={() => setOpenId(null)}
        />
      )}
      {rowAction?.kind === 'copy' && acting && (
        <CopyWeekDialog
          key={`copy-${acting.id}-${start}`}
          patient={acting}
          toStart={start}
          careTeam={careTeam}
          onClose={() => setRowAction(null)}
        />
      )}
      {rowAction?.kind === 'apply' && acting && (
        <ApplyProgramDialog
          key={`apply-${acting.id}-${start}`}
          patient={acting}
          defaultStart={start}
          careTeam={careTeam}
          onClose={() => setRowAction(null)}
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
  onRowAction,
  onDropChip,
  onTextToday,
}: {
  patients: SchedulePatient[]
  days: string[]
  today: string
  dense: boolean
  captionId: string
  onAssign: (patientId: string, date: string) => void
  onOpen: (a: Assignment) => void
  onRowAction: (kind: 'copy' | 'apply', patientId: string) => void
  onDropChip: (id: number, title: string, date: string, copy: boolean) => void
  onTextToday: (p: SchedulePatient) => void
}) {
  const colMin = dense ? 'min-w-[92px]' : 'min-w-[128px]'
  const lastWeek = rangeLabel(weekDays(addDays(days[0], -7)))
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
                className={`${dense ? 'w-[176px]' : 'w-[236px]'} px-4 py-3 align-bottom text-label font-medium tracking-label text-secondary`}
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
              const adherence = p.adherence ?? null
              return (
                <tr key={p.id}>
                  <th scope="row" className={`border-t border-hairline py-3 pl-4 pr-2 align-top text-left font-normal`}>
                    <div className="flex items-start gap-3">
                      <Avatar name={p.name} tier={tierKey(p.risk_tier)} size="sm" className="mt-0.5" />
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/patients/${p.id}`}
                          className="block truncate rounded-[6px] text-copy font-medium text-ink hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                        >
                          {p.name}
                        </Link>
                        {p.pathway && <span className="meta block truncate">{p.pathway}</span>}
                        {(tier || (adherence && adherence.assigned > 0) || p.load_week) && (
                          <div className="mt-1.5 flex flex-wrap items-center gap-1">
                            {tier && <span className={`chip ${tier.pill}`}>{tier.label}</span>}
                            {adherence && (
                              <AdherenceChip done={adherence.done} assigned={adherence.assigned} pct={adherence.pct} />
                            )}
                            {!dense && (
                              <LoadTrendChip
                                changePct={p.load_week?.done_change_pct ?? p.load_week?.change_pct}
                              />
                            )}
                            {!dense && (p.over_week ?? 0) > 0 && (
                              <span
                                className="chip bg-risk-med-tint normal-case tabular-nums text-risk-med-ink"
                                title="Done days in the last seven that went over the dose"
                              >
                                {p.over_week} over the dose
                              </span>
                            )}
                          </div>
                        )}
                        {(p.awaiting_review ?? 0) > 0 && <AwaitingReview count={p.awaiting_review} className="mt-1.5" />}
                      </div>
                      <Menu
                        label={`More for ${p.name}`}
                        triggerClassName="btn-icon btn-sm -mr-1 -mt-1 shrink-0"
                        items={[
                          {
                            key: 'copy',
                            label: 'Copy last week →',
                            description: `${lastWeek} onto ${rangeLabel(days)}`,
                            icon: <CopyPlus />,
                            onSelect: () => onRowAction('copy', p.id),
                          },
                          {
                            key: 'apply',
                            label: 'Apply a program…',
                            description: 'A pattern by weekday, from a start date',
                            icon: <ClipboardList />,
                            onSelect: () => onRowAction('apply', p.id),
                          },
                          {
                            key: 'text',
                            label: 'Text today’s plan',
                            description: 'A text with a link that opens the app on today',
                            icon: <MessageSquareText />,
                            onSelect: () => onTextToday(p),
                          },
                        ]}
                      />
                    </div>
                  </th>
                  {days.map((d) => (
                    <Cell
                      key={d}
                      patient={p}
                      date={d}
                      today={today}
                      dense={dense}
                      onAssign={onAssign}
                      onOpen={onOpen}
                      onDropChip={onDropChip}
                    />
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
  onDropChip,
}: {
  patient: SchedulePatient
  date: string
  today: string
  dense: boolean
  onAssign: (patientId: string, date: string) => void
  onOpen: (a: Assignment) => void
  onDropChip: (id: number, title: string, date: string, copy: boolean) => void
}) {
  const toast = useToast()
  const [over, setOver] = useState(false)
  const items = p.assignments
    .filter((a) => a.scheduled_for === d)
    .sort((x, y) => x.sort_order - y.sort_order || x.id - y.id)
  const isToday = d === today
  const canAdd = assignable(d, today)

  // While a chip is over the cell only its type can be read, not what it
  // is: whose row it came from is checked when it lands.
  const onDragOver = (e: DragEvent<HTMLTableCellElement>) => {
    if (!canAdd || !e.dataTransfer.types.includes(DRAG_TYPE)) return
    e.preventDefault()
    e.dataTransfer.dropEffect = e.altKey || e.dataTransfer.effectAllowed === 'copy' ? 'copy' : 'move'
    if (!over) setOver(true)
  }
  const onDrop = (e: DragEvent<HTMLTableCellElement>) => {
    setOver(false)
    const dragged = readDragged(e.dataTransfer.getData(DRAG_TYPE))
    if (!dragged) return
    e.preventDefault()
    if (dragged.patientId !== p.id) {
      toast('An exercise moves within one person’s row. Use “Apply a program” to give it to someone else.', 'info')
      return
    }
    if (dragged.date === d) return
    const row = p.assignments.find((a) => a.id === dragged.id)
    onDropChip(dragged.id, row?.title ?? 'The exercise', d, e.altKey || dragged.done)
  }

  return (
    <td
      onDragOver={dense ? undefined : onDragOver}
      onDragLeave={dense ? undefined : () => setOver(false)}
      onDrop={dense ? undefined : onDrop}
      className={`border-l border-t border-hairline align-top transition-colors duration-state ease-apple ${
        dense ? 'p-1' : 'p-1.5'
      } ${over ? 'bg-brand-tint' : isToday ? 'bg-brand-tint/40' : ''}`}
    >
      <div className={`group/cell flex flex-col gap-1 ${dense ? 'min-h-[72px]' : 'min-h-[96px]'}`}>
        {items.map((a) => (
          <AssignmentChip key={a.id} assignment={a} onOpen={onOpen} draggable={!dense} />
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
