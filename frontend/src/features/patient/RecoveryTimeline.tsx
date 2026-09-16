import { usePatientTimeline } from '../../api/queries'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay } from '../../components/Skeleton'
import { shortDate, signedPct } from '../../lib/format'
import { TRAJECTORY_LABEL } from '../../lib/risk'
import type { Trajectory } from '../../api/types'

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

/** Milestone rail: surgery → discharge → flags/change-points → today. */
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

  return (
    <SectionCard
      title="Recovery timeline"
      aside={
        <span
          className={`chip ${
            trajectory.state === 'behind'
              ? 'bg-risk-high-tint text-risk-high-ink'
              : trajectory.state === 'unknown'
                ? 'bg-risk-missing-tint text-risk-missing-ink'
                : 'bg-risk-low-tint text-risk-low-ink'
          }`}
        >
          {TRAJECTORY_LABEL[trajectory.state]}
          {trajectory.pct != null && trajectory.state !== 'on' && (
            <span className="tabular-nums">({signedPct(trajectory.pct)})</span>
          )}
        </span>
      }
    >
      <RefreshOverlay show={refreshing} />
      {events.length === 0 ? (
        <p className="text-copy text-muted">
          Timeline will appear as events are recorded.
        </p>
      ) : (
        <div className="overflow-x-auto pb-1">
          <div className="relative flex min-w-max items-start gap-8 px-1 pt-1.5">
            <span aria-hidden className="absolute left-2 right-2 top-[10px] h-px bg-line" />
            {events.map((e, i) => (
              <div key={`${e.date}-${e.kind}-${i}`} className="relative flex w-24 flex-col items-start">
                <span className={`relative z-10 h-3.5 w-3.5 rounded-pill ${DOT[e.kind] ?? 'bg-line'}`} />
                <span className="mt-2 text-copy font-medium text-ink">{e.label}</span>
                <span className="text-label font-medium tabular-nums text-muted">
                  {shortDate(e.date)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </SectionCard>
  )
}
