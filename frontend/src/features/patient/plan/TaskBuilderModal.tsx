import { ClipboardList, Plus, Search, Sparkles, Star, Wand2, Zap } from 'lucide-react'
import { useId, useMemo, useState, type ReactNode } from 'react'
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
import EmptyState from '../../../components/EmptyState'
import ListRow, { ListGroup } from '../../../components/ListRow'
import Modal from '../../../components/Modal'
import SegmentedControl from '../../../components/SegmentedControl'
import Tile from '../../../components/Tile'
import { useToast } from '../../../components/Toast'
import DraftRowEditor from './DraftRowEditor'
import {
  blankDraft,
  draftFromTemplate,
  normalizeDraft,
  phaseLabel,
  taskKindTile,
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
 *  list that becomes N of their tasks (plus one summary text) on Assign.
 *
 *  App anatomy: plain sentence-case section labels (no rules), a tinted
 *  one-press check-in card, gray quick-pick capsules, the library as an
 *  inset-hairline list with the app's task-kind tiles, and an EmptyState for
 *  an empty draft list. Secondary text is `text-secondary` (--body inside the
 *  Modal; dark --muted and --disabled-ink both fail on the overlay panel). */
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
  const uid = useId()
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
        const waiting = r.reused ? `${first} already had today’s check-in waiting` : `Daily check-in is in ${first}'s app`
        if (r.sms.sent) toast(`${waiting} — and texted`, 'success')
        else if (!r.sms.attempted) toast(`${waiting} — not texted, no phone on file`, 'info')
        else toast(`${waiting} — the text didn’t go through (${r.sms.detail})`, 'warning')
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
          else toast(`${tasks} — the text didn’t go through (${r.delivery?.detail || 'not sent'})`, 'warning')
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
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      {/* Disabled text stays --body: --disabled-ink is 3.655:1 on the dark
          overlay panel, and the reason it is off is information. */}
      <label
        title={textHint}
        className={`inline-flex min-h-9 items-center gap-2 text-copy ${
          canText ? 'cursor-pointer text-ink' : 'cursor-not-allowed text-secondary'
        }`}
      >
        <input
          type="checkbox"
          className="h-4 w-4 accent-brand disabled:cursor-not-allowed"
          checked={notify && canText}
          disabled={!canText}
          onChange={(e) => setNotify(e.target.checked)}
        />
        <span>
          Text {first} the plan
          {!canText && <span className="meta ml-1.5">· {textHint}</span>}
        </span>
      </label>
      <button
        type="button"
        className="btn-filled ml-auto"
        disabled={!ready || assign.isPending}
        onClick={submit}
      >
        {assign.isPending
          ? 'Assigning…'
          : `Assign ${drafts.length} task${drafts.length === 1 ? '' : 's'}`}
      </button>
    </div>
  )

  const onPin = (t: TaskTemplate) => pin.mutate({ id: t.id, pinned: !t.pinned })

  return (
    <Modal
      size="xl"
      title={`Build ${first}'s care plan`}
      eyebrow={pathway?.name ? <p className="meta mb-0.5">Pathway · {pathway.name}</p> : undefined}
      onClose={onClose}
      footer={footer}
    >
      <div className="space-y-6 pt-1">
        {/* 1. Quick picks */}
        <Section id={`${uid}-quick`} label="Quick picks">
          <button
            type="button"
            onClick={sendCheckin}
            disabled={checkin.isPending}
            title={`Sends ${first} today’s check-in now — in the app, and by text if they have a number`}
            className="on-tint mb-3 flex w-full cursor-pointer items-center gap-3 rounded-surface bg-brand-tint px-4 py-3 text-left transition-[background-color,transform] duration-state ease-apple hover:bg-brand-tint-strong focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:scale-press disabled:cursor-not-allowed disabled:bg-disabled-fill"
          >
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-control bg-brand text-on-brand">
              <Zap aria-hidden size={20} className={checkin.isPending ? 'motion-safe:animate-pulse' : undefined} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-copy-lg font-medium text-on-brand-tint">
                {checkin.isPending ? 'Sending…' : 'Send daily check-in'}
              </span>
              <span className="block text-copy text-on-brand-tint">
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
                className="btn-gray btn-sm"
              >
                <Plus aria-hidden /> {t.title}
              </button>
            ))}
            {library.isLoading && <span className="meta">Loading the library…</span>}
            {library.isError && <span className="meta">The library is not available yet.</span>}
            {!library.isLoading && !library.isError && pinned.length === 0 && (
              <span className="meta">Pin templates in the library to see them here.</span>
            )}
            <button
              type="button"
              onClick={runSuggest}
              disabled={suggest.isPending}
              className="btn-tinted btn-sm ml-auto"
            >
              <Sparkles aria-hidden className={suggest.isPending ? 'motion-safe:animate-spin' : undefined} />
              {suggest.isPending ? 'Thinking…' : `Suggest for ${first}`}
            </button>
          </div>
        </Section>

        {/* 2. Describe the plan */}
        <Section
          id={`${uid}-describe`}
          label="Describe the plan"
          aside={provider ? <AIAttribution kind="task builder" provider={provider} /> : undefined}
        >
          <div className="relative">
            <Wand2
              aria-hidden
              size={18}
              className={`pointer-events-none absolute left-4 top-3.5 text-cat-teal-ink ${
                build.isPending ? 'motion-safe:animate-pulse' : ''
              }`}
            />
            <textarea
              rows={3}
              aria-labelledby={`${uid}-describe`}
              className={`field resize-y rounded-surface py-3 pl-11 pr-4 text-copy-lg ${
                build.isPending ? 'shimmer text-transparent' : ''
              }`}
              placeholder="e.g. Three short walks a day, log knee pain morning and evening, one flight of stairs by next week"
              value={describe}
              disabled={build.isPending}
              onChange={(e) => setDescribe(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) runBuild()
              }}
            />
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
            <p className="meta px-1">Drafts are editable — nothing is assigned until you confirm.</p>
            <button
              type="button"
              className="btn-tinted btn-sm"
              disabled={!describe.trim() || build.isPending}
              onClick={runBuild}
            >
              <Wand2 aria-hidden />
              {build.isPending ? 'Building…' : 'Build with AI'}
            </button>
          </div>
        </Section>

        {/* 3. Library */}
        <Section id={`${uid}-library`} label="Library">
          <div className="flex flex-wrap items-center gap-2">
            <label className="relative min-w-[180px] flex-1">
              <span className="sr-only">Search the task library</span>
              <Search
                aria-hidden
                size={16}
                className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-secondary"
              />
              <input
                type="search"
                className="field rounded-pill pl-10"
                placeholder="Search tasks"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <SegmentedControl<PhaseFilter>
              options={PHASE_FILTERS}
              value={phase}
              onChange={setPhase}
              size="sm"
              role="radiogroup"
              aria-label="Phase"
              className="flex-none"
            />
          </div>

          <div className="mt-3 max-h-80 overflow-y-auto rounded-surface border border-line">
            {groups.length === 0 && elsewhere.length === 0 && (
              <p className="meta px-4 py-4">
                {library.isLoading
                  ? 'Loading…'
                  : library.isError
                    ? 'The library is not available yet.'
                    : 'No templates match.'}
              </p>
            )}
            {groups.map((g) => (
              <div key={g.key} className="pt-2">
                <h4
                  id={`${uid}-uc-${g.key}`}
                  className="px-4 text-label font-medium tracking-label text-secondary"
                >
                  {g.label}
                </h4>
                <ListGroup embedded inset="tile" aria-labelledby={`${uid}-uc-${g.key}`}>
                  {g.items.map((t) => (
                    <LibraryRow key={t.id} t={t} onAdd={() => addTemplate(t)} onPin={() => onPin(t)} />
                  ))}
                </ListGroup>
              </div>
            ))}
            {elsewhere.length > 0 && (
              <div className="px-4 py-2">
                <Disclosure label="Other pathways" hint={`${elsewhere.length}`}>
                  <ListGroup embedded inset="tile" aria-label="Other pathways" className="-mx-4">
                    {elsewhere.map((t) => (
                      <LibraryRow
                        key={t.id}
                        t={t}
                        showUseCase
                        onAdd={() => addTemplate(t)}
                        onPin={() => onPin(t)}
                      />
                    ))}
                  </ListGroup>
                </Disclosure>
              </div>
            )}
          </div>
        </Section>

        {/* 4. Draft list */}
        <Section
          id={`${uid}-drafts`}
          label={
            <>
              Draft list
              {drafts.length > 0 && (
                <span className="ml-1.5 tabular-nums">· {drafts.length}</span>
              )}
            </>
          }
          aside={
            <button
              type="button"
              className="btn-plain btn-sm -mr-2"
              onClick={() => append([blankDraft(kinds)])}
            >
              <Plus aria-hidden /> Custom task
            </button>
          }
        >
          {drafts.length === 0 ? (
            <EmptyState
              variant="inline"
              family="violet"
              icon={<ClipboardList />}
              title="Nothing drafted yet"
              className="rounded-surface bg-soft !py-6"
            >
              Pick a quick pick, describe the plan, or add from the library.
            </EmptyState>
          ) : (
            <ol className="space-y-3" aria-labelledby={`${uid}-drafts`}>
              {drafts.map((d, i) => (
                <li key={i}>
                  <DraftRowEditor
                    index={i}
                    value={d}
                    kinds={kinds}
                    onChange={(next) => update(i, next)}
                    onRemove={() => remove(i)}
                  />
                </li>
              ))}
            </ol>
          )}
          {drafts.length > MAX_ITEMS && (
            <p className="mt-2 px-1 text-label font-medium text-risk-med-ink">
              One assignment takes at most {MAX_ITEMS} tasks — remove {drafts.length - MAX_ITEMS}.
            </p>
          )}
        </Section>
      </div>
    </Modal>
  )
}

