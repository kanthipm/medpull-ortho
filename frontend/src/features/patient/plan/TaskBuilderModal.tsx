import { Plus, Search, Sparkles, Star, Wand2, Zap } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { CarePathway } from '../../../api/care'
import type { DraftTask, TaskPhase, TaskTemplate } from '../../../api/plan'
import {
  firstNameOf,
  useAssignPlan,
  useDraftTasks,
  useSendDailyCheckin,
  useSuggestPlan,
  useTaskTemplates,
  useUpdateTaskTemplate,
} from '../../../api/plan'
import AIAttribution from '../../../components/AIAttribution'
import Disclosure from '../../../components/Disclosure'
import SegmentedControl from '../../../components/SegmentedControl'
import { useToast } from '../../../components/Toast'
import DraftRowEditor from './DraftRowEditor'
import PlanModal from './PlanModal'
import {
  blankDraft,
  draftFromTemplate,
  normalizeDraft,
  phaseLabel,
  templateFitsPathway,
  toPlanItem,
  ucLabel,
} from './planCopy'

type PhaseFilter = 'all' | TaskPhase
const PHASE_FILTERS: { key: PhaseFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'early', label: 'Early' },
  { key: 'mid', label: 'Mid' },
  { key: 'late', label: 'Late' },
  { key: 'ongoing', label: 'Ongoing' },
]

/** The care-plan builder: quick picks, a free-text plan the AI structures,
 *  the library grouped by use case for this pathway, and the editable draft
 *  list that becomes N of their tasks (plus one summary text) on Assign. */
