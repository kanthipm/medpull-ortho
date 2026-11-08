import { ArrowDown, ArrowUp, ChevronLeft, Eye, Film, Plus, Send, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { Exercise, HepOptions, Plan, PublishResult } from '../../api/hep'
import {
  useArchivePlan,
  useCreatePlan,
  useHepOptions,
  usePlan,
  usePublishPlan,
  useUpdatePlan,
} from '../../api/hep'
import { ApiError } from '../../api/client'
import EmptyState from '../../components/EmptyState'
import Modal from '../../components/Modal'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'
import { diagnosticWarning } from './hepCopy'
import LibraryPicker from './LibraryPicker'
import {
  doseLine,
  editable,
  itemFromExercise,
  itemFromPlan,
  planStatus,
  serialize,
  toItemBody,
  type EditorItem,
} from './planCopy'

const LABEL = 'mb-1 block px-1 text-label font-medium tracking-label text-secondary'

interface Draft {
  title: string
  notes: string
  patient_id: string | null
  assigned_by: string
  items: EditorItem[]
}

/** `/exercise-plans/new` and `/exercise-plans/:id` — build a home exercise
 *  plan: pick exercises from the library on the left, dose them in the tray
 *  on the right, save as a draft, preview what the patient will read, then
 *  publish. Publishing freezes the wording; the confirmation reports the
 *  plan's state and the patient's delivery separately. */
export default function PlanEditorPage() {
  const { id } = useParams()
  const planId = id && id !== 'new' ? Number(id) : null
  const plan = usePlan(planId)
  const options = useHepOptions()

  if (planId != null && plan.isLoading) {
    return (
      <div className="space-y-stack pt-2">
        <SkeletonCard lines={2} />
        <SkeletonCard rows={4} />
      </div>
    )
  }
  if (planId != null && (plan.isError || !plan.data)) {
    return (
      <EmptyState title="This plan couldn’t be opened." action={<Link to="/exercise-plans" className="btn-tinted">Back to plans</Link>}>
        It may have been removed, or the link is wrong.
      </EmptyState>
    )
  }
  if (!options.data) return <SkeletonCard rows={4} />
  return <Editor key={plan.data?.id ?? 'new'} plan={plan.data ?? null} options={options.data} />
}

function Editor({ plan, options }: { plan: Plan | null; options: HepOptions }) {
  const toast = useToast()
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const create = useCreatePlan()
  const update = useUpdatePlan()
  const publish = usePublishPlan()
  const archive = useArchivePlan()
  const canEdit = editable(plan)

  const [draft, setDraft] = useState<Draft>(() =>
    plan
      ? {
          title: plan.title,
          notes: plan.notes,
          patient_id: plan.patient?.id ?? null,
          assigned_by: plan.assigned_by,
          items: (plan.items ?? []).map(itemFromPlan),
        }
      : {
          title: 'Home exercise plan',
          notes: '',
          patient_id: params.get('patient'),
          assigned_by: options.care_team[0]?.id ?? 'provider',
          items: [],
        },
  )
  const [saved, setSaved] = useState(() => (plan ? serialize({
    title: plan.title, notes: plan.notes, patient_id: plan.patient?.id ?? null,
    assigned_by: plan.assigned_by, items: (plan.items ?? []).map(itemFromPlan),
  }) : ''))
  const dirty = serialize(draft) !== saved
  const [preview, setPreview] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [result, setResult] = useState<PublishResult | null>(null)

  // Leaving with unsaved work: the browser's own prompt, nothing custom.
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const set = <K extends keyof Draft>(key: K, v: Draft[K]) => setDraft((d) => ({ ...d, [key]: v }))
  const setItem = (index: number, next: EditorItem) =>
    setDraft((d) => ({ ...d, items: d.items.map((it, i) => (i === index ? next : it)) }))
  const move = (index: number, dir: -1 | 1) =>
    setDraft((d) => {
      const items = [...d.items]
      const j = index + dir
      if (j < 0 || j >= items.length) return d
      ;[items[index], items[j]] = [items[j], items[index]]
      return { ...d, items }
    })
  const remove = (index: number) => setDraft((d) => ({ ...d, items: d.items.filter((_, i) => i !== index) }))
  const add = (e: Exercise) => {
    if (draft.items.some((i) => i.exercise_id === e.id)) return
    if (draft.items.length >= options.max_items) {
      toast(`A plan holds at most ${options.max_items} exercises`, 'warning')
      return
    }
    set('items', [...draft.items, itemFromExercise(e)])
  }

  const onError = (e: unknown) => {
    if (e instanceof ApiError && e.status === 409) {
      toast('This plan changed elsewhere — reload to see the latest', 'warning')
      return
    }
    toast(`Could not save — ${(e as Error).message}`, 'warning')
  }

  const body = {
    title: draft.title.trim(),
    notes: draft.notes.trim(),
    patient_id: draft.patient_id,
    assigned_by: draft.assigned_by,
    items: draft.items.map(toItemBody),
    actor: draft.assigned_by,
  }

  /** Save, then hand the saved plan to `then` (publish needs the version). */
  const save = (then?: (p: Plan) => void) => {
    if (plan) {
      update.mutate(
        { id: plan.id, version: plan.version, ...body },
        {
          onSuccess: (p) => {
            setSaved(serialize(draft))
            if (then) then(p)
            else toast(plan.status === 'active' ? 'Plan revised' : 'Draft saved', 'success')
          },
          onError,
        },
      )
    } else {
      create.mutate(body, {
        onSuccess: (p) => {
          setSaved(serialize(draft))
          if (then) then(p)
          else {
            toast('Draft saved', 'success')
            navigate(`/exercise-plans/${p.id}`, { replace: true })
          }
        },
        onError,
      })
    }
  }

  const doPublish = () => {
    const run = (p: Plan) =>
      publish.mutate(
        { id: p.id, version: p.version, actor: draft.assigned_by },
        {
          onSuccess: (r) => {
            setConfirming(false)
            setResult(r)
            if (!plan) navigate(`/exercise-plans/${p.id}`, { replace: true })
          },
          onError: (e) => {
            setConfirming(false)
            onError(e)
          },
        },
      )
    if (dirty || !plan) save(run)
    else run(plan)
  }

  const saving = create.isPending || update.isPending || publish.isPending
  const patient = options.patients.find((p) => p.id === draft.patient_id) ?? null
  const chip = plan ? planStatus(plan.status) : planStatus('draft')
  const canPublish = plan?.status !== 'active' && draft.items.length > 0 && !!draft.patient_id
  const textWarn = diagnosticWarning(
    [draft.title, draft.notes, ...draft.items.flatMap((i) => [i.clinician_instructions, i.precautions_override])].join('\n'),
  )

  return (
    <div className="pb-28">
      <header data-hero className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <Link to="/exercise-plans" className="btn-plain-muted btn-sm -ml-2">
          <ChevronLeft size={16} /> Plans
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="display-title text-display text-ink">
            {plan ? (plan.patient ? `${plan.patient.name}’s plan` : 'Exercise plan') : 'New exercise plan'}
          </h1>
          <span className={`chip ${chip.pill}`}>{chip.label}</span>
          {plan?.published_at && <span className="meta">Published {relativeTime(plan.published_at)}</span>}
        </div>
        <p className="mt-3 max-w-[60ch] text-lede text-body">
          {plan?.status === 'active'
            ? 'This plan is live. Changes you save here update what the patient sees right away.'
            : 'Add exercises from the library, set the dose for each, and publish when it is ready.'}
        </p>
      </header>

      <div className="rise mt-8 grid gap-stack lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]" style={{ '--rise-delay': '80ms' } as CSSProperties}>
        <div className="space-y-stack">
          <SectionCard title="Plan details">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label htmlFor="plan-title" className={LABEL}>Title</label>
                <input id="plan-title" className="field" value={draft.title} maxLength={80} disabled={!canEdit}
                  onChange={(e) => set('title', e.target.value)} />
              </div>
              <div>
                <label htmlFor="plan-patient" className={LABEL}>Patient</label>
                <select id="plan-patient" className="field cursor-pointer" value={draft.patient_id ?? ''}
                  disabled={!canEdit || plan?.status === 'active'}
                  onChange={(e) => set('patient_id', e.target.value || null)}>
                  <option value="">Choose a patient…</option>
                  {options.patients.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="plan-by" className={LABEL}>Assigned by</label>
                <select id="plan-by" className="field cursor-pointer" value={draft.assigned_by} disabled={!canEdit}
                  onChange={(e) => set('assigned_by', e.target.value)}>
                  {!options.care_team.some((m) => m.id === draft.assigned_by) && (
                    <option value={draft.assigned_by}>{draft.assigned_by}</option>
                  )}
                  {options.care_team.map((m) => (
                    <option key={m.id} value={m.id}>{m.name}</option>
                  ))}
                </select>
              </div>
              <div className="sm:col-span-2">
                <label htmlFor="plan-notes" className={LABEL}>
                  Note to the patient <span className="font-normal">optional</span>
                </label>
                <textarea id="plan-notes" rows={2} className="field" value={draft.notes} maxLength={600} disabled={!canEdit}
                  placeholder="A line they will see above their exercises."
                  onChange={(e) => set('notes', e.target.value)} />
              </div>
            </div>
          </SectionCard>

          {canEdit && <LibraryPicker options={options} chosen={draft.items.map((i) => i.exercise_id)} onAdd={add} />}
        </div>

        <SectionCard
          title="Exercises in this plan"
          aside={`${draft.items.length} of ${options.max_items}`}
          action={
            draft.items.length > 0 ? (
              <button type="button" className="btn-plain btn-sm" onClick={() => setPreview(true)}>
                <Eye size={14} /> Patient view
              </button>
            ) : undefined
          }
        >
          {draft.items.length === 0 ? (
            <EmptyState variant="inline" title="No exercises yet" icon={<Plus />} family="teal">
              Pick from the library on the left. Each one gets its own sets, reps, hold and frequency.
            </EmptyState>
          ) : (
            <ol className="space-y-3" aria-label="Exercises in this plan">
              {draft.items.map((item, i) => (
                <ItemRow
                  key={item.exercise_id}
                  item={item}
                  index={i}
                  count={draft.items.length}
                  options={options}
                  disabled={!canEdit}
                  onChange={(next) => setItem(i, next)}
                  onMove={(dir) => move(i, dir)}
                  onRemove={() => remove(i)}
                />
              ))}
            </ol>
          )}
        </SectionCard>
      </div>

      {canEdit && (
        <div className="fixed inset-x-0 bottom-4 z-30 flex justify-center px-4">
          <div className="glass flex w-full max-w-[720px] flex-wrap items-center gap-2 rounded-pill py-2 pl-5 pr-2">
            <span className="min-w-0 flex-1 truncate text-copy text-body">
              {textWarn ?? (dirty ? 'Unsaved changes' : plan ? 'Saved' : 'Not saved yet')}
            </span>
            {plan && plan.status === 'draft' && (
              <button type="button" className="btn-gray btn-sm" disabled={saving}
                onClick={() => archive.mutate({ id: plan.id, actor: draft.assigned_by }, {
                  onSuccess: () => { toast('Draft archived', 'info'); navigate('/exercise-plans') },
                  onError,
                })}>
                Archive
              </button>
            )}
            <button type="button" className="btn-gray btn-sm" disabled={saving || !dirty} onClick={() => save()}>
              {saving && !publish.isPending ? 'Saving…' : plan?.status === 'active' ? 'Save changes' : 'Save draft'}
            </button>
            {plan?.status !== 'active' && (
              <button type="button" className="btn-filled btn-sm" disabled={saving || !canPublish || !!textWarn}
                onClick={() => setConfirming(true)}>
                <Send size={14} /> Publish
              </button>
            )}
          </div>
        </div>
      )}

      {preview && <PatientPreview draft={draft} options={options} patientName={patient?.name} onClose={() => setPreview(false)} />}

      {confirming && (
        <Modal
          title="Publish this plan?"
          size="md"
          onClose={() => setConfirming(false)}
          description={`${patient?.name ?? 'The patient'} will see ${draft.items.length} exercise${draft.items.length === 1 ? '' : 's'} in MedPull. Any plan they are on now is replaced.`}
          footer={
            <>
              <button type="button" className="btn-gray" onClick={() => setConfirming(false)}>Cancel</button>
              <button type="button" className="btn-filled" disabled={saving} onClick={doPublish}>
                {saving ? 'Publishing…' : 'Publish'}
              </button>
            </>
          }
        >
          <ul className="space-y-2">
            {draft.items.map((i) => (
              <li key={i.exercise_id} className="flex items-baseline justify-between gap-3 text-copy">
                <span className="font-medium text-ink">{i.title}</span>
                <span className="text-right text-secondary">{doseLine(i, label(options.frequencies, i.frequency), label(options.sides, i.side))}</span>
              </li>
            ))}
          </ul>
          <p className="meta mt-4">
            The wording of each exercise is frozen as published. Library edits later do not change this plan.
          </p>
        </Modal>
      )}

      {result && (
        <Modal
          title="Plan published"
          size="md"
          onClose={() => setResult(null)}
          footer={
            <>
              {result.plan.patient && (
                <Link to={`/patients/${result.plan.patient.id}`} className="btn-gray">Open patient</Link>
              )}
              <button type="button" className="btn-filled" onClick={() => setResult(null)}>Done</button>
            </>
          }
        >
          <dl className="space-y-3">
            <Fact label="Plan">
              Published for {result.plan.patient?.name ?? 'the patient'} with {result.plan.exercise_count} exercise
              {result.plan.exercise_count === 1 ? '' : 's'}
              {result.superseded.length > 0 && `, replacing ${result.superseded.length === 1 ? 'their previous plan' : `${result.superseded.length} previous plans`}`}.
            </Fact>
            <Fact label="Invitation">{result.invitation.detail}</Fact>
            <Fact label="Delivery">{result.delivery.detail}</Fact>
          </dl>
        </Modal>
      )}
    </div>
  )
}

function Fact({ label: l, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-surface bg-soft p-4">
      <dt className="text-label font-medium tracking-label text-secondary">{l}</dt>
      <dd className="mt-1 text-copy text-ink">{children}</dd>
    </div>
  )
}

function label(vocab: { key: string; label: string }[], key: string): string {
  return vocab.find((v) => v.key === key)?.label ?? key
}

// --- one tray row --------------------------------------------------------------

function ItemRow({
  item,
  index,
  count,
  options,
  disabled,
  onChange,
  onMove,
  onRemove,
}: {
  item: EditorItem
  index: number
  count: number
  options: HepOptions
  disabled: boolean
  onChange: (next: EditorItem) => void
  onMove: (dir: -1 | 1) => void
  onRemove: () => void
}) {
  const [more, setMore] = useState(Boolean(item.clinician_instructions || item.precautions_override))
  const set = <K extends keyof EditorItem>(key: K, v: EditorItem[K]) => onChange({ ...item, [key]: v })
  const id = `pi-${item.exercise_id}`
  const dose = doseLine(item, label(options.frequencies, item.frequency), label(options.sides, item.side))

  return (
    <li className="rounded-surface bg-soft p-4">
      <div className="mb-3 flex items-start gap-3">
        <span aria-hidden className="grid h-7 w-7 shrink-0 place-items-center rounded-pill bg-panel text-label font-medium tabular-nums text-ink">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <span className="block text-copy-lg font-medium text-ink">
            <span className="sr-only">Exercise {index + 1}: </span>
            {item.title}
          </span>
          <span className="meta block">
            {item.body_region_label} · {item.category_label}
            {item.media_playable ? <> · <Film aria-hidden size={12} className="inline align-[-1px]" /> Clip</> : ' · No clip yet'}
            {item.library_changed && ' · Library wording has changed since publish'}
          </span>
          <span className="mt-1 block text-copy text-body">{dose}</span>
        </div>
        {!disabled && (
          <span className="flex shrink-0 items-center gap-0.5">
            <button type="button" className="btn-icon btn-sm hover:!bg-panel" aria-label={`Move ${item.title} up`} disabled={index === 0} onClick={() => onMove(-1)}>
              <ArrowUp aria-hidden />
            </button>
            <button type="button" className="btn-icon btn-sm hover:!bg-panel" aria-label={`Move ${item.title} down`} disabled={index === count - 1} onClick={() => onMove(1)}>
              <ArrowDown aria-hidden />
            </button>
            <button type="button" className="btn-icon btn-sm hover:!bg-panel" aria-label={`Remove ${item.title}`} onClick={onRemove}>
              <X aria-hidden />
            </button>
          </span>
        )}
      </div>

      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
        <NumberField id={`${id}-sets`} label="Sets" value={item.sets} disabled={disabled} onChange={(v) => set('sets', v)} />
        <NumberField id={`${id}-reps`} label="Reps" value={item.reps} disabled={disabled} onChange={(v) => set('reps', v)} />
        <NumberField id={`${id}-hold`} label="Hold (s)" value={item.hold_seconds} disabled={disabled} onChange={(v) => set('hold_seconds', v)} />
        <div>
          <label htmlFor={`${id}-freq`} className={LABEL}>Frequency</label>
          <select id={`${id}-freq`} className="field cursor-pointer !min-h-10 !py-1.5" value={item.frequency} disabled={disabled} onChange={(e) => set('frequency', e.target.value)}>
            {options.frequencies.map((f) => <option key={f.key} value={f.key}>{f.label}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-side`} className={LABEL}>Side</label>
          <select id={`${id}-side`} className="field cursor-pointer !min-h-10 !py-1.5" value={item.side} disabled={disabled} onChange={(e) => set('side', e.target.value)}>
            {options.sides.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </div>
      </div>

      {more ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor={`${id}-notes`} className={LABEL}>Instructions for this patient</label>
            <textarea id={`${id}-notes`} rows={2} className="field" value={item.clinician_instructions} maxLength={400} disabled={disabled}
              placeholder="e.g. Start with the operated leg." onChange={(e) => set('clinician_instructions', e.target.value)} />
          </div>
          <div>
            <label htmlFor={`${id}-prec`} className={LABEL}>
              Precautions <span className="font-normal">replaces the library’s</span>
            </label>
            <textarea id={`${id}-prec`} rows={2} className="field" value={item.precautions_override} maxLength={400} disabled={disabled}
              placeholder={item.library_precautions || 'None in the library'} onChange={(e) => set('precautions_override', e.target.value)} />
          </div>
        </div>
      ) : (
        !disabled && (
          <button type="button" className="btn-plain btn-sm mt-2 -ml-2" onClick={() => setMore(true)}>
            Add instructions or precautions
          </button>
        )
      )}
    </li>
  )
}

function NumberField({ id, label: l, value, disabled, onChange }: {
  id: string
  label: string
  value: string
  disabled: boolean
  onChange: (v: string) => void
}) {
  return (
    <div>
      <label htmlFor={id} className={LABEL}>{l}</label>
      <input id={id} type="number" inputMode="numeric" min={0} max={999} className="field !min-h-10 !py-1.5 tabular-nums" value={value}
        disabled={disabled} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

// --- the patient view ------------------------------------------------------------

function PatientPreview({ draft, options, patientName, onClose }: {
  draft: Draft
  options: HepOptions
  patientName?: string
  onClose: () => void
}) {
  return (
    <Modal title="What the patient sees" size="lg" onClose={onClose}
      description={`${patientName ? `${patientName}’s` : 'Their'} Today screen lists these in this order.`}
      footer={<button type="button" className="btn-filled" onClick={onClose}>Done</button>}>
      {draft.notes.trim() && <p className="mb-4 rounded-surface bg-soft p-4 text-copy text-ink">{draft.notes.trim()}</p>}
      <ol className="space-y-5">
        {draft.items.map((i, n) => (
          <li key={i.exercise_id}>
            <div className="flex items-baseline gap-2">
              <span className="text-copy tabular-nums text-secondary">{n + 1}.</span>
              <span className="text-copy-lg font-medium text-ink">{i.title}</span>
            </div>
            <p className="mt-0.5 pl-5 text-copy text-body">{doseLine(i, label(options.frequencies, i.frequency), label(options.sides, i.side))}</p>
            <div className="ml-5 mt-2 flex aspect-video max-w-[320px] flex-col items-center justify-center gap-1 rounded-surface bg-soft text-secondary">
              <Film aria-hidden size={22} />
              <span className="text-label">{i.media_playable ? 'Demonstration plays here' : 'Written steps until a clip is approved'}</span>
            </div>
            <ol className="mt-2 list-decimal space-y-1 pl-10 text-copy text-ink">
              {i.steps.map((s, k) => <li key={k}>{s}</li>)}
            </ol>
            {i.clinician_instructions.trim() && (
              <p className="mt-2 pl-5 text-copy text-ink"><span className="font-medium">From your care team:</span> {i.clinician_instructions.trim()}</p>
            )}
            {(i.precautions_override.trim() || i.library_precautions) && (
              <p className="mt-1 pl-5 text-copy text-secondary">Take care: {i.precautions_override.trim() || i.library_precautions}</p>
            )}
          </li>
        ))}
      </ol>
    </Modal>
  )
}
