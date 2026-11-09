/* Today's exercises: the therapist's schedule for this day, one row per
   exercise, above the plan on Today (docs/dev/hep-schedule.md, "Patient web
   UI"). A row reads like a plan row — a glyph, the title, one line of
   facts, the state — and opens the exercise screen. "See the week" and the
   row under the list open the program (the second pass). */

import {
  Dates, DOT, effortLabel, isDoneAssignment, isOpenAssignment, painLabel, typeset,
  type ExerciseAssignment, type ExercisesResponse,
} from '../../core/models'
import { Card, cx, EmptyRow, InsetDivider } from '../../ui/components'
import { Sym } from '../../ui/icons'
import { CardTitleRow, Chevron, Glyph, ListRow, RowDivider } from '../../ui/rows'

/** The card. Today decides whether to show it (`hasExerciseSchedule`).
 *  `onProgram` adds the way to the program: the title's action and a row
 *  under the list. */
export function ExercisesCard({ feed, onOpen, onProgram }: {
  feed: ExercisesResponse; onOpen: (a: ExerciseAssignment) => void; onProgram?: () => void
}) {
  const items = feed.items
  const overdue = feed.overdue ?? []
  const done = items.filter(isDoneAssignment).length
  const open = items.filter(isOpenAssignment)
  const settled = items.filter((a) => !isOpenAssignment(a))
  const ordered = [...open, ...settled]
  return (
    <Card padding={0}>
      <CardTitleRow title="Today’s exercises" note={items.length === 0 ? null : `${done} of ${items.length} done`}
        actionTitle={onProgram ? 'See the week' : undefined} onAction={onProgram} />
      {items.length === 0 && overdue.length === 0 ? (
        <div style={{ paddingBottom: 4 }}>
          <EmptyRow icon="figure.strengthtraining.traditional" title="Nothing today" detail={restDayLine(feed)} />
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
          {!onProgram && <div style={{ height: 4 }} />}
        </>
      )}
      {onProgram && (
        <>
          <InsetDivider leading={16} />
          <ListRow title="Your program" subtitle="The last week and the one ahead, day by day." symbol="calendar" family="teal" onClick={onProgram} />
        </>
      )}
    </Card>
  )
}

/** "Monday", for a row from an earlier day. */
function dayName(iso: string): string {
  const day = Dates.parse(iso)
  return day ? day.toLocaleDateString(undefined, { weekday: 'long' }) : iso
}

/** "A rest day. Your next exercises are on Wednesday." */
function restDayLine(feed: ExercisesResponse): string {
  const next = feed.week.find((d) => d.date > feed.date && d.assigned > 0)
  if (next) {
    const day = Dates.parse(next.date)
    const name = day ? day.toLocaleDateString(undefined, { weekday: 'long' }) : next.date
    return `A rest day. Your next exercises are on ${name}.`
  }
  return 'A rest day. New exercises from your therapist show up here.'
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
