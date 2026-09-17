import {
  CheckCheck,
  ClipboardList,
  ExternalLink,
  MessageSquare,
  Phone,
  Send,
  Sparkles,
  TriangleAlert,
  X,
} from 'lucide-react'
import { useId, useState, type MouseEvent, type ReactNode } from 'react'
import type { NextStep, NextStepActionType } from '../../../api/plan'
import {
  useCompleteNextStep,
  useDismissNextStep,
  useExecuteNextStep,
  useNextSteps,
} from '../../../api/plan'
import type { MessagePatientResult, SuggestedAction } from '../../../api/types'
import ListRow, { ListGroup } from '../../../components/ListRow'
import { Tooltip } from '../../../components/Menu'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay, SkeletonLine } from '../../../components/Skeleton'
import Tile, { type TileFamily } from '../../../components/Tile'
import { useToast } from '../../../components/Toast'
import { relativeTime } from '../../../lib/format'
import { URGENCY, type Urgency } from '../../../lib/risk'
import { sourceLabel } from '../../../lib/sourceLabels'
import MessageComposerModal from './MessageComposerModal'
import { shortStepLabel, titlesOverlap } from './planCopy'

/** Verb label, leading tile and icon per action. Tile families follow
 *  components/Tile: blue = communication, risk-high = escalate only,
 *  violet = plan, indigo = rules-based review, teal = done/acknowledge. */
const ACTION = {
  message: { label: 'Message', icon: MessageSquare, family: 'blue' },
  assign_tasks: { label: 'Assign', icon: ClipboardList, family: 'violet' },
  send_checkin: { label: 'Send check-in', icon: Send, family: 'blue' },
  escalate: { label: 'Escalate', icon: TriangleAlert, family: 'risk-high' },
  call: { label: 'Log call', icon: Phone, family: 'blue' },
  open: { label: 'Open', icon: ExternalLink, family: 'indigo' },
  acknowledge: { label: 'Mark reviewed', icon: CheckCheck, family: 'teal' },
} as const satisfies Record<
  NextStepActionType,
  { label: string; icon: typeof Phone; family: TileFamily }
>

/** Codes the header already states: the one risk pill says the composite
 *  level, so "Composite risk high" under a step only restates it. */
const HEADER_CODES = /^COMPOSITE_/

/** A step's evidence as one line, minus what the header already says. */
function evidenceOf(step: NextStep): string {
  return (step.source ?? [])
    .filter((src) => !HEADER_CODES.test(src))
    .map((src) => sourceLabel(src))
    .join(' · ')
}

const URGENCY_ORDER: Urgency[] = ['today', 'this_week', 'routine']

function stepActionLabel(step: NextStep, canText: boolean): string {
  // "Open check-in link" is the honest label only when no text can carry it.
  if (step.action.type === 'send_checkin' && !canText) return 'Open check-in link'
  return ACTION[step.action.type]?.label ?? 'Do it'
}

/** "Next steps" — the rules-based planner's ranked list, grouped under
 *  "Today" / "This week" subheaders (dot + word, R7) instead of a pill per
 *  row. Each row has ONE action capsule and an icon "Not now". A message
 *  step opens the composer pre-filled, and the send is logged back as the
 *  step's completion. The AI's suggested-actions wording is shown only under
 *  a step whose title it overlaps; it never becomes a button of its own. */
