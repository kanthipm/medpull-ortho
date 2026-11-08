/* Today's exercises: the therapist's schedule for this day, one row per
   exercise, above the plan on Today (docs/dev/hep-schedule.md, "Patient web
   UI"). A row reads like a plan row — a glyph, the title, one line of
   facts, the state — and opens the exercise screen. */

import { Dates, DOT, isDoneAssignment, isOpenAssignment, painLabel, typeset, type ExerciseAssignment, type ExercisesResponse } from '../../core/models'
import { Card, cx, EmptyRow } from '../../ui/components'
import { Sym } from '../../ui/icons'
import { CardTitleRow, Chevron, Glyph, RowDivider } from '../../ui/rows'

/** The card. Today decides whether to show it (`hasExerciseSchedule`). */
export function ExercisesCard({ feed, onOpen }: { feed: ExercisesResponse; onOpen: (a: ExerciseAssignment) => void }) {
  const items = feed.items
  const done = items.filter(isDoneAssignment).length
  const open = items.filter(isOpenAssignment)
  const settled = items.filter((a) => !isOpenAssignment(a))
  const ordered = [...open, ...settled]
  return (
    <Card padding={0}>
      <CardTitleRow title="Today’s exercises" note={items.length === 0 ? null : `${done} of ${items.length} done`} />
      {items.length === 0 ? (
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
          <div style={{ height: 4 }} />
        </>
      )}
    </Card>
  )
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
 *  note in her words. A chevron while it is to do; the state glyph after. */
export function ExerciseRow({ a }: { a: ExerciseAssignment }) {
  const isDone = isDoneAssignment(a)
  const open = isOpenAssignment(a)
  let status: [string, string] | null = null
  if (isDone) {
    const pain = painLabel(a.completion?.painAfter)
    status = [pain ? `sent${DOT}${pain}` : 'sent', 'c-muted']
  } else if (a.status === 'skipped') status = ['skipped today', 'c-muted']
  const spoken = `${a.title}, ${a.dose}${isDone ? ', done' : open ? '' : ', skipped'}${a.video ? ', with a clip' : ''}`
  return (
    <div className="row" aria-label={spoken}>
      <Glyph name="figure.strengthtraining.traditional" family="teal" />
      <span className="row-main">
        <span className="row-title" style={isDone ? { textDecoration: 'line-through', textDecorationColor: 'rgb(var(--muted))' } : undefined}>{a.title}</span>
        <span className="t-label clamp-2">
          <span className="c-muted">{a.dose}</span>
          {status && <><span className="c-muted">{DOT}</span><span className={status[1]}>{status[0]}</span></>}
          {a.video && <><span className="c-muted">{DOT}</span><span className="clip-badge"><Sym name="film" size={11} weight="medium" />Clip</span></>}
        </span>
        {a.clinicianInstructions && (
          <span className="t-label c-body clamp-2" style={{ marginTop: 2 }}>“{typeset(a.clinicianInstructions)}”</span>
        )}
      </span>
      {open ? <Chevron /> : (
        <span className={cx(isDone ? 'c-risk-low' : 'c-muted')}>
          <Sym name={isDone ? 'checkmark.circle.fill' : 'minus.circle'} size={18} weight="regular" />
        </span>
      )}
    </div>
  )
}
