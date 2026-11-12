import { Check, CircleSlash, Film, Repeat2, TrendingUp } from 'lucide-react'
import type { DragEvent } from 'react'
import type { Assignment } from '../../api/hep'
import { ReviewDot } from './AdherenceChip'
import { DRAG_TYPE, assignmentSummary, awaitingReview, painChipClass, stateOf } from './scheduleCopy'

/** One exercise on one day, as the week grid and the patient page's strip
 *  draw it: the title over the dose, and where it stands.
 *
 *    done         a check and a `pain n` badge (5 and up in the warning
 *                 tone); a rising mark when the session went over the dose
 *    skipped      muted, with the slashed circle
 *    missed       a dashed outline and the word, once the day has passed
 *    in progress  the word, while the session is open on their phone
 *    open         the plain chip (today's column is already tinted)
 *
 *  A film mark when a clip exists; a repeat mark when the day belongs to a
 *  repeat; a small amber dot when a done day waits for the therapist. It is
 *  a button — it opens the AssignmentDialog — and its name says everything
 *  its marks do. With `draggable` it can be dragged onto another day of the
 *  same row: the dialog's "Move" and "Copy to" do the same from the
 *  keyboard. */
export default function AssignmentChip({
  assignment: a,
  onOpen,
  draggable = false,
}: {
  assignment: Assignment
  onOpen: (a: Assignment) => void
  draggable?: boolean
}) {
  const state = stateOf(a)
  const done = state === 'done'
  const skipped = state === 'skipped'
  const missed = state === 'missed'
  const live = state === 'in_progress'
  const pain = done ? (a.completion?.pain_after ?? null) : null
  const over = done && a.completion?.over === true
  const review = awaitingReview(a)
  const tone = done
    ? 'bg-risk-low-tint/60 ring-1 ring-inset ring-risk-low-tint hover:bg-risk-low-tint'
    : skipped
      ? 'bg-transparent ring-1 ring-inset ring-hairline hover:bg-soft'
      : missed
        ? 'bg-transparent outline-dashed outline-1 -outline-offset-1 outline-line-strong hover:bg-soft'
        : live
          ? 'bg-brand-tint/70 ring-1 ring-inset ring-brand-tint-strong hover:bg-brand-tint'
          : 'bg-panel/80 ring-1 ring-inset ring-hairline hover:bg-panel'
  const word = missed ? 'missed' : live ? 'in progress' : null

  const onDragStart = (e: DragEvent<HTMLButtonElement>) => {
    e.dataTransfer.setData(
      DRAG_TYPE,
      JSON.stringify({ id: a.id, patientId: a.patient_id, date: a.scheduled_for, done: a.status !== 'assigned' }),
    )
    e.dataTransfer.setData('text/plain', a.title)
    // A done or skipped day stays where it is: it can only be copied.
    e.dataTransfer.effectAllowed = a.status === 'assigned' ? 'copyMove' : 'copy'
  }

  return (
    <button
      type="button"
      onClick={() => onOpen(a)}
      draggable={draggable || undefined}
      onDragStart={draggable ? onDragStart : undefined}
      aria-label={assignmentSummary(a)}
      title={`${a.title}${a.dose ? ` · ${a.dose}` : ''}${word ? ` · ${word}` : ''}${over ? ' · more than prescribed' : ''}${review ? ' · awaiting review' : ''}`}
      className={`block w-full rounded-[10px] px-2 py-1.5 text-left transition-[background-color,box-shadow] duration-state ease-apple focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus ${tone}`}
    >
      <span
        className={`flex items-center gap-1 text-label font-medium leading-tight ${
          skipped || missed ? 'text-secondary' : 'text-ink'
        }`}
      >
        {done && <Check aria-hidden size={12} className="shrink-0 text-risk-low-ink" />}
        {skipped && <CircleSlash aria-hidden size={12} className="shrink-0" />}
        <span className="min-w-0 truncate">{a.title}</span>
        <span className="ml-auto flex shrink-0 items-center gap-1">
          {review && <ReviewDot />}
          {over && <TrendingUp aria-hidden size={11} className="text-risk-med-ink" />}
          {a.series_id && <Repeat2 aria-hidden size={11} className="text-secondary" />}
          {a.video && <Film aria-hidden size={11} className="text-secondary" />}
        </span>
      </span>
      {(a.dose || pain != null || word) && (
        <span className="mt-0.5 flex items-center gap-1 text-micro leading-tight text-secondary">
          {a.dose && <span className="min-w-0 truncate">{a.dose}</span>}
          {word && (
            <span
              className={`ml-auto shrink-0 rounded-pill px-1.5 py-px font-medium ${
                missed ? 'bg-risk-med-tint text-risk-med-ink' : 'bg-panel text-brand-ink'
              }`}
            >
              {word}
            </span>
          )}
          {pain != null && (
            <span
              className={`ml-auto shrink-0 rounded-pill px-1.5 py-px font-medium tabular-nums ${painChipClass(pain)}`}
            >
              pain {pain}
            </span>
          )}
        </span>
      )}
    </button>
  )
}