export default function NextSteps({
  patientId,
  patientName,
  surgeon,
  phone,
  canText,
  aiActions,
  refreshing,
  onOpen,
}: {
  patientId: string
  patientName: string
  surgeon?: string | null
  phone: string | null
  /** A text can reach this patient. Separate from `phone`, which is what a
   *  dial link needs: the worklist knows one without the other. */
  canText?: boolean
  aiActions: SuggestedAction[]
  refreshing: boolean
  /** `open` steps: "full_stats:M12" | "wearables" | "plan" | "messages". */
  onOpen: (target: string) => void
}) {
  const steps = useNextSteps(patientId)
  const dismiss = useDismissNextStep(patientId)
  const complete = useCompleteNextStep(patientId)
  const toast = useToast()
  const [composer, setComposer] = useState<NextStep | null>(null)

  const list = steps.data?.steps ?? []
  const planner = !steps.isError
  if (!steps.isLoading && planner && list.length === 0 && aiActions.length === 0) return null

  const grouped = groupByUrgency(list, (s) => s.urgency)
  const aiGrouped = groupByUrgency(aiActions, (a) => a.urgency)

  return (
    <>
      <SectionCard
        flush
        title="Next steps"
        aside={steps.data?.generated_at ? relativeTime(steps.data.generated_at) : undefined}
      >
        <RefreshOverlay show={refreshing} />

        {steps.isLoading && (
          <div className="space-y-3 px-4 pb-5 pt-1">
            <SkeletonLine className="h-4 w-2/3" />
            <SkeletonLine className="h-4 w-1/2" />
          </div>
        )}

        {!planner && (
          // The planner is not answering: keep the AI's suggestions visible
          // as text, clearly labelled as wording rather than actions.
          <div className="space-y-2">
            {aiGrouped.map(({ urgency, items }) => (
              <UrgencyGroup key={urgency} urgency={urgency}>
                {items.map((a, i) => (
                  <ListRow
                    key={i}
                    leading={<Tile family="teal" icon={<Sparkles />} />}
                    title={a.title}
                    wrapTitle
                    subtitle={a.detail || undefined}
                    subtitleLines={2}
                  />
                ))}
              </UrgencyGroup>
            ))}
            {aiActions.length === 0 && (
              <p className="meta px-4 pb-4">No next steps are available yet.</p>
            )}
            {aiActions.length > 0 && (
              <p className="meta px-4 pb-4 pt-2">
                The planner is unavailable, so these are the AI's suggestions as wording only.
              </p>
            )}
          </div>
        )}

        {planner && list.length > 0 && (
          <div className="space-y-2">
            {grouped.map(({ urgency, items }) => (
              <UrgencyGroup key={urgency} urgency={urgency}>
                {items.map((s, i) => {
                  const done = s.state.status !== 'open'
                  const wording = aiActions.find((a) => titlesOverlap(a.title, s.title))
                  const meta = ACTION[s.action.type] ?? ACTION.acknowledge
                  const Icon = meta.icon
                  // Consecutive steps from one finding share a detail; say it once.
                  const repeat = i > 0 && items[i - 1].detail === s.detail
                  // Evidence, said once per run (R7): a step that cites the same
                  // evidence as the one above it shows none, and the composite
                  // risk code is dropped because the header pill already says it.
                  const sources = evidenceOf(s)
                  const sourcesRepeat = i > 0 && evidenceOf(items[i - 1]) === sources
                  return (
                    <ListRow
                      key={s.key}
                      leading={
                        <Tile
                          family={done ? 'teal' : meta.family}
                          icon={done ? <CheckCheck /> : <Icon />}
                        />
                      }
                      title={s.title}
                      wrapTitle
                      titleClassName={done ? '!text-secondary' : ''}
                      subtitle={
                        s.detail && !repeat ? (
                          <span className="block max-w-[64ch]">{s.detail}</span>
                        ) : undefined
                      }
                      subtitleLines={2}
                      meta={
                        (sources && !sourcesRepeat) || wording ? (
                          <>
                            {sources && !sourcesRepeat && <span className="block">{sources}</span>}
                            {wording && (
                              <span className="block">
                                AI wording · {wording.title}
                                {wording.detail ? ` — ${wording.detail}` : ''}
                              </span>
                            )}
                          </>
                        ) : undefined
                      }
                      aside={
                        done ? (
                          <>
                            {s.state.status === 'done' ? 'Done' : 'Dismissed'}
                            {s.state.executed_at && <> · {relativeTime(s.state.executed_at)}</>}
                          </>
                        ) : undefined
                      }
                      trailing={
                        done ? undefined : (
                          <>
                            <NextStepButton
                              patientId={patientId}
                              step={s}
                              phone={phone}
                              canText={canText}
                              onMessage={setComposer}
                              onOpen={onOpen}
                            />
                            <Tooltip content="Not now">
                              <button
                                type="button"
                                className="btn-icon btn-sm"
                                aria-label={`Not now: ${s.title}`}
                                disabled={dismiss.isPending}
                                onClick={() =>
                                  dismiss.mutate(s.key, {
                                    onSuccess: () => toast('Hidden for now', 'info'),
                                    onError: () => toast('Could not dismiss — try again', 'warning'),
                                  })
                                }
                              >
                                <X />
                              </button>
                            </Tooltip>
                          </>
                        )
                      }
                    />
                  )
                })}
              </UrgencyGroup>
            ))}
            <p className="meta px-4 pb-4 pt-2">
              Steps are rules-based, and every button does exactly what it says. Done steps stay
              listed and are not suggested again for a few days.
            </p>
          </div>
        )}
      </SectionCard>

      {composer && (
        <MessageComposerModal
          patientId={patientId}
          patientName={patientName}
          surgeon={surgeon}
          phone={phone}
          prefill={composer.action.prefill ?? ''}
          onClose={() => setComposer(null)}
          onSent={(r: MessagePatientResult) =>
            complete.mutate({
              key: composer.key,
              result: { message_id: r.message?.id ?? null, status: r.status },
            })
          }
        />
      )}
    </>
  )
}

