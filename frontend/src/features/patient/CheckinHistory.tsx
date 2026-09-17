import { ChevronRight, MessageCircle, MessageSquareText } from 'lucide-react'
import { useId, useState } from 'react'
import { usePatientCheckins } from '../../api/queries'
import type { Checkin } from '../../api/types'
import EmptyState from '../../components/EmptyState'
import { ListGroup } from '../../components/ListRow'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { relativeTime } from '../../lib/format'

/** The digest tone is the ONE chip on a check-in row: it is state, in words,
 *  on its own tint (4.835 / 5.701 high, 5.369-on-panel low pair measured in
 *  lib/risk.ts). Topics and channel are plain secondary text. */
const TONE: Record<string, { label: string; cls: string }> = {
  worse: { label: 'Reported worse', cls: 'bg-risk-high-tint text-risk-high-ink' },
  better: { label: 'Reported better', cls: 'bg-risk-low-tint text-risk-low-ink' },
  steady: { label: 'About the same', cls: 'bg-risk-missing-tint text-risk-missing-ink' },
}

/** Message bubbles, shaped like the app's: 18px corners with a tucked tail
 *  corner. Patient = brand fill with white text (4.602); care team = soft
 *  fill with ink (16.202 / 16.060). */
function Transcript({ checkin }: { checkin: Checkin }) {
  return (
    <ol className="space-y-1.5" aria-label="Transcript">
      {checkin.messages.map((m, i) => {
        const patient = m.who === 'patient'
        return (
          <li key={i} className={`flex ${patient ? 'justify-end' : 'justify-start'}`}>
            <span className="sr-only">{patient ? 'Patient: ' : 'Care team: '}</span>
            <p
              className={`max-w-[85%] rounded-[18px] px-3.5 py-2 text-copy ${
                patient ? 'rounded-br-md bg-brand text-on-brand' : 'rounded-bl-md bg-soft text-ink'
              }`}
            >
              {m.text}
            </p>
          </li>
        )
      })}
    </ol>
  )
}

function CheckinRow({ checkin }: { checkin: Checkin }) {
  const [open, setOpen] = useState(false)
  const panelId = useId()
  const tone = checkin.digest.tone ? TONE[checkin.digest.tone] : null
  const channel = checkin.channel === 'sms' ? 'by text' : 'in the app'
  const detail = [...checkin.digest.topics, channel].join(' · ')

  return (
    <li>
      {/* The time is the row's one button; its ::after covers the row, so the
          whole row toggles. The chip and chevron are decoration under it. */}
      <div className="card-row group grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-x-3">
        <span className="pt-0.5">
          <Tile
            family="blue"
            icon={checkin.channel === 'sms' ? <MessageSquareText /> : <MessageCircle />}
          />
        </span>
        <div className="min-w-0">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-controls={panelId}
            className="stretched-link cursor-pointer text-left text-copy-lg font-medium tabular-nums text-ink outline-none"
          >
            {relativeTime(checkin.occurred_at)}
            {tone && <span className="sr-only">, {tone.label}</span>}
          </button>
          <p className="mt-0.5 text-copy text-secondary">{detail}</p>
          {checkin.digest.highlight && (
            <p className="mt-2 w-fit max-w-full rounded-control bg-soft px-3 py-2 text-copy text-ink transition-colors duration-state ease-apple group-hover:bg-panel">
              “{checkin.digest.highlight}”
            </p>
          )}
        </div>
        <div aria-hidden className="flex items-center gap-2 pt-0.5">
          {tone && <span className={`chip ${tone.cls}`}>{tone.label}</span>}
          <ChevronRight
            size={16}
            className={`text-faint transition-transform duration-spring ease-spring ${
              open ? 'rotate-90' : ''
            }`}
          />
        </div>
      </div>
      <div
        id={panelId}
        inert={!open}
        className="grid transition-[grid-template-rows,opacity] duration-spring ease-apple"
        style={{ gridTemplateRows: open ? '1fr' : '0fr', opacity: open ? 1 : 0 }}
      >
        <div className="overflow-hidden">
          <div className="pb-4 pl-[56px] pr-4 pt-1">
            <Transcript checkin={checkin} />
          </div>
        </div>
      </div>
    </li>
  )
}

export default function CheckinHistory({
  patientId,
  refreshing,
}: {
  patientId: string
  refreshing: boolean
}) {
  const { data } = usePatientCheckins(patientId)
  const [showAll, setShowAll] = useState(false)
  const checkins = data?.checkins ?? []
  const visible = showAll ? checkins : checkins.slice(0, 4)

  return (
    <SectionCard
      flush
      title="Check-ins"
      icon={<Tile size="sm" family="blue" icon={<MessageCircle />} />}
      aside={
        checkins.length > 0
          ? `${checkins.length} total · last ${relativeTime(checkins[0].occurred_at).toLowerCase()}`
          : undefined
      }
      action={
        checkins.length > 4 ? (
          <button type="button" className="btn-plain btn-sm" onClick={() => setShowAll((s) => !s)}>
            {showAll ? 'Recent only' : `Show all ${checkins.length}`}
          </button>
        ) : undefined
      }
    >
      <RefreshOverlay show={refreshing} />
      {checkins.length === 0 ? (
        <EmptyState
          variant="inline"
          title="No check-ins yet"
          icon={<MessageCircle />}
          className="px-5 pb-5"
        >
          Recovery conversations appear here once they happen.
        </EmptyState>
      ) : (
        <>
          <ListGroup embedded inset="tile" aria-label="Check-ins">
            {visible.map((c) => (
              <CheckinRow key={c.id} checkin={c} />
            ))}
          </ListGroup>
          <p className="meta px-5 pb-4 pt-2">
            Quotes are the patient's own words, selected from each conversation. Expand a check-in
            for the full transcript.
          </p>
        </>
      )}
    </SectionCard>
  )
}
