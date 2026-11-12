/* Today's exercises: the therapist's schedule for this day, one row per
   exercise, above the plan on Today (docs/dev/hep-schedule.md, "Patient web
   UI"). A row reads like a plan row — a glyph, the title, one line of
   facts, the state — and opens the exercise screen. "See the week" and the
   row under the list open the program (the second pass). Between visits
   (docs/dev/pt.md) the card also says when the day is a rest day the clinic
   set and when the next visit is, and "Your program" under it carries the
   phase, the person's goals and the line about their trainer. */

import type { ReactNode } from 'react'
import {
  ceilingOf, Dates, DOT, effortLabel, goalRating, handoffLine, isDoneAssignment, isOpenAssignment, nextVisitDetail,
  painLabel, therapistShortName, typeset,
  type ExerciseAssignment, type ExercisesResponse, type FunctionGoal, type ProgramSummary,
} from '../../core/models'
import { Card, cx, EmptyRow, InsetDivider } from '../../ui/components'
import { Sym } from '../../ui/icons'
import { CardTitleRow, Chevron, Glyph, ListRow, RowDivider } from '../../ui/rows'

/** The card. Today decides whether to show it (`hasExerciseSchedule`).
 *  `onProgram` adds the way to the program: the title's action and a row
 *  under the list. `programRow` is false when "Your program" sits under
 *  this card and carries that row itself. */
export function ExercisesCard({ feed, onOpen, onProgram, programRow = true }: {
  feed: ExercisesResponse; onOpen: (a: ExerciseAssignment) => void; onProgram?: () => void; programRow?: boolean
}) {
  const items = feed.items
  const overdue = feed.overdue ?? []
  const done = items.filter(isDoneAssignment).length
  const open = items.filter(isOpenAssignment)
  const settled = items.filter((a) => !isOpenAssignment(a))
  const ordered = [...open, ...settled]
  const empty = items.length === 0 && overdue.length === 0
  const rest = feed.restDay ?? null
  const visit = feed.nextVisit ?? null
  const footer = !!onProgram && programRow
  return (
    <Card padding={0}>
      <CardTitleRow title="Today’s exercises" note={items.length === 0 ? null : `${done} of ${items.length} done`}
        actionTitle={onProgram ? 'See the week' : undefined} onAction={onProgram} />
      {rest && !empty && <RestDayLine note={rest.note} underTitle />}
      {empty ? (
        <div style={{ paddingBottom: 4 }}>
          {rest
            ? <EmptyRow icon="moon.fill" title="Rest day" detail={typeset((rest.note ?? '').trim()) || nextExercisesLine(feed) || undefined} />
            : <EmptyRow icon="figure.strengthtraining.traditional" title="Nothing today" detail={restDayLine(feed)} />}
        </div>
      ) : (
        <>
          {ordered.map((a, i) => (
            <div key={a.id}>
              <button type="button" className="row-button" onClick={() => onOpen(a)}>
                <ExerciseRow a={a} />
              </button>
              {i < ordered.length - 1 && <RowDivider />}
            </div>
          ))}
          {overdue.length > 0 && (
            <>
              {ordered.length > 0 && <RowDivider />}
              <div className="row" style={{ paddingTop: 10, paddingBottom: 2 }}>
                <span className="t-label c-muted">Still to do from earlier this week</span>
              </div>
              {overdue.map((a, i) => (
                <div key={a.id}>
                  <button type="button" className="row-button" onClick={() => onOpen(a)}>
                    <ExerciseRow a={a} dayLabel={dayName(a.scheduledFor)} />
                  </button>
                  {i < overdue.length - 1 && <RowDivider />}
                </div>
              ))}
            </>
          )}
          {!footer && !visit && <div style={{ height: 4 }} />}
        </>
      )}
      {visit && (
        <>
          <InsetDivider leading={16} />
          <CardLine symbol="calendar"><b>Next visit</b>{DOT}{nextVisitDetail(visit)}</CardLine>
        </>
      )}
      {footer && (
        <>
          <InsetDivider leading={16} />
          <ListRow title="Your program" subtitle="The last week and the one ahead, day by day." symbol="calendar" family="teal" onClick={onProgram} />
        </>
      )}
    </Card>
  )
}

