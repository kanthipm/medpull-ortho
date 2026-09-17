import { ArrowUp, Ban, CircleCheck, ClipboardList, Plus, Sparkles, Wand2 } from 'lucide-react'
import { useId, useState } from 'react'
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
import EmptyState from '../../../components/EmptyState'
import InlineReadout from '../../../components/InlineReadout'
import ListRow, { ListGroup } from '../../../components/ListRow'
import { Menu } from '../../../components/Menu'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay, SkeletonLine } from '../../../components/Skeleton'
import Tile from '../../../components/Tile'
import { useToast } from '../../../components/Toast'
import { shortDate } from '../../../lib/format'
import TaskBuilderModal from './TaskBuilderModal'
import {
  RECORD_DOT,
  TASK_STATUS,
  phaseLabel,
  planRates,
  scheduleLabel,
  taskKindTile,
  taskPhase,
  taskSchedule,
  todayIso,
  verifiedByLabel,
} from './planCopy'

type Builder = { drafts?: DraftTask[]; provider?: string | null } | null

/** "Care plan" — the patient's tasks as our `/plan` view sees them: their
 *  lifecycle status, our verification kind and the last 14 days of records.
 *
 *  App anatomy: an ask-style capsule field that drafts tasks with AI, a
 *  single-baseline readout, and an inset-hairline list whose rows carry the
 *  app's category tile (TasksView's mapping). Neutral facts (verified by,
 *  schedule, phase) are one .meta line; the lifecycle status is the only
 *  chip. Row actions live in a top-layer "…" menu (R5). */
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
  const promptId = useId()

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

  const busy = record.isPending || endTask.isPending

  return (
    <>
      <SectionCard
        flush
        title="Care plan"
        action={
          <button type="button" className="btn-plain btn-sm" onClick={() => setBuilder({})}>
            <ClipboardList aria-hidden /> Assign tasks
          </button>
        }
      >
        <RefreshOverlay show={refreshing} />

        {/* The ask field: the app's rounded capsule, a wand at the left and a
            round send button at the right. */}
        <form
          className="px-5 pb-3"
          onSubmit={(e) => {
            e.preventDefault()
            runBuild()
          }}
        >
          <div className="relative">
            <label htmlFor={promptId} className="sr-only">
              Describe tasks to build with AI
            </label>
            <Wand2
              aria-hidden
              size={18}
              className={`pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-cat-teal-ink ${
                build.isPending ? 'motion-safe:animate-pulse' : ''
              }`}
            />
            <input
              id={promptId}
              className={`field field-pill text-copy ${build.isPending ? 'shimmer text-transparent' : ''}`}
              placeholder={`Tell ${first} what to do, e.g. walk twice a day and log pain each evening`}
              value={prompt}
              disabled={build.isPending}
              onChange={(e) => setPrompt(e.target.value)}
            />
            {/* Wrapped: the press scale sets `transform`, which would undo a
                translate on the button itself. */}
            <span className="absolute right-2 top-1/2 flex -translate-y-1/2">
              <button
                type="submit"
                className="btn-send"
                disabled={!prompt.trim() || build.isPending}
                aria-label={build.isPending ? 'Building tasks…' : 'Build tasks with AI'}
                title="Turn this sentence into tasks you can review and assign"
              >
                <ArrowUp aria-hidden size={16} />
              </button>
            </span>
          </div>
          <p className="meta mt-1.5 px-4">
            Drafts open in the builder for review — nothing is assigned until you confirm.
          </p>
        </form>

        {plan.isLoading && (
          <div className="space-y-3 px-5 pb-5 pt-1">
            <SkeletonLine className="h-5 w-1/2" />
            <SkeletonLine className="h-3.5 w-full" />
            <SkeletonLine className="h-3.5 w-2/3" />
          </div>
        )}

        {plan.isError && (
          <p className="px-5 pb-5 text-copy text-secondary">
            The care plan is not available for this patient yet.
          </p>
        )}

        {plan.data && tasks.length === 0 && (
          <EmptyState
            variant="inline"
            family="violet"
            icon={<ClipboardList />}
            title="No care plan yet"
            action={
              <>
                <button
                  type="button"
                  className="btn-tinted"
                  disabled={suggest.isPending}
                  onClick={runSuggest}
                >
                  <Sparkles
                    aria-hidden
                    size={16}
                    className={suggest.isPending ? 'motion-safe:animate-spin' : undefined}
                  />
                  {suggest.isPending ? 'Thinking…' : 'Suggest a plan'}
                </button>
                <button type="button" className="btn-gray" onClick={() => setBuilder({})}>
                  <Plus aria-hidden size={16} /> Assign by hand
                </button>
              </>
            }
          >
            Let the builder pick a starting set for {first}'s pathway, or assign tasks by hand.
          </EmptyState>
        )}

        {plan.data && tasks.length > 0 && (
          <>
            <InlineReadout
              className="px-5 pb-2 pt-1"
              items={[
                {
                  key: 'active',
                  label: `active task${active.length === 1 ? '' : 's'}`,
                  value: String(summary?.active ?? active.length),
                },
                {
                  key: 'verified',
                  label: 'verified by data',
                  value: rates.verifiedPct == null ? '—' : `${rates.verifiedPct}%`,
                },
                {
                  key: 'incl',
                  label: 'incl. self-report',
                  value: rates.inclSelfPct == null ? '—' : `${rates.inclSelfPct}%`,
                },
              ]}
            />

            <ListGroup embedded inset="tile" aria-label="Active tasks">
              {active.map((t) => (
                <TaskRow
                  key={t.id}
                  t={t}
                  verifiedBy={verifiedByLabel(kinds, t)}
                  onDone={() => markDone(t)}
                  onEnd={() => end(t)}
                  busy={busy}
                />
              ))}
            </ListGroup>

            {ended.length > 0 && (
              <div className="px-5 pt-1">
                <Disclosure label="Ended tasks" hint={`${ended.length}`}>
                  <ListGroup embedded inset="tile" aria-label="Ended tasks" className="-mx-5">
                    {ended.map((t) => (
                      <TaskRow key={t.id} t={t} verifiedBy={verifiedByLabel(kinds, t)} />
                    ))}
                  </ListGroup>
                </Disclosure>
              </div>
            )}

            <Legend />
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

/** The strip's key, drawn with the strip's own marks (shape, not only hue). */
function Legend() {
  const keys = ['verified', 'self_attested', 'missed'] as const
  return (
    <div className="px-5 pb-5 pt-3">
      <ul className="meta flex flex-wrap items-center gap-x-4 gap-y-1">
        {keys.map((k) => (
          <li key={k} className="inline-flex items-center gap-1.5">
            <span aria-hidden className={`inline-block ${RECORD_DOT[k].cls}`} />
            {RECORD_DOT[k].label}
          </li>
        ))}
      </ul>
      <p className="meta mt-1">
        Each strip is the last 14 days, oldest first. The patient sees task titles and reasons only — never these numbers.
      </p>
    </div>
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
  const kind = taskKindTile(t.task_kind)
  const Icon = kind.icon
  const ended = t.active === false
  const pct = rate == null ? '—' : `${Math.round(rate * 100)}%`

  return (
    <ListRow
      leading={<Tile family={kind.family} icon={<Icon />} />}
      title={t.title}
      wrapTitle
      titleClassName={ended ? '!text-secondary' : ''}
      subtitle={t.why || undefined}
      subtitleLines={2}
      meta={[verifiedBy, scheduleLabel(taskSchedule(t)), phaseLabel(taskPhase(t))].join(' · ')}
      aside={<span className={`chip ${status.pill}`}>{status.label}</span>}
      trailing={
        onDone || onEnd ? (
          <Menu
            label={`Actions for ${t.title}`}
            items={[
              ...(onDone
                ? [
                    {
                      key: 'done',
                      label: 'Mark done today',
                      description: 'Counts as self-reported, not device-verified',
                      icon: <CircleCheck aria-hidden />,
                      disabled: busy,
                      onSelect: onDone,
                    },
                  ]
                : []),
              ...(onDone && onEnd ? [{ key: 'sep', separator: true as const }] : []),
              ...(onEnd
                ? [
                    {
                      key: 'end',
                      label: 'End task',
                      icon: <Ban aria-hidden />,
                      danger: true,
                      disabled: busy,
                      onSelect: onEnd,
                    },
                  ]
                : []),
            ]}
          />
        ) : undefined
      }
    >
      {/* The 14-day strip and its rate: an opaque row on the panel. */}
      <div className="flex items-center gap-3">
        <div
          className="flex items-center gap-1.5"
          role="img"
          aria-label={`Last 14 days${rate != null ? `, ${pct} done` : ''}`}
        >
          {strip.map((r, i) => (
            <span
              key={i}
              title={r.date ? `${shortDate(r.date)} · ${RECORD_DOT[r.status].label}` : undefined}
              className={RECORD_DOT[r.status].cls}
            />
          ))}
        </div>
        <span className="text-copy font-medium tabular-nums text-ink">{pct}</span>
      </div>
    </ListRow>
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
