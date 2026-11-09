import { ArrowDown, ArrowUp, CalendarDays, ChevronLeft, Film, Plus, X } from 'lucide-react'
import { useEffect, useState, type CSSProperties } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../../api/client'
import type { Exercise, HepOptions, Template } from '../../api/hep'
import { useCreateTemplate, useExercises, useHepOptions, useTemplates, useUpdateTemplate } from '../../api/hep'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'
import ApplyProgramDialog from './ApplyProgramDialog'
import { LABEL, NumberField, RequirementControl, WeekdayPicker } from './DoseFields'
import { diagnosticWarning } from './hepCopy'
import LibraryPicker from './LibraryPicker'
import {
  blankProgram,
  draftFromTemplate,
  editorItemDose,
  itemFromExercise,
  serializeProgram,
  toItemBody,
  type ProgramDraft,
  type ProgramItem,
} from './programCopy'
import { countOf, requirementsText, weekdaysLabel } from './scheduleCopy'

/** `/exercise-programs/new` and `/exercise-programs/:id` — build a program:
 *  pick exercises from the library on the left, and on the right give each
 *  its weekdays, its dose (sets, reps, hold, load, target effort, side),
 *  what you ask for with it and a note. Save creates or updates the
 *  template; "Apply to…" puts a saved one on a lifter's calendar. */
export default function ProgramEditorPage() {
  const { id } = useParams()
  const templateId = id && id !== 'new' ? Number(id) : null
  const templates = useTemplates({ enabled: templateId != null })
  const options = useHepOptions()
  // The template payload names its exercises but carries no region or clip;
  // the library fills those in for the tray rows.
  const library = useExercises({})
  const template = templateId != null ? templates.data?.templates.find((t) => t.id === templateId) : null

  if (templateId != null && (templates.isLoading || library.isLoading)) {
    return (
      <div className="space-y-stack pt-2">
        <SkeletonCard lines={2} />
        <SkeletonCard rows={4} />
      </div>
    )
  }
  if (templateId != null && (templates.isError || !template)) {
    return (
      <EmptyState
        title="This program couldn’t be opened."
        action={
          <Link to="/exercise-programs" className="btn-tinted">
            Back to programs
          </Link>
        }
      >
        It may have been archived, or the link is wrong.
      </EmptyState>
    )
  }
  if (!options.data) return <SkeletonCard rows={4} />
  return (
    <Editor
      key={template?.id ?? 'new'}
      template={template ?? null}
      options={options.data}
      library={library.data?.exercises ?? []}
    />
  )
}

