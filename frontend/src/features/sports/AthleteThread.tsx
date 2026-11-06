import { MessageCircle, Send } from 'lucide-react'
import { Fragment, useId, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useSendStaffMessage, useTeamDashboard, type ThreadMessage } from '../../api/sports'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'
import { dayLabel } from './sportsFormat'

/** The athlete <-> staff thread, oldest first with the composer under it.
 *  Messages-app bubbles like the patient page: the athlete's lines sit left
 *  on --soft, staff and copilot lines sit right on the brand fill. The
 *  composer signs the line with a staff member; the list comes from the
 *  team board's query, which the dashboard has usually cached already. */
export default function AthleteThread({
  teamId,
  athleteId,
  firstName,
  thread,
}: {
  teamId: string
  athleteId: string
  firstName: string
  thread: ThreadMessage[]
}) {
  const toast = useToast()
  const { data: board } = useTeamDashboard(teamId)
  const staff = board?.staff ?? []
  const send = useSendStaffMessage(teamId, athleteId)
  const [text, setText] = useState('')
  const [staffId, setStaffId] = useState('')
  const id = useId()
  // The chosen sender, else the first athlete-facing member of staff.
  const chosen =
    (staffId && staff.some((s) => s.id === staffId) ? staffId : '') ||
    staff.find((s) => s.athlete_facing)?.id ||
    staff[0]?.id ||
    ''

  const submit = (e?: FormEvent) => {
    e?.preventDefault()
    const t = text.trim()
    if (!t || send.isPending) return
    send.mutate(
      { text: t, staff_id: chosen || null },
      {
        onSuccess: () => {
          setText('')
          toast('Message sent', 'success')
        },
        onError: (err) => toast(`Could not send — ${err.message}`, 'warning'),
      },
    )
  }
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <SectionCard title="Messages" aside={thread.length > 0 ? `${thread.length}` : undefined}>
      {thread.length === 0 ? (
        <EmptyState variant="inline" icon={<MessageCircle />} title="No messages yet" className="!py-4">
          Anything {firstName} writes in the app, and every staff note, lands here.
        </EmptyState>
      ) : (
        <ol className="space-y-3" aria-label={`Thread with ${firstName}, oldest first`}>
          {thread.map((m, i) => {
            const day = dayLabel(m.created_at)
            const newDay = i === 0 || dayLabel(thread[i - 1].created_at) !== day
            return (
              <Fragment key={m.id}>
                {newDay && (
                  <li className="meta pb-0.5 pt-1 text-center font-medium" aria-hidden>
                    {day}
                  </li>
                )}
                <Bubble m={m} first={firstName} />
              </Fragment>
            )
          })}
        </ol>
      )}

      <form className="mt-4 border-t border-hairline pt-4" onSubmit={submit}>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor={`${id}-from`} className="text-copy text-secondary">
            From
          </label>
          <select
            id={`${id}-from`}
            className="field !min-h-9 !w-auto max-w-full !py-1 pr-8 text-copy"
            value={chosen}
            onChange={(e) => setStaffId(e.target.value)}
            disabled={staff.length === 0}
          >
            {staff.length === 0 ? (
              <option value="">Staff</option>
            ) : (
              staff.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.role_label}
                </option>
              ))
            )}
          </select>
        </div>
        <div className="mt-2 flex items-end gap-2">
          <label htmlFor={`${id}-text`} className="sr-only">
            Message
          </label>
          <textarea
            id={`${id}-text`}
            className="field min-h-[44px] flex-1 resize-none"
            rows={2}
            maxLength={2000}
            placeholder={`Message ${firstName}…`}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={onKey}
          />
          <button type="submit" className="btn-send" disabled={!text.trim() || send.isPending} aria-label="Send">
            <Send aria-hidden />
          </button>
        </div>
        <p className="meta mt-1.5">Enter sends · Shift+Enter for a new line · the athlete sees the sender’s name and role.</p>
      </form>
    </SectionCard>
  )
}

function Bubble({ m, first }: { m: ThreadMessage; first: string }) {
  const inbound = m.sender === 'patient'
  const who = inbound ? first : m.sender === 'care_team' ? 'Staff' : 'Copilot'
  return (
    <li className={`flex ${inbound ? 'justify-start' : 'justify-end'}`}>
      <div className={`flex max-w-[78%] flex-col ${inbound ? 'items-start' : 'items-end'}`}>
        <div
          className={`whitespace-pre-wrap break-words rounded-[20px] px-4 py-2.5 text-copy-lg ${
            inbound ? 'rounded-bl-[6px] bg-soft text-ink' : 'rounded-br-[6px] bg-brand text-on-brand'
          }`}
        >
          {m.text}
        </div>
        <p className={`meta mt-1 px-2 ${inbound ? '' : 'text-right'}`}>
          <span className={who === 'Staff' ? 'font-medium' : undefined}>{who}</span>
          <span aria-hidden> · </span>
          <time dateTime={m.created_at} className="tabular-nums">
            {relativeTime(m.created_at)}
          </time>
        </p>
      </div>
    </li>
  )
}
