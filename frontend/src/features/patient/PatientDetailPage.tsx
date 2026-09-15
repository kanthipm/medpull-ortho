import { ArrowLeft } from 'lucide-react'
import { useCallback, useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useCareMetrics } from '../../api/care'
import { usePatientDelivery } from '../../api/plan'
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
import { PRIORITY, TRAJECTORY_LABEL } from '../../lib/risk'
import ActionBar from './ActionBar'
import CheckinHistory from './CheckinHistory'
import ContactCard from './ContactCard'
import FullStats from './metrics/FullStats'
import HeadlineMetrics from './metrics/HeadlineMetrics'
import MessagesSection from './plan/MessagesSection'
import NextSteps from './plan/NextSteps'
import TasksSection from './plan/TasksSection'
import RecoveryTimeline from './RecoveryTimeline'
import WearableConnectionCard from './WearableConnectionCard'

function rise(index: number) {
  return { className: 'rise', style: { '--rise-delay': `${index * 55}ms` } as CSSProperties }
}

export default function PatientDetailPage() {
  const { id = '' } = useParams()
  const { data: p, isLoading, isError } = usePatient(id)
  const recompute = useRecompute(id)
  const toast = useToast()
  const [minHold, setMinHold] = useState(false)
  // The care-metrics query is shared by the header's pathway line, the
  // headline tiles and Full stats — one request, one cache entry.
  const care = useCareMetrics(id)
  // Full stats is controlled from here so a headline tile can open it on
  // its own metric's card; the focus clears once the card has been scrolled to.
  const [fullStatsOpen, setFullStatsOpen] = useState(false)
  const [focusMetricId, setFocusMetricId] = useState<string | null>(null)
  const openMetric = useCallback((metricId: string) => {
    setFullStatsOpen(true)
    setFocusMetricId(metricId)
  }, [])
  const clearFocus = useCallback(() => setFocusMetricId(null), [])
  // Whether a text can reach this patient — the builder's "Text the plan"
  // checkbox and the composer's button label read it.
  const delivery = usePatientDelivery(id, p)
  // An `open` next step lands on a metric card or scrolls to a section.
  const openTarget = useCallback(
    (target: string) => {
      if (target.startsWith('full_stats:')) {
        openMetric(target.slice('full_stats:'.length))
        return
      }
      const anchor = target === 'plan' ? 'care-plan' : target
      document.getElementById(anchor)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    },
    [openMetric],
  )
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
            {care.data?.pathway?.name && (
              <p className="mt-0.5 text-[12px] font-medium text-faint">
                Pathway · {care.data.pathway.name}
              </p>
            )}
          </div>
        </div>

        <MetricCluster
          className="mt-4"
          items={[
            { key: 'day', label: 'Post-op day', value: `D${p.postop_day}` },
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
            surgeon={p.surgeon}
            pathway={care.data?.pathway}
            phone={delivery.phone}
            smsAvailable={delivery.smsAvailable}
            onRefresh={onRefresh}
            refreshing={refreshing}
          />
        </div>
        <div className="mt-3">
          <ContactCard
            patientId={p.id}
            patientName={p.name}
            phone={p.phone}
            app={p.app}
            smsConfigured={p.sms_configured}
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

        <div {...rise(3)}>
          <NextSteps
            patientId={p.id}
            patientName={p.name}
            surgeon={p.surgeon}
            phone={delivery.phone}
            aiActions={p.actions}
            refreshing={refreshing}
            onOpen={openTarget}
          />
        </div>

        <div {...rise(5)}>
          <RecoveryTimeline patientId={p.id} trajectory={p.trajectory} refreshing={refreshing} />
        </div>

        <div {...rise(6)}>
          <CheckinHistory patientId={p.id} refreshing={refreshing} />
        </div>

        <div {...rise(7)}>
          <HeadlineMetrics patientId={p.id} refreshing={refreshing} onOpen={openMetric} />
        </div>

        <div {...rise(8)}>
          <FullStats
            patientId={p.id}
            refreshing={refreshing}
            open={fullStatsOpen}
            onOpenChange={setFullStatsOpen}
            focusMetricId={focusMetricId}
            onFocusHandled={clearFocus}
          />
        </div>

        <div id="care-plan" {...rise(9)}>
          <TasksSection
            patientId={p.id}
            patientName={p.name}
            pathway={care.data?.pathway}
            phone={delivery.phone}
            smsAvailable={delivery.smsAvailable}
            refreshing={refreshing}
          />
        </div>

        <div id="messages" {...rise(10)}>
          <MessagesSection
            patientId={p.id}
            patientName={p.name}
            surgeon={p.surgeon}
            phone={delivery.phone}
            refreshing={refreshing}
          />
        </div>

        <div id="wearables" {...rise(11)}>
          <WearableConnectionCard patientId={p.id} patientName={p.name} refreshing={refreshing} />
        </div>
      </div>

      <GuardrailFootnote className="mt-8" />
    </div>
  )
}