function Editor({ template, options, library }: { template: Template | null; options: HepOptions; library: Exercise[] }) {
  const toast = useToast()
  const navigate = useNavigate()
  const create = useCreateTemplate()
  const update = useUpdateTemplate()
  const [draft, setDraft] = useState<ProgramDraft>(() => (template ? draftFromTemplate(template, library) : blankProgram()))
  const [saved, setSaved] = useState(() => (template ? serializeProgram(draftFromTemplate(template, library)) : ''))
  const [applying, setApplying] = useState(false)
  const dirty = serializeProgram(draft) !== saved
  const saving = create.isPending || update.isPending

  // Leaving with unsaved work: the browser's own prompt, nothing custom.
  useEffect(() => {
    if (!dirty) return
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty])

  const set = <K extends keyof ProgramDraft>(key: K, v: ProgramDraft[K]) => setDraft((d) => ({ ...d, [key]: v }))
  const setItem = (index: number, next: ProgramItem) =>
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
    set('items', [...draft.items, itemFromExercise(e)])
  }

  const weeks = countOf(draft.weeks)
  const textWarn = diagnosticWarning(
    [draft.name, draft.description, ...draft.items.map((i) => i.clinician_instructions)].join('\n'),
  )
  const problem = !draft.name.trim()
    ? 'Give the program a name'
    : weeks == null || weeks < 1 || weeks > 26
      ? 'Weeks: 1 to 26'
      : draft.items.length === 0
        ? 'Add at least one exercise'
        : textWarn
  const canSave = !problem && dirty && !saving

  const onError = (e: unknown) =>
    toast(`Could not save — ${e instanceof ApiError && e.message ? e.message : 'try again'}`, 'warning')

  const save = () => {
    const body = {
      name: draft.name.trim(),
      description: draft.description.trim(),
      weeks: weeks ?? 1,
      items: draft.items.map(toItemBody),
    }
    if (template) {
      update.mutate(
        { id: template.id, ...body },
        {
          onSuccess: () => {
            setSaved(serializeProgram(draft))
            toast('Program saved', 'success')
          },
          onError,
        },
      )
    } else {
      create.mutate(body, {
        onSuccess: (t) => {
          setSaved(serializeProgram(draft))
          toast('Program saved', 'success')
          navigate(`/exercise-programs/${t.id}`, { replace: true })
        },
        onError,
      })
    }
  }

  return (
    <div className="pb-28">
      <header data-hero className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <Link to="/exercise-programs" className="btn-plain-muted btn-sm -ml-2">
          <ChevronLeft size={16} aria-hidden /> Programs
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="display-title text-display text-ink">{template ? template.name : 'New program'}</h1>
          {template?.updated_at && <span className="meta">Updated {relativeTime(template.updated_at)}</span>}
          {template && (
            <button type="button" className="btn-tinted btn-sm ml-auto" onClick={() => setApplying(true)}>
              <CalendarDays size={14} aria-hidden /> Apply to…
            </button>
          )}
        </div>
        <p className="mt-3 max-w-[60ch] text-lede text-body">
          Pick exercises from the library, give each its weekdays, its dose and what you ask for with
          it. Applying the program puts them on a lifter’s calendar from a start date.
        </p>
      </header>

      <div
        className="rise mt-8 grid gap-stack lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
        style={{ '--rise-delay': '80ms' } as CSSProperties}
      >
        <div className="space-y-stack">
          <SectionCard title="Program">
            <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_120px]">
              <div>
                <label htmlFor="program-name" className={LABEL}>
                  Name
                </label>
                <input
                  id="program-name"
                  className="field"
                  value={draft.name}
                  maxLength={80}
                  placeholder="e.g. Patellar tendinopathy · phase 2"
                  onChange={(e) => set('name', e.target.value)}
                />
              </div>
              <NumberField id="program-weeks" label="Weeks" value={draft.weeks} min={1} max={26} onChange={(v) => set('weeks', v)} />
              <div className="sm:col-span-2">
                <label htmlFor="program-desc" className={LABEL}>
                  Description <span className="font-normal">optional</span>
                </label>
                <textarea
                  id="program-desc"
                  rows={2}
                  className="field"
                  value={draft.description}
                  maxLength={400}
                  placeholder="Who it is for and what it builds towards."
                  onChange={(e) => set('description', e.target.value)}
                />
              </div>
            </div>
          </SectionCard>

          <LibraryPicker options={options} chosen={draft.items.map((i) => i.exercise_id)} onAdd={add} />
        </div>

        <SectionCard title="Exercises in this program" aside={`${draft.items.length}`}>
          {draft.items.length === 0 ? (
            <EmptyState variant="inline" title="No exercises yet" icon={<Plus />} family="teal">
              Pick from the library on the left. Each one gets its weekdays, its dose and what you ask
              for with it.
            </EmptyState>
          ) : (
            <ol className="space-y-3" aria-label="Exercises in this program">
              {draft.items.map((item, i) => (
                <ItemRow
                  key={item.exercise_id}
                  item={item}
                  index={i}
                  count={draft.items.length}
                  options={options}
                  onChange={(next) => setItem(i, next)}
                  onMove={(dir) => move(i, dir)}
                  onRemove={() => remove(i)}
                />
              ))}
            </ol>
          )}
        </SectionCard>
      </div>

      <div className="fixed inset-x-0 bottom-4 z-30 flex justify-center px-4">
        <div className="glass flex w-full max-w-[720px] flex-wrap items-center gap-2 rounded-pill py-2 pl-5 pr-2">
          <span className="min-w-0 flex-1 truncate text-copy text-body" role="status">
            {dirty ? (problem ?? 'Unsaved changes') : template ? 'Saved' : 'Not saved yet'}
          </span>
          <button type="button" className="btn-filled btn-sm" disabled={!canSave} onClick={save}>
            {saving ? 'Saving…' : template ? 'Save changes' : 'Save program'}
          </button>
        </div>
      </div>

      {applying && template && <ApplyProgramDialog template={template} onClose={() => setApplying(false)} />}
    </div>
  )
}

// --- one tray row --------------------------------------------------------------

