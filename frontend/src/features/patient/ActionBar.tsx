import {
  CalendarClock,
  ClipboardList,
  MessageSquare,
  NotebookPen,
  Phone,
  RefreshCw,
  Sparkles,
  TriangleAlert,
} from 'lucide-react'
import { useState } from 'react'
import {
  useAssignTask,
  useDraftMessage,
  useEscalate,
  useLogCall,
  useMessagePatient,
  useScheduleFollowup,
  useUpdatePlan,
} from '../../api/queries'
import Modal from '../../components/Modal'
import { useToast } from '../../components/Toast'

export default function ActionBar({
  patientId,
  patientName,
  onRefresh,
  refreshing,
}: {
  patientId: string
  patientName: string
  onRefresh: () => void
  refreshing: boolean
}) {
  const toast = useToast()
  const [modal, setModal] = useState<'assign' | 'message' | 'call' | 'followup' | 'plan' | null>(
    null,
  )
  const [taskTitle, setTaskTitle] = useState('')
  const [taskWhy, setTaskWhy] = useState('')
  const [messageText, setMessageText] = useState('')
  const [callMinutes, setCallMinutes] = useState('5')
  const [callNote, setCallNote] = useState('')
  const [followupWhen, setFollowupWhen] = useState('')
  const [followupNote, setFollowupNote] = useState('')
  const [planSummary, setPlanSummary] = useState('')

  const assign = useAssignTask(patientId)
  const message = useMessagePatient(patientId)
  const escalate = useEscalate(patientId)
  const draft = useDraftMessage(patientId)
  const logCall = useLogCall(patientId)
  const followup = useScheduleFollowup(patientId)
  const updatePlan = useUpdatePlan(patientId)

  const firstName = patientName.split(' ')[0]

  const submitTask = () => {
    if (!taskTitle.trim()) return
    assign.mutate(
      { title: taskTitle.trim(), why: taskWhy.trim() },
      {
        onSuccess: () => {
          // The task is written to the patient's plan and the minute is
          // logged, but nothing reads it back yet — no patient-facing surface
          // and no completion tracking — so the toast does not promise one.
          toast(`Task saved to ${firstName}'s plan — nothing is sent to the patient yet`, 'info')
          setModal(null)
          setTaskTitle('')
          setTaskWhy('')
        },
        onError: () => toast('Task could not be saved — try again', 'warning'),
      },
    )
  }

  const submitMessage = () => {
    if (!messageText.trim()) return
    message.mutate(messageText.trim(), {
      onSuccess: () => {
        toast(`Message queued for ${firstName} — sends when SMS goes live`, 'info')
        setModal(null)
        setMessageText('')
      },
      onError: () => toast('Message could not be queued — try again', 'warning'),
    })
  }

  const fireEscalate = () => {
    escalate.mutate(undefined, {
      onSuccess: () => toast('Escalated — care team notified', 'warning'),
      onError: () => toast('Escalation failed — try again', 'warning'),
    })
  }

  const submitCall = () => {
    const minutes = Math.max(1, Number(callMinutes) || 5)
    logCall.mutate(
      { minutes, note: callNote.trim() },
      {
        onSuccess: () => {
          toast(`Call logged — ${minutes} min counted toward treatment management`)
          setModal(null)
          setCallMinutes('5')
          setCallNote('')
        },
        onError: () => toast('Call could not be logged — try again', 'warning'),
      },
    )
  }

  const submitFollowup = () => {
    if (!followupWhen.trim()) return
    followup.mutate(
      { when: followupWhen.trim(), note: followupNote.trim() },
      {
        onSuccess: () => {
          toast(`Follow-up scheduled for ${firstName}`)
          setModal(null)
          setFollowupWhen('')
          setFollowupNote('')
        },
        onError: () => toast('Follow-up could not be scheduled — try again', 'warning'),
      },
    )
  }

  const submitPlan = () => {
    if (!planSummary.trim()) return
    updatePlan.mutate(planSummary.trim(), {
      onSuccess: () => {
        toast('Treatment plan update logged')
        setModal(null)
        setPlanSummary('')
      },
      onError: () => toast('Plan update failed — try again', 'warning'),
    })
  }

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 rounded-card border border-line bg-panel p-2.5">
        <button type="button" className="qa-btn flex-1" onClick={() => setModal('assign')}>
          <ClipboardList size={14} className="text-brand" /> Assign tasks
        </button>
        <button type="button" className="qa-btn flex-1" onClick={() => setModal('message')}>
          <MessageSquare size={14} className="text-brand" /> Message
        </button>
        <button type="button" className="qa-btn flex-1" onClick={() => setModal('call')}>
          <Phone size={14} className="text-brand" /> Call patient
        </button>
        <button type="button" className="qa-btn flex-1" onClick={() => setModal('followup')}>
          <CalendarClock size={14} className="text-brand" /> Follow-up
        </button>
        <button type="button" className="qa-btn flex-1" onClick={() => setModal('plan')}>
          <NotebookPen size={14} className="text-brand" /> Update plan
        </button>
        <button
          type="button"
          className="qa-btn flex-1 text-risk-high"
          onClick={fireEscalate}
          disabled={escalate.isPending}
        >
          <TriangleAlert size={14} /> Escalate
        </button>
        <button
          type="button"
          className="qa-btn flex-1"
          onClick={onRefresh}
          disabled={refreshing}
          title="Re-run the analysis and regenerate the AI summary"
        >
          <RefreshCw size={14} className={`text-brand ${refreshing ? 'animate-spin' : ''}`} />
          {refreshing ? 'Refreshing…' : 'Refresh analysis'}
        </button>
      </div>

      {modal === 'assign' && (
        <Modal title={`Assign a task to ${firstName}`} onClose={() => setModal(null)}>
          <div className="space-y-3">
            <div>
              <label htmlFor="task-title" className="micro mb-1 block">
                Task
              </label>
              <input
                id="task-title"
                className="field"
                placeholder="e.g. Walk 10 minutes, twice daily"
                value={taskTitle}
                onChange={(e) => setTaskTitle(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="task-why" className="micro mb-1 block">
                Why it matters{' '}
                <span className="normal-case tracking-normal">(recorded with the task)</span>
              </label>
              <input
                id="task-why"
                className="field"
                placeholder="e.g. Restores knee motion and circulation"
                value={taskWhy}
                onChange={(e) => setTaskWhy(e.target.value)}
              />
            </div>
            <p className="text-[11px] font-medium text-faint">
              Saved to the patient's plan and counted as care-coordination time.
              Delivery and completion tracking arrive with the patient check-in
              assistant.
            </p>
            <button
              type="button"
              onClick={submitTask}
              disabled={!taskTitle.trim() || assign.isPending}
              className="btn-primary"
            >
              {assign.isPending ? 'Saving…' : 'Save task'}
            </button>
          </div>
        </Modal>
      )}

      {modal === 'message' && (
        <Modal title={`Message ${firstName}`} onClose={() => setModal(null)}>
          <div className="space-y-3">
            <div>
              <div className="mb-1 flex items-center justify-between">
                <label htmlFor="message-text" className="micro block">
                  Message
                </label>
                <button
                  type="button"
                  disabled={draft.isPending}
                  onClick={() =>
                    draft.mutate(undefined, {
                      onSuccess: (result) => setMessageText(result.message),
                      onError: () => toast('Drafting failed — try again', 'warning'),
                    })
                  }
                  className="inline-flex cursor-pointer items-center gap-1 rounded-btn px-2 py-1 text-[11px] font-medium text-brand transition-colors duration-150 hover:bg-brand-tint disabled:opacity-50"
                >
                  <Sparkles size={11} className={draft.isPending ? 'animate-spin' : ''} />
                  {draft.isPending ? 'Drafting…' : 'Draft with AI'}
                </button>
              </div>
              <textarea
                id="message-text"
                rows={4}
                className={`field ${draft.isPending ? 'shimmer text-transparent' : ''}`}
                placeholder="e.g. Hi Marcus — please take your temperature this morning and tell the check-in assistant the reading."
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                disabled={draft.isPending}
              />
              <p className="mt-1.5 text-[11px] font-medium text-faint">
                AI drafts are editable — nothing sends without your review. Delivery is queued
                until the SMS integration is connected.
              </p>
            </div>
            <button
              type="button"
              onClick={submitMessage}
              disabled={!messageText.trim() || message.isPending}
              className="btn-primary"
            >
              {message.isPending ? 'Queueing…' : 'Queue message'}
            </button>
          </div>
        </Modal>
      )}

      {modal === 'call' && (
        <Modal title={`Log a call with ${firstName}`} onClose={() => setModal(null)}>
          <div className="space-y-3">
            <div>
              <label htmlFor="call-minutes" className="micro mb-1 block">
                Call length (minutes)
              </label>
              <input
                id="call-minutes"
                type="number"
                min={1}
                max={60}
                className="field font-mono"
                value={callMinutes}
                onChange={(e) => setCallMinutes(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="call-note" className="micro mb-1 block">
                Note <span className="normal-case tracking-normal">(optional)</span>
              </label>
              <input
                id="call-note"
                className="field"
                placeholder="e.g. Pain reviewed, PT plan reinforced"
                value={callNote}
                onChange={(e) => setCallNote(e.target.value)}
              />
            </div>
            <p className="text-[11px] font-medium text-faint">
              Logged as live interactive communication — counts toward the treatment-management
              requirement (CPT 98980).
            </p>
            <button
              type="button"
              onClick={submitCall}
              disabled={logCall.isPending}
              className="btn-primary"
            >
              {logCall.isPending ? 'Logging…' : 'Log call'}
            </button>
          </div>
        </Modal>
      )}

      {modal === 'followup' && (
        <Modal title={`Schedule a follow-up for ${firstName}`} onClose={() => setModal(null)}>
          <div className="space-y-3">
            <div>
              <label htmlFor="followup-when" className="micro mb-1 block">
                When
              </label>
              <input
                id="followup-when"
                className="field"
                placeholder="e.g. Thursday 2:30 PM"
                value={followupWhen}
                onChange={(e) => setFollowupWhen(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="followup-note" className="micro mb-1 block">
                Note <span className="normal-case tracking-normal">(optional)</span>
              </label>
              <input
                id="followup-note"
                className="field"
                placeholder="e.g. Recheck swelling and ROM"
                value={followupNote}
                onChange={(e) => setFollowupNote(e.target.value)}
              />
            </div>
            <button
              type="button"
              onClick={submitFollowup}
              disabled={!followupWhen.trim() || followup.isPending}
              className="btn-primary"
            >
              {followup.isPending ? 'Scheduling…' : 'Schedule follow-up'}
            </button>
          </div>
        </Modal>
      )}

      {modal === 'plan' && (
        <Modal title={`Update ${firstName}'s treatment plan`} onClose={() => setModal(null)}>
          <div className="space-y-3">
            <div>
              <label htmlFor="plan-summary" className="micro mb-1 block">
                What changed
              </label>
              <textarea
                id="plan-summary"
                rows={4}
                className="field"
                placeholder="e.g. Advance to stage-2 exercises; ice protocol after each session"
                value={planSummary}
                onChange={(e) => setPlanSummary(e.target.value)}
              />
            </div>
            <p className="text-[11px] font-medium text-faint">
              Logged to the RTM record and counted as treatment-management time.
            </p>
            <button
              type="button"
              onClick={submitPlan}
              disabled={!planSummary.trim() || updatePlan.isPending}
              className="btn-primary"
            >
              {updatePlan.isPending ? 'Saving…' : 'Log plan update'}
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
