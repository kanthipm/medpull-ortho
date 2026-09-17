import { Milestone } from 'lucide-react'
import { usePatientTimeline } from '../../api/queries'
import type { Trajectory } from '../../api/types'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { shortDate, signedPct } from '../../lib/format'
import { TRAJECTORY_LABEL } from '../../lib/risk'

/** Rail markers. Shape does part of the work so colour is never the only
 *  carrier: milestones are filled discs, flags and shifts are filled discs in
 *  their risk ink AND say what happened in words, today is a brand ring. */
const DOT: Record<string, string> = {
  surgery: 'bg-ink',
  // A general patient's rail starts when monitoring did, not at an operation.
  enrolled: 'bg-ink',
  discharge: 'bg-line-strong',
  flag: 'bg-risk-high-ink',
  change_point: 'bg-risk-med-ink',
  today: 'border-2 border-brand bg-panel',
  checkin: 'bg-line',
}

/** Milestone rail: surgery → discharge → flags/change-points → today.
 *
 *  A vertical list now, so it reads in the page's 360px side column and at
 *  phone width alike. The trajectory is not repeated as a chip (the recovery
 *  card already states it, R7); it is the "Today" entry's detail instead. */
export default function RecoveryTimeline({
  patientId,
  trajectory,
  refreshing,
}: {
  patientId: string
  trajectory: Trajectory
  refreshing: boolean
}) {
  const { data } = usePatientTimeline(patientId)
  const events = (data?.events ?? []).filter((e) => e.kind !== 'checkin')
  const todayDetail =
    trajectory.state === 'unknown'
      ? null
      : `${TRAJECTORY_LABEL[trajectory.state]}${
          trajectory.pct != null && trajectory.state !== 'on' ? ` (${signedPct(trajectory.pct)})` : ''
        }`

  return (
    <SectionCard
      title="Timeline"
      icon={<Tile size="sm" family="indigo" icon={<Milestone />} />}
    >
      <RefreshOverlay show={refreshing} />
      {events.length === 0 ? (
        <p className="text-copy text-secondary">Milestones appear here as they are recorded.</p>
      ) : (
        <ol className="relative" aria-label="Recovery milestones">
          {events.map((e, i) => {
            const last = i === events.length - 1
            return (
              <li
                key={`${e.date}-${e.kind}-${i}`}
                className="relative grid grid-cols-[14px_minmax(0,1fr)_auto] gap-x-3 pb-3.5 last:pb-0"
              >
                {/* Connector to the next marker. */}
                {!last && (
                  <span
                    aria-hidden
                    className="absolute bottom-0 left-[6.5px] top-[18px] w-px bg-line"
                  />
                )}
                <span
                  aria-hidden
                  className={`relative mt-[4px] h-3.5 w-3.5 rounded-pill ${DOT[e.kind] ?? 'bg-line'}`}
                />
                <div className="min-w-0">
                  <p className="text-copy font-medium text-ink">{e.label}</p>
                  {e.kind === 'today' && todayDetail && (
                    <p className="text-copy text-secondary">{todayDetail}</p>
                  )}
                </div>
                <time dateTime={e.date} className="meta pt-0.5 tabular-nums">
                  {shortDate(e.date)}
                </time>
              </li>
            )
          })}
        </ol>
      )}
    </SectionCard>
  )
}