/** A builder section: a plain sentence-case label (no rule under it, the
 *  app's grouped-list header) with an optional right-hand slot. */
function Section({
  id,
  label,
  aside,
  children,
}: {
  id: string
  label: ReactNode
  aside?: ReactNode
  children: ReactNode
}) {
  return (
    <section aria-labelledby={id}>
      <div className="mb-2 flex min-h-8 items-center justify-between gap-3 px-1">
        <h3 id={id} className="text-copy font-medium text-secondary">
          {label}
        </h3>
        {aside}
      </div>
      {children}
    </section>
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
  const kind = taskKindTile(t.task_kind)
  const Icon = kind.icon
  const meta = [
    showUseCase ? ucLabel(t.use_case) : null,
    phaseLabel(t.phase),
    t.verified_by || 'self-report',
    t.clinical_target || null,
  ]
    .filter(Boolean)
    .join(' · ')
  // The title is the row's one stretched button (it adds the template); the
  // pin is the only other control and sits above it.
  return (
    <ListRow
      compact
      leading={<Tile family={kind.family} icon={<Icon />} />}
      title={t.title}
      onClick={onAdd}
      linkLabel={`Add ${t.title}`}
      subtitle={<span title={t.clinical_target || t.why}>{meta}</span>}
      aside={<Plus aria-hidden size={16} className="text-brand-ink" />}
      trailing={
        <button
          type="button"
          onClick={onPin}
          aria-pressed={t.pinned}
          aria-label={t.pinned ? `Unpin ${t.title}` : `Pin ${t.title} as a quick pick`}
          title={t.pinned ? 'Unpin from quick picks' : 'Pin as a quick pick'}
          className={`btn-icon btn-sm ${t.pinned ? '!text-brand-ink' : ''}`}
        >
          <Star aria-hidden fill={t.pinned ? 'currentColor' : 'none'} />
        </button>
      }
    />
  )
}
