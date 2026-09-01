import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useParams } from 'react-router-dom'
import { usePatient, useRecompute } from '../../api/queries'
import AIAttribution from '../../components/AIAttribution'
import ConfidenceChip from '../../components/ConfidenceChip'
import EmptyState from '../../components/EmptyState'
import GuardrailFootnote from '../../components/GuardrailFootnote'
import MetricCluster from '../../components/MetricCluster'
import PriorityBadge from '../../components/PriorityBadge'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay, SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { relativeTime, signedPct } from '../../lib/format'
import { PRIORITY, TRAJECTORY_LABEL, URGENCY } from '../../lib/risk'
import ActionBar from './ActionBar'
import CheckinHistory from './CheckinHistory'
import RecoveryTimeline from './RecoveryTimeline'
import RtmReadinessCard from './RtmReadinessCard'
import SignalsSection from './SignalsSection'
import useReviewTimeTracker from './useReviewTimeTracker'

function rise(index: number) {
  return { className: 'rise', style: { '--rise-delay': `${index * 55}ms` } as CSSProperties }
}

export default function PatientDetailPage() {
  const { id = '' } = useParams()
  const { data: p, isLoading, isError } = usePatient(id)
  useReviewTimeTracker(id)
  const recompute = useRecompute(id)
  const toast = useToast()
  const [minHold, setMinHold] = useState(false)
  // Only an explicit Refresh shimmers. The recompute stays pending until its
  // invalidated queries have refetched, so this covers the whole round trip
  // without catching the background loads that share the ['patient', id] key.
  const refreshing = recompute.isPending || minHold

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonCard lines={2} />
        <SkeletonCard lines={4} />
        <SkeletonCard lines={3} />
      </div>
    )
  }
  if (isError || !p) {
    return (
      <EmptyState title="This patient couldn't be loaded.">
        <Link to="/" className="font-semibold text-brand hover:underline">
          Back to the worklist
        </Link>
      </EmptyState>
    )
  }

  const onRefresh = () => {
    setMinHold(true)
    window.setTimeout(() => setMinHold(false), 1100)
    recompute.mutate(undefined, {
      onSuccess: () => toast('Analysis refreshed — new AI summary generated', 'info'),
      onError: () => toast('Refresh failed — try again', 'warning'),
    })
  }

  const rtmValue = !p.rtm.enrolled
    ? 'Enrolling'
    : p.rtm.qualifies
      ? 'Complete'
      : `${Math.min(p.rtm.days_with_data, p.rtm.target)}/${p.rtm.target}d`
  const trajValue =
    p.trajectory.pct != null && p.trajectory.state !== 'on'
      ? signedPct(p.trajectory.pct)
      : p.trajectory.state === 'on'
        ? 'On curve'
        : '—'

  return (
    <div>
      <div {...rise(0)}>
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-[13px] font-medium text-brand transition-opacity duration-150 hover:opacity-75"
        >
          <ArrowLeft size={15} /> Worklist
        </Link>

        <div className="mt-3 flex flex-wrap items-center gap-3">
          <span
            aria-hidden
            className={`grid h-10 w-10 place-items-center rounded-full font-mono text-[13px] font-medium text-white ${
              p.risk.level === 'high' ? 'bg-risk-high' : 'bg-brand'
            }`}
          >
            {p.initials}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-[26px] font-semibold tracking-[-.03em] text-ink">{p.name}</h1>
              <PriorityBadge priority={p.risk.level} />
              <ConfidenceChip level={p.data_confidence.level} />
            </div>
            <p className="mt-1 text-[12.5px] font-medium text-muted">
              {p.age} {p.sex} · {p.procedure_display} · {p.surgeon}
              {p.device && <> · {p.device.model}</>}
            </p>
          </div>
        </div>

        <MetricCluster
          className="mt-4"
          items={[
            { key: 'day', label: 'Post-op day', value: `D${p.postop_day}` },
            {
              key: 'rtm',
              label: 'RTM monitoring',
              value: rtmValue,
              tone: p.rtm.qualifies ? 'low' : undefined,
            },
            {
              key: 'traj',
              label: 'Trajectory',
              value: trajValue,
              tone:
                p.trajectory.state === 'behind'
                  ? 'med'
                  : p.trajectory.state === 'on' || p.trajectory.state === 'ahead'
                    ? 'low'
                    : undefined,
              hint:
                p.trajectory.state !== 'on' && p.trajectory.state !== 'unknown'
                  ? TRAJECTORY_LABEL[p.trajectory.state].replace(/ expected curve| of expected curve/i, '')
                  : undefined,
            },
            {
              key: 'checkin',
              label: 'Last check-in',
              value: p.last_checkin_at ? relativeTime(p.last_checkin_at) : 'None yet',
            },
          ]}
        />
      </div>

      <div {...rise(1)}>
        <div className="mt-5">
          <ActionBar
            patientId={p.id}
            patientName={p.name}
            onRefresh={onRefresh}
            refreshing={refreshing}
          />
        </div>
      </div>

      <div className="mt-5 space-y-3.5">
        <SectionCard
          sum
          spine={PRIORITY[p.risk.level].spine}
          {...rise(2)}
          eyebrow={
            <AIAttribution
              kind="recovery summary"
              generatedAt={p.summary.generated_at}
              provider={p.summary.provider}
            />
          }
        >
          <RefreshOverlay show={refreshing} />
          <p className="text-[13.5px] font-medium leading-[1.6] text-body">{p.summary.text}</p>
        </SectionCard>

        {p.actions.length > 0 && (
          <SectionCard title="Suggested follow-up" {...rise(3)}>
            <RefreshOverlay show={refreshing} />
            <ul className="divide-y divide-line">
              {p.actions.map((a, i) => (
                <li key={i} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                  <span
                    className={`chip mt-0.5 shrink-0 uppercase tracking-[.03em] ${URGENCY[a.urgency]?.pill ?? URGENCY.routine.pill}`}
                  >
                    {URGENCY[a.urgency]?.label ?? 'Routine'}
                  </span>
                  <span>
                    <span className="block text-[13.5px] font-semibold text-ink">{a.title}</span>
                    {a.detail && (
                      <span className="mt-0.5 block text-[12.5px] font-medium leading-snug text-muted">
                        {a.detail}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </SectionCard>
        )}

        <div {...rise(4)}>
          <RtmReadinessCard patientId={p.id} refreshing={refreshing} />
        </div>

        <div {...rise(5)}>
          <RecoveryTimeline patientId={p.id} trajectory={p.trajectory} refreshing={refreshing} />
        </div>

        <div {...rise(6)}>
          <CheckinHistory patientId={p.id} refreshing={refreshing} />
        </div>

        <div {...rise(7)}>
          <SignalsSection patientId={p.id} rtm={p.rtm} refreshing={refreshing} />
        </div>
      </div>

      <GuardrailFootnote className="mt-8" />
    </div>
  )
}
