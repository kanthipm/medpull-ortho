/* The program (route `/today/program`): the fourteen days around today as
   two rows of seven, one dot per exercise — done, missed, still to do —
   with today ringed, and the chosen day's exercises under it. Past days
   are read-only with what happened, today's rows open the exercise, the
   days ahead are a preview (docs/dev/hep-schedule.md, "Second pass",
   "Patient web UI"). Today is where it opens. */

import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useApp } from '../../core/appModel'
import { Dates, DOT, hasProgram, isOpenAssignment, type ExerciseAssignment, type ProgramDay } from '../../core/models'
import { Card, cx, EmptyRow, ErrorBanner, NavBar, Screen, SecondaryButton, Spinner } from '../../ui/components'
import { CardTitleRow, RowDivider } from '../../ui/rows'
import { useBack } from '../../ui/useBack'
import { ExerciseRow } from './ExercisesSection'

export function ProgramView() {
  const app = useApp()
  const navigate = useNavigate()
  const location = useLocation()
  const back = useBack('/today')
  const from = (location.state as { from?: string } | null)?.from ?? 'Today'
  const today = Dates.dayString(new Date())
  const [selected, setSelected] = useState(today)
  const [waited, setWaited] = useState(app.program != null)

  // The program polls beside the day while this screen is showing, so a
  // change on the therapist's board lands here too.
  useEffect(() => app.watchProgram(), [app])
  useEffect(() => {
    let cancelled = false
    void app.refreshProgram(false).then(() => { if (!cancelled) setWaited(true) })
    return () => { cancelled = true }
  }, [app])

  const program = app.program
  const day = program?.days.find((d) => d.date === selected) ?? null
  const open = (a: ExerciseAssignment) => navigate(`/today/exercises/${a.id}`, { state: { from: 'Program' } })

  let body: React.ReactNode
  if (!program && !waited) {
    body = <div className="hstack" style={{ justifyContent: 'center', color: 'rgb(var(--brand))', padding: 32 }}><Spinner /></div>
  } else if (!program) {
    body = (
      <div className="stack-12">
        <ErrorBanner text="Couldn’t load your program. Check your connection and try again." />
        <SecondaryButton title="Try again" icon="arrow.counterclockwise" onClick={() => { setWaited(false); void app.refreshProgram(false).then(() => setWaited(true)) }} />
      </div>
    )
  } else if (!hasProgram(program)) {
    body = (
      <Card padding={0}>
        <EmptyRow icon="calendar" title="No exercises on your program yet" detail="They show up here as soon as your therapist sets them." />
      </Card>
    )
  } else {
    const past = program.days.filter((d) => d.date < today)
    const ahead = program.days.filter((d) => d.date >= today)
    body = (
      <>
        <Card padding={0}>
          <div className="day-strip" role="group" aria-label="The days of your program">
            {past.length > 0 && <span className="week-label">The last {past.length} days</span>}
            {past.map((d) => <DayCell key={d.date} d={d} today={today} selected={d.date === selected} onSelect={() => setSelected(d.date)} />)}
            {ahead.length > 0 && <span className="week-label">From today</span>}
            {ahead.map((d) => <DayCell key={d.date} d={d} today={today} selected={d.date === selected} onSelect={() => setSelected(d.date)} />)}
          </div>
          <div className="dot-legend" aria-hidden="true">
            <span><i className="done" />done</span>
            <span><i />to do</span>
            <span><i className="missed" />missed</span>
          </div>
        </Card>
        <DayCard day={day} date={selected} today={today} onOpen={open} />
      </>
    )
  }

  return (
    <Screen withTabBar nav={(s) => <NavBar title="Program" scrolled={s} back={{ label: from, onClick: back }} />}>
      <div className="content" style={{ gap: 14, padding: '8px 18px 28px' }}>
        {body}
      </div>
    </Screen>
  )
}

/** One day of the strip: the weekday, the date, a dot for each exercise
 *  in its state. Today is ringed; the chosen day is filled. */
