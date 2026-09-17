import { MessageCircle, MessageSquarePlus, MessageSquareText, Phone, Smartphone, Terminal } from 'lucide-react'
import { Fragment, useState } from 'react'
import { firstNameOf } from '../../../api/plan'
import { useMarkPatientMessagesRead, usePatientMessages } from '../../../api/queries'
import type { PatientMessage } from '../../../api/types'
import EmptyState from '../../../components/EmptyState'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay, SkeletonLine } from '../../../components/Skeleton'
import { useToast } from '../../../components/Toast'
import { relativeTime } from '../../../lib/format'
import ThreadAttachments from '../ThreadAttachments'
import MessageComposerModal from './MessageComposerModal'

const SHOW = 20

const CHANNEL = {
  app: { icon: Smartphone, label: 'app' },
  sms: { icon: MessageSquareText, label: 'text' },
  voice: { icon: Phone, label: 'voice' },
  console: { icon: Terminal, label: 'console' },
} as const

/** The patient <-> care team thread, newest first, read through the thread's
 *  own hooks. Messages-app bubbles: the patient's lines sit left in a grey
 *  bubble (ink on --soft, 16.202 light / 16.060 dark), the care team's and
 *  the copilot's sit right in a filled brand bubble (white on #1976D2,
 *  4.602 in both modes), each with a small "tail" corner. Days are marked
 *  by a centred .meta label, like the app's thread. */
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
        aside={unread > 0 ? `${unread} new` : undefined}
        action={
          <>
            {unread > 0 && (
              <button
                type="button"
                className="btn-plain btn-sm"
                disabled={markRead.isPending}
                onClick={() =>
                  markRead.mutate(undefined, {
                    onSuccess: () => toast('Marked as read', 'info'),
                  })
                }
              >
                Mark all read
              </button>
            )}
            <button type="button" className="btn-tinted btn-sm" onClick={() => setComposer(true)}>
              <MessageSquarePlus aria-hidden /> New message
            </button>
          </>
        }
      >
        <RefreshOverlay show={refreshing} />

        {thread.isLoading && (
          <div className="space-y-2.5">
            <SkeletonLine className="ml-auto h-9 w-2/3 !rounded-[20px]" />
            <SkeletonLine className="h-9 w-1/2 !rounded-[20px]" />
          </div>
        )}
        {thread.isError && (
          <p className="text-copy text-secondary">The thread could not be loaded.</p>
        )}
        {thread.data && messages.length === 0 && (
          <EmptyState
            variant="inline"
            icon={<MessageCircle />}
            title="No messages yet"
            className="!py-4"
          >
            Anything {first} writes in the app or texts back lands here.
          </EmptyState>
        )}

        {messages.length > 0 && (
          <>
            <ol className="space-y-3" aria-label={`Thread with ${first}, newest first`}>
              {visible.map((m, i) => {
                const day = dayLabel(m.created_at)
                const newDay = i === 0 || dayLabel(visible[i - 1].created_at) !== day
                return (
                  <Fragment key={m.id}>
                    {newDay && (
                      <li className="meta pb-0.5 pt-1 text-center font-medium" aria-hidden>
                        {day}
                      </li>
                    )}
                    <Bubble m={m} first={first} patientId={patientId} />
                  </Fragment>
                )
              })}
            </ol>
            {messages.length > SHOW && (
              <div className="mt-3 flex justify-center">
                <button
                  type="button"
                  onClick={() => setShowAll((s) => !s)}
                  className="btn-plain btn-sm"
                >
                  {showAll ? 'Show recent only' : `Show all ${messages.length} messages`}
                </button>
              </div>
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

/** "Today", "Yesterday", else "Mon, Sep 14". */
function dayLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const today = new Date()
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((startOf(today) - startOf(d)) / 86_400_000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...(d.getFullYear() !== today.getFullYear() ? { year: 'numeric' } : {}),
  })
}

function Bubble({ m, first, patientId }: { m: PatientMessage; first: string; patientId: string }) {
  const inbound = m.sender === 'patient'
  const channel = CHANNEL[m.channel] ?? CHANNEL.app
  const Icon = channel.icon
  // A clinician's message says so by name; the copilot's says nothing, which
  // is what "AI is the default" means — a badge is a claim, and only a person
  // standing behind the words is a claim worth printing.
  const clinician = !inbound && m.authored_by?.kind === 'care_team' ? m.authored_by.name : null
  const who = inbound ? first : clinician ? `${clinician}, care team` : 'Copilot'
  const unread = inbound && !m.read_by_care_team
  const failed = m.delivery_status === 'failed'
  // Delivery as a word in the meta line; only a failure is a state chip.
  const delivery =
    inbound || failed
      ? null
      : m.delivery_status === 'delivered'
        ? 'Delivered'
        : m.delivery_status === 'sent'
          ? 'Texted'
          : null

  return (
    <li className={`flex ${inbound ? 'justify-start' : 'justify-end'}`}>
      <div className={`flex max-w-[78%] flex-col ${inbound ? 'items-start' : 'items-end'}`}>
        {/* A photo can be the whole message, so an empty bubble is not drawn. */}
        {m.text.trim() !== '' && (
          <div
            className={`whitespace-pre-wrap break-words rounded-[20px] px-4 py-2.5 text-copy-lg ${
              inbound
                ? 'rounded-bl-[6px] bg-soft text-ink'
                : 'rounded-br-[6px] bg-brand text-on-brand'
            } ${failed ? 'ring-2 ring-risk-high-ink ring-offset-2 ring-offset-panel' : ''}`}
          >
            {m.text}
          </div>
        )}
        <ThreadAttachments
          patientId={patientId}
          items={m.attachments ?? []}
          align={inbound ? 'start' : 'end'}
        />
        <p
          className={`meta mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 px-2 ${
            inbound ? '' : 'justify-end'
          }`}
        >
          {unread && (
            <span className="inline-flex items-center gap-1 font-medium text-brand-ink">
              <span aria-hidden className="h-2 w-2 rounded-pill bg-brand" />
              New
            </span>
          )}
          {unread && <span aria-hidden>·</span>}
          <span className={clinician ? 'font-medium' : undefined}>{who}</span>
          <span aria-hidden>·</span>
          <span className="inline-flex items-center gap-1">
            <Icon aria-hidden size={12} />
            <span>{channel.label}</span>
          </span>
          <span aria-hidden>·</span>
          <time dateTime={m.created_at} className="tabular-nums">
            {relativeTime(m.created_at)}
          </time>
          {delivery && (
            <>
              <span aria-hidden>·</span>
              <span>{delivery}</span>
            </>
          )}
          {failed && <span className="chip bg-risk-high-tint text-risk-high-ink">Not delivered</span>}
        </p>
        {failed && m.delivery_detail && (
          // The provider's own words. "Not delivered" alone left a clinician
          // unable to tell a landline from a broken texting account.
          <p className="mt-0.5 px-2 text-label text-risk-high-ink">{m.delivery_detail}</p>
        )}
      </div>
    </li>
  )
}
