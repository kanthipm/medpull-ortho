import { Check, CircleSlash, Film } from 'lucide-react'
import type { Assignment } from '../../api/hep'
import { assignmentSummary, painChipClass } from './scheduleCopy'

/** One exercise on one day, as the week grid and the patient page's strip
 *  draw it: the title over the dose; once done, a check and a `pain n`
 *  badge (5 and up in the warning tone); muted when skipped; a film mark
 *  when a clip exists. It is a button — it opens the AssignmentDialog — and
 *  its name says everything its marks do. */
export default function AssignmentChip({
  assignment: a,
  onOpen,
}: {
  assignment: Assignment
  onOpen: (a: Assignment) => void
}) {
  const done = a.status === 'done'
  const skipped = a.status === 'skipped'
  const pain = done ? (a.completion?.pain_after ?? null) : null
  const tone = done
    ? 'bg-risk-low-tint/60 ring-risk-low-tint hover:bg-risk-low-tint'
    : skipped
      ? 'bg-transparent ring-hairline hover:bg-soft'
      : 'bg-panel/80 ring-hairline hover:bg-panel'
  return (
    <button
      type="button"
      onClick={() => onOpen(a)}
      aria-label={assignmentSummary(a)}
      title={a.dose ? `${a.title} · ${a.dose}` : a.title}
      className={`block w-full rounded-[10px] px-2 py-1.5 text-left ring-1 ring-inset transition-[background-color,box-shadow] duration-state ease-apple focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus ${tone}`}
    >
      <span
        className={`flex items-center gap-1 text-label font-medium leading-tight ${
          skipped ? 'text-secondary' : 'text-ink'
        }`}
      >
        {done && <Check aria-hidden size={12} className="shrink-0 text-risk-low-ink" />}
        {skipped && <CircleSlash aria-hidden size={12} className="shrink-0" />}
        <span className="min-w-0 truncate">{a.title}</span>
        {a.video && <Film aria-hidden size={11} className="ml-auto shrink-0 text-secondary" />}
      </span>
      {(a.dose || pain != null) && (
        <span className="mt-0.5 flex items-center gap-1 text-micro leading-tight text-secondary">
          {a.dose && <span className="min-w-0 truncate">{a.dose}</span>}
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