function DayCell({ d, today, selected, onSelect }: { d: ProgramDay; today: string; selected: boolean; onSelect: () => void }) {
  const date = Dates.parse(d.date)
  const past = d.date < today
  const isToday = d.date === today
  const dots = dotsFor(d, past)
  const longDay = date ? date.toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' }) : d.date
  const spoken = d.assigned === 0
    ? `${longDay}, a rest day`
    : `${longDay}, ${d.assigned} ${d.assigned === 1 ? 'exercise' : 'exercises'}, ${d.done} done${d.missed > 0 ? `, ${d.missed} missed` : ''}`
  return (
    <button type="button" className={cx('day-cell', past && 'past', isToday && 'today')} aria-pressed={selected}
      aria-label={isToday ? `Today, ${spoken}` : spoken} onClick={onSelect}>
      <span className="wd">{date ? date.toLocaleDateString(undefined, { weekday: 'narrow' }) : ''}</span>
      <span className="num">{date ? date.getDate() : ''}</span>
      <span className="day-dots">{dots.map((c, i) => <i key={i} className={c || undefined} />)}</span>
    </button>
  )
}

/** A dot's class per exercise: done, skipped, missed (still to do and the
 *  day has passed), or plain for one still to do. Five at most. */
function dotsFor(d: ProgramDay, past: boolean): string[] {
  if (d.items.length > 0) {
    return d.items.slice(0, 5).map((a) => (a.status === 'done' ? 'done' : a.status === 'skipped' ? 'skipped' : past ? 'missed' : ''))
  }
  const out: string[] = []
  for (let i = 0; i < d.done; i++) out.push('done')
  for (let i = 0; i < d.skipped; i++) out.push('skipped')
  for (let i = 0; i < d.missed; i++) out.push('missed')
  while (out.length < d.assigned) out.push('')
  return out.slice(0, 5)
}

/** The chosen day's exercises. Today's open rows open the exercise; past
 *  rows show what happened and still open, so a done one can be looked at
 *  and one still to do can be caught up; the days ahead are a preview. */
function DayCard({ day, date, today, onOpen }: { day: ProgramDay | null; date: string; today: string; onOpen: (a: ExerciseAssignment) => void }) {
  const past = date < today
  const future = date > today
  const items = day?.items ?? []
  const ordered = date === today ? [...items.filter(isOpenAssignment), ...items.filter((a) => !isOpenAssignment(a))] : items
  const context = past ? 'past' : future ? 'future' : 'today'
  return (
    <Card padding={0}>
      <CardTitleRow title={dayTitle(date, today)} note={dayNote(day, date, past, future)} />
      {ordered.length === 0 ? (
        <div style={{ paddingBottom: 4 }}>
          <EmptyRow icon="figure.strengthtraining.traditional" title={future ? 'Nothing planned yet' : 'A rest day'}
            detail={future ? 'Your therapist may still add to this day.' : past ? 'Nothing was scheduled.' : 'Nothing scheduled today.'} />
        </div>
      ) : (
        <>
          {ordered.map((a, i) => (
            <div key={a.id}>
              {future ? (
                <ExerciseRow a={a} context="future" />
              ) : (
                <button type="button" className="row-button" onClick={() => onOpen(a)}>
                  <ExerciseRow a={a} context={context} />
                </button>
              )}
              {i < ordered.length - 1 && <RowDivider />}
            </div>
          ))}
          <div style={{ height: 4 }} />
        </>
      )}
    </Card>
  )
}

/** "Today", "Yesterday", "Tomorrow", else the weekday. */
function dayTitle(date: string, today: string): string {
  const n = Dates.daysAgo(date)
  if (date === today) return 'Today'
  if (n === 1) return 'Yesterday'
  if (n === -1) return 'Tomorrow'
  const d = Dates.parse(date)
  return d ? d.toLocaleDateString(undefined, { weekday: 'long' }) : date
}

/** "Nov 3 · 3 of 4 done · 1 missed" beside the title. */
function dayNote(day: ProgramDay | null, date: string, past: boolean, future: boolean): string {
  const parts = [Dates.monthDay(date)]
  if (!day || day.assigned === 0) return parts.join(DOT)
  if (future) parts.push(`${day.assigned} ${day.assigned === 1 ? 'exercise' : 'exercises'}`)
  else {
    parts.push(`${day.done} of ${day.assigned} done`)
    if (past && day.missed > 0) parts.push(`${day.missed} missed`)
  }
  return parts.join(DOT)
}