/** Buckets in Today → This week → Routine order; an unknown urgency is
 *  routine. The planner's rank order is kept inside each bucket. */
function groupByUrgency<T>(items: T[], key: (item: T) => Urgency | undefined) {
  const bucket = (item: T): Urgency => {
    const u = key(item)
    return u && u in URGENCY ? u : 'routine'
  }
  return URGENCY_ORDER.map((urgency) => ({
    urgency,
    items: items.filter((item) => bucket(item) === urgency),
  })).filter((g) => g.items.length > 0)
}

/** A subheader (dot + word; the word carries the meaning, R20) over an
 *  embedded inset-hairline list. */
function UrgencyGroup({ urgency, children }: { urgency: Urgency; children: ReactNode }) {
  const u = URGENCY[urgency]
  const id = useId()
  return (
    <div className="pt-1">
      <h3
        id={id}
        className="flex items-center gap-2 px-4 pb-0.5 text-label font-medium tracking-label text-secondary"
      >
        <span aria-hidden className={`h-2 w-2 shrink-0 rounded-pill ${u.dot}`} />
        {u.label}
      </h3>
      <ListGroup embedded inset="tile" aria-labelledby={id}>
        {children}
      </ListGroup>
    </div>
  )
}

/** The step's primary action: ONE capsule.
 *
 *  Patient page (default): a tinted capsule with the verb ("Message",
 *  "Log call"); escalate is the danger capsule.
 *
 *  Worklist (`compact`): R4. Pass `labelFromStep` so the capsule's label IS
 *  the step ("Nudge device sync", "Call today"), and `onTint` inside a
 *  risk-tinted row so the capsule is panel-filled (R1). A drafted message
 *  also gets "Send now" as a plain one-click text button — it stays in the
 *  row; the clinical workflow does not change.
 *
 *  Every control carries `.above-stretch`, so it sits above a row's
 *  stretched name link; none of them is ever nested inside that link. */
