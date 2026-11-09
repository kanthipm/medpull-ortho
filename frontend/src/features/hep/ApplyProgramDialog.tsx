import { ClipboardList, Film } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client'
import type { CareTeamMember, Template } from '../../api/hep'
import { todayIso, useApplyTemplate, useHepOptions, useTemplates } from '../../api/hep'
import EmptyState from '../../components/EmptyState'
import Modal from '../../components/Modal'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { LABEL, NumberField } from './DoseFields'
import { programItemDose } from './programCopy'
import {
  ASSIGN_FUTURE_DAYS,
  ASSIGN_PAST_DAYS,
  addDays,
  countOf,
  longDay,
  requirementsText,
  weekdaysLabel,
} from './scheduleCopy'

/** "Apply a program…": a template onto one patient's calendar from a start
 *  date, for a number of weeks (the program's own unless changed). Opened
 *  from a schedule row with the patient fixed and the program to choose, or
 *  from the Programs page with the program fixed and the patient to choose.
 *  One POST; every item lands on its weekdays, duplicates skipped. */
export default function ApplyProgramDialog({
  template,
  patient,
  defaultStart,
  careTeam,
  onClose,
}: {
  /** Fixed when opened from the Programs page. */
  template?: Template | null
  /** Fixed when opened from a schedule row. */
  patient?: { id: string; name: string; assigned_provider_id?: string | null } | null
  /** The board's first day, else today. */
  defaultStart?: string
  careTeam?: CareTeamMember[]
  onClose: () => void
}) {
  const toast = useToast()
  const options = useHepOptions()
  const templates = useTemplates({ enabled: !template })
  const apply = useApplyTemplate()
  const today = todayIso()
  const team = careTeam && careTeam.length > 0 ? careTeam : (options.data?.care_team ?? [])
  const patients = options.data?.patients ?? []

  const [templateId, setTemplateId] = useState<string>(template ? String(template.id) : '')
  const [patientId, setPatientId] = useState<string>(patient?.id ?? '')
  const [start, setStart] = useState(() => {
    const s = defaultStart ?? today
    return s < today ? today : s
  })
  const [weeks, setWeeks] = useState<string>(template ? String(template.weeks) : '')
  const [assignedBy, setAssignedBy] = useState(patient?.assigned_provider_id ?? team[0]?.id ?? '')
  const [error, setError] = useState<string | null>(null)

  const list = template ? [template] : (templates.data?.templates ?? [])
  const chosen = list.find((t) => String(t.id) === templateId) ?? null
  const chosenPatient = patient ?? patients.find((p) => p.id === patientId) ?? null
  const weeksN = countOf(weeks) ?? chosen?.weeks ?? null
  const minStart = addDays(today, -ASSIGN_PAST_DAYS)
  const maxStart = addDays(today, ASSIGN_FUTURE_DAYS)
  const startOk = /^\d{4}-\d{2}-\d{2}$/.test(start) && start >= minStart && start <= maxStart
  const ready = !!chosen && !!chosenPatient && startOk && (weeksN == null || (weeksN >= 1 && weeksN <= 26))

  const pickTemplate = (id: string) => {
    setTemplateId(id)
    const t = list.find((x) => String(x.id) === id)
    if (t) setWeeks(String(t.weeks))
  }

  const run = () => {
    if (!chosen || !chosenPatient) return
    setError(null)
    apply.mutate(
      {
        id: chosen.id,
        patient_id: chosenPatient.id,
        start,
        weeks: weeksN ?? undefined,
        assigned_by: assignedBy || undefined,
      },
      {
        onSuccess: (r) => {
          const n = r.assignments.length
          toast(
            n === 0
              ? `${chosenPatient.name} already had every exercise of ${chosen.name} on those days`
              : `${chosen.name}: ${n} exercise${n === 1 ? '' : 's'} put on ${chosenPatient.name}’s calendar`,
            n === 0 ? 'info' : 'success',
          )
          onClose()
        },
        onError: (e) => setError(e instanceof ApiError && e.message ? e.message : 'Could not apply the program'),
      },
    )
  }

  const loading = options.isLoading || (!template && templates.isLoading)
  const noTemplates = !template && !templates.isLoading && !templates.isError && list.length === 0
  const endsOn = weeksN && weeksN > 0 ? addDays(start, weeksN * 7 - 1) : null

  return (
    <Modal
      title={template ? `Apply ${template.name}` : 'Apply a program'}
      size="xl"
      onClose={onClose}
      description={patient ? patient.name : 'Its exercises land on the chosen weekdays from the start date.'}
      initialFocus={template ? '#apply-patient' : '#apply-template'}
      footer={
        <>
          <button type="button" className="btn-gray" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn-filled" disabled={!ready || apply.isPending} onClick={run}>
            <ClipboardList size={16} aria-hidden /> {apply.isPending ? 'Applying…' : 'Apply'}
          </button>
        </>
      }
    >
      {loading ? (
        <SkeletonCard rows={3} />
      ) : noTemplates ? (
        <EmptyState
          variant="inline"
          title="No programs yet"
          icon={<ClipboardList />}
          family="teal"
          action={
            <Link to="/exercise-programs/new" className="btn-tinted" onClick={onClose}>
              Build a program
            </Link>
          }
        >
          A program is a pattern of exercises by weekday. Build one once and put it on any lifter’s
          calendar from here.
        </EmptyState>
      ) : (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2">
            {!template && (
              <div className="sm:col-span-2">
                <label htmlFor="apply-template" className={LABEL}>
                  Program
                </label>
                <select
                  id="apply-template"
                  className="field cursor-pointer"
                  value={templateId}
                  onChange={(e) => pickTemplate(e.target.value)}
                >
                  <option value="">Choose a program…</option>
                  {list.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} · {t.weeks} week{t.weeks === 1 ? '' : 's'} · {t.items.length} exercise
                      {t.items.length === 1 ? '' : 's'}
                    </option>
                  ))}
                </select>
                {templates.isError && (
                  <p role="alert" className="mt-1 px-1 text-label text-risk-high-ink">
                    The programs couldn’t be loaded.
                  </p>
                )}
              </div>
            )}
            {!patient && (
              <div className="sm:col-span-2">
                <label htmlFor="apply-patient" className={LABEL}>
                  Patient
                </label>
                <select
                  id="apply-patient"
                  className="field cursor-pointer"
                  value={patientId}
                  onChange={(e) => setPatientId(e.target.value)}
                >
                  <option value="">Choose a patient…</option>
                  {patients.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <div>
              <label htmlFor="apply-start" className={LABEL}>
                Start
              </label>
              <input
                id="apply-start"
                type="date"
                className="field tabular-nums"
                value={start}
                min={minStart}
                max={maxStart}
                onChange={(e) => setStart(e.target.value)}
              />
              {!startOk && (
                <p role="alert" className="mt-1 px-1 text-label text-risk-med-ink">
                  A start within {ASSIGN_PAST_DAYS} days back or {ASSIGN_FUTURE_DAYS} days ahead.
                </p>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <NumberField
                id="apply-weeks"
                label="Weeks"
                value={weeks}
                min={1}
                max={26}
                placeholder={chosen ? String(chosen.weeks) : ''}
                onChange={setWeeks}
              />
              <div>
                <label htmlFor="apply-by" className={LABEL}>
                  Assigned by
                </label>
                <select
                  id="apply-by"
                  className="field cursor-pointer !min-h-10 !py-1.5"
                  value={assignedBy}
                  onChange={(e) => setAssignedBy(e.target.value)}
                >
                  {team.length === 0 && <option value="">The patient’s provider</option>}
                  {assignedBy && !team.some((m) => m.id === assignedBy) && (
                    <option value={assignedBy}>{assignedBy}</option>
                  )}
                  {team.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {chosen && (
            <section aria-label="What goes on the calendar" className="rounded-surface bg-soft p-4">
              <p className="text-copy text-ink">
                <span className="font-medium">{chosen.name}</span>
                {chosen.description && <span className="text-body"> — {chosen.description}</span>}
              </p>
              <p className="meta mt-1">
                From {longDay(start)}
                {endsOn && ` to ${longDay(endsOn)}`}
                {weeksN != null && ` · ${weeksN} week${weeksN === 1 ? '' : 's'}`}
                {chosenPatient && ` · for ${chosenPatient.name}`}. Days that already have an exercise keep it.
              </p>
              <ul className="mt-3 divide-y divide-hairline" aria-label="Exercises in the program">
                {chosen.items.map((it, i) => {
                  const asks = requirementsText(it.video_requirement, it.wearable_requirement)
                  return (
                    <li key={`${it.exercise_id}-${i}`} className="flex items-baseline gap-3 py-2 text-copy">
                      <div className="min-w-0 flex-1">
                        <span className="block font-medium text-ink">{it.title}</span>
                        <span className="meta block">
                          {weekdaysLabel(it.weekdays)}
                          {programItemDose(it) && ` · ${programItemDose(it)}`}
                          {it.rpe_target != null && ` · RPE ${it.rpe_target}`}
                          {asks && ` · ${asks}`}
                        </span>
                      </div>
                      {it.video_requirement === 'required' && (
                        <Film aria-hidden size={12} className="shrink-0 text-secondary" />
                      )}
                    </li>
                  )
                })}
                {chosen.items.length === 0 && <li className="py-2 text-copy text-secondary">This program has no exercises yet.</li>}
              </ul>
            </section>
          )}

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
