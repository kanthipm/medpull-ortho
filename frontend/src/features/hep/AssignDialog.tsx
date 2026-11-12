import { Film, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '../../api/client'
import type {
  Assignment,
  CareTeamMember,
  Exercise,
  LoadUnit,
  Requirement,
  ScheduleCreateBody,
  SchedulePatientSummary,
} from '../../api/hep'
import { useCreateAssignments, useHepOptions } from '../../api/hep'
import Modal from '../../components/Modal'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { LABEL, NumberField, RequirementControl, WeekdayPicker } from './DoseFields'
import { diagnosticWarning } from './hepCopy'
import LibraryPicker from './LibraryPicker'
import {
  addDays,
  countOf,
  doseText,
  longDay,
  monthDay,
  parseIso,
  requirementsText,
  shortDay,
  vocabLabel,
  weekdaysLabel,
} from './scheduleCopy'
import { loadBounds, loadKg } from './units'

type When = 'days' | 'repeat'

/** The most weeks a repeat can run (`schedule.MAX_REPEAT_WEEKS`). */
const MAX_WEEKS = 12

/** The `+` in a cell: put one exercise on one patient's day. Pick from the
 *  library first, then the dose — sets, reps, hold, the load in hand in the
 *  clinic's own unit, the effort it should feel like — the side, what she
 *  asks for with it (a clip of their attempt, the wearable on), a note the
 *  patient reads, who assigns it, and when: this day and others of the
 *  week, or a repeat on chosen weekdays for a number of weeks. Save is one
 *  POST. With days, one that already has the exercise comes back as a 409
 *  naming the date, shown in place; a repeat lands around what is already
 *  there and says what it left out. "Text them" also sends a text with a
 *  link that opens the app on the first of the days. */
export default function AssignDialog({
  patient,
  date,
  days,
  assignments,
  careTeam,
  unit = 'kg',
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
  /** The unit the clinic reads loads in; the row is sent in kilograms. */
  unit?: LoadUnit
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
  const [when, setWhen] = useState<When>('days')
  // Monday 0 … Sunday 6, starting with the weekday that was pressed.
  const pressed = (parseIso(date).getDay() + 6) % 7
  const [weekdays, setWeekdays] = useState<number[] | null>([pressed])
  const [weeks, setWeeks] = useState('4')
  const [textThem, setTextThem] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const team = careTeam.length > 0 ? careTeam : (options.data?.care_team ?? [])
  const sides = options.data?.sides ?? []
  const exerciseOn = (day: string) =>
    assignments.filter((a) => a.scheduled_for === day).map((a) => a.exercise_id)
  const otherDays = days.filter((d) => d !== date)
  const dates = [date, ...alsoOn].sort()
  const warn = diagnosticWarning(note)
  const dose = doseText({ sets, reps, hold, load, side, sideLabel: vocabLabel(sides, side), unit })
  const rpeTarget = countOf(rpe)
  const asks = requirementsText(video, wearable)
  const bounds = loadBounds(unit)
  const first = patient.name.split(' ')[0]

  // The days a repeat would land on, counted here only for the sentence
  // under the control; the server works the real ones out.
  const nWeeks = Math.min(MAX_WEEKS, Math.max(1, countOf(weeks) ?? 1))
  const onDays = weekdays ?? [0, 1, 2, 3, 4, 5, 6]
  const repeatDays = Array.from({ length: nWeeks * 7 }, (_, i) => addDays(date, i)).filter((d) =>
    onDays.includes((parseIso(d).getDay() + 6) % 7),
  )
  const repeating = when === 'repeat'

  const toggleDay = (d: string) =>
    setAlsoOn((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]))

  const save = () => {
    if (!exercise) return
    setError(null)
    const body: ScheduleCreateBody = {
      patient_id: patient.id,
      exercise_id: exercise.id,
      ...(repeating
        ? { repeat: { weekdays: onDays, weeks: nWeeks, start: date } }
        : { dates }),
      sets: countOf(sets),
      reps: countOf(reps),
      hold_seconds: countOf(hold),
      side,
      load_kg: loadKg(load, unit),
      rpe_target: rpeTarget,
      video_requirement: video,
      wearable_requirement: wearable,
      clinician_instructions: note.trim(),
      assigned_by: assignedBy || undefined,
      text_patient: textThem,
    }
    create.mutate(body, {
      onSuccess: (r) => {
        const n = r.assignments.length
        const parts = [`${exercise.title} assigned to ${patient.name} on ${n} day${n === 1 ? '' : 's'}`]
        const left = r.skipped ?? 0
        if (left > 0) parts.push(`${left} day${left === 1 ? '' : 's'} left out (already on, or out of reach)`)
        if (textThem) {
          parts.push(
            r.text?.sent
              ? `${first} was texted a link`
              : `no text went${r.text?.detail ? `: ${r.text.detail}` : ' (nothing new from today on, or this chart cannot be texted)'}`,
          )
        }
        toast(parts.join(' · '), n > 0 ? 'success' : 'info')
        onClose()
      },
      onError: (e) => setError(e instanceof ApiError && e.message ? e.message : 'Could not save'),
    })
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
              : repeating
                ? `Assign for ${nWeeks} week${nWeeks === 1 ? '' : 's'}`
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
              <NumberField
                id="assign-load"
                label={`Load (${unit})`}
                value={load}
                max={bounds.max}
                step={bounds.step}
                onChange={setLoad}
              />
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

          <div>
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <span id="assign-when" className={`${LABEL} !mb-0`}>
                When
              </span>
              <SegmentedControl<When>
                options={[
                  { key: 'days', label: 'These days' },
                  { key: 'repeat', label: 'Repeat' },
                ]}
                value={when}
                onChange={setWhen}
                size="sm"
                role="radiogroup"
                aria-labelledby="assign-when"
              />
            </div>
            {repeating ? (
              <div className="space-y-3 rounded-control bg-soft p-4">
                <WeekdayPicker label="On" value={weekdays} onChange={setWeekdays} />
                <div className="flex flex-wrap items-end gap-3">
                  <div className="w-28">
                    <NumberField id="assign-weeks" label="For (weeks)" value={weeks} min={1} max={MAX_WEEKS} onChange={setWeeks} />
                  </div>
                  <p className="meta min-w-0 flex-1 pb-2">
                    {weekdaysLabel(weekdays)} for {nWeeks} week{nWeeks === 1 ? '' : 's'} from {monthDay(date)}:{' '}
                    {repeatDays.length} day{repeatDays.length === 1 ? '' : 's'}, the last on{' '}
                    {repeatDays.length > 0 ? monthDay(repeatDays[repeatDays.length - 1]) : monthDay(date)}. A day that
                    already has this exercise is left out. The days stay one repeat: re-dose or clear
                    “this and the following” from any of them.
                  </p>
                </div>
              </div>
            ) : (
              <fieldset>
                <legend className="sr-only">Also on</legend>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="meta mr-1">{shortDay(date)}, and also on</span>
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
            )}
          </div>

          <label className="flex cursor-pointer items-start gap-3 rounded-control bg-soft px-4 py-3">
            <input
              type="checkbox"
              className="mt-0.5 h-4 w-4 accent-brand"
              checked={textThem}
              onChange={(e) => setTextThem(e.target.checked)}
            />
            <span className="min-w-0">
              <span className="block text-copy font-medium text-ink">Text {first} about it</span>
              <span className="meta block">
                One text naming what was added, with a link that opens the app on the first of these
                days. Nothing is texted for days already behind today.
              </span>
            </span>
          </label>

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
