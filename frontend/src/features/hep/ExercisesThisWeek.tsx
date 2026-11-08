import { CalendarDays, ChevronRight, Plus } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { todayIso, usePatientSchedule } from '../../api/hep'
import { useHealth } from '../../api/queries'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay, SkeletonCard } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import AssignmentChip from './AssignmentChip'
import AssignmentDialog from './AssignmentDialog'
import { dayOfMonth, mondayOf, weekDays, weekdayShort } from './scheduleCopy'

/** The patient page's "Exercises this week" strip: this week's seven days
 *  with the patient's assignments as chips (status and pain on each), the
 *  count done, and the way to the schedule. A chip opens the same dialog
 *  the grid uses. Rendered only while the server's HEP flag is on. */
export default function ExercisesThisWeek({
  patientId,
  refreshing,
}: {
  patientId: string
  refreshing: boolean
}) {
  const hep = useHealth().data?.hep === true
  const today = todayIso()
  const start = mondayOf(today)
  const week = usePatientSchedule(patientId, start, 7, { enabled: hep })
  const [openId, setOpenId] = useState<number | null>(null)
  if (!hep) return null
  if (week.isLoading) return <SkeletonCard rows={2} />

  const days = week.data?.days ?? weekDays(start)
  const items = week.data?.assignments ?? []
  const done = items.filter((a) => a.status === 'done').length
  const open = openId == null ? undefined : items.find((a) => a.id === openId)

  return (
    <SectionCard
      title="Exercises this week"
      icon={<Tile size="sm" family="teal" icon={<CalendarDays />} />}
      aside={items.length > 0 ? `${done} of ${items.length} done` : undefined}
      action={
        <Link to="/exercise-schedule" className="btn-plain btn-sm">
          Schedule <ChevronRight aria-hidden size={14} />
        </Link>
      }
    >
      <RefreshOverlay show={refreshing} />
      {week.isError ? (
        <EmptyState variant="inline" title="This week couldn’t be loaded." icon={<CalendarDays />}>
          Refresh the page to try again.
        </EmptyState>
      ) : items.length === 0 ? (
        <EmptyState
          variant="inline"
          title="Nothing scheduled this week"
          icon={<CalendarDays />}
          family="teal"
          action={
            <Link to="/exercise-schedule" className="btn-tinted">
              <Plus size={16} aria-hidden /> Schedule exercises
            </Link>
          }
        >
          Put exercises on their days from the schedule; they show in the app at once.
        </EmptyState>
      ) : (
        <ol className="grid gap-1.5 sm:grid-cols-7" aria-label="This week, by day">
          {days.map((d) => {
            const isToday = d === today
            const todays = items
              .filter((a) => a.scheduled_for === d)
              .sort((x, y) => x.sort_order - y.sort_order || x.id - y.id)
            return (
              <li
                key={d}
                aria-current={isToday ? 'date' : undefined}
                className={`rounded-control p-1.5 ${isToday ? 'bg-brand-tint/40' : 'bg-soft/60'}`}
              >
                <div className="flex items-baseline gap-1 px-1 pb-1">
                  <span className="text-label font-medium text-secondary">{weekdayShort(d)}</span>
                  <span className="text-copy font-medium tabular-nums text-ink">{dayOfMonth(d)}</span>
                  {isToday && (
                    <>
                      <span className="dot-lime ml-auto" aria-hidden />
                      <span className="sr-only">today</span>
                    </>
                  )}
                </div>
                {todays.length === 0 ? (
                  <p className="meta px-1 py-1">
                    <span aria-hidden>—</span>
                    <span className="sr-only">nothing</span>
                  </p>
                ) : (
                  <ul className="space-y-1">
                    {todays.map((a) => (
                      <li key={a.id}>
                        <AssignmentChip assignment={a} onOpen={(x) => setOpenId(x.id)} />
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            )
          })}
        </ol>
      )}
      {open && (
        <AssignmentDialog
          key={open.id}
          assignment={open}
          patientName={week.data?.patient.name ?? 'the patient'}
          days={days}
          onClose={() => setOpenId(null)}
        />
      )}
    </SectionCard>
  )
}
