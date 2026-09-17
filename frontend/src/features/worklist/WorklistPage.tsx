import {
  CheckCheck,
  ClipboardList,
  ExternalLink,
  MessageSquare,
  Phone,
  Send,
  Sigma,
  Sparkles,
  TriangleAlert,
  Users,
} from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import type { CSSProperties, MouseEvent, ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { NextStep, NextStepActionType, WorklistRowWithStep } from '../../api/plan'
import { useCompleteNextStep, useExecuteNextStep } from '../../api/plan'
import { useWorklist, type AskResult } from '../../api/queries'
import MessageComposerModal from '../patient/plan/MessageComposerModal'
import AskBar from './AskBar'
import Avatar from '../../components/Avatar'
import ConfidenceChip from '../../components/ConfidenceChip'
import EmptyState from '../../components/EmptyState'
import GuardrailFootnote from '../../components/GuardrailFootnote'
import { ListGroup } from '../../components/ListRow'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'
import { longDate, relativeTime } from '../../lib/format'
import { PRIORITY, type Priority } from '../../lib/risk'

type Filter = 'all' | 'high' | 'missing_data'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'high', label: 'High risk' },
  { key: 'missing_data', label: 'Missing data' },
]

const TIER_ORDER: Priority[] = ['high', 'medium', 'missing_data', 'low']

/** How long the first-load rise runs before rows stop animating in. Rows
 *  that remount later (filter changes, ask results) appear without motion. */
const INTRO_MS = 1200