export function NextStepButton({
  patientId,
  step,
  phone,
  canText,
  compact = false,
  onTint = false,
  labelFromStep = false,
  onMessage,
  onOpen,
}: {
  patientId: string
  step: NextStep
  phone: string | null
  canText?: boolean
  /** The worklist row's variant: adds the one-click "Send now". */
  compact?: boolean
  /** Inside a tinted row: panel-filled capsules (R1). */
  onTint?: boolean
  /** Label the capsule with the step itself (R4). */
  labelFromStep?: boolean
  onMessage: (step: NextStep) => void
  onOpen: (target: string, step: NextStep) => void
}) {
  const toast = useToast()
  const execute = useExecuteNextStep(patientId)
  const complete = useCompleteNextStep(patientId)
  const type = step.action.type
  const meta = ACTION[type] ?? ACTION.acknowledge
  const Icon = meta.icon
  const textable = canText ?? phone != null
  const tel = type === 'call' ? step.action.tel ?? phone : null
  const verb = stepActionLabel(step, textable)
  const stepLabel = shortStepLabel(step, textable)
  const busy = execute.isPending || complete.isPending

  const run = (e: MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (type === 'message') return onMessage(step)
    if (type === 'open') {
      const target = step.action.target ?? ''
      onOpen(target, step)
      complete.mutate({ key: step.key, result: { target } })
      return
    }
    execute.mutate(
      { key: step.key },
      {
        onSuccess: (r) => {
          // A check-in for a patient with no phone comes back as a tokenized
          // link for the clinician to hand over; put it on the clipboard so
          // the toast is actionable rather than a URL to retype.
          const url = (r.result as Record<string, unknown> | null)?.url
          if (typeof url === 'string' && url) void navigator.clipboard?.writeText(url).catch(() => {})
          toast(resultToast(step, r.result), type === 'escalate' ? 'warning' : 'success')
        },
        onError: (err) => toast(`${step.title} failed — ${err.message}`, 'warning'),
      },
    )
  }

  const sendNow = (e: MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    execute.mutate(
      { key: step.key },
      {
        onSuccess: () => toast('Sent as drafted', 'success'),
        onError: (err) => toast(`Could not send — ${err.message}`, 'warning'),
      },
    )
  }

  const capsule =
    type === 'escalate'
      ? onTint
        ? 'btn-danger-on-tint'
        : 'btn-danger'
      : onTint
        ? 'btn-on-tint'
        : 'btn-tinted'
  const cls = `${capsule} btn-sm above-stretch max-w-[16rem]`
  const plain = 'btn-plain btn-sm above-stretch'

  // With a dial link, the capsule dials and "Log call" is the plain
  // follow-up; without one, the capsule logs the call.
  if (tel) {
    return (
      <span className="inline-flex items-center gap-1">
        <a
          href={`tel:${tel}`}
          onClick={(e) => e.stopPropagation()}
          className={cls}
          title={`Call ${tel}`}
        >
          <Phone aria-hidden />
          <span className="truncate">{labelFromStep ? stepLabel : 'Call'}</span>
        </a>
        <button type="button" className={plain} disabled={busy} onClick={run} title={step.detail}>
          {busy ? 'Working…' : 'Log call'}
        </button>
      </span>
    )
  }

  const label = labelFromStep && type !== 'call' ? stepLabel : verb
  return (
    <span className="inline-flex items-center gap-1">
      <button
        type="button"
        className={cls}
        disabled={busy}
        onClick={run}
        title={labelFromStep ? step.title : step.detail}
      >
        <Icon aria-hidden />
        <span className="truncate">{busy ? 'Working…' : label}</span>
      </button>
      {compact && type === 'message' && step.action.prefill && (
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
    </span>
  )
}

function resultToast(step: NextStep, result: Record<string, unknown> | null): string {
  const sms = (result?.sms as { sent?: boolean } | undefined)?.sent
  switch (step.action.type) {
    case 'assign_tasks': {
      const n = Array.isArray(result?.task_ids) ? result.task_ids.length : null
      return `${n != null ? `${n} task${n === 1 ? '' : 's'}` : 'Tasks'} assigned${sms ? ' — texted' : ''}`
    }
    case 'send_checkin':
      if (sms) return 'Check-in sent by text'
      // With no phone on file the server mints the tokenized link instead, so
      // the clinician has something to hand over. It used to be dropped.
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
