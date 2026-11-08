import { ArrowRight, Check, Film, Trash2 } from 'lucide-react'
import { useEffect, useId, useState, type KeyboardEvent } from 'react'
import { attachmentSrc } from '../../api/attachments'
import { ApiError } from '../../api/client'
import type { Assignment, AssignmentCompletion, CareTeamMember } from '../../api/hep'
import {
  useCompleteAssignment,
  useDeleteAssignment,
  useHepOptions,
  useUpdateAssignment,
} from '../../api/hep'
import Modal from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'
import ClinicClipUpload from './ClinicClipUpload'
import ClipPlayer from './ClipPlayer'
import { diagnosticWarning } from './hepCopy'
import {
  completionSource,
  countOf,
  doseText,
  longDay,
  painChipClass,
  shortDay,
  statusChip,
  vocabLabel,
} from './scheduleCopy'

const LABEL = 'mb-1 block px-1 text-label font-medium tracking-label text-secondary'

/** A chip on the grid, opened: the clip the patient follows (or the button
 *  to film one), what came back once it is done — when, pain, the note, the
 *  patient's own clip — the steps and precautions, the dose editor, a move
 *  to another day, Remove, and "Log it done" for the room. A done row keeps
 *  its dose and its day (the server answers 409), so those controls close. */