function greeting(d: Date = new Date()): string {
  const h = d.getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

/** The page's one big line. Warm, but it only says what the numbers say. */
function headline(stats: { high: number; medium: number; missing: number }): string {
  if (stats.high === 1) return '1 patient needs you today'
  if (stats.high > 1) return `${stats.high} patients need you today`
  if (stats.missing > 0) {
    return `Nothing urgent — ${stats.missing} ${stats.missing === 1 ? 'patient has' : 'patients have'} data gaps`
  }
  if (stats.medium > 0) {
    return `Nothing urgent — ${stats.medium} to review when you can`
  }
  return 'Everyone’s on track today'
}

export default function WorklistPage() {
  const { data, isLoading, isError } = useWorklist()
  const [filter, setFilter] = useState<Filter>('all')
  const [askResult, setAskResult] = useState<AskResult | null>(null)
  // A row's "Message" next step opens the composer for that patient; the
  // send is logged back as the step's completion.
  const [composer, setComposer] = useState<{ patient: WorklistRowWithStep; step: NextStep } | null>(
    null,
  )
  // Rows rise in on the first load only.
  const [intro, setIntro] = useState(true)
  const ready = Boolean(data)
  useEffect(() => {
    if (!ready) return
    const t = window.setTimeout(() => setIntro(false), INTRO_MS)
    return () => window.clearTimeout(t)
  }, [ready])
  const patientsHeadingId = useId()

  if (isLoading) {
    return (
      <div className="pt-8" role="status" aria-label="Loading the worklist">
        <SkeletonLine className="h-3.5 w-56" />
        <SkeletonLine className="mt-3 h-8 w-96 max-w-full" />
        <div className="mt-stack space-y-stack">
          <SkeletonCard lines={3} />
          <SkeletonCard rows={4} />
        </div>
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className="pt-8">
        <EmptyState title="The worklist couldn't be loaded." family="blue">
          Check that the API is running, then reload this page.
        </EmptyState>
      </div>
    )
  }

  const askIds = askResult && askResult.patient_ids.length > 0 ? new Set(askResult.patient_ids) : null
  const groups = TIER_ORDER.map((tier) => ({
    tier,
    patients: data.patients.filter((p) =>
      askIds
        ? askIds.has(p.id) && p.priority === tier
        : p.priority === tier && (filter === 'all' || p.priority === filter),
    ),
  })).filter((g) => g.patients.length > 0)

  const rulesBased = data.briefing.provider === 'fallback'
  // First-load entrance: `.rise` plus a staggered delay; nothing afterwards.
  const riseCls = intro ? 'rise' : ''
  const riseAt = (ms: number) =>
    intro ? ({ '--rise-delay': `${ms}ms` } as CSSProperties) : undefined

  let riseIndex = 0

  return (
    <div className="pb-4 pt-8">
      <header className={riseCls} style={riseAt(0)}>
        {/* --body, not --muted: dark muted on the densest part of the wash is
            4.351:1; body is 6.423 light / 5.899 dark there. */}
        <p className="text-copy font-medium text-body">
          {greeting()}
          <span aria-hidden> · </span>
          <span className="sr-only">, </span>
          {longDate()}
        </p>
        <h1 className="mt-1 text-section font-semibold text-ink">{headline(data.stats)}</h1>
      </header>

      <div className={`mt-stack ${riseCls}`} style={riseAt(60)}>
        <SectionCard
          sum
          title="Today’s briefing"
          icon={
            <Tile
              size="sm"
              family={rulesBased ? 'indigo' : 'teal'}
              icon={rulesBased ? <Sigma /> : <Sparkles />}
            />
          }
          aside={
            <span className="meta tabular-nums">
              {rulesBased ? 'Rules-based' : 'AI'}
              <span aria-hidden> · </span>
              <span className="sr-only">, </span>
              {relativeTime(data.briefing.generated_at)}
            </span>
          }
        >
          <p className="max-w-[64ch] text-copy-lg text-ink">{data.briefing.text}</p>
        </SectionCard>
      </div>

      <div className={`mt-stack ${riseCls}`} style={riseAt(100)}>
        <AskBar result={askResult} onResult={setAskResult} onClear={() => setAskResult(null)} />
      </div>

      <div
        className={`mt-10 flex flex-wrap items-center justify-between gap-3 ${riseCls}`}
        style={riseAt(140)}
      >
        <h2 id={patientsHeadingId} className="text-subhead font-semibold text-ink">
          {askIds ? 'Matching patients' : 'Patients'}
          <span className="ml-2 text-copy-lg font-normal tabular-nums text-secondary">
            {askIds ? groups.reduce((n, g) => n + g.patients.length, 0) : data.patients.length}
          </span>
        </h2>
        {!askIds && (
          <SegmentedControl
            options={FILTERS}
            value={filter}
            onChange={setFilter}
            role="radiogroup"
            aria-label="Filter patients"
            className="flex-none"
          />
        )}
      </div>

      {groups.length === 0 ? (
        <div className="mt-4">
          <EmptyState
            icon={<Users />}
            title={askIds ? 'No patients matched that question' : 'No patients match this filter'}
          >
            {askIds
              ? 'Clear the question to see the full roster.'
              : 'Switch back to All to see the full roster.'}
          </EmptyState>
        </div>
      ) : (
        <div className="mt-4 space-y-stack" aria-labelledby={patientsHeadingId} role="region">
          {groups.map(({ tier, patients }) => (
            <TierGroup key={tier} tier={tier} count={patients.length}>
              {patients.map((p) => (
                <WorklistRow
                  key={p.id}
                  patient={p}
                  rise={intro ? 160 + riseIndex++ * 40 : null}
                  onMessage={(step) => setComposer({ patient: p, step })}
                />
              ))}
            </TierGroup>
          ))}
        </div>
      )}

      <GuardrailFootnote className="mt-8" />

      {composer && (
        <WorklistComposer
          patient={composer.patient}
          step={composer.step}
          onClose={() => setComposer(null)}
        />
      )}
    </div>
  )
}

/** One tier: its own rounded group, with a sticky dot + word header that
 *  replaces the per-row risk badge (R4). The header sticks under the app bar
 *  (`top-bar`) while the tier scrolls, so a row never loses its tier. The
 *  outer group clips with `overflow: clip`, which is not a scroll container,
 *  so `position: sticky` still tracks the viewport. */
function TierGroup({
  tier,
  count,
  children,
}: {
  tier: Priority
  count: number
  children: ReactNode
}) {
  const id = useId()
  return (
    <section className="card-group" aria-labelledby={id}>
      <div className="sticky top-bar z-10 flex items-center gap-2 bg-panel px-4 pb-1.5 pt-3">
        <span aria-hidden className={`h-2 w-2 shrink-0 rounded-pill ${PRIORITY[tier].dot}`} />
        <h3 id={id} className="text-copy font-medium text-ink">
          {PRIORITY[tier].label}
        </h3>
        <span className="text-copy tabular-nums text-secondary">
          <span className="sr-only">, </span>
          {count}
          <span className="sr-only"> {count === 1 ? 'patient' : 'patients'}</span>
        </span>
      </div>
      <ListGroup embedded inset="avatar" aria-labelledby={id}>
        {children}
      </ListGroup>
    </section>
  )
}

/** The composer for a row's message step. Its own component so the
 *  completion hook is bound to the row's patient id. */
function WorklistComposer({
  patient,
  step,
  onClose,
}: {
  patient: WorklistRowWithStep
  step: NextStep
  onClose: () => void
}) {
  const complete = useCompleteNextStep(patient.id)
  const phone = step.action.tel ?? null
  return (
    <MessageComposerModal
      patientId={patient.id}
      patientName={patient.name}
      phone={phone}
      prefill={step.action.prefill ?? ''}
      onClose={onClose}
      onSent={(r) =>
        complete.mutate({
          key: step.key,
          result: { message_id: r.message?.id ?? null, status: r.status },
        })
      }
    />
  )
}

/** Row grid (R4). At ≥1024px five fixed columns, so names, reasons, actions
 *  and times each share one x:
 *
 *    [avatar 32] [name 196] [reason 1fr] [action 288] [time 136]
 *
 *  At the 1080px worklist cap the reason keeps ~348px; 288 fits a step
 *  capsule plus "Send now", and 136 fits "Yesterday · 10:27 PM".
 *
 *  Narrower, the action and time wrap under the reason. The row is an <li>;
 *  the patient name is its only link, stretched over the row, and the action
 *  controls sit above that overlay. Nothing interactive nests in the <a>. */
const ROW_GRID = [
  'grid items-center gap-x-3 gap-y-2',
  "grid-cols-[32px_minmax(0,1fr)_auto] [grid-template-areas:'av_id_tm'_'._rs_rs'_'._ac_ac']",
  "lg:grid-cols-[32px_196px_minmax(0,1fr)_288px_136px] lg:[grid-template-areas:'av_id_rs_ac_tm']",
].join(' ')

function WorklistRow({
  patient: p,
  rise,
  onMessage,
}: {
  patient: WorklistRowWithStep
  /** Rise delay in ms on the first load; null once the intro is over. */
  rise: number | null
  onMessage: (step: NextStep) => void
}) {
  const high = p.priority === 'high'
  const step = p.next_step && p.next_step.state.status === 'open' ? p.next_step : null
  const procedure = p.procedure_display.replace(/\s*\(.*\)$/, '')
  // "D6" means post-op day six, which says nothing true about a patient who
  // never had an operation.
  const day = p.postop_day == null ? null : p.mode === 'general' ? `${p.postop_day}d` : `D${p.postop_day}`
  // Low confidence is a muted meta line, never a chip, and only when the
  // reason does not already say it.
  const showConfidence =
    p.data_confidence.level !== 'high' && !/confidence/i.test(p.reason)

  // `.row-risk-high` carries the tint and flips secondary text to --body
  // (R8: dark muted on the risk tint is 3.698, body 5.013).
  // Interaction-state guards (secondary text must hold 4.5:1 while the row
  // is hovered or pressed):
  //  - pressed row (--hairline fill): muted is 4.260 light / 3.655 dark, so
  //    it flips to --body (5.705 / 4.955);
  //  - dark high-risk hover (--risk-high-tint-strong #45353C): body is 4.444,
  //    so it lifts to n-300 (7.397).
  const stateGuard = high
    ? 'dark:hover:[--text-secondary:var(--n-300)]'
    : 'active:[--text-secondary:var(--body)]'
  return (
    <li
      className={`card-row ${high ? 'row-risk-high' : ''} ${stateGuard} ${ROW_GRID} ${rise != null ? 'rise' : ''}`}
      style={rise != null ? ({ '--rise-delay': `${rise}ms` } as CSSProperties) : undefined}
    >
      <span className="flex [grid-area:av]">
        <Avatar name={p.name} tier={p.priority} />
      </span>

      <div className="min-w-0 [grid-area:id]">
        <Link
          to={`/patients/${p.id}`}
          className="stretched-link block truncate text-copy-lg font-medium text-ink"
        >
          {p.name}
          {high && <span className="sr-only">, high risk</span>}
        </Link>
        <p className="meta mt-0.5 truncate">
          {procedure}
          {day && (
            <>
              <span aria-hidden> · </span>
              <span className="sr-only">, </span>
              <span className="tabular-nums">{day}</span>
            </>
          )}
        </p>
      </div>

      <div className="min-w-0 [grid-area:rs]">
        <p className="line-clamp-2 text-copy text-ink lg:line-clamp-1 lg:block lg:truncate" title={p.reason}>
          {p.reason}
        </p>
        {showConfidence && (
          <p className="mt-0.5 truncate">
            <ConfidenceChip level={p.data_confidence.level} variant="meta" />
          </p>
        )}
      </div>

      <div className="flex min-w-0 items-center gap-1 [grid-area:ac] empty:hidden">
        {step && (
          <RowAction patientId={p.id} step={step} canText={p.can_text} high={high} onMessage={onMessage} />
        )}
      </div>

      <div className="min-w-0 text-right [grid-area:tm]">
        <p className="meta truncate font-medium tabular-nums">{relativeTime(p.last_checkin_at)}</p>
        <p className="meta mt-0.5 truncate">{p.assigned_provider.name}</p>
      </div>
    </li>
  )
}

const ACTION_ICON = {
  message: MessageSquare,
  assign_tasks: ClipboardList,
  send_checkin: Send,
  escalate: TriangleAlert,
  call: Phone,
  open: ExternalLink,
  acknowledge: CheckCheck,
} as const satisfies Record<NextStepActionType, unknown>

/** The row's ONE capsule, labelled with the next step itself (R4), plus at
 *  most one plain text button beside it for the step's direct shortcut:
 *
 *    message       [Nudge the device sync] opens the composer   · Send now
 *    call (tel)    [Call the patient today] tel: link            · Log call
 *    call (no tel) [Call the patient today] opens the chart      · Log call
 *    escalate      [Escalate …] danger capsule, executes
 *    open          [step] navigates and marks it done
 *    other         [step] executes (assign, check-in, reviewed)
 *
 *  "Send now" stays a ONE-click plain button; the clinical workflow is
 *  unchanged. On the high-risk row the capsule is panel-filled (R1), since
 *  the row already wears the risk tint. */
function RowAction({
  patientId,
  step,
  canText,
  high,
  onMessage,
}: {
  patientId: string
  step: NextStep
  canText: boolean
  high: boolean
  onMessage: (step: NextStep) => void
}) {
  const navigate = useNavigate()
  const toast = useToast()
  const execute = useExecuteNextStep(patientId)
  const complete = useCompleteNextStep(patientId)
  const type = step.action.type
  const Icon = ACTION_ICON[type] ?? CheckCheck
  const busy = execute.isPending || complete.isPending
  const danger = type === 'escalate'
  const capsule = `${
    danger ? (high ? 'btn-danger-on-tint' : 'btn-danger') : high ? 'btn-on-tint' : 'btn-tinted'
  } btn-sm above-stretch min-w-0 max-w-full`
  const plain = 'btn-plain btn-sm above-stretch shrink-0'
  const tel = type === 'call' ? step.action.tel ?? null : null

  const runExecute = () =>
    execute.mutate(
      { key: step.key },
      {
        onSuccess: (r) => {
          // A check-in for a patient with no phone comes back as a tokenized
          // link; put it on the clipboard so the toast is actionable.
          const url = (r.result as Record<string, unknown> | null)?.url
          if (typeof url === 'string' && url) void navigator.clipboard?.writeText(url).catch(() => {})
          toast(resultToast(step, r.result), danger ? 'warning' : 'success')
        },
        onError: (err) => toast(`${step.title} failed — ${err.message}`, 'warning'),
      },
    )

  const onPrimary = (e: MouseEvent) => {
    e.stopPropagation()
    if (type === 'message') return onMessage(step)
    if (type === 'call') {
      // No number on file: the chart is where one gets added.
      navigate(`/patients/${patientId}`)
      return
    }
    if (type === 'open') {
      const target = step.action.target ?? ''
      navigate(`/patients/${patientId}`)
      complete.mutate({ key: step.key, result: { target } })
      return
    }
    runExecute()
  }

  const sendNow = (e: MouseEvent) => {
    e.stopPropagation()
    execute.mutate(
      { key: step.key },
      {
        onSuccess: () => toast('Sent as drafted', 'success'),
        onError: (err) => toast(`Could not send — ${err.message}`, 'warning'),
      },
    )
  }

  const label = (
    <>
      <Icon aria-hidden />
      <span className="truncate">{busy ? 'Working…' : step.title}</span>
    </>
  )
  const hint = step.detail || step.title
  // A check-in the patient can't receive by text is handed over as a link.
  const primaryName =
    type === 'send_checkin' && !canText ? `${step.title} (opens a check-in link to copy)` : undefined

  return (
    <>
      {tel ? (
        <a href={`tel:${tel}`} className={capsule} title={`Call ${tel}`}>
          {label}
        </a>
      ) : (
        <button
          type="button"
          className={capsule}
          disabled={busy}
          onClick={onPrimary}
          title={hint}
          aria-label={primaryName}
        >
          {label}
        </button>
      )}
      {type === 'message' && step.action.prefill && (
        <button
          type="button"
          className={plain}
          disabled={busy}
          onClick={sendNow}
          title="Send the drafted text as-is"
        >
          Send now
        </button>
      )}
      {type === 'call' && (
        <button
          type="button"
          className={plain}
          disabled={busy}
          onClick={(e) => {
            e.stopPropagation()
            runExecute()
          }}
        >
          Log call
        </button>
      )}
    </>
  )
}

// Mirrors NextSteps.tsx's toast copy (that helper is not exported).
function resultToast(step: NextStep, result: Record<string, unknown> | null): string {
  const sms = (result?.sms as { sent?: boolean } | undefined)?.sent
  switch (step.action.type) {
    case 'assign_tasks': {
      const n = Array.isArray(result?.task_ids) ? result.task_ids.length : null
      return `${n != null ? `${n} task${n === 1 ? '' : 's'}` : 'Tasks'} assigned${sms ? ' — texted' : ''}`
    }
    case 'send_checkin':
      if (sms) return 'Check-in sent by text'
      return typeof result?.url === 'string'
        ? `Check-in link ready — copied: ${result.url}`
        : 'Check-in created — waiting in the app'
    case 'escalate':
      return 'Escalated — care team notified'
    case 'call':
      return 'Call logged'
    case 'acknowledge':
      return 'Marked reviewed'
    default:
      return `Done — ${step.title}`
  }
}
