import { ChevronLeft, Sigma, Sparkles } from 'lucide-react'
import { Fragment, useCallback, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useCareMetrics } from '../../api/care'
import { usePatientDelivery } from '../../api/plan'
import { usePatient, useRecompute } from '../../api/queries'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import GuardrailFootnote from '../../components/GuardrailFootnote'
import type { ReadoutTone } from '../../components/MetricCluster'
import PriorityBadge from '../../components/PriorityBadge'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay, SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'
import { relativeTime, signedPct } from '../../lib/format'
import { CONFIDENCE_LABEL, TRAJECTORY_LABEL } from '../../lib/risk'
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

/* Layout (R3, spec W3). AppShell already caps the page at 1240px and adds the
 * gutter, so nothing here sets a width or horizontal padding.
 *
 *   header      on the ambient wash: 56px avatar, name 26/600, the ONE risk
 *               pill (R7), a facts line, reachability, then the action
 *               capsules. Text on the wash is ink / body / brand-ink only
 *               (body 6.371 worst, btn-plain 5.069 worst — see ContactCard).
 *   >= 1200px   grid [main 1fr | side 360px], gap 20.
 *               main: recovery, next steps, check-ins, tasks, messages
 *               side: headline metrics, timeline, wearables
 *   <  1200px   one column. The two column wrappers become `display:
 *               contents` so every card is a direct flex child and `order-*`
 *               interleaves them in reading priority (metrics right after
 *               the next steps, not after the message thread).
 *   Full stats  spans the width under the grid: its metric cards need room.
 */

const ANCHOR = 'scroll-mt-[calc(var(--bar-height)+16px)]'
const COLUMN = 'contents min-[1200px]:flex min-[1200px]:min-w-0 min-[1200px]:flex-col min-[1200px]:gap-stack'

function Block({
  index,
  order,
  id,
  children,
}: {
  index: number
  order: string
  id?: string
  children: ReactNode
}) {
  return (
    <div
      id={id}
      className={`rise min-w-0 ${order} ${id ? ANCHOR : ''}`}
      style={{ '--rise-delay': `${index * 55}ms` } as CSSProperties}
    >
      {children}
    </div>
  )
}

/** Recovery-card stats: label over a 26/500 figure on the opaque brand tint.
 *  Ink 15.871 / 14.255; risk-med-ink 5.022 / 7.993; risk-low-ink 4.637 /
 *  7.491 (26px). A tinted figure always carries a word ("Behind"), so the
 *  state is never colour alone. Labels are --body on the tint (R8). */
const STAT_TONE: Record<ReadoutTone, string> = {
  high: 'text-risk-high-ink',
  med: 'text-risk-med-ink',
  low: 'text-risk-low-ink',
  missing: 'text-risk-missing-ink',
}

