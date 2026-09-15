import {
  CheckCheck,
  ClipboardList,
  ExternalLink,
  MessageSquare,
  Phone,
  Send,
  TriangleAlert,
} from 'lucide-react'
import { useState, type MouseEvent } from 'react'
import type { NextStep, NextStepActionType } from '../../../api/plan'
import {
  useCompleteNextStep,
  useDismissNextStep,
  useExecuteNextStep,
  useNextSteps,
} from '../../../api/plan'
import type { MessagePatientResult, SuggestedAction } from '../../../api/types'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay, SkeletonLine } from '../../../components/Skeleton'
import { useToast } from '../../../components/Toast'
import { relativeTime } from '../../../lib/format'
import { URGENCY } from '../../../lib/risk'
import MessageComposerModal from './MessageComposerModal'
import { titlesOverlap } from './planCopy'

const ACTION = {
  message: { label: 'Message', icon: MessageSquare },
  assign_tasks: { label: 'Assign', icon: ClipboardList },
  send_checkin: { label: 'Send check-in', icon: Send },
  escalate: { label: 'Escalate', icon: TriangleAlert },
  call: { label: 'Log call', icon: Phone },
  open: { label: 'Open', icon: ExternalLink },
  acknowledge: { label: 'Mark reviewed', icon: CheckCheck },
} as const satisfies Record<NextStepActionType, unknown>

function stepActionLabel(step: NextStep, canText: boolean): string {
  // "Open check-in link" is the honest label only when no text can carry it.
  if (step.action.type === 'send_checkin' && !canText) return 'Open check-in link'
  return ACTION[step.action.type]?.label ?? 'Do it'
}

