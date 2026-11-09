import { Film, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '../../api/client'
import type { Assignment, CareTeamMember, Exercise, Requirement, SchedulePatientSummary } from '../../api/hep'
import { useCreateAssignments, useHepOptions } from '../../api/hep'
import Modal from '../../components/Modal'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { LABEL, NumberField, RequirementControl } from './DoseFields'
import { diagnosticWarning } from './hepCopy'
import LibraryPicker from './LibraryPicker'
import { countOf, decimalOf, doseText, longDay, requirementsText, shortDay, vocabLabel } from './scheduleCopy'

/** The `+` in a cell: put one exercise on one patient's day (and, with
 *  "also on", the other days of the week). Pick from the library first,
 *  then the dose — sets, reps, hold, the load on the bar, the effort it
 *  should feel like — the side, what she asks for with it (a clip of their
 *  attempt, the wearable on), a note the patient reads, who assigns it, and
 *  the days. Save is one POST; a day that already has the exercise comes
 *  back as a 409 naming the date, shown in place. */
export default function AssignDialog({
  patient,
  date,
  days,
  assignments,
  careTeam,
  onClose,
}: {
  patient: SchedulePatientSummary
  /** The day whose `+` was pressed. */
  date: string
  /** The week on the grid, for "also on". */
  days: string[]
  /** The patient's rows in view, so a day already holding the exercise is marked. */
  assignments: Assignment[]
  careTeam: CareTeamMember[]
  onClose: () => void
}) {
  const toast = useToast()
  const options = useHepOptions()
  const create = useCreateAssignments()
  const [exercise, setExercise] = useState<Exercise | null>(null)
  const [sets, setSets] = useState('')
  const [reps, setReps] = useState('')
  const [hold, setHold] = useState('')
  const [load, setLoad] = useState('')
  const [rpe, setRpe] = useState('')
  const [side, setSide] = useState('not_applicable')
  const [video, setVideo] = useState<Requirement>('optional')
  const [wearable, setWearable] = useState<Requirement>('optional')
  const [note, setNote] = useState('')
  const [assignedBy, setAssignedBy] = useState(patient.assigned_provider_id ?? careTeam[0]?.id ?? '')
  const [alsoOn, setAlsoOn] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)

  const team = careTeam.length > 0 ? careTeam : (options.data?.care_team ?? [])
  const sides = options.data?.sides ?? []
  const exerciseOn = (day: string) =>
    assignments.filter((a) => a.scheduled_for === day).map((a) => a.exercise_id)
  const otherDays = days.filter((d) => d !== date)
  const dates = [date, ...alsoOn].sort()
  const warn = diagnosticWarning(note)
  const dose = doseText({ sets, reps, hold, load, side, sideLabel: vocabLabel(sides, side) })
  const rpeTarget = countOf(rpe)
  const asks = requirementsText(video, wearable)

  const toggleDay = (d: string) =>
    setAlsoOn((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]))

  const save = () => {
    if (!exercise) return
    setError(null)
    create.mutate(
      {
        patient_id: patient.id,
        exercise_id: exercise.id,
        dates,
        sets: countOf(sets),
        reps: countOf(reps),
        hold_seconds: countOf(hold),
        side,
        load_kg: decimalOf(load),
        rpe_target: rpeTarget,
        video_requirement: video,
        wearable_requirement: wearable,
        clinician_instructions: note.trim(),
        assigned_by: assignedBy || undefined,
      },
      {
        onSuccess: (r) => {
          const n = r.assignments.length
          toast(`${exercise.title} assigned to ${patient.name} on ${n} day${n === 1 ? '' : 's'}`, 'success')
          onClose()
        },
        onError: (e) => setError(e instanceof ApiError && e.message ? e.message : 'Could not save'),
      },
    )
  }

  const clipNote = exercise
    ? exercise.clinic_media?.playable
      ? 'Your clip'
      : exercise.media?.playable
        ? 'Library clip'
        : 'No clip yet'
    : ''

  return (
    <Modal
      title={exercise ? exercise.title : 'Add an exercise'}
      size="xl"
      onClose={onClose}
      description={`${patient.name} · ${longDay(date)}`}
      initialFocus={exercise ? '#assign-sets' : undefined}
      footer={
        <>
          <button type="button" className="btn-gray" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-filled"
            disabled={!exercise || create.isPending || !!warn}
            onClick={save}
          >
            {create.isPending
              ? 'Saving…'
              : dates.length > 1
                ? `Assign on ${dates.length} days`
                : 'Assign'}
          </button>
        </>
      }
    >
      {options.isLoading ? (
        <SkeletonCard rows={4} />
      ) : !exercise ? (
        <LibraryPicker
          options={{ regions: options.data?.regions ?? [], categories: options.data?.categories ?? [] }}
          chosen={exerciseOn(date)}
          chosenLabel="On this day"
          mode="pick"
          flat
          autoFocus
          listClassName="max-h-[min(48vh,420px)]"
          onAdd={setExercise}
        />
      ) : (
        <div className="space-y-5">
          <div className="flex items-center gap-3 rounded-control bg-soft px-4 py-3">
            <div className="min-w-0 flex-1">
              <span className="block truncate text-copy font-medium text-ink">{exercise.title}</span>
              <span className="meta flex items-center gap-1">
                {exercise.body_region_label} · {exercise.category_label} ·{' '}
                {clipNote !== 'No clip yet' && <Film aria-hidden size={11} className="inline" />}
                {clipNote}
              </span>
            </div>
            <button type="button" className="btn-plain btn-sm" onClick={() => setExercise(null)}>
              <RefreshCw size={14} aria-hidden /> Change
            </button>
          </div>

          <fieldset>
            <legend className={LABEL}>Dose</legend>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-7">
              <NumberField id="assign-sets" label="Sets" value={sets} onChange={setSets} />
              <NumberField id="assign-reps" label="Reps" value={reps} onChange={setReps} />
              <NumberField id="assign-hold" label="Hold (s)" value={hold} onChange={setHold} />
              <NumberField id="assign-load" label="Load (kg)" value={load} max={500} step={0.5} onChange={setLoad} />
              <NumberField id="assign-rpe" label="Target RPE" value={rpe} max={10} onChange={setRpe} />
              <div className="sm:col-span-2">
                <label htmlFor="assign-side" className={LABEL}>
                  Side
                </label>
                <select
                  id="assign-side"
                  className="field cursor-pointer !min-h-10 !py-1.5"
                  value={side}
                  onChange={(e) => setSide(e.target.value)}
                >
                  {sides.length === 0 && <option value="not_applicable">Not applicable</option>}
                  {sides.map((s) => (
                    <option key={s.key} value={s.key}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <p className="meta mt-2 px-1">
              {dose ? `The patient reads: ${dose}` : 'No dose yet — the patient sees the exercise without counts.'}
              {rpeTarget != null && ` · should feel like ${rpeTarget}/10`}
            </p>
          </fieldset>

          <div className="grid gap-3 sm:grid-cols-2">
            <RequirementControl label="Clip of their attempt" value={video} onChange={setVideo} />
            <RequirementControl label="Wearable on" value={wearable} onChange={setWearable} />
            {asks && <p className="meta -mt-1 px-1 sm:col-span-2">{asks}</p>}
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label htmlFor="assign-note" className={LABEL}>
                Note to the patient <span className="font-normal">optional</span>
              </label>
              <textarea
                id="assign-note"
                rows={2}
                className="field"
                value={note}
                maxLength={400}
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
              <label htmlFor="assign-by" className={LABEL}>
                Assigned by
              </label>
              <select
                id="assign-by"
                className="field cursor-pointer"
                value={assignedBy}
                onChange={(e) => setAssignedBy(e.target.value)}
              >
                {team.length === 0 && <option value="">The patient’s provider</option>}
                {assignedBy && !team.some((m) => m.id === assignedBy) && (
                  <option value={assignedBy}>{patient.assigned_provider_name ?? assignedBy}</option>
                )}
                {team.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <fieldset>
            <legend className={LABEL}>Also on</legend>
            <div className="flex flex-wrap gap-1.5">
              {otherDays.map((d) => {
                const taken = exerciseOn(d).includes(exercise.id)
                const on = alsoOn.includes(d)
                return (
                  <label
                    key={d}
                    title={taken ? `${exercise.title} is already on ${shortDay(d)}` : undefined}
                    className={`inline-flex min-h-9 cursor-pointer select-none items-center gap-2 rounded-pill px-3 text-copy ring-1 ring-inset transition-colors duration-state ease-apple ${
                      taken
                        ? 'cursor-not-allowed text-disabled-ink ring-hairline'
                        : on
                          ? 'bg-brand-tint text-brand-ink ring-brand-tint-strong'
                          : 'bg-panel/70 text-ink ring-line-strong/60 hover:bg-panel'
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-brand"
                      checked={on}
                      disabled={taken}
                      onChange={() => toggleDay(d)}
                    />
                    {shortDay(d)}
                    {taken && <span className="sr-only">, already assigned</span>}
                  </label>
                )
              })}
            </div>
          </fieldset>

          {error && (
            <p role="alert" className="rounded-control bg-risk-high-tint px-4 py-3 text-copy text-risk-high-ink">
              {error}
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}
