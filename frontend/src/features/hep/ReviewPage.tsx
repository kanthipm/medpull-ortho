import { Check, Film, MessageSquare, Watch } from 'lucide-react'
import { useState, type CSSProperties } from 'react'
import type { Assignment, ReviewItem } from '../../api/hep'
import { useHepOptions, useReviewQueue } from '../../api/hep'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import ListRow, { ListGroup } from '../../components/ListRow'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard } from '../../components/Skeleton'
import { relativeTime } from '../../lib/format'
import { GroupFooter, GroupHeader, SettingsHero } from '../settings/Switch'
import AssignmentDialog from './AssignmentDialog'
import ExercisesNav from './ExercisesNav'
import { durationText, kgText, mondayOf, painChipClass, sessionSeconds, shortDay, weekDays } from './scheduleCopy'

type Window = '7' | '14' | '30'
const WINDOWS: { key: Window; label: string }[] = [
  { key: '7', label: 'Last 7 days' },
  { key: '14', label: '14 days' },
  { key: '30', label: '30 days' },
]

/** `/exercise-review` — the queue: every completed exercise a lifter sent a
 *  clip with and the therapist has not answered, newest first. A row opens
 *  the same dialog the grid uses, where Compare puts her clip beside theirs
 *  and Reply posts the review. Reviewing a row takes it off the list. */
export default function ReviewPage() {
  const [span, setSpan] = useState<Window>('14')
  const queue = useReviewQueue(Number(span))
  const options = useHepOptions()
  const [open, setOpen] = useState<ReviewItem | null>(null)

  const items = [...(queue.data?.items ?? [])].sort((a, b) =>
    (b.completion?.completed_at ?? '').localeCompare(a.completion?.completed_at ?? ''),
  )
  // A refetch while the dialog is open hands it the fresh row; once the row
  // leaves the queue (reviewed) the dialog keeps the copy the server answered.
  const fresh = open ? items.find((i) => i.id === open.id) : undefined
  const opened = open ? (fresh ?? open) : null

  const onChanged = (row: Assignment) => setOpen((prev) => (prev ? { ...row, patient_name: prev.patient_name } : prev))

  return (
    <div className="pb-10">
      <SettingsHero
        nav={<ExercisesNav />}
        icon={<Film />}
        title="Review"
        decor={[<Film key="f" />, <MessageSquare key="m" />, <Check key="c" />]}
      >
        Clips your lifters sent with a finished exercise, newest first. Open one to watch it beside
        your own demonstration and reply; your note reaches them in Care.
      </SettingsHero>

      <div
        className="rise mt-8 flex flex-wrap items-center gap-x-3 gap-y-3"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        <SegmentedControl<Window>
          options={WINDOWS}
          value={span}
          onChange={setSpan}
          tone="glass"
          role="radiogroup"
          aria-label="How far back"
        />
        {queue.data && (
          <span className="meta ml-auto tabular-nums">
            {items.length === 0 ? 'Nothing waiting' : `${items.length} waiting on you`}
          </span>
        )}
      </div>

      <div
        className={`rise mt-6 transition-opacity duration-state ease-apple ${queue.isPlaceholderData ? 'opacity-60' : ''}`}
        style={{ '--rise-delay': '100ms' } as CSSProperties}
        aria-busy={queue.isPlaceholderData || undefined}
      >
        {queue.isLoading ? (
          <SkeletonCard rows={4} />
        ) : queue.isError ? (
          <EmptyState
            title="The queue couldn’t be loaded."
            icon={<Film />}
            action={
              <button type="button" className="btn-tinted" onClick={() => void queue.refetch()}>
                Try again
              </button>
            }
          >
            {queue.error instanceof Error && queue.error.message
              ? queue.error.message
              : 'Check that the API is running, then try again.'}
          </EmptyState>
        ) : items.length === 0 ? (
          <EmptyState title="Nothing to review" icon={<Check />} family="teal">
            A clip a lifter sends with a finished exercise waits here until you reply or mark it
            reviewed. Nothing from the last {span} days is waiting.
          </EmptyState>
        ) : (
          <section aria-labelledby="hep-review">
            <GroupHeader id="hep-review" onSky>
              Awaiting your review
              <span className="sr-only">, </span>
              <span className="badge-ring ml-2 align-[1px] tabular-nums">
                {items.length}
                <span className="sr-only"> {items.length === 1 ? 'clip' : 'clips'}</span>
              </span>
            </GroupHeader>
            <ListGroup inset="avatar" aria-labelledby="hep-review">
              {items.map((it) => (
                <QueueRow key={it.id} item={it} onOpen={() => setOpen(it)} />
              ))}
            </ListGroup>
            <GroupFooter>
              Replying texts your note to the lifter and marks the clip reviewed; “Mark reviewed” does
              the second without the first.
            </GroupFooter>
          </section>
        )}
      </div>

      {opened && (
        <AssignmentDialog
          key={opened.id}
          assignment={opened}
          patientName={opened.patient_name}
          days={weekDays(mondayOf(opened.scheduled_for))}
          careTeam={options.data?.care_team}
          onClose={() => setOpen(null)}
          onChanged={onChanged}
        />
      )}
    </div>
  )
}

/** One clip waiting: who and what, how it went in numbers, when. */
function QueueRow({ item: it, onOpen }: { item: ReviewItem; onOpen: () => void }) {
  const c = it.completion
  const seconds = sessionSeconds(it.session)
  const did = [
    c?.sets_done != null && c?.reps_done != null ? `${c.sets_done} × ${c.reps_done}` : '',
    c?.load_done_kg != null ? kgText(c.load_done_kg) : '',
  ]
    .filter(Boolean)
    .join(' · ')
  const facts = [
    c?.effort != null ? `effort ${c.effort}/10` : '',
    seconds != null ? durationText(seconds) : '',
    did,
    it.session?.wearable_worn ? 'wearable on' : '',
  ].filter(Boolean)
  return (
    <ListRow
      leading={<Avatar name={it.patient_name} size="sm" />}
      title={
        <>
          {it.patient_name}
          <span className="text-secondary"> · </span>
          {it.title}
        </>
      }
      linkLabel={`${it.patient_name}, ${it.title}, done ${relativeTime(c?.completed_at)}`}
      subtitle={
        <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          {c?.pain_after != null && (
            <span className={`chip ${painChipClass(c.pain_after)}`}>pain {c.pain_after}/10</span>
          )}
          {facts.length > 0 && <span>{facts.join(' · ')}</span>}
          {it.session?.wearable_worn && <Watch aria-hidden size={12} className="text-secondary" />}
          {c?.note && <span className="truncate">“{c.note}”</span>}
        </span>
      }
      meta={`Done ${relativeTime(c?.completed_at)} · scheduled ${shortDay(it.scheduled_for)}${it.dose ? ` · ${it.dose}` : ''}`}
      onClick={onOpen}
      trailing={
        <span className="chip bg-soft text-secondary">
          <Film aria-hidden size={12} /> Clip
        </span>
      }
      wrapTitle
    />
  )
}
