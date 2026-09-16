import { ClipboardList, MessageSquare, RefreshCw, TriangleAlert } from 'lucide-react'
import { useState } from 'react'
import type { CarePathway } from '../../api/care'
import { useEscalate } from '../../api/queries'
import { useToast } from '../../components/Toast'
import MessageComposerModal from './plan/MessageComposerModal'
import TaskBuilderModal from './plan/TaskBuilderModal'

/** The patient page's quick actions. Assign tasks opens the care-plan
 *  builder, Message the composer; both live in `plan/` and are the same
 *  modals the sections below open. Escalate and Refresh are unchanged. */
export default function ActionBar({
  patientId,
  patientName,
  surgeon,
  pathway,
  phone,
  smsAvailable,
  onRefresh,
  refreshing,
}: {
  patientId: string
  patientName: string
  surgeon?: string | null
  pathway: CarePathway | null | undefined
  phone: string | null
  smsAvailable: boolean
  onRefresh: () => void
  refreshing: boolean
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
      <div className="panel flex flex-wrap items-center gap-2.5 p-3">
        <button type="button" className="qa-btn flex-1" onClick={() => setModal('assign')}>
          <ClipboardList size={16} /> Assign tasks
        </button>
        <button type="button" className="qa-btn flex-1" onClick={() => setModal('message')}>
          <MessageSquare size={16} /> Message
        </button>
        <button
          type="button"
          className="qa-btn flex-1 text-risk-high-ink"
          onClick={fireEscalate}
          disabled={escalate.isPending}
        >
          <TriangleAlert size={16} /> Escalate
        </button>
        <button
          type="button"
          className="qa-btn flex-1"
          onClick={onRefresh}
          disabled={refreshing}
          title="Re-run the analysis and regenerate the AI summary"
        >
          <RefreshCw size={16} className={refreshing ? 'animate-spin' : undefined} />
          {refreshing ? 'Refreshing…' : 'Refresh analysis'}
        </button>
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