// MARK: - Between visits (docs/dev/pt.md)

/** One quiet line in a card of rows: a small mark where a row's glyph
 *  sits, then the words. */
export function CardLine({ symbol, children, underTitle = false }: { symbol: string; children: ReactNode; underTitle?: boolean }) {
  return (
    <div className={cx('card-line', underTitle && 'under-title')}>
      <span className="mark" aria-hidden="true"><Sym name={symbol} size={15} weight="medium" /></span>
      <span className="grow">{children}</span>
    </div>
  )
}

/** "Rest day", and the clinic's note when it left one: the day is empty,
 *  or light, on purpose. */
export function RestDayLine({ note, underTitle }: { note?: string | null; underTitle?: boolean }) {
  const words = note?.trim()
  return (
    <CardLine symbol="moon.fill" underTitle={underTitle}>
      <b>Rest day</b>{words ? <>{DOT}{typeset(words)}</> : null}
    </CardLine>
  )
}

/** The therapist's ceiling on a dose, in her words, wherever the dose is
 *  read: the exercise screen and the session while the person works. A
 *  quiet note in ink, never a warning; nothing when she wrote none. */
export function CeilingNote({ a }: { a: ExerciseAssignment }) {
  const text = ceilingOf(a)
  if (!text) return null
  const who = a.assignedByName?.trim() ? therapistShortName(a.assignedByName) : 'Your therapist'
  return (
    <div className="ceiling-note">
      <span className="t-label-m secondary">{who}’s limit</span>
      <span className="t-copy-lg-m c-ink">{typeset(text)}</span>
    </div>
  )
}

/** "Your program": where the person is between visits. The phase and what
 *  it is for, their own goals with the latest rating out of ten (the first
 *  beside it when it moved), and the one line about their trainer. Today
 *  shows it under the day's exercises and hands it the way to the calendar.
 *  The caller leaves it out when there is nothing to say
 *  (`hasProgramSummary`). */
export function ProgramSummaryCard({ summary, onCalendar }: { summary: ProgramSummary; onCalendar?: () => void }) {
  const phase = summary.phase ?? null
  const goals = summary.goals ?? []
  const trainer = handoffLine(summary.handoff)
  const pips = phase && phase.count > 1 && phase.count <= 8 ? phase.count : 0
  return (
    <Card padding={0}>
      <CardTitleRow title="Your program" />
      {phase && (
        <div className="program-phase">
          <span className="t-copy-lg-m c-ink">Phase {phase.number} of {phase.count}{phase.name ? `${DOT}${typeset(phase.name)}` : ''}</span>
          {pips > 0 && (
            <div className="set-pips" aria-hidden="true">
              {Array.from({ length: pips }, (_, i) => (
                <i key={i} className={i + 1 < phase.number ? 'done' : i + 1 === phase.number ? 'now' : undefined} />
              ))}
            </div>
          )}
          {phase.goal && <span className="t-copy c-body lh-2">{typeset(phase.goal)}</span>}
        </div>
      )}
      {goals.length > 0 && (
        <>
          {phase && <InsetDivider leading={16} />}
          <div className="goal-head">
            <span>{goals.length === 1 ? 'Your goal' : 'Your goals'}</span>
            <span className="spacer" />
            <span>out of 10</span>
          </div>
          <ul className="goal-list">
            {goals.map((g) => <GoalRow key={g.id} g={g} />)}
          </ul>
        </>
      )}
      {trainer && (
        <>
          {(phase || goals.length > 0) && <InsetDivider leading={16} />}
          <CardLine symbol="person.2.fill">{trainer}</CardLine>
        </>
      )}
      {onCalendar && (
        <>
          <InsetDivider leading={16} />
          <ListRow title="Day by day" subtitle="The last week and the one ahead." symbol="calendar" family="teal" onClick={onCalendar} />
        </>
      )}
    </Card>
  )
}

/** One goal in the person's words and where they put it: "6", or "4 → 6"
 *  when the first rating was different. No colour: the number is theirs. */