function ItemRow({
  item,
  index,
  count,
  options,
  onChange,
  onMove,
  onRemove,
}: {
  item: ProgramItem
  index: number
  count: number
  options: HepOptions
  onChange: (next: ProgramItem) => void
  onMove: (dir: -1 | 1) => void
  onRemove: () => void
}) {
  const [more, setMore] = useState(Boolean(item.clinician_instructions))
  const set = <K extends keyof ProgramItem>(key: K, v: ProgramItem[K]) => onChange({ ...item, [key]: v })
  const id = `pr-${item.exercise_id}`
  const dose = editorItemDose(item, options.sides)
  const rpe = countOf(item.rpe_target)
  const asks = requirementsText(item.video_requirement, item.wearable_requirement)
  const warn = diagnosticWarning(item.clinician_instructions)

  return (
    <li className="rounded-surface bg-soft p-4">
      <div className="mb-3 flex items-start gap-3">
        <span
          aria-hidden
          className="grid h-7 w-7 shrink-0 place-items-center rounded-pill bg-panel text-label font-medium tabular-nums text-ink"
        >
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <span className="block text-copy-lg font-medium text-ink">
            <span className="sr-only">Exercise {index + 1}: </span>
            {item.title}
          </span>
          <span className="meta block">
            {[item.body_region_label, item.category_label].filter(Boolean).join(' · ')}
            {item.media_playable ? (
              <>
                {' · '}
                <Film aria-hidden size={12} className="inline align-[-1px]" /> Clip
              </>
            ) : (
              ' · No clip yet'
            )}
          </span>
          <span className="mt-1 block text-copy text-body">
            {weekdaysLabel(item.weekdays)}
            {dose && ` · ${dose}`}
            {rpe != null && ` · should feel like ${rpe}/10`}
            {asks && ` · ${asks}`}
          </span>
        </div>
        <span className="flex shrink-0 items-center gap-0.5">
          <button
            type="button"
            className="btn-icon btn-sm hover:!bg-panel"
            aria-label={`Move ${item.title} up`}
            disabled={index === 0}
            onClick={() => onMove(-1)}
          >
            <ArrowUp aria-hidden />
          </button>
          <button
            type="button"
            className="btn-icon btn-sm hover:!bg-panel"
            aria-label={`Move ${item.title} down`}
            disabled={index === count - 1}
            onClick={() => onMove(1)}
          >
            <ArrowDown aria-hidden />
          </button>
          <button type="button" className="btn-icon btn-sm hover:!bg-panel" aria-label={`Remove ${item.title}`} onClick={onRemove}>
            <X aria-hidden />
          </button>
        </span>
      </div>

      <WeekdayPicker value={item.weekdays} onChange={(v) => set('weekdays', v)} />

      <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-7">
        <NumberField id={`${id}-sets`} label="Sets" value={item.sets} onChange={(v) => set('sets', v)} />
        <NumberField id={`${id}-reps`} label="Reps" value={item.reps} onChange={(v) => set('reps', v)} />
        <NumberField id={`${id}-hold`} label="Hold (s)" value={item.hold_seconds} onChange={(v) => set('hold_seconds', v)} />
        <NumberField id={`${id}-load`} label="Load (kg)" value={item.load_kg} max={500} step={0.5} onChange={(v) => set('load_kg', v)} />
        <NumberField id={`${id}-rpe`} label="Target RPE" value={item.rpe_target} max={10} onChange={(v) => set('rpe_target', v)} />
        <div className="sm:col-span-2">
          <label htmlFor={`${id}-side`} className={LABEL}>
            Side
          </label>
          <select
            id={`${id}-side`}
            className="field cursor-pointer !min-h-10 !py-1.5"
            value={item.side}
            onChange={(e) => set('side', e.target.value)}
          >
            {options.sides.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <RequirementControl label="Clip of their attempt" value={item.video_requirement} onChange={(v) => set('video_requirement', v)} />
        <RequirementControl label="Wearable on" value={item.wearable_requirement} onChange={(v) => set('wearable_requirement', v)} />
      </div>

      {more ? (
        <div className="mt-3">
          <label htmlFor={`${id}-notes`} className={LABEL}>
            Note to the patient
          </label>
          <textarea
            id={`${id}-notes`}
            rows={2}
            className="field"
            value={item.clinician_instructions}
            maxLength={400}
            placeholder="e.g. Slow on the way down."
            onChange={(e) => set('clinician_instructions', e.target.value)}
          />
          {warn && (
            <p role="alert" className="mt-1 px-1 text-label text-risk-med-ink">
              {warn}
            </p>
          )}
        </div>
      ) : (
        <button type="button" className="btn-plain btn-sm -ml-2 mt-2" onClick={() => setMore(true)}>
          Add a note to the patient
        </button>
      )}
    </li>
  )
}
