import { MessageSquarePlus, Smartphone, MessageSquareText, Phone, Terminal } from 'lucide-react'
import { useState } from 'react'
import { firstNameOf } from '../../../api/plan'
import { useMarkPatientMessagesRead, usePatientMessages } from '../../../api/queries'
import type { PatientMessage } from '../../../api/types'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay, SkeletonLine } from '../../../components/Skeleton'
import { useToast } from '../../../components/Toast'
import { relativeTime } from '../../../lib/format'
import MessageComposerModal from './MessageComposerModal'

const SHOW = 20

const CHANNEL_ICON = {
  app: Smartphone,
  sms: MessageSquareText,
  voice: Phone,
  console: Terminal,
} as const

/** The patient <-> care team thread, newest first, read through the thread's
 *  own hooks. Patient lines sit left on the panel surface; the care team's
 *  and the copilot's sit right in brand, like a check-in transcript. */
export default function MessagesSection({
  patientId,
  patientName,
  surgeon,
  phone,
  refreshing,
}: {
  patientId: string
  patientName: string
  surgeon?: string | null
  phone: string | null
  refreshing: boolean
}) {
  const toast = useToast()
  const first = firstNameOf(patientName)
  const thread = usePatientMessages(patientId)
  const markRead = useMarkPatientMessagesRead(patientId)
  const [composer, setComposer] = useState(false)
  const [showAll, setShowAll] = useState(false)

  const messages = [...(thread.data?.messages ?? [])].sort(
    (a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id,
  )
  const unread = messages.filter((m) => m.sender === 'patient' && !m.read_by_care_team).length
  const visible = showAll ? messages : messages.slice(0, SHOW)

  return (
    <>
      <SectionCard
        title="Messages"
        aside={
          <span className="flex items-center gap-1.5">
            {unread > 0 && (
              <button
                type="button"
                className="chip cursor-pointer bg-brand-tint text-brand transition-opacity hover:opacity-80 disabled:opacity-50"
                disabled={markRead.isPending}
                onClick={() =>
                  markRead.mutate(undefined, {
                    onSuccess: () => toast('Marked as read', 'info'),
                  })
                }
              >
                {unread} new · Mark all read
              </button>
            )}
            <button type="button" className="qa-btn" onClick={() => setComposer(true)}>
              <MessageSquarePlus size={13} className="text-brand" /> New message
            </button>
          </span>
        }
      >
        <RefreshOverlay show={refreshing} />

        {thread.isLoading && (
          <div className="space-y-2.5">
            <SkeletonLine className="ml-auto h-8 w-2/3 rounded-none" />
            <SkeletonLine className="h-8 w-1/2 rounded-none" />
          </div>
        )}
        {thread.isError && (
          <p className="text-[12.5px] font-medium text-muted">The thread could not be loaded.</p>
        )}
        {thread.data && messages.length === 0 && (
          <p className="text-[12.5px] font-medium text-muted">
            No messages yet. Anything {first} writes in the app or texts back lands here.
          </p>
        )}

        {messages.length > 0 && (
          <>
            <ul className="space-y-2.5">
              {visible.map((m) => (
                <Bubble key={m.id} m={m} first={first} />
              ))}
            </ul>
            {messages.length > SHOW && (
              <button
                type="button"
                onClick={() => setShowAll((s) => !s)}
                className="mt-2 cursor-pointer rounded-btn px-1 py-1 text-[12px] font-medium text-brand transition-colors duration-150 hover:bg-brand-tint"
              >
                {showAll ? 'Show recent only' : `Show all ${messages.length} messages`}
              </button>
            )}
          </>
        )}
      </SectionCard>

      {composer && (
        <MessageComposerModal
          patientId={patientId}
          patientName={patientName}
          surgeon={surgeon}
          phone={phone}
          onClose={() => setComposer(false)}
        />
      )}
    </>
  )
}

function Bubble({ m, first }: { m: PatientMessage; first: string }) {
  const inbound = m.sender === 'patient'
  const Icon = CHANNEL_ICON[m.channel] ?? Smartphone
  // A clinician's message says so by name; the copilot's says nothing, which
  // is what "AI is the default" means — a badge is a claim, and only a person
  // standing behind the words is a claim worth printing.
  const clinician = !inbound && m.authored_by?.kind === 'care_team' ? m.authored_by.name : null
  const who = inbound ? first : clinician ? clinician : 'Copilot'
  const status = inbound
    ? { label: 'received', pill: 'bg-soft text-muted' }
    : m.delivery_status === 'delivered'
      ? { label: 'delivered', pill: 'bg-risk-low-bg text-risk-low' }
      : m.delivery_status === 'sent'
        ? { label: 'texted', pill: 'bg-risk-low-bg text-risk-low' }
        : m.delivery_status === 'failed'
        ? { label: 'failed', pill: 'bg-risk-high-bg text-risk-high' }
        : { label: 'in app', pill: 'bg-soft text-muted' }
  return (
    <li className={`flex ${inbound ? 'justify-start' : 'justify-end'}`}>
      <div className={`max-w-[85%] ${inbound ? 'items-start' : 'items-end'} flex flex-col`}>
        <div
          className={`rounded-none px-3.5 py-2 text-[13px] font-medium leading-[1.45] ${
            inbound
              ? 'border border-line bg-panel text-ink'
              : 'bg-brand text-white'
          }`}
        >
          {m.text}
        </div>
        <span className="mt-1 flex flex-wrap items-center gap-1.5 px-1 text-[10.5px] font-medium uppercase tracking-[.05em] text-faint">
          {inbound && !m.read_by_care_team && (
            <span aria-label="Unread" className="h-1.5 w-1.5 rounded-full bg-brand" />
          )}
          <span>{who}</span>
          {clinician && (
            <span className="chip bg-brand-tint normal-case tracking-normal text-brand">
              Care team approved
            </span>
          )}
          <span className="inline-flex items-center gap-1">
            <Icon size={10} /> {m.channel}
          </span>
          <span className="font-mono normal-case tracking-normal">{relativeTime(m.created_at)}</span>
          <span className={`chip normal-case tracking-normal ${status.pill}`}>{status.label}</span>
        </span>
        {m.delivery_status === 'failed' && m.delivery_detail && (
          // The provider's own words. "Not delivered" alone left a clinician
          // unable to tell a landline from a broken texting account.
          <span className="mt-0.5 px-1 text-[11px] font-medium text-risk-high">
            {m.delivery_detail}
          </span>
        )}
      </div>
    </li>
  )
}
