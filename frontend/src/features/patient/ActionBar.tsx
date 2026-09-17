import { ClipboardList, MessageSquare, RefreshCw, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import type { CarePathway } from '../../api/care'
import { useEscalate } from '../../api/queries'
import { Tooltip } from '../../components/Menu'
import { useToast } from '../../components/Toast'
import MessageComposerModal from './plan/MessageComposerModal'
import TaskBuilderModal from './plan/TaskBuilderModal'

/** The patient header's action cluster: four capsules, no panel around them.
 *
 *    Message        .btn-filled   the primary action (white on #1976D2 4.602)
 *    Assign tasks   .btn-tinted   opens the care-plan builder
 *    Escalate       .btn-danger   risk ink on its tint (4.835 / 5.701) + icon + word
 *    Refresh        .btn-icon     labelled "Refresh analysis"; spins while busy
 *
 *  Assign tasks and Message open the same modals the sections below open.
 *  Escalate and Refresh behave exactly as before. */
export default function ActionBar({
  patientId,
  patientName,
  surgeon,
  pathway,
  phone,
  smsAvailable,
  onRefresh,
  refreshing,
  className = '',
}: {
  patientId: string
  patientName: string
  surgeon?: string | null
  pathway: CarePathway | null | undefined
  phone: string | null
  smsAvailable: boolean
  onRefresh: () => void
  refreshing: boolean
  className?: string
}) {
  const toast = useToast()
  const [modal, setModal] = useState<'assign' | 'message' | null>(null)
  const escalate = useEscalate(patientId)

  const fireEscalate = () => {
    escalate.mutate(undefined, {
      onSuccess: () => toast('Escalated — care team notified', 'warning'),
      onError: () => toast('Escalation failed — try again', 'warning'),
    })
  }

  return (
    <>
      <div
        role="group"
        aria-label={`Actions for ${patientName}`}
        className={`flex flex-wrap items-center gap-2 ${className}`}
      >
        <button type="button" className="btn-filled" onClick={() => setModal('message')}>
          <MessageSquare size={16} aria-hidden /> Message
        </button>
        <button type="button" className="btn-tinted" onClick={() => setModal('assign')}>
          <ClipboardList size={16} aria-hidden /> Assign tasks
        </button>
        <button
          type="button"
          className="btn-danger"
          onClick={fireEscalate}
          disabled={escalate.isPending}
        >
          <TriangleAlert size={16} aria-hidden /> Escalate
        </button>
        <Tooltip content={refreshing ? 'Refreshing…' : 'Re-run the analysis and regenerate the AI summary'}>
          <button
            type="button"
            className="btn-icon"
            onClick={onRefresh}
            disabled={refreshing}
            aria-label={refreshing ? 'Refreshing analysis' : 'Refresh analysis'}
            aria-busy={refreshing || undefined}
          >
            <RefreshCw size={18} aria-hidden className={refreshing ? 'animate-spin' : undefined} />
          </button>
        </Tooltip>
      </div>

      {modal === 'assign' && (
        <TaskBuilderModal
          patientId={patientId}
          patientName={patientName}
          pathway={pathway}
          phone={phone}
          smsAvailable={smsAvailable}
          onClose={() => setModal(null)}
        />
      )}

      {modal === 'message' && (
        <MessageComposerModal
          patientId={patientId}
          patientName={patientName}
          surgeon={surgeon}
          phone={phone}
          onClose={() => setModal(null)}
        />
      )}
    </>
  )
}