/** "Recommended next steps" — the rules-based planner's ranked list, each
 *  row executable in one click (two for a message: it opens the composer
 *  pre-filled, and the send is logged back as the step's completion). The
 *  AI's suggested-actions wording is shown only under a step whose title it
 *  overlaps; it never becomes a button of its own. */
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

  return (
    <>
      <SectionCard
        title="Recommended next steps"
        aside={
          steps.data?.generated_at ? (
            <span className="font-mono text-[11px] font-medium tabular-nums text-faint">
              {relativeTime(steps.data.generated_at)}
            </span>
          ) : undefined
        }
      >
        <RefreshOverlay show={refreshing} />

        {steps.isLoading && (
          <div className="space-y-3">
            <SkeletonLine className="h-4 w-2/3" />
            <SkeletonLine className="h-4 w-1/2" />
          </div>
        )}

        {!planner && (
          // The planner is not answering: keep the AI's suggestions visible
          // as text, clearly labelled as wording rather than actions.
          <ul className="divide-y divide-line">
            {aiActions.map((a, i) => (
              <li key={i} className="flex items-start gap-3 py-2.5 first:pt-0 last:pb-0">
                <span className={`chip mt-0.5 shrink-0 uppercase tracking-[.03em] ${URGENCY[a.urgency]?.pill ?? URGENCY.routine.pill}`}>
                  {URGENCY[a.urgency]?.label ?? 'Routine'}
                </span>
                <span>
                  <span className="block text-[13.5px] font-semibold text-ink">{a.title}</span>
                  {a.detail && (
                    <span className="mt-0.5 block text-[12.5px] font-medium leading-snug text-muted">{a.detail}</span>
                  )}
                </span>
              </li>
            ))}
            {aiActions.length === 0 && (
              <li className="text-[12.5px] font-medium text-muted">No next steps are available yet.</li>
            )}
          </ul>
        )}

        {planner && list.length > 0 && (
          <ul className="divide-y divide-line">
            {list.map((s) => {
              const done = s.state.status !== 'open'
              const wording = aiActions.find((a) => titlesOverlap(a.title, s.title))
              return (
                <li key={s.key} className={`py-3 first:pt-0 last:pb-0 ${done ? 'opacity-60' : ''}`}>
                  <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
                    <span className={`chip mt-0.5 shrink-0 uppercase tracking-[.03em] ${URGENCY[s.urgency]?.pill ?? URGENCY.routine.pill}`}>
                      {URGENCY[s.urgency]?.label ?? 'Routine'}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13.5px] font-semibold tracking-[-.01em] text-ink">{s.title}</p>
                      {s.detail && (
                        <p className="mt-0.5 text-[12.5px] font-medium leading-snug text-muted">{s.detail}</p>
                      )}
                      {(s.source?.length > 0 || s.clicks) && (
                        <div className="mt-1.5 flex flex-wrap items-center gap-1">
                          {s.source?.map((src) => (
                            <span key={src} className="chip bg-soft font-mono text-faint">{src}</span>
                          ))}
                          {s.clicks && (
                            <span className="text-[10.5px] font-medium text-faint">
                              · {s.clicks === 1 ? 'one click' : 'two clicks'}
                            </span>
                          )}
                        </div>
                      )}
                      {wording && (
                        <p className="mt-1 text-[11.5px] font-medium italic leading-snug text-faint">
                          AI wording · {wording.title}
                          {wording.detail ? ` — ${wording.detail}` : ''}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                      {done ? (
                        <span className="text-[11.5px] font-medium text-muted">
                          {s.state.status === 'done' ? 'Done' : 'Dismissed'}
                          {s.state.executed_at && <> · {relativeTime(s.state.executed_at)}</>}
                        </span>
                      ) : (
                        <>
                          <NextStepButton
                            patientId={patientId}
                            step={s}
                            phone={phone}
                            canText={canText}
                            onMessage={setComposer}
                            onOpen={onOpen}
                          />
                          <button
                            type="button"
                            className="cursor-pointer rounded-btn px-2 py-1 text-[11.5px] font-medium text-muted transition-colors duration-150 hover:bg-soft hover:text-ink disabled:opacity-50"
                            disabled={dismiss.isPending}
                            onClick={() =>
                              dismiss.mutate(s.key, {
                                onSuccess: () => toast('Hidden for now', 'info'),
                                onError: () => toast('Could not dismiss — try again', 'warning'),
                              })
                            }
                          >
                            Not now
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </li>
              )
            })}
          </ul>
        )}

        {planner && list.length > 0 && (
          <p className="mt-2.5 border-t border-line pt-2 text-[11px] font-medium leading-[1.5] text-faint">
            Steps are rules-based — every button does exactly what it says. Executed steps stay
            listed as done and are not re-suggested for a few days.
          </p>
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

/** The step's primary action. `compact` is the worklist row's variant: a
 *  small button that never lets the click reach the row's Link. */
export function NextStepButton({
  patientId,
  step,
  phone,
  canText,
  compact = false,
  onMessage,
  onOpen,
}: {
  patientId: string
  step: NextStep
  phone: string | null
  canText?: boolean
  compact?: boolean
  onMessage: (step: NextStep) => void
  onOpen: (target: string, step: NextStep) => void
}) {
  const toast = useToast()
  const execute = useExecuteNextStep(patientId)
  const complete = useCompleteNextStep(patientId)
  const type = step.action.type
  const meta = ACTION[type] ?? ACTION.acknowledge
  const Icon = meta.icon
  const label = stepActionLabel(step, canText ?? phone != null)
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

  const cls = compact
    ? 'qa-btn !px-2 !py-1 text-[11.5px]'
    : 'qa-btn'
  const tel = type === 'call' ? step.action.tel ?? phone : null

  return (
    <span className="inline-flex items-center gap-1.5">
      {tel && (
        <a
          href={`tel:${tel}`}
          onClick={(e) => e.stopPropagation()}
          className={`${cls} text-brand`}
          title={`Call ${tel}`}
        >
          <Phone size={compact ? 11 : 13} /> Call
        </a>
      )}
      <button type="button" className={cls} disabled={busy} onClick={run} title={step.detail}>
        <Icon size={compact ? 11 : 13} className={type === 'escalate' ? 'text-risk-high' : 'text-brand'} />
        {busy ? 'Working…' : label}
      </button>
      {compact && type === 'message' && step.action.prefill && (
        <button
          type="button"
          className={`${cls} text-muted`}
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
