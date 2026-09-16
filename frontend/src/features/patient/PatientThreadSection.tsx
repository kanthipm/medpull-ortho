import { CheckCircle2, Circle, MinusCircle, Paperclip, Send, Smartphone } from 'lucide-react'
import { useState } from 'react'
import {
  useMarkPatientMessagesRead,
  useMessagePatient,
  usePatientMessages,
  usePatientTasks,
} from '../../api/queries'
import SectionCard from '../../components/SectionCard'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'
import type { PatientMessage, PatientTask } from '../../api/types'
import ThreadAttachments, { PendingAttachments } from './ThreadAttachments'
import { useAttachmentPicker } from './useAttachmentPicker'

/**
 * Tasks and the message thread, as the patient app sees them. Standalone so
 * the patient page can mount it wherever it fits:
 *   <PatientThreadSection patientId={p.id} patientName={p.name} />
 */
export default function PatientThreadSection({
  patientId,
  patientName,
}: {
  patientId: string
  patientName: string
}) {
  const tasks = usePatientTasks(patientId)
  const messages = usePatientMessages(patientId)
  const send = useMessagePatient(patientId)
  const markRead = useMarkPatientMessagesRead(patientId)
  const toast = useToast()
  const files = useAttachmentPicker(patientId)
  const [draft, setDraft] = useState('')
  const firstName = patientName.split(' ')[0]

  const open = (tasks.data?.tasks ?? []).filter((t) => t.status === 'pending' || t.status === 'sent')
  const closed = (tasks.data?.tasks ?? []).filter((t) => t.status !== 'pending' && t.status !== 'sent')
  const unread = (messages.data?.messages ?? []).filter(
    (m) => m.sender === 'patient' && !m.read_by_care_team,
  ).length

  const submit = () => {
    const text = draft.trim()
    // A photo with no words is a message. Only both being empty is not.
    if (!text && files.ids.length === 0) return
    send.mutate({ text, attachment_ids: files.ids }, {
      onSuccess: (r) => {
        setDraft('')
        files.reset()
        toast(
          r.status === 'sent_sms'
            ? `Texted ${firstName} — also in the app`
            : r.status === 'stored_sms_failed'
              ? `Saved to ${firstName}'s app thread — text failed: ${r.detail || 'no reason given'}`
              : `Saved to ${firstName}'s app thread — no phone on file to text`,
          r.status === 'sent_sms' ? 'info' : 'warning',
        )
      },
      onError: () => toast('Message could not be sent — try again', 'warning'),
    })
  }

  return (
    <div className="space-y-3.5">
      <SectionCard
        title="Tasks"
        aside={
          <span className="text-[11.5px] font-medium text-faint">
            {open.length} open · {closed.length} done
          </span>
        }
      >
        {tasks.isLoading ? (
          <p className="text-[13px] text-muted">Loading…</p>
        ) : open.length + closed.length === 0 ? (
          <p className="text-[13px] font-medium text-muted">
            Nothing assigned yet. Assign a task above and {firstName} gets a text with a link to do it
            in the app, on the web, or by replying.
          </p>
        ) : (
          <ul className="divide-y divide-line">
            {[...open, ...closed.slice(0, 8)].map((t) => (
              <TaskLine key={t.id} task={t} />
            ))}
          </ul>
        )}
      </SectionCard>

      <SectionCard
        title="Messages"
        aside={
          unread > 0 ? (
            <button
              type="button"
              onClick={() => markRead.mutate()}
              className="chip cursor-pointer bg-brand-tint text-brand"
            >
              {unread} new · mark read
            </button>
          ) : undefined
        }
      >
        <div className="max-h-80 space-y-2 overflow-y-auto pr-1">
          {(messages.data?.messages ?? []).length === 0 && (
            <p className="text-[13px] font-medium text-muted">
              No messages yet. Anything {firstName} writes in the app or texts back lands here.
            </p>
          )}
          {(messages.data?.messages ?? []).map((m) => (
            <MessageLine key={m.id} message={m} patientId={patientId} />
          ))}
        </div>
        <div className="mt-3" onDrop={files.drop} onDragOver={(e) => e.preventDefault()}>
          <div className="flex gap-2">
            <input
              className="field"
              placeholder={`Message ${firstName}`}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') submit()
              }}
            />
            <input {...files.inputProps} />
            <button
              type="button"
              className="qa-btn shrink-0"
              title="Attach a photo or file"
              disabled={files.busy}
              onClick={files.open}
            >
              <Paperclip size={14} className="text-brand" /> Attach
            </button>
            <button
              type="button"
              className="qa-btn shrink-0"
              disabled={(!draft.trim() && files.ids.length === 0) || send.isPending || files.busy}
              onClick={submit}
            >
              <Send size={14} className="text-brand" /> Send
            </button>
          </div>
          <PendingAttachments items={files.pending} onRemove={files.remove} busy={files.busy} />
        </div>
      </SectionCard>
    </div>
  )
}

function TaskLine({ task }: { task: PatientTask }) {
  const Icon = task.status === 'done' ? CheckCircle2 : task.status === 'skipped' ? MinusCircle : Circle
  const tone =
    task.status === 'done' ? 'text-risk-low' : task.status === 'skipped' ? 'text-faint' : 'text-brand'
  return (
    <li className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
      <Icon size={16} className={`mt-0.5 shrink-0 ${tone}`} />
      <div className="min-w-0 flex-1">
        <p className="text-[13.5px] font-semibold text-ink">{task.title}</p>
        <p className="text-[12px] font-medium text-muted">
          {task.kind_label}
          {task.status === 'sent' && task.sent_at && <> · texted {relativeTime(task.sent_at)}</>}
          {task.status === 'pending' && <> · in the app only</>}
          {task.status === 'done' && task.completed_at && (
            <>
              {' '}
              · done {relativeTime(task.completed_at)} by {task.completed_via}
            </>
          )}
          {task.status === 'skipped' && <> · skipped</>}
        </p>
        {task.answers && Object.keys(task.answers).length > 0 && (
          <p className="mt-0.5 text-[12px] text-body">
            {Object.entries(task.answers)
              .map(([k, v]) => `${k}: ${String(v)}`)
              .join(' · ')}
          </p>
        )}
      </div>
    </li>
  )
}

function MessageLine({ message, patientId }: { message: PatientMessage; patientId: string }) {
  const mine = message.sender !== 'patient'
  const who =
    message.sender === 'patient'
      ? message.channel === 'sms'
        ? 'Patient · text'
        : message.channel === 'voice'
          ? 'Patient · voice'
          : 'Patient'
      : message.sender === 'copilot'
        ? 'MedPull'
        : 'Care team'
  return (
    <div className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-row px-3 py-2 text-[13px] ${
          message.sender === 'patient'
            ? 'border border-line bg-panel text-ink'
            : message.sender === 'copilot'
              ? 'bg-soft text-body'
              : 'bg-brand-tint text-ink'
        }`}
      >
        {message.text.trim() !== '' && (
          <p className="whitespace-pre-wrap">{message.text}</p>
        )}
        <ThreadAttachments patientId={patientId} items={message.attachments ?? []} />
        <p className="mt-1 flex items-center gap-1 text-[10.5px] font-medium text-faint">
          {message.channel === 'sms' && <Smartphone size={10} />}
          {who} · {relativeTime(message.created_at)}
          {message.delivery_status === 'failed' && (
            <span className="text-risk-med"> · {message.delivery_detail || 'text not delivered'}</span>
          )}
        </p>
      </div>
    </div>
  )
}
