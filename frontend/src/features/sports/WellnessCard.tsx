import { ClipboardList } from 'lucide-react'
import type { Wellness } from '../../api/sports'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { shortDate } from '../../lib/format'
import DotLine from '../patient/DotLine'
import { StatusChip } from './SportsBits'
import { TONE_TEXT, fmt, sd, statusTone } from './sportsFormat'

/** This morning's answers as soft tiles: the value out of 10, the z-score
 *  against the athlete's own month (negative is always worse) and the state
 *  in a word when it is off; then the finding, the Hooper index and any
 *  note the athlete typed. */
export default function WellnessCard({ wellness }: { wellness: Wellness | null }) {
  if (!wellness || wellness.items.length === 0) {
    return (
      <SectionCard title="Wellness today">
        <EmptyState variant="inline" icon={<ClipboardList />} family="blue" title="No morning answers yet">
          The six questions land here once the athlete answers them in the app.
        </EmptyState>
      </SectionCard>
    )
  }
  const w = wellness
  const notes = [...new Map(w.notes.map((n) => [`${n.date}|${n.text}`, n])).values()]
  return (
    <SectionCard title="Wellness today" aside={<StatusChip status={w.status} text={w.status_text} />}>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 min-[1200px]:grid-cols-2" aria-label="Morning answers">
        {w.items.map((it) => {
          const tone = statusTone(it.state)
          return (
            <li key={it.key} className="min-w-0 rounded-control bg-soft px-3.5 py-3">
              <span className="block truncate text-copy text-secondary">{it.label}</span>
              <span className="mt-1 flex items-baseline gap-1 text-title font-medium tabular-nums text-ink">
                {fmt(it.value, 1)}
                <span className="text-label font-normal text-secondary">/10</span>
              </span>
              <span className={`meta mt-0.5 block tabular-nums ${tone ? TONE_TEXT[tone] : ''}`}>
                {sd(it.z)}
                {tone ? ` · ${it.state === 'flag' ? 'Flag' : 'Watch'}` : ''}
              </span>
            </li>
          )
        })}
      </ul>
      {w.finding && <p className="mt-3 text-copy text-body">{w.finding}</p>}
      <DotLine
        as="p"
        className="meta mt-2"
        parts={[
          w.hooper != null && `Hooper ${fmt(w.hooper, 1)}`,
          w.composite_z != null && `Composite ${sd(w.composite_z)}`,
          `${w.answered_today} answered today`,
          w.latest_date && shortDate(w.latest_date),
        ]}
      />
      {notes.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-hairline pt-3" aria-label="Athlete notes">
          {notes.map((n, i) => (
            <li key={i} className="text-copy text-ink">
              “{n.text}”<span className="meta"> · {shortDate(n.date)}</span>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  )
}
