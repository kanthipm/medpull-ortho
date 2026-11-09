import { ArrowRight, CopyPlus } from 'lucide-react'
import { useState } from 'react'
import { ApiError } from '../../api/client'
import type { CareTeamMember, SchedulePatientSummary } from '../../api/hep'
import { useCopyWeek } from '../../api/hep'
import Modal from '../../components/Modal'
import { useToast } from '../../components/Toast'
import { LABEL } from './DoseFields'
import { addDays, rangeLabel, weekDays } from './scheduleCopy'

/** "Copy last week →" from a row's menu: every exercise of the seven days
 *  before the board's week goes onto the same weekday of the board's week,
 *  dose, note and requirements included; a day that already holds the
 *  exercise is skipped by the server. One POST; the count comes back. */
export default function CopyWeekDialog({
  patient,
  toStart,
  careTeam,
  onClose,
}: {
  patient: SchedulePatientSummary
  /** The board's current first day; the source is the seven days before it. */
  toStart: string
  careTeam: CareTeamMember[]
  onClose: () => void
}) {
  const toast = useToast()
  const copy = useCopyWeek()
  const fromStart = addDays(toStart, -7)
  const [assignedBy, setAssignedBy] = useState(patient.assigned_provider_id ?? careTeam[0]?.id ?? '')
  const [error, setError] = useState<string | null>(null)
  const from = rangeLabel(weekDays(fromStart))
  const to = rangeLabel(weekDays(toStart))

  const run = () => {
    setError(null)
    copy.mutate(
      { patient_id: patient.id, from_start: fromStart, to_start: toStart, assigned_by: assignedBy || undefined },
      {
        onSuccess: (r) => {
          const n = r.assignments.length
          toast(
            n === 0
              ? `Nothing to copy — ${to} already had every exercise of ${from}`
              : `${n} exercise${n === 1 ? '' : 's'} copied onto ${to} for ${patient.name}`,
            n === 0 ? 'info' : 'success',
          )
          onClose()
        },
        onError: (e) => setError(e instanceof ApiError && e.message ? e.message : 'Could not copy the week'),
      },
    )
  }

  return (
    <Modal
      title="Copy last week onto this one?"
      size="md"
      onClose={onClose}
      description={patient.name}
      footer={
        <>
          <button type="button" className="btn-gray" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn-filled" disabled={copy.isPending} onClick={run}>
            <CopyPlus size={16} aria-hidden /> {copy.isPending ? 'Copying…' : 'Copy the week'}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        <p className="flex flex-wrap items-center gap-2 rounded-control bg-soft px-4 py-3 text-copy text-ink">
          <span className="font-medium tabular-nums">{from}</span>
          <ArrowRight aria-hidden size={16} className="text-secondary" />
          <span className="sr-only">onto</span>
          <span className="font-medium tabular-nums">{to}</span>
        </p>
        <p className="text-copy text-body">
          Every exercise of {from} goes onto the same weekday of {to}, with its dose, note and
          requirements. A day that already has the exercise is left as it is.
        </p>
        <div>
          <label htmlFor="copy-by" className={LABEL}>
            Assigned by
          </label>
          <select
            id="copy-by"
            className="field cursor-pointer"
            value={assignedBy}
            onChange={(e) => setAssignedBy(e.target.value)}
          >
            {careTeam.length === 0 && <option value="">The patient’s provider</option>}
            {assignedBy && !careTeam.some((m) => m.id === assignedBy) && (
              <option value={assignedBy}>{patient.assigned_provider_name ?? assignedBy}</option>
            )}
            {careTeam.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
        {error && (
          <p role="alert" className="rounded-control bg-risk-high-tint px-4 py-3 text-copy text-risk-high-ink">
            {error}
          </p>
        )}
      </div>
    </Modal>
  )
}