export default function AssignmentDialog({
  assignment: a,
  patientName,
  days,
  careTeam,
  onClose,
}: {
  assignment: Assignment
  patientName: string
  /** The week on the grid, for "Move to…". */
  days: string[]
  /** The clinic's own therapists (the schedule payload's care_team); the
   *  library's whole care-team list is the fallback. */
  careTeam?: CareTeamMember[]
  onClose: () => void
}) {
  const toast = useToast()
  const options = useHepOptions()
  const update = useUpdateAssignment()
  const remove = useDeleteAssignment()
  const complete = useCompleteAssignment()
  const ids = useId()
  const done = a.status === 'done'
  const chip = statusChip(a.status)
  const sides = options.data?.sides ?? []
  const team = careTeam && careTeam.length > 0 ? careTeam : (options.data?.care_team ?? [])

  const [sets, setSets] = useState(a.sets == null ? '' : String(a.sets))
  const [reps, setReps] = useState(a.reps == null ? '' : String(a.reps))
  const [hold, setHold] = useState(a.hold_seconds == null ? '' : String(a.hold_seconds))
  const [side, setSide] = useState(a.side)
  const [note, setNote] = useState(a.clinician_instructions)
  const [assignedBy, setAssignedBy] = useState(a.assigned_by)
  const [moveTo, setMoveTo] = useState('')
  const [confirming, setConfirming] = useState(false)
  const [logging, setLogging] = useState(false)
  const [pain, setPain] = useState<number | null>(null)
  const [logNote, setLogNote] = useState('')

  const dirty =
    countOf(sets) !== a.sets ||
    countOf(reps) !== a.reps ||
    countOf(hold) !== a.hold_seconds ||
    side !== a.side ||
    note.trim() !== a.clinician_instructions ||
    assignedBy !== a.assigned_by
  const warn = diagnosticWarning(note)
  const dose = doseText(sets, reps, hold, side, vocabLabel(sides, side))

  const fail = (fallback: string) => (e: unknown) =>
    toast(e instanceof ApiError && e.message ? e.message : fallback, 'warning')

  const saveDose = () =>
    update.mutate(
      {
        id: a.id,
        sets: countOf(sets),
        reps: countOf(reps),
        hold_seconds: countOf(hold),
        side,
        clinician_instructions: note.trim(),
        assigned_by: assignedBy,
      },
      { onSuccess: () => toast('Dose updated', 'success'), onError: fail('Could not save the dose') },
    )

  const move = () => {
    if (!moveTo) return
    update.mutate(
      { id: a.id, scheduled_for: moveTo },
      {
        onSuccess: () => {
          toast(`${a.title} moved to ${shortDay(moveTo)}`, 'success')
          setMoveTo('')
        },
        onError: fail('Could not move it'),
      },
    )
  }

  const removeIt = () =>
    remove.mutate(a.id, {
      onSuccess: () => {
        toast(`${a.title} removed from ${shortDay(a.scheduled_for)}`, 'info')
        onClose()
      },
      onError: fail('Could not remove it'),
    })

  const logDone = () =>
    complete.mutate(
      { id: a.id, pain_after: pain, note: logNote.trim(), actor: assignedBy || a.assigned_by },
      {
        onSuccess: () => {
          toast(`${a.title} logged as done`, 'success')
          setLogging(false)
        },
        onError: fail('Could not log it'),
      },
    )

  const clipCaption = a.video
    ? a.video.source === 'clinic'
      ? `Your demonstration${a.video.uploaded_by_name ? ` · ${a.video.uploaded_by_name}` : ''}`
      : 'Library demonstration — your own replaces it on their phone'
    : 'No demonstration for this exercise yet'

  const footer = (
    <>
      {!done &&
        (confirming ? (
          <span className="mr-auto flex flex-wrap items-center gap-2 text-copy text-body">
            Remove from {shortDay(a.scheduled_for)}?
            <button type="button" className="btn-danger btn-sm" disabled={remove.isPending} onClick={removeIt}>
              {remove.isPending ? 'Removing…' : 'Remove'}
            </button>
            <button type="button" className="btn-plain-muted btn-sm" onClick={() => setConfirming(false)}>
              Keep
            </button>
          </span>
        ) : (
          <button type="button" className="btn-plain-muted mr-auto" onClick={() => setConfirming(true)}>
            <Trash2 size={16} aria-hidden /> Remove
          </button>
        ))}
      {!done && !logging && (
        <button type="button" className="btn-tinted" onClick={() => setLogging(true)}>
          <Check size={16} aria-hidden /> Log it done
        </button>
      )}
      <button type="button" className="btn-filled" onClick={onClose}>
        Close
      </button>
    </>
  )

  return (
    <Modal
      title={a.title}
      size="xl"
      onClose={onClose}
      footer={footer}
      eyebrow={
        <p className="mb-1 flex flex-wrap items-center gap-2 text-label text-secondary">
          <span>{patientName}</span>
          <span aria-hidden>·</span>
          <span>{longDay(a.scheduled_for)}</span>
          <span className={`chip ${chip.pill}`}>{chip.label}</span>
        </p>
      }
      description={a.dose || undefined}
    >
      <div className="space-y-5">
        <section aria-labelledby={`${ids}-clip`}>
          <h3 id={`${ids}-clip`} className="sr-only">
            Demonstration
          </h3>
          {a.video?.url ? (
            <ClipPlayer
              src={a.video.url}
              poster={a.video.poster_url}
              label={`${a.title} demonstration`}
              className="max-h-[420px]"
            />
          ) : (
            <div
              role="img"
              aria-label="No demonstration yet. The steps below describe the movement."
              className="flex max-h-[220px] min-h-[160px] w-full flex-col items-center justify-center gap-2 rounded-control bg-soft px-4 text-center text-secondary"
            >
              <Film aria-hidden size={28} />
              <span className="text-copy font-medium">No demonstration yet</span>
              <span className="text-label">
                Film yours and it plays on their phone wherever this exercise is assigned
              </span>
            </div>
          )}
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <span className="meta">{clipCaption}</span>
            <ClinicClipUpload
              exerciseId={a.exercise_id}
              exerciseTitle={a.title}
              actor={a.assigned_by}
              own={a.video?.source === 'clinic' ? { id: a.video.id } : null}
            />
          </div>
        </section>

        {done && a.completion && <Completion patientId={a.patient_id} c={a.completion} title={a.title} patientName={patientName} id={`${ids}-done`} />}
        {a.status === 'skipped' && (
          <p className="rounded-control bg-soft px-4 py-3 text-copy text-ink">
            <span className="font-medium">Skipped.</span>
            {a.skip_reason ? ` “${a.skip_reason}”` : ' No reason given.'}
          </p>
        )}

        <section aria-labelledby={`${ids}-steps`}>
          <h3 id={`${ids}-steps`} className="mb-2 text-copy font-medium text-body">
            Steps
          </h3>
          {a.steps.length > 0 ? (
            <ol className="list-decimal space-y-1.5 pl-5 text-copy-lg text-ink">
              {a.steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          ) : (
            <p className="text-copy text-secondary">No steps written yet.</p>
          )}
        </section>
        <dl className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-surface bg-soft p-4">
            <dt className="text-label font-medium tracking-label text-secondary">Equipment</dt>
            <dd className="mt-1 text-copy text-ink">{a.equipment || 'None'}</dd>
          </div>
          <div className="rounded-surface bg-soft p-4">
            <dt className="text-label font-medium tracking-label text-secondary">Precautions</dt>
            <dd className="mt-1 text-copy text-ink">{a.precautions || 'None noted'}</dd>
          </div>
        </dl>

        <section aria-labelledby={`${ids}-dose`}>
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h3 id={`${ids}-dose`} className="text-copy font-medium text-body">
              Dose and note
            </h3>
            {done && <span className="meta">A done row keeps its dose.</span>}
          </div>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
            <NumberField id={`${ids}-sets`} label="Sets" value={sets} disabled={done} onChange={setSets} />
            <NumberField id={`${ids}-reps`} label="Reps" value={reps} disabled={done} onChange={setReps} />
            <NumberField id={`${ids}-hold`} label="Hold (s)" value={hold} disabled={done} onChange={setHold} />
            <div className="col-span-3 sm:col-span-1">
              <label htmlFor={`${ids}-side`} className={LABEL}>
                Side
              </label>
              <select
                id={`${ids}-side`}
                className="field cursor-pointer !min-h-10 !py-1.5"
                value={side}
                disabled={done}
                onChange={(e) => setSide(e.target.value)}
              >
                {!sides.some((s) => s.key === side) && <option value={side}>{a.side_label || side}</option>}
                {sides.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <p className="meta mt-2 px-1">{dose ? `The patient reads: ${dose}` : 'No counts set.'}</p>
          <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_200px]">
            <div>
              <label htmlFor={`${ids}-note`} className={LABEL}>
                Note to the patient <span className="font-normal">optional</span>
              </label>
              <textarea
                id={`${ids}-note`}
                rows={2}
                className="field"
                value={note}
                maxLength={400}
                disabled={done}
                placeholder="e.g. Slow on the way down."
                onChange={(e) => setNote(e.target.value)}
              />
              {warn && (
                <p role="alert" className="mt-1 px-1 text-label text-risk-med-ink">
                  {warn}
                </p>
              )}
            </div>
            <div>
              <label htmlFor={`${ids}-by`} className={LABEL}>
                Assigned by
              </label>
              <select
                id={`${ids}-by`}
                className="field cursor-pointer"
                value={assignedBy}
                disabled={done}
                onChange={(e) => setAssignedBy(e.target.value)}
              >
                {!team.some((m) => m.id === assignedBy) && (
                  <option value={assignedBy}>{a.assigned_by_name ?? assignedBy}</option>
                )}
                {team.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          {!done && (
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                className="btn-gray btn-sm"
                disabled={!dirty || update.isPending || !!warn}
                onClick={saveDose}
              >
                {update.isPending ? 'Saving…' : 'Save changes'}
              </button>
            </div>
          )}
        </section>

        {!done && (
          <section aria-labelledby={`${ids}-move`}>
            <h3 id={`${ids}-move`} className="mb-2 text-copy font-medium text-body">
              Move to another day
            </h3>
            <div className="flex items-center gap-2">
              <label className="min-w-0 flex-1">
                <span className="sr-only">Day</span>
                <select
                  className="field cursor-pointer"
                  value={moveTo}
                  onChange={(e) => setMoveTo(e.target.value)}
                >
                  <option value="">Choose a day…</option>
                  {days
                    .filter((d) => d !== a.scheduled_for)
                    .map((d) => (
                      <option key={d} value={d}>
                        {longDay(d)}
                      </option>
                    ))}
                </select>
              </label>
              <button type="button" className="btn-gray" disabled={!moveTo || update.isPending} onClick={move}>
                Move <ArrowRight size={16} aria-hidden />
              </button>
            </div>
          </section>
        )}

        {!done && logging && (
          <section aria-labelledby={`${ids}-log`} className="rounded-surface bg-soft p-4">
            <h3 id={`${ids}-log`} className="text-copy font-medium text-ink">
              Log it done
            </h3>
            <p className="meta mt-0.5">For the room: they did it here and told you how it felt.</p>
            <div className="mt-3">
              <span id={`${ids}-pain`} className={LABEL}>
                Pain after, 0–10
              </span>
              <PainScale labelledBy={`${ids}-pain`} value={pain} onChange={setPain} />
              <p className="meta mt-1 px-1">0 is no pain, 10 the worst imaginable. Leave it if they didn’t say.</p>
            </div>
            <div className="mt-3">
              <label htmlFor={`${ids}-lognote`} className={LABEL}>
                Note <span className="font-normal">optional</span>
              </label>
              <textarea
                id={`${ids}-lognote`}
                rows={2}
                className="field"
                value={logNote}
                maxLength={400}
                onChange={(e) => setLogNote(e.target.value)}
              />
            </div>
            <div className="mt-3 flex justify-end gap-2">
              <button type="button" className="btn-plain-muted btn-sm" onClick={() => setLogging(false)}>
                Cancel
              </button>
              <button type="button" className="btn-filled btn-sm" disabled={complete.isPending} onClick={logDone}>
                <Check size={14} aria-hidden /> {complete.isPending ? 'Logging…' : 'Log it done'}
              </button>
            </div>
          </section>
        )}
      </div>
    </Modal>
  )
}

/** What came back: when, from where, the pain, the note, the patient's clip. */
function Completion({
  c,
  title,
  patientName,
  patientId,
  id,
}: {
  c: AssignmentCompletion
  title: string
  patientName: string
  patientId: string
  id: string
}) {
  return (
    <section aria-labelledby={id} className="rounded-surface bg-risk-low-tint/50 p-4">
      <h3 id={id} className="flex flex-wrap items-center gap-2 text-copy font-medium text-ink">
        <Check aria-hidden size={16} className="text-risk-low-ink" />
        Done {relativeTime(c.completed_at)}
        {completionSource(c.source) && <span className="meta">{completionSource(c.source)}</span>}
        {c.pain_after != null ? (
          <span className={`chip ${painChipClass(c.pain_after)}`}>pain {c.pain_after}/10</span>
        ) : (
          <span className="chip bg-soft text-secondary">no pain score</span>
        )}
      </h3>
      {c.note && <p className="mt-2 text-copy text-ink">“{c.note}”</p>}
      <div className="mt-3">
        {c.video ? (
          <ReturnedClip patientId={patientId} video={c.video} label={`${patientName}’s clip of ${title}`} />
        ) : (
          <p className="meta">No clip was sent with it.</p>
        )}
      </div>
    </section>
  )
}

/** The patient's clip. On AWS the payload carries a presigned link; on a
 *  laptop it carries none and the bytes come through the console's own
 *  attachment route, fetched with the console's credential the way the
 *  thread does it (api/attachments.ts). */
function ReturnedClip({
  patientId,
  video,
  label,
}: {
  patientId: string
  video: NonNullable<AssignmentCompletion['video']>
  label: string
}) {
  const [src, setSrc] = useState<string | null>(video.url ?? null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (video.url) return
    let revoke: string | null = null
    let cancelled = false
    attachmentSrc(patientId, video.id)
      .then(({ src: s, objectUrl }) => {
        if (cancelled) {
          if (objectUrl) URL.revokeObjectURL(s)
          return
        }
        if (objectUrl) revoke = s
        setSrc(s)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
      if (revoke) URL.revokeObjectURL(revoke)
    }
  }, [patientId, video.id, video.url])
  if (failed) return <p className="meta">The clip could not be loaded.</p>
  if (!src) return <p className="meta">Loading the clip…</p>
  return <ClipPlayer src={src} label={label} className="max-h-[360px]" />
}

function NumberField({
  id,
  label,
  value,
  disabled,
  onChange,
}: {
  id: string
  label: string
  value: string
  disabled: boolean
  onChange: (v: string) => void
}) {
  return (
    <div>
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode="numeric"
        min={0}
        max={999}
        className="field !min-h-10 !py-1.5 tabular-nums"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

/** 0–10 as a row of radios: one tab stop, arrows move, the number is the
 *  state (and the pressed capsule its echo). */
function PainScale({
  labelledBy,
  value,
  onChange,
}: {
  labelledBy: string
  value: number | null
  onChange: (n: number) => void
}) {
  const onKey = (e: KeyboardEvent<HTMLButtonElement>, n: number) => {
    let next: number | null = null
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') next = Math.min(10, n + 1)
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') next = Math.max(0, n - 1)
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = 10
    if (next == null) return
    e.preventDefault()
    onChange(next)
    e.currentTarget.parentElement?.querySelector<HTMLButtonElement>(`[data-pain="${next}"]`)?.focus()
  }
  return (
    <div role="radiogroup" aria-labelledby={labelledBy} className="flex flex-wrap gap-1">
      {Array.from({ length: 11 }, (_, n) => {
        const on = value === n
        return (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={on}
            data-pain={n}
            tabIndex={on || (value == null && n === 0) ? 0 : -1}
            onClick={() => onChange(n)}
            onKeyDown={(e) => onKey(e, n)}
            className={`h-9 min-w-9 rounded-pill px-2 text-copy tabular-nums ring-1 ring-inset transition-colors duration-state ease-apple focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
              on ? 'bg-action text-on-action ring-action' : 'bg-panel/70 text-ink ring-line-strong/60 hover:bg-panel'
            }`}
          >
            {n}
          </button>
        )
      })}
    </div>
  )
}