export default function TaskBuilderModal({
  patientId,
  patientName,
  pathway,
  phone,
  smsAvailable,
  initialDrafts,
  initialProvider,
  onClose,
}: {
  patientId: string
  patientName: string
  pathway: CarePathway | null | undefined
  phone: string | null
  smsAvailable: boolean
  /** Rows to start with — the section's "Suggest a plan" hands its drafts in. */
  initialDrafts?: DraftTask[]
  initialProvider?: string | null
  onClose: () => void
}) {
  const toast = useToast()
  const first = firstNameOf(patientName)
  const library = useTaskTemplates()
  const kinds = useMemo(() => library.data?.kinds ?? [], [library.data])
  const templates = useMemo(
    () => (library.data?.templates ?? []).filter((t) => !t.archived),
    [library.data],
  )

  const [drafts, setDrafts] = useState<DraftTask[]>(() =>
    (initialDrafts ?? []).map((d) => normalizeDraft(d, library.data?.kinds)),
  )
  const [provider, setProvider] = useState<string | null>(initialProvider ?? null)
  const [describe, setDescribe] = useState('')
  const [query, setQuery] = useState('')
  const [phase, setPhase] = useState<PhaseFilter>('all')
  const canText = smsAvailable && !!phone
  const [notify, setNotify] = useState(canText)

  const suggest = useSuggestPlan(patientId)
  const build = useDraftTasks()
  const pin = useUpdateTaskTemplate()
  const assign = useAssignPlan(patientId)
  const checkin = useSendDailyCheckin(patientId)

  /** One press, no draft list: today's check-in into the patient's app, and a
   *  text telling them it's there. The text is the part that can fail — a
   *  number Sendblue won't deliver to, or no number at all — and the toast
   *  says so plainly, because the check-in itself has landed either way and
   *  a warning that reads like nothing happened would be a lie. */
  const sendCheckin = () => {
    if (checkin.isPending) return
    checkin.mutate(undefined, {
      onSuccess: (r) => {
        const waiting = r.reused ? `${first} already had today's check-in waiting` : `Daily check-in is in ${first}'s app`
        if (r.sms.sent) toast(`${waiting} — and texted`, 'success')
        else if (!r.sms.attempted) toast(`${waiting} — not texted, no phone on file`, 'info')
        else toast(`${waiting} — the text didn't go through (${r.sms.detail})`, 'warning')
        onClose()
      },
      onError: (e) => toast(`Could not send the check-in — ${e.message}`, 'warning'),
    })
  }

  const append = (rows: Partial<DraftTask>[]) =>
    setDrafts((d) => [...d, ...rows.map((r) => normalizeDraft(r, kinds))])
  const addTemplate = (t: TaskTemplate) => append([draftFromTemplate(t)])
  const update = (i: number, next: DraftTask) =>
    setDrafts((d) => d.map((row, j) => (j === i ? next : row)))
  const remove = (i: number) => setDrafts((d) => d.filter((_, j) => j !== i))

  const runSuggest = () =>
    suggest.mutate(undefined, {
      onSuccess: (r) => {
        append(r.tasks.map((t) => ({ ...t, assigned_by: 'ai' as const })))
        setProvider(r.provider)
        if (r.tasks.length === 0) toast(`No suggestions for ${first} right now`, 'info')
      },
      onError: () => toast('Suggestions are not available — try again', 'warning'),
    })

  const runBuild = () => {
    const text = describe.trim()
    if (!text) return
    build.mutate(
      { text, patient_id: patientId, pathway: pathway?.key },
      {
        onSuccess: (r) => {
          append(r.tasks.map((t) => ({ ...t, assigned_by: 'ai' as const })))
          setProvider(r.provider)
          setDescribe('')
          if (r.tasks.length === 0) toast('Nothing recognisable in that plan — add rows by hand', 'info')
        },
        onError: () => toast('The builder could not draft that — try again', 'warning'),
      },
    )
  }

  const pinned = templates.filter((t) => t.pinned)
  const q = query.trim().toLowerCase()
  const matches = (t: TaskTemplate) =>
    (phase === 'all' || t.phase === phase) &&
    (!q ||
      t.title.toLowerCase().includes(q) ||
      t.why.toLowerCase().includes(q) ||
      (t.clinical_target ?? '').toLowerCase().includes(q) ||
      (t.key ?? '').toLowerCase().includes(q))
  const here = templates.filter((t) => matches(t) && templateFitsPathway(t, pathway))
  const elsewhere = templates.filter((t) => matches(t) && !templateFitsPathway(t, pathway))
  const groups = groupByUseCase(here)

  // The API takes at most 12 items per assignment.
  const MAX_ITEMS = 12
  const ready =
    drafts.length > 0 && drafts.length <= MAX_ITEMS && drafts.every((d) => d.title.trim())
  const submit = () => {
    if (!ready) return
    assign.mutate(
      { items: drafts.map(toPlanItem), notify: notify && canText },
      {
        onSuccess: (r) => {
          const n = r.tasks?.length ?? drafts.length
          const tasks = `${n} task${n === 1 ? '' : 's'} assigned`
          if (r.delivery?.sent) toast(`${tasks} — texted to ${first}`, 'success')
          else if (!phone) toast(`${tasks} — nothing sent (no phone on file)`, 'info')
          else if (!notify || !canText) toast(`${tasks} — in the app only`, 'info')
          else toast(`${tasks} — the text didn't go through (${r.delivery?.detail || 'not sent'})`, 'warning')
          onClose()
        },
        onError: (e) => toast(`Tasks could not be assigned — ${e.message}`, 'warning'),
      },
    )
  }

  const textHint = !phone
    ? 'No phone on file for this patient'
    : !smsAvailable
      ? 'Texting is not available right now'
      : `Sends one text summarising the plan to ${first}`

  const footer = (
    <div className="flex flex-wrap items-center gap-3">
      <label
        title={textHint}
        className={`inline-flex items-center gap-2 text-[12.5px] font-medium ${
          canText ? 'cursor-pointer text-body' : 'cursor-not-allowed text-faint'
        }`}
      >
        <input
          type="checkbox"
          className="h-3.5 w-3.5 accent-[rgb(var(--brand))]"
          checked={notify && canText}
          disabled={!canText}
          onChange={(e) => setNotify(e.target.checked)}
        />
        Text {first} the plan
        {!canText && <span className="text-[11px] text-faint">· {textHint}</span>}
      </label>
      <button
        type="button"
        className="btn-primary sm:ml-auto sm:w-auto"
        disabled={!ready || assign.isPending}
        onClick={submit}
      >
        {assign.isPending
          ? 'Assigning…'
          : `Assign ${drafts.length} task${drafts.length === 1 ? '' : 's'}`}
      </button>
    </div>
  )

  return (
    <PlanModal
      size="xl"
      title={`Build ${first}'s care plan`}
      eyebrow={
        pathway?.name ? (
          <span className="micro mb-0.5 block">Pathway · {pathway.name}</span>
        ) : undefined
      }
      onClose={onClose}
      footer={footer}
    >
      <div className="space-y-5">
        {/* 1. Quick picks */}
        <section>
          <p className="zone-label mb-2">Quick picks</p>
          <button
            type="button"
            onClick={sendCheckin}
            disabled={checkin.isPending}
            title={`Sends ${first} today's check-in now — in the app, and by text if they have a number`}
            className="mb-2 flex w-full cursor-pointer items-center gap-2 rounded-row border border-brand/30 bg-brand-tint px-3 py-2.5 text-left transition-colors duration-150 hover:border-brand/50 disabled:opacity-60"
          >
            <Zap size={15} className={`shrink-0 text-brand ${checkin.isPending ? 'animate-pulse' : ''}`} />
            <span className="min-w-0 flex-1">
              <span className="block text-[13.5px] font-semibold tracking-[-.01em] text-brand">
                {checkin.isPending ? 'Sending…' : 'Send daily check-in'}
              </span>
              <span className="block text-[11.5px] font-medium text-muted">
                Goes straight to {first} — no draft list, nothing else to confirm
              </span>
            </span>
          </button>
          <div className="flex flex-wrap items-center gap-1.5">
            {pinned.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => addTemplate(t)}
                title={t.clinical_target || t.why}
                className="chip cursor-pointer border border-line bg-panel text-body transition-colors duration-150 hover:border-brand/35 hover:bg-brand-tint hover:text-brand"
              >
                <Plus size={10} /> {t.title}
              </button>
            ))}
            {library.isLoading && <span className="text-[11.5px] text-faint">Loading the library…</span>}
            {library.isError && (
              <span className="text-[11.5px] text-faint">The library is not available yet.</span>
            )}
            {!library.isLoading && !library.isError && pinned.length === 0 && (
              <span className="text-[11.5px] text-faint">Pin templates in the library to see them here.</span>
            )}
            <button
              type="button"
              onClick={runSuggest}
              disabled={suggest.isPending}
              className="qa-btn ml-auto"
            >
              <Sparkles size={13} className={`text-brand ${suggest.isPending ? 'animate-spin' : ''}`} />
              {suggest.isPending ? 'Thinking…' : `Suggest for ${first}`}
            </button>
          </div>
        </section>

        {/* 2. Describe the plan */}
        <section>
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <p className="zone-label flex-1">Describe the plan</p>
            {provider && <AIAttribution kind="task builder" provider={provider} />}
          </div>
          <textarea
            rows={3}
            className={`field ${build.isPending ? 'shimmer text-transparent' : ''}`}
            placeholder="e.g. Three short walks a day, log knee pain morning and evening, one flight of stairs by next week"
            value={describe}
            disabled={build.isPending}
            onChange={(e) => setDescribe(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) runBuild()
            }}
          />
          <div className="mt-2 flex items-center justify-between gap-3">
            <p className="text-[11px] font-medium text-faint">
              Drafts are editable — nothing is assigned until you confirm.
            </p>
            <button
              type="button"
              className="qa-btn"
              disabled={!describe.trim() || build.isPending}
              onClick={runBuild}
            >
              <Wand2 size={13} className="text-brand" />
              {build.isPending ? 'Building…' : 'Build with AI'}
            </button>
          </div>
        </section>

        {/* 3. Library */}
        <section>
          <p className="zone-label mb-2">Library</p>
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative min-w-[180px] flex-1">
              <Search size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
              <input
                className="field pl-8"
                placeholder="Search tasks"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Search the task library"
              />
            </label>
            <SegmentedControl<PhaseFilter>
              options={PHASE_FILTERS}
              value={phase}
              onChange={setPhase}
              aria-label="Phase"
              className="flex-none"
            />
          </div>

          <div className="mt-2.5 max-h-72 space-y-3 overflow-y-auto rounded-row border border-line p-2.5">
            {groups.length === 0 && elsewhere.length === 0 && (
              <p className="px-1 py-2 text-[12px] font-medium text-faint">
                {library.isLoading
                  ? 'Loading…'
                  : library.isError
                    ? 'The library is not available yet.'
                    : 'No templates match.'}
              </p>
            )}
            {groups.map((g) => (
              <div key={g.key}>
                <p className="micro mb-1 px-1">{g.label}</p>
                <ul className="divide-y divide-line">
                  {g.items.map((t) => (
                    <LibraryRow
                      key={t.id}
                      t={t}
                      onAdd={() => addTemplate(t)}
                      onPin={() => pin.mutate({ id: t.id, pinned: !t.pinned })}
                    />
                  ))}
                </ul>
              </div>
            ))}
            {elsewhere.length > 0 && (
              <Disclosure label="Other pathways" hint={`${elsewhere.length}`}>
                <ul className="divide-y divide-line">
                  {elsewhere.map((t) => (
                    <LibraryRow
                      key={t.id}
                      t={t}
                      showUseCase
                      onAdd={() => addTemplate(t)}
                      onPin={() => pin.mutate({ id: t.id, pinned: !t.pinned })}
                    />
                  ))}
                </ul>
              </Disclosure>
            )}
          </div>
        </section>

        {/* 4. Draft list */}
        <section>
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <p className="zone-label flex-1">
              Draft list
              <span className="font-mono normal-case tracking-normal">{drafts.length}</span>
            </p>
            <button
              type="button"
              className="cursor-pointer rounded-btn px-2 py-1 text-[12px] font-medium text-brand transition-colors duration-150 hover:bg-brand-tint"
              onClick={() => append([blankDraft(kinds)])}
            >
              + Custom task
            </button>
          </div>
          {drafts.length === 0 ? (
            <p className="rounded-row border border-dashed border-line px-3 py-4 text-center text-[12.5px] font-medium text-faint">
              Nothing drafted yet — pick a quick pick, describe the plan, or add from the library.
            </p>
          ) : (
            <div className="space-y-2.5">
              {drafts.map((d, i) => (
                <DraftRowEditor
                  key={i}
                  index={i}
                  value={d}
                  kinds={kinds}
                  onChange={(next) => update(i, next)}
                  onRemove={() => remove(i)}
                />
              ))}
            </div>
          )}
        </section>
      </div>
    </PlanModal>
  )
}