function GoalRow({ g }: { g: FunctionGoal }) {
  const rating = goalRating(g)
  const moved = g.first != null && g.latest != null && g.first !== g.latest
  const spoken = g.latest == null ? `${g.text}, not rated yet`
    : `${g.text}, ${g.latest} out of 10${moved ? `, ${g.first} at first` : ''}`
  return (
    <li className="goal-row" aria-label={spoken}>
      <span className="t-copy-lg c-ink grow" aria-hidden="true">{typeset(g.text)}</span>
      {rating
        ? <span className="row-figure" aria-hidden="true"><b>{rating}</b></span>
        : <span className="t-label c-muted" aria-hidden="true">not rated yet</span>}
    </li>
  )
}

/** "Monday", for a row from an earlier day. */
function dayName(iso: string): string {
  const day = Dates.parse(iso)
  return day ? day.toLocaleDateString(undefined, { weekday: 'long' }) : iso
}

/** "Your next exercises are on Wednesday.", or null when the week ahead
 *  has none yet. */
function nextExercisesLine(feed: ExercisesResponse): string | null {
  const next = feed.week.find((d) => d.date > feed.date && d.assigned > 0)
  if (!next) return null
  const day = Dates.parse(next.date)
  return `Your next exercises are on ${day ? day.toLocaleDateString(undefined, { weekday: 'long' }) : next.date}.`
}

/** "A rest day. Your next exercises are on Wednesday." */
function restDayLine(feed: ExercisesResponse): string {
  return `A rest day. ${nextExercisesLine(feed) ?? 'New exercises from your therapist show up here.'}`
}

/** One exercise as a row: the glyph, the title, the dose with the state
 *  and a film badge when there is a clip to follow, then the therapist's
 *  note in her words. A chevron while it is to do; the state glyph after.
 *  `context` is the program's: a past day's open row reads "missed", a
 *  day ahead is a preview with nothing to tap. */
export function ExerciseRow({ a, dayLabel, context = 'today' }: {
  a: ExerciseAssignment; dayLabel?: string; context?: 'today' | 'past' | 'future'
}) {
  const isDone = isDoneAssignment(a)
  const open = isOpenAssignment(a)
  let status: [string, string] | null = null
  if (isDone) {
    const bits = ['sent', painLabel(a.completion?.painAfter), effortLabel(a.completion?.effort)].filter((s): s is string => !!s)
    status = [bits.join(DOT), 'c-muted']
  } else if (a.status === 'skipped') status = [context === 'today' ? 'skipped today' : 'skipped', 'c-muted']
  else if (context === 'past') status = ['missed', 'c-risk-med']
  const spoken = `${a.title}, ${a.dose}${isDone ? ', done' : open ? (context === 'past' ? ', missed' : '') : ', skipped'}${a.video ? ', with a clip' : ''}`
  return (
    <div className="row" aria-label={spoken}>
      <Glyph name="figure.strengthtraining.traditional" family="teal" />
      <span className="row-main">
        <span className="row-title" style={isDone ? { textDecoration: 'line-through', textDecorationColor: 'rgb(var(--muted))' } : undefined}>{a.title}</span>
        <span className="t-label clamp-2">
          {dayLabel && <><span className="c-body">{dayLabel}</span><span className="c-muted">{DOT}</span></>}
          <span className="c-muted">{a.dose}</span>
          {status && <><span className="c-muted">{DOT}</span><span className={status[1]}>{status[0]}</span></>}
          {a.video && <><span className="c-muted">{DOT}</span><span className="clip-badge"><Sym name="film" size={11} weight="medium" />Clip</span></>}
        </span>
        {a.clinicianInstructions && (
          <span className="t-label c-body clamp-2" style={{ marginTop: 2 }}>“{typeset(a.clinicianInstructions)}”</span>
        )}
      </span>
      {open ? (context === 'future' ? null : <Chevron />) : (
        <span className={cx(isDone ? 'c-risk-low' : 'c-muted')}>
          <Sym name={isDone ? 'checkmark.circle.fill' : 'minus.circle'} size={18} weight="regular" />
        </span>
      )}
    </div>
  )
}
