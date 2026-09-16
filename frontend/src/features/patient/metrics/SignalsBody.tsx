import type { CSSProperties } from 'react'
import type { MetricInsight, PatientMetrics } from '../../../api/types'
import AdherenceDots from '../../../components/AdherenceDots'
import Sparkline from '../../../components/charts/Sparkline'
import TrajectoryChart from '../../../components/charts/TrajectoryChart'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay } from '../../../components/Skeleton'
import { METRIC_STATUS } from '../../../lib/risk'

/** The Signals tab of Full stats — the former "Supporting signals" body
 *  (trajectory, multi-signal deviation, wearable trend cards, adherence),
 *  moved here unchanged. Its data comes from the lazy `usePatientMetrics`
 *  query the tab owns. */

function SignalCard({
  m,
  index,
  refreshing,
}: {
  m: MetricInsight
  index: number
  refreshing: boolean
}) {
  const s = METRIC_STATUS[m.status]
  return (
    <div
      style={{ '--rise-delay': `${index * 40}ms` } as CSSProperties}
      className="rise relative overflow-hidden rounded-card border border-line bg-panel p-5 pl-[22px] shadow-card"
    >
      <RefreshOverlay show={refreshing} />
      <span aria-hidden className={`absolute inset-y-0 left-0 w-[4px] ${s.spine}`} />
      <div className="flex items-center justify-between gap-2">
        <span className="text-[15px] font-medium text-ink">{m.name}</span>
        <span className={`chip shrink-0 uppercase tracking-[.03em] ${s.pill}`}>
          {m.status === 'flag' || m.status === 'watch' ? m.status_text : s.label}
        </span>
      </div>
      <div className="mt-2">
        <Sparkline series={m.series} baseline={m.baseline_mean} unit={m.unit} />
      </div>
      <p className="mt-2.5 text-[14px] leading-[1.5] text-body">{m.finding}</p>
      {m.next_step && (
        <p className="mt-2 flex items-start gap-1.5 text-[13.5px] font-medium text-brand">
          <span aria-hidden>→</span> {m.next_step}
        </p>
      )}
      <p className="mt-3 border-t border-line pt-2 text-[12px] leading-[1.5] text-muted">
        {m.coverage_text}
        {m.guarded && ' · guarded phrasing'}
      </p>
    </div>
  )
}

export default function SignalsBody({
  data,
  refreshing,
}: {
  data: PatientMetrics
  refreshing: boolean
}) {
  return (
    <div className="space-y-4">
      <SectionCard title="Recovery trajectory">
        <RefreshOverlay show={refreshing} />
        <TrajectoryChart
          actual={data.trajectory.actual}
          expected={data.trajectory.expected}
          changePointDay={data.trajectory.change_point_day}
        />
      </SectionCard>

      {data.composite.drivers.length > 0 && (
        <SectionCard
          title="Multi-signal deviation"
          aside={
            <span
              className={`chip ${
                data.composite.level === 'high'
                  ? 'bg-risk-high-bg text-risk-high'
                  : data.composite.level === 'elevated'
                    ? 'bg-risk-med-bg text-risk-med'
                    : 'bg-risk-low-bg text-risk-low'
              }`}
            >
              {data.composite.level === 'high'
                ? 'High'
                : data.composite.level === 'elevated'
                  ? 'Elevated'
                  : 'Normal'}
            </span>
          }
        >
          <RefreshOverlay show={refreshing} />
          <div className="space-y-2.5">
            {data.composite.drivers.map((d) => (
              <div key={d.metric_type} className="flex items-center gap-3">
                <span className="w-36 shrink-0 text-[13px] font-medium text-muted">{d.label}</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-line">
                  <div
                    className="h-full rounded-full bg-brand transition-[width] duration-500 ease-out"
                    style={{ width: `${Math.round(d.contribution * 100)}%` }}
                  />
                </div>
                <span className="w-9 shrink-0 text-right font-mono text-[12px] font-medium tabular-nums text-muted">
                  {Math.round(d.contribution * 100)}%
                </span>
              </div>
            ))}
          </div>
          <p className="mt-3 border-t border-line pt-2 text-[12px] leading-[1.5] text-muted">
            Contribution of each signal to the deviation index — for review, not a diagnosis.
          </p>
        </SectionCard>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {data.metrics.map((m, i) => (
          <SignalCard key={m.metric_key} m={m} index={i} refreshing={refreshing} />
        ))}
      </div>

      <SectionCard title="Adherence & monitoring">
        <RefreshOverlay show={refreshing} />
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="micro mb-1.5">
              Task adherence · last 14 days{' '}
              <span className="normal-case tracking-normal">
                ({data.adherence.verified} verified, {data.adherence.self_attested} self-attested)
              </span>
            </p>
            <AdherenceDots days={data.adherence.days} rate={data.adherence.rate} />
          </div>
        </div>
      </SectionCard>
    </div>
  )
}