function groupByUseCase(items: TaskTemplate[]) {
  const map = new Map<string, TaskTemplate[]>()
  for (const t of items) {
    const key = t.use_case || 'custom'
    const list = map.get(key)
    if (list) list.push(t)
    else map.set(key, [t])
  }
  return [...map.entries()]
    .sort(([a], [b]) => ucOrder(a) - ucOrder(b))
    .map(([key, list]) => ({ key, label: ucLabel(key), items: list }))
}

function ucOrder(key: string): number {
  const m = /^UC(\d+)$/i.exec(key)
  return m ? parseInt(m[1], 10) : 999
}

function LibraryRow({
  t,
  showUseCase = false,
  onAdd,
  onPin,
}: {
  t: TaskTemplate
  showUseCase?: boolean
  onAdd: () => void
  onPin: () => void
}) {
  return (
    <li className="flex items-center gap-2 py-1.5 first:pt-0 last:pb-0">
      <button
        type="button"
        onClick={onAdd}
        title={t.clinical_target || t.why}
        className="group min-w-0 flex-1 cursor-pointer rounded-btn px-1.5 py-1 text-left transition-colors duration-150 hover:bg-soft"
      >
        <span className="flex items-center gap-1.5">
          <Plus size={12} className="shrink-0 text-faint transition-colors group-hover:text-brand" />
          <span className="truncate text-[13px] font-medium text-ink">{t.title}</span>
        </span>
        <span className="mt-0.5 block truncate pl-[18px] text-[11px] font-medium text-faint">
          {showUseCase && <>{ucLabel(t.use_case)} · </>}
          {phaseLabel(t.phase)} · {t.verified_by || 'self-report'}
          {t.clinical_target && <> · {t.clinical_target}</>}
        </span>
      </button>
      <button
        type="button"
        onClick={onPin}
        aria-pressed={t.pinned}
        aria-label={t.pinned ? 'Unpin' : 'Pin as quick pick'}
        title={t.pinned ? 'Unpin from quick picks' : 'Pin as a quick pick'}
        className={`grid h-7 w-7 shrink-0 cursor-pointer place-items-center rounded-btn transition-colors duration-150 hover:bg-soft ${
          t.pinned ? 'text-brand' : 'text-faint hover:text-ink'
        }`}
      >
        <Star size={13} fill={t.pinned ? 'currentColor' : 'none'} />
      </button>
    </li>
  )
}
