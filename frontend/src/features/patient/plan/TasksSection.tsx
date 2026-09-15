import { ClipboardList, Sparkles, Wand2 } from 'lucide-react'
import { useState } from 'react'
import type { CarePathway } from '../../../api/care'
import type { DraftTask, PlanTask } from '../../../api/plan'
import {
  firstNameOf,
  useDraftTasks,
  useEndPlanTask,
  usePatientPlan,
  useRecordPlanTask,
  useSuggestPlan,
  useTaskTemplates,
} from '../../../api/plan'
import Disclosure from '../../../components/Disclosure'
import InlineReadout from '../../../components/InlineReadout'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay, SkeletonLine } from '../../../components/Skeleton'
import { useToast } from '../../../components/Toast'
import { shortDate } from '../../../lib/format'
import TaskBuilderModal from './TaskBuilderModal'
import {
  RECORD_DOT,
  TASK_STATUS,
  phaseLabel,
  planRates,
  scheduleLabel,
  taskPhase,
  taskSchedule,
  todayIso,
  verifiedByLabel,
} from './planCopy'

type Builder = { drafts?: DraftTask[]; provider?: string | null } | null

/** "Care plan" — the patient's tasks as our `/plan` view sees them: their
 *  lifecycle status, our verification kind and the last 14 days of records. */
export default function TasksSection({
  patientId,
  patientName,
  pathway,
  phone,
  smsAvailable,
  refreshing,
}: {
  patientId: string
  patientName: string
  pathway: CarePathway | null | undefined
  phone: string | null
  smsAvailable: boolean
  refreshing: boolean
}) {
  const toast = useToast()
  const first = firstNameOf(patientName)
  const plan = usePatientPlan(patientId)
  const library = useTaskTemplates()
  const kinds = library.data?.kinds
  const suggest = useSuggestPlan(patientId)
  const build = useDraftTasks()
  const endTask = useEndPlanTask(patientId)
  const record = useRecordPlanTask(patientId)
  const [builder, setBuilder] = useState<Builder>(null)
  const [prompt, setPrompt] = useState('')

  const tasks = plan.data?.tasks ?? []
  const active = tasks.filter((t) => t.active !== false)
  const ended = tasks.filter((t) => t.active === false)
  const rates = planRates(tasks)
  const summary = plan.data?.summary

  const runSuggest = () =>
    suggest.mutate(undefined, {
      onSuccess: (r) => setBuilder({ drafts: r.tasks, provider: r.provider }),
      onError: () => toast('Suggestions are not available — try again', 'warning'),
    })

  /** One sentence in, a reviewable draft list out. The AI structures the
   *  prompt into tasks; nothing is assigned until the clinician confirms in
   *  the builder, which opens pre-filled. */
  const runBuild = () => {
    const text = prompt.trim()
    if (!text || build.isPending) return
    build.mutate(
      { text, patient_id: patientId, pathway: pathway?.key },
      {
        onSuccess: (r) => {
          if (r.tasks.length === 0) {
            toast('Nothing recognisable in that — try naming the activity, e.g. "walk twice a day"', 'info')
            return
          }
          setPrompt('')
          setBuilder({
            drafts: r.tasks.map((t) => ({ ...t, assigned_by: 'ai' as const })),
            provider: r.provider,
          })
        },
        onError: () => toast('The builder could not draft that — try again', 'warning'),
      },
    )
  }

  const markDone = (t: PlanTask) =>
    record.mutate(
      { taskId: t.id, date: todayIso(), status: 'self_attested' },
      {
        onSuccess: () => toast(`Marked "${t.title}" done today`, 'success'),
        onError: () => toast('Could not record that — try again', 'warning'),
      },
    )

  const end = (t: PlanTask) =>
    endTask.mutate(t.id, {
      onSuccess: () => toast(`Ended "${t.title}"`, 'info'),
      onError: () => toast('Could not end the task — try again', 'warning'),
    })

  const assignButton = (
    <button type="button" className="qa-btn" onClick={() => setBuilder({})}>
      <ClipboardList size={13} className="text-brand" /> Assign tasks
    </button>
  )

  return (
    <>
      <SectionCard title="Care plan" aside={assignButton}>
        <RefreshOverlay show={refreshing} />

        <form
          className="mb-3 flex flex-wrap items-center gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            runBuild()
          }}
        >
          <label className="relative min-w-[220px] flex-1">
            <Wand2
              size={13}
              className={`pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-brand ${build.isPending ? 'animate-pulse' : ''}`}
            />
            <input
              className={`field pl-8 ${build.isPending ? 'shimmer text-transparent' : ''}`}
              placeholder={`Tell ${first} what to do, e.g. walk twice a day and log pain each evening`}
              value={prompt}
              disabled={build.isPending}
              onChange={(e) => setPrompt(e.target.value)}
              aria-label="Describe tasks to build with AI"
            />
          </label>
          <button
            type="submit"
            className="qa-btn"
            disabled={!prompt.trim() || build.isPending}
            title="Turn this sentence into tasks you can review and assign"
          >
            <Wand2 size={13} className="text-brand" />
            {build.isPending ? 'Building…' : 'Build with AI'}
          </button>
        </form>

        {plan.isLoading && (
          <div className="space-y-3">
            <SkeletonLine className="h-5 w-1/2" />
            <SkeletonLine className="h-3.5 w-full" />
            <SkeletonLine className="h-3.5 w-2/3" />
          </div>
        )}

        {plan.isError && (
          <p className="text-[12.5px] font-medium text-muted">
            The care plan is not available for this patient yet.
          </p>
        )}

        {plan.data && tasks.length === 0 && (
          <div className="rounded-row border border-dashed border-line px-4 py-6 text-center">
            <p className="text-[13.5px] font-semibold tracking-[-.01em] text-ink">No care plan yet.</p>
            <p className="mt-1 text-[12.5px] font-medium text-faint">
              Let the builder pick a starting set for {first}'s pathway, or assign tasks by hand.
            </p>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
              <button
                type="button"
                className="qa-btn"
                disabled={suggest.isPending}
                onClick={runSuggest}
              >
                <Sparkles size={13} className={`text-brand ${suggest.isPending ? 'animate-spin' : ''}`} />
                {suggest.isPending ? 'Thinking…' : 'Suggest a plan'}
              </button>
            </div>
          </div>
        )}

        {plan.data && tasks.length > 0 && (
          <>
            <InlineReadout
              className="mb-3"
              items={[
                {
                  key: 'active',
                  label: `active task${active.length === 1 ? '' : 's'}`,
                  value: String(summary?.active ?? active.length),
                },
                {
                  key: 'verified',
                  label: 'verified',
                  value: rates.verifiedPct == null ? '—' : `${rates.verifiedPct}%`,
                  hint: 'by data',
                },
                {
                  key: 'incl',
                  label: 'incl. self-report',
                  value: rates.inclSelfPct == null ? '—' : `${rates.inclSelfPct}%`,
                },
              ]}
            />

            <ul className="divide-y divide-line">
              {active.map((t) => (
                <TaskRow
                  key={t.id}
                  t={t}
                  verifiedBy={verifiedByLabel(kinds, t)}
                  onDone={() => markDone(t)}
                  onEnd={() => end(t)}
                  busy={record.isPending || endTask.isPending}
                />
              ))}
            </ul>

            {ended.length > 0 && (
              <div className="mt-2 border-t border-line">
                <Disclosure label="Ended tasks" hint={`${ended.length}`}>
                  <ul className="divide-y divide-line opacity-70">
                    {ended.map((t) => (
                      <TaskRow key={t.id} t={t} verifiedBy={verifiedByLabel(kinds, t)} />
                    ))}
                  </ul>
                </Disclosure>
              </div>
            )}

            <p className="mt-2.5 border-t border-line pt-2 text-[11px] font-medium leading-[1.5] text-faint">
              Solid dots are days confirmed by device data; faded dots are the patient's own report;
              rings are missed days. The patient sees task titles and reasons only — never these
              numbers.
            </p>
          </>
        )}
      </SectionCard>

      {builder && (
        <TaskBuilderModal
          patientId={patientId}
          patientName={patientName}
          pathway={pathway}
          phone={phone}
          smsAvailable={smsAvailable}
          initialDrafts={builder.drafts}
          initialProvider={builder.provider}
          onClose={() => setBuilder(null)}
        />
      )}
    </>
  )
}

