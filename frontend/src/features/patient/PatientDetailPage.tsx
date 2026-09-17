import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useCallback, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useCareMetrics } from '../../api/care'
import { usePatientDelivery } from '../../api/plan'
import { usePatient, useRecompute } from '../../api/queries'
import { NarrativeTile } from '../../components/AIAttribution'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import GuardrailFootnote from '../../components/GuardrailFootnote'
import type { ReadoutTone } from '../../components/MetricCluster'
import PriorityBadge from '../../components/PriorityBadge'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay, SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { relativeTime, signedPct } from '../../lib/format'
import { CONFIDENCE_LABEL, TRAJECTORY_LABEL } from '../../lib/risk'
import ActionBar from './ActionBar'
import CheckinHistory from './CheckinHistory'
import ContactCard from './ContactCard'
import DotLine from './DotLine'
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
 *   header      the page head (`data-hero`), inside AppShell's sky window —
 *               Aside's rounded window with the static Medical Blue / Teal
 *               clouds. The window sizes itself to this element. On it:
 *               a glass `.badge-ring` naming the pathway, the 56px avatar
 *               lifted on a white ring, the name at the section step with
 *               the ONE opaque risk pill (R7), the facts line, reachability,
 *               then the action capsules (all opaque).
 *               Text contract (safe sky, worst points light / dark): ink
 *               15.453 / 12.002, body 6.073 / 4.642, brand-ink 4.832 /
 *               4.735, risk-low 4.514 / 6.307. Secondary text is --body here
 *               (`data-hero` flips it). No clinical number sits on the sky:
 *               post-op day, trajectory and the check-in time are on the
 *               opaque recovery card below.
 *               At >= 1024px the right side of the window (from 58% of its
 *               width) is the DECOR zone, where only ink and opaque controls
 *               may sit. The text column is capped at calc(58% - 76px) of
 *               the header (the window is the header plus 28px each side, so
 *               58% of it is 58% of the header + 4.5px; the column starts
 *               76px in, after the avatar and gap), so head text never runs
 *               into it; the action bar, which is opaque, may.
 *   >= 1200px   grid [main 1fr | side 360px], gap 20.
 *               main: recovery, next steps, check-ins, tasks, messages
 *               side: headline metrics, timeline, wearables
 *   <  1200px   one column. The two column wrappers become `display:
 *               contents` so every card is a direct flex child and `order-*`
 *               interleaves them in reading priority (metrics right after
 *               the next steps, not after the message thread).
 *   Full stats  spans the width under the grid: its metric cards need room.
 */

const ANCHOR = 'scroll-mt-[calc(var(--bar-height)+var(--bar-inset)+16px)]'
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
    <dl className="mt-6 flex flex-wrap gap-x-12 gap-y-5 border-t border-hairline pt-5">
      {items.map((s) => (
        <div key={s.key} className="flex min-w-0 flex-col">
          <dt className="text-copy text-secondary">{s.label}</dt>
          <dd className="mt-0.5 flex items-baseline gap-1.5">
            <span className={`big-num text-[2.5rem] ${s.tone ? STAT_TONE[s.tone] : 'text-ink'}`}>
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
        title="This patient couldn’t be loaded"
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

  // The facts line. Every part is plain body text on the sky; confidence is
  // said in words only when it is reduced (R7: no chip beside the risk pill).
  // The pathway has its own badge above the name, so the procedure is left
  // out when the pathway name already starts with it.
  const pathwayName = care.data?.pathway?.name ?? null
  const procedure = general ? 'No surgery on file' : p.procedure_display
  const restated =
    !general &&
    !!pathwayName &&
    !!procedure &&
    pathwayName.toLowerCase().startsWith(procedure.toLowerCase())
  const facts = [
    `${p.age} ${p.sex}`,
    restated ? null : procedure,
    p.surgeon,
    p.device?.model,
    p.data_confidence.level !== 'high' ? CONFIDENCE_LABEL[p.data_confidence.level] : null,
  ]

  return (
    <div className="pb-4">
      {/* ── Page head, in the sky window ────────────────────────────────── */}
      <header data-hero className="rise pb-2 pt-3" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <Link to="/" className="btn-plain btn-sm -ml-3">
          <ChevronLeft aria-hidden size={16} /> Worklist
        </Link>

        <div className="mt-4 flex flex-wrap items-start gap-x-5 gap-y-4">
          <Avatar
            name={p.name}
            tier={p.risk.level}
            size="xl"
            className="mt-1 shrink-0 shadow-soft ring-4 ring-panel"
          />
          <div className="min-w-0 flex-1 basis-[240px] min-[1024px]:max-w-[calc(58%-76px)]">
            {pathwayName && (
              <button
                type="button"
                className="badge-ring mb-2 max-w-full"
                onClick={() => openTarget('plan')}
              >
                <span className="min-w-0 truncate">{pathwayName}</span>
                <ChevronRight aria-hidden />
                <span className="sr-only">: go to the care plan</span>
              </button>
            )}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <h1 className="display-title text-display text-ink">{p.name}</h1>
              <PriorityBadge priority={p.risk.level} />
            </div>
            <DotLine as="p" className="mt-1.5 text-copy text-body" parts={facts} />
            <ContactCard
              className="mt-2"
              patientId={p.id}
              patientName={p.name}
              phone={p.phone}
              app={p.app}
              smsConfigured={p.sms_configured}
            />
          </div>
          <ActionBar
            className="w-full min-[900px]:ml-auto min-[900px]:w-auto min-[900px]:justify-end min-[900px]:pt-1"
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

      {/* ── Headline bento ──────────────────────────────────────────────── */}
      <div className="mt-8">
        <HeadlineMetrics patientId={p.id} refreshing={refreshing} onOpen={openMetric} />
      </div>

      {/* ── Two-column body ─────────────────────────────────────────────── */}
      <div className="mt-stack flex flex-col gap-stack min-[1200px]:grid min-[1200px]:grid-cols-[minmax(0,1fr)_360px] min-[1200px]:items-start">
        <div className={COLUMN}>
          <Block index={1} order="order-1">
            <SectionCard
              sum
              title="Recovery summary"
              icon={<NarrativeTile provider={p.summary.provider} />}
              aside={
                refreshing ? (
                  // Aside's AI signature, only while the summary is being
                  // rewritten; static secondary text under Reduce Motion.
                  <span role="status" className="shimmer-text text-label font-medium">
                    {rulesBased ? 'Updating summary…' : 'Writing AI summary…'}
                  </span>
                ) : (
                  <DotLine
                    className="meta tabular-nums"
                    parts={[
                      rulesBased ? 'Rules-based' : 'Written by AI',
                      p.summary.generated_at && relativeTime(p.summary.generated_at),
                    ]}
                  />
                )
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