function Stats({
  items,
}: {
  items: { key: string; label: string; value: string; tone?: ReadoutTone; hint?: string }[]
}) {
  return (
    <dl className="mt-5 flex flex-wrap gap-x-10 gap-y-4">
      {items.map((s) => (
        <div key={s.key} className="flex min-w-0 flex-col">
          <dt className="text-copy text-secondary">{s.label}</dt>
          <dd className="mt-0.5 flex items-baseline gap-1.5">
            <span
              className={`text-title font-medium tabular-nums ${s.tone ? STAT_TONE[s.tone] : 'text-ink'}`}
            >
              {s.value}
            </span>
            {s.hint && <span className="text-copy text-secondary">{s.hint}</span>}
          </dd>
        </div>
      ))}
    </dl>
  )
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
      <div className="pt-6" role="status" aria-label="Loading patient">
        <div className="flex items-center gap-4">
          <span className="h-14 w-14 shrink-0 animate-pulse rounded-pill bg-soft" />
          <div className="w-full max-w-sm space-y-2">
            <SkeletonLine className="h-6 w-2/3" />
            <SkeletonLine className="w-full" />
          </div>
        </div>
        <div className="mt-8 grid gap-stack min-[1200px]:grid-cols-[minmax(0,1fr)_360px]">
          <div className="space-y-stack">
            <SkeletonCard lines={4} />
            <SkeletonCard rows={3} />
          </div>
          <div className="space-y-stack">
            <SkeletonCard lines={3} />
            <SkeletonCard lines={4} />
          </div>
        </div>
      </div>
    )
  }
  if (isError || !p) {
    return (
      <EmptyState
        title="This patient couldn't be loaded"
        className="mt-6"
        action={
          <Link to="/" className="btn-tinted">
            <ChevronLeft aria-hidden size={16} /> Back to the worklist
          </Link>
        }
      >
        Check the link, or pick the patient from the worklist again.
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

  const general = p.mode === 'general'
  const trajValue =
    p.trajectory.pct != null && p.trajectory.state !== 'on'
      ? signedPct(p.trajectory.pct)
      : p.trajectory.state === 'on'
        ? 'On curve'
        : '—'
  const rulesBased = p.summary.provider === 'fallback'

  // The facts line. Every part is plain body text on the wash; confidence is
  // said in words only when it is reduced (R7: no chip beside the risk pill).
  const facts = [
    `${p.age} ${p.sex}`,
    general ? 'No surgery on file' : p.procedure_display,
    p.surgeon,
    p.device?.model,
    care.data?.pathway?.name ? `Pathway: ${care.data.pathway.name}` : null,
    p.data_confidence.level !== 'high' ? CONFIDENCE_LABEL[p.data_confidence.level] : null,
  ].filter(Boolean) as string[]

  return (
    <div className="pb-4">
      {/* ── Header, on the ambient wash ─────────────────────────────────── */}
      <header className="rise pt-3" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <Link to="/" className="btn-plain btn-sm -ml-3">
          <ChevronLeft aria-hidden size={16} /> Worklist
        </Link>

        <div className="mt-3 flex flex-wrap items-start gap-x-4 gap-y-4">
          <Avatar name={p.name} tier={p.risk.level} size="xl" className="shrink-0" />
          <div className="min-w-0 flex-1 basis-[240px]">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <h1 className="text-title font-semibold text-ink">{p.name}</h1>
              <PriorityBadge priority={p.risk.level} />
            </div>
            <p className="mt-1 text-copy text-body">
              {facts.map((f, i) => (
                <Fragment key={i}>
                  {i > 0 && <span aria-hidden> · </span>}
                  <span className="whitespace-nowrap">{f}</span>
                </Fragment>
              ))}
            </p>
            <ContactCard
              className="mt-1.5"
              patientId={p.id}
              patientName={p.name}
              phone={p.phone}
              app={p.app}
              smsConfigured={p.sms_configured}
            />
          </div>
          <ActionBar
            className="min-[900px]:ml-auto min-[900px]:justify-end min-[900px]:pt-1"
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
      </header>

      {/* ── Two-column body ─────────────────────────────────────────────── */}
      <div className="mt-8 flex flex-col gap-stack min-[1200px]:grid min-[1200px]:grid-cols-[minmax(0,1fr)_360px] min-[1200px]:items-start">
        <div className={COLUMN}>
          <Block index={1} order="order-1">
            <SectionCard
              sum
              title="Recovery summary"
              icon={
                <Tile
                  size="sm"
                  family={rulesBased ? 'indigo' : 'teal'}
                  icon={rulesBased ? <Sigma /> : <Sparkles />}
                />
              }
              aside={
                <span className="meta tabular-nums">
                  {rulesBased ? 'Rules-based' : 'Written by AI'}
                  {p.summary.generated_at && (
                    <>
                      <span aria-hidden className="px-1">·</span>
                      {relativeTime(p.summary.generated_at)}
                    </>
                  )}
                </span>
              }
            >
              <RefreshOverlay show={refreshing} />
              <p className="max-w-[68ch] text-copy-lg text-ink">{p.summary.text}</p>
              <Stats
                items={[
                  // A general patient never had an operation: "Post-op day D6"
                  // is simply false about them.
                  general
                    ? { key: 'day', label: 'Days monitored', value: `${p.postop_day ?? 0}` }
                    : { key: 'day', label: 'Post-op day', value: `D${p.postop_day}` },
                  {
                    key: 'traj',
                    label: general ? 'Vs. baseline' : 'Vs. expected',
                    value: trajValue,
                    tone:
                      p.trajectory.state === 'behind'
                        ? 'med'
                        : p.trajectory.state === 'on' || p.trajectory.state === 'ahead'
                          ? 'low'
                          : undefined,
                    hint:
                      p.trajectory.state !== 'on' && p.trajectory.state !== 'unknown'
                        ? TRAJECTORY_LABEL[p.trajectory.state].replace(
                            / expected curve| of expected curve/i,
                            '',
                          )
                        : undefined,
                  },
                  {
                    key: 'checkin',
                    label: 'Last check-in',
                    value: p.last_checkin_at ? relativeTime(p.last_checkin_at) : 'None yet',
                  },
                ]}
              />
            </SectionCard>
          </Block>

          <Block index={2} order="order-2">
            <NextSteps
              patientId={p.id}
              patientName={p.name}
              surgeon={p.surgeon}
              phone={delivery.phone}
              canText={delivery.smsAvailable}
              aiActions={p.actions}
              refreshing={refreshing}
              onOpen={openTarget}
            />
          </Block>

          <Block index={4} order="order-4">
            <CheckinHistory patientId={p.id} refreshing={refreshing} />
          </Block>

          <Block index={6} order="order-6" id="care-plan">
            <TasksSection
              patientId={p.id}
              patientName={p.name}
              pathway={care.data?.pathway}
              phone={delivery.phone}
              smsAvailable={delivery.smsAvailable}
              refreshing={refreshing}
            />
          </Block>

          <Block index={7} order="order-7" id="messages">
            <MessagesSection
              patientId={p.id}
              patientName={p.name}
              surgeon={p.surgeon}
              phone={delivery.phone}
              refreshing={refreshing}
            />
          </Block>
        </div>

        <div className={COLUMN}>
          <Block index={3} order="order-3">
            <HeadlineMetrics patientId={p.id} refreshing={refreshing} onOpen={openMetric} />
          </Block>

          <Block index={5} order="order-5">
            <RecoveryTimeline patientId={p.id} trajectory={p.trajectory} refreshing={refreshing} />
          </Block>

          <Block index={8} order="order-8" id="wearables">
            <WearableConnectionCard patientId={p.id} patientName={p.name} refreshing={refreshing} />
          </Block>
        </div>
      </div>

      <div className={`rise mt-stack ${ANCHOR}`} id="full-stats" style={{ '--rise-delay': '495ms' } as CSSProperties}>
        <FullStats
          patientId={p.id}
          refreshing={refreshing}
          open={fullStatsOpen}
          onOpenChange={setFullStatsOpen}
          focusMetricId={focusMetricId}
          onFocusHandled={clearFocus}
        />
      </div>

      <GuardrailFootnote className="mt-8" />
    </div>
  )
}