function TaskRow({
  t,
  verifiedBy,
  onDone,
  onEnd,
  busy = false,
}: {
  t: PlanTask
  verifiedBy: string
  onDone?: () => void
  onEnd?: () => void
  busy?: boolean
}) {
  const status = TASK_STATUS[t.status] ?? TASK_STATUS.pending
  const rate = t.verified_rate ?? t.rate
  const strip = padStrip(t.last14 ?? [])
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1">
          <p className="text-[13.5px] font-semibold tracking-[-.01em] text-ink">{t.title}</p>
          {t.why && <p className="mt-0.5 text-[12.5px] font-medium leading-snug text-muted">{t.why}</p>}
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span className="chip bg-soft text-muted">{verifiedBy}</span>
            <span className="chip bg-soft text-muted">{scheduleLabel(taskSchedule(t))}</span>
            <span className="chip bg-soft text-muted">{phaseLabel(taskPhase(t))}</span>
            <span className={`chip ${status.pill}`}>{status.label}</span>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <div
            className="flex items-center gap-1.5"
            role="img"
            aria-label={`Last 14 days${rate != null ? `, ${Math.round(rate * 100)}% done` : ''}`}
          >
            {strip.map((r, i) => (
              <span
                key={i}
                title={r.date ? `${shortDate(r.date)} · ${RECORD_DOT[r.status].label}` : undefined}
                className={RECORD_DOT[r.status].cls}
              />
            ))}
          </div>
          <span className="w-10 text-right font-mono text-[15px] font-medium tabular-nums tracking-tight text-ink">
            {rate == null ? '—' : `${Math.round(rate * 100)}%`}
          </span>
        </div>
      </div>
      {(onDone || onEnd) && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {onDone && (
            <button
              type="button"
              className="cursor-pointer rounded-btn px-2 py-1 text-[11.5px] font-medium text-brand transition-colors duration-150 hover:bg-brand-tint disabled:opacity-50"
              disabled={busy}
              onClick={onDone}
              title="Records that the patient did this today (counts as self-reported, not device-verified)"
            >
              Mark done today
            </button>
          )}
          {onEnd && (
            <button
              type="button"
              className="cursor-pointer rounded-btn px-2 py-1 text-[11.5px] font-medium text-muted transition-colors duration-150 hover:bg-soft hover:text-ink disabled:opacity-50"
              disabled={busy}
              onClick={onEnd}
            >
              End task
            </button>
          )}
        </div>
      )}
    </li>
  )
}

/** Always 14 cells, oldest first: the server sends what it has and the
 *  strip pads with invisible days so rows align. */
function padStrip(records: PlanTask['last14']) {
  const sorted = [...records].sort((a, b) => a.date.localeCompare(b.date)).slice(-14)
  const pad = Math.max(0, 14 - sorted.length)
  return [
    ...Array.from({ length: pad }, () => ({ date: '', status: 'none' as const })),
    ...sorted,
  ]
}
