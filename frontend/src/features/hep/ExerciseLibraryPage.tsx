import { Dumbbell, Film, Plus, Search, Sparkles, Stethoscope } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import type { Exercise, ExerciseOrigin, Vocab } from '../../api/hep'
import { useCreateExercise, useExercises } from '../../api/hep'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import Switch, { GroupFooter, GroupHeader, SettingsHero } from '../settings/Switch'
import ExerciseForm from './ExerciseForm'
import ExercisesNav from './ExercisesNav'
import ExercisePreviewModal from './ExercisePreviewModal'
import { blankExercise, statusChip, toBody, type ExerciseDraft } from './hepCopy'

type Tab = ExerciseOrigin
const TABS: { key: Tab; label: string }[] = [
  { key: 'standard', label: 'Standard' },
  { key: 'custom', label: 'My exercises' },
]

/** `/exercise-library` — the exercises a clinic prescribes from. The
 *  standard set is shared and read-only; "My exercises" are the clinic's
 *  own. Search covers names and synonyms; filters are body region and
 *  category. Each row previews what the patient will read. */
export default function ExerciseLibraryPage() {
  const [tab, setTab] = useState<Tab>('standard')
  const [q, setQ] = useState('')
  const [region, setRegion] = useState('')
  const [category, setCategory] = useState('')
  const [showArchived, setShowArchived] = useState(false)
  const [creating, setCreating] = useState(false)
  const [open, setOpen] = useState<Exercise | null>(null)

  const library = useExercises({
    q,
    region: region || undefined,
    category: category || undefined,
    origin: tab,
    include_archived: tab === 'custom' && showArchived,
  })
  const regions = library.data?.regions ?? []
  const categories = library.data?.categories ?? []
  const rows = useMemo(() => library.data?.exercises ?? [], [library.data])
  const current = open ? (rows.find((e) => e.id === open.id) ?? open) : null

  return (
    <div className="pb-10">
      <SettingsHero
        nav={<ExercisesNav />}
        icon={<Dumbbell />}
        title="Exercise library"
        decor={[<Dumbbell key="d" />, <Film key="f" />, <Stethoscope key="s" />]}
      >
        The exercises your clinic prescribes. Standard ones are shared and reviewed; add your own
        under My exercises. Demonstrations appear once a therapist has approved them.
      </SettingsHero>

      <div
        className="rise mt-8 flex flex-wrap items-center gap-x-3 gap-y-3"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        <SegmentedControl<Tab>
          options={TABS}
          value={tab}
          onChange={(t) => {
            setTab(t)
            setCreating(false)
          }}
          tone="glass"
          aria-label="Library section"
        />
        {tab === 'custom' && (
          <span className="glass inline-flex min-h-11 items-center gap-2.5 rounded-pill py-1 pl-2 pr-4">
            <Switch
              id="hep-show-archived"
              checked={showArchived}
              onChange={setShowArchived}
              aria-labelledby="hep-show-archived-label"
            />
            <label
              id="hep-show-archived-label"
              htmlFor="hep-show-archived"
              className="cursor-pointer text-copy font-medium text-ink"
            >
              Show archived
            </label>
          </span>
        )}
        <button
          type="button"
          className="btn-filled ml-auto"
          aria-expanded={creating}
          onClick={() => {
            setTab('custom')
            setCreating((c) => !c)
          }}
        >
          <Plus size={16} /> New exercise
        </button>
      </div>

      <div
        className="rise mt-4 flex flex-wrap items-center gap-3"
        style={{ '--rise-delay': '80ms' } as CSSProperties}
      >
        <label className="relative min-w-[220px] flex-1">
          <span className="sr-only">Search exercises</span>
          <Search aria-hidden size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            type="search"
            className="field !pl-10"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name or what it's also called"
          />
        </label>
        <FilterSelect id="hep-region" label="Body region" value={region} onChange={setRegion} options={regions} all="All regions" />
        <FilterSelect id="hep-category" label="Category" value={category} onChange={setCategory} options={categories} all="All categories" />
      </div>

      <div className="rise mt-6" style={{ '--rise-delay': '100ms' } as CSSProperties}>
        {creating && (
          <NewExercise
            regions={regions}
            categories={categories}
            onDone={() => setCreating(false)}
            initialRegion={region}
            initialCategory={category}
          />
        )}
        {library.isLoading ? (
          <SkeletonCard rows={6} />
        ) : library.isError ? (
          <EmptyState title="The exercise library couldn’t be loaded." icon={<Dumbbell />}>
            Refresh the page to try again.
          </EmptyState>
        ) : (
          <LibraryTable
            tab={tab}
            rows={rows}
            filtered={Boolean(q.trim() || region || category)}
            clinic={library.data?.clinic.name}
            onOpen={setOpen}
            onCreate={() => {
              setTab('custom')
              setCreating(true)
            }}
          />
        )}
      </div>

      {current && (
        <ExercisePreviewModal
          exercise={current}
          regions={regions}
          categories={categories}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}

function FilterSelect({
  id,
  label,
  value,
  onChange,
  options,
  all,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  options: Vocab[]
  all: string
}) {
  return (
    <label className="min-w-[160px]">
      <span className="sr-only">{label}</span>
      <select id={id} className="field cursor-pointer" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{all}</option>
        {options.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function NewExercise({
  regions,
  categories,
  onDone,
  initialRegion,
  initialCategory,
}: {
  regions: Vocab[]
  categories: Vocab[]
  onDone: () => void
  initialRegion: string
  initialCategory: string
}) {
  const toast = useToast()
  const create = useCreateExercise()
  const [draft, setDraft] = useState<ExerciseDraft>(() =>
    blankExercise(initialRegion || regions[0]?.key || 'knee', initialCategory || categories[0]?.key || 'mobility'),
  )
  const save = () => {
    if (!draft.title.trim()) return
    create.mutate(toBody(draft), {
      onSuccess: () => {
        toast('Exercise added to My exercises', 'success')
        setDraft(blankExercise(draft.body_region, draft.category))
        onDone()
      },
      onError: (e) => toast(`Could not save — ${e.message}`, 'warning'),
    })
  }
  return (
    <SectionCard title="New exercise" className="mb-8">
      <div className="space-y-5">
        <ExerciseForm value={draft} onChange={setDraft} regions={regions} categories={categories} idPrefix="new" />
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <span className="meta">
            Saved as a draft for your clinic. Attach a demonstration later, once it has been reviewed.
          </span>
          <span className="ml-auto flex items-center gap-2">
            <button type="button" className="btn-gray" onClick={onDone}>
              Cancel
            </button>
            <button type="button" className="btn-filled" disabled={!draft.title.trim() || create.isPending} onClick={save}>
              {create.isPending ? 'Saving…' : 'Save exercise'}
            </button>
          </span>
        </div>
      </div>
    </SectionCard>
  )
}

function LibraryTable({
  tab,
  rows,
  filtered,
  clinic,
  onOpen,
  onCreate,
}: {
  tab: Tab
  rows: Exercise[]
  filtered: boolean
  clinic?: string
  onOpen: (e: Exercise) => void
  onCreate: () => void
}) {
  const id = `hep-${tab}`
  const title = tab === 'standard' ? 'Standard exercises' : clinic ? `${clinic} exercises` : 'My exercises'
  const empty =
    tab === 'custom' && !filtered ? (
      <EmptyState
        variant="inline"
        title="No exercises of your own yet"
        icon={<Sparkles />}
        family="teal"
        action={
          <button type="button" className="btn-tinted" onClick={onCreate}>
            <Plus size={16} /> New exercise
          </button>
        }
      >
        Anything the standard set is missing lives here, and only your clinic sees it.
      </EmptyState>
    ) : (
      <EmptyState variant="inline" title="Nothing matches" icon={<Search />} family="blue">
        Try another name, or clear the region and category filters.
      </EmptyState>
    )

  return (
    <section aria-labelledby={id}>
      <GroupHeader id={id} onSky>
        {title}
        <span className="sr-only">, </span>
        <span className="badge-ring ml-2 align-[1px] tabular-nums">
          {rows.length}
          <span className="sr-only"> {rows.length === 1 ? 'exercise' : 'exercises'}</span>
        </span>
      </GroupHeader>
      <div className="card-group">
        {rows.length === 0 ? (
          <div className="px-4 py-6">{empty}</div>
        ) : (
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-labelledby={id}>
            <table className="w-full min-w-[720px] text-left text-copy">
              <thead>
                <tr className="border-b border-hairline">
                  <Th>Exercise</Th>
                  <Th>Region</Th>
                  <Th>Category</Th>
                  <Th>Demonstration</Th>
                  <Th className="text-right">Status</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {rows.map((e) => {
                  const chip = statusChip(e.status)
                  return (
                    <tr key={e.id} className={e.status === 'archived' ? 'bg-soft [--text-secondary:var(--body)]' : ''}>
                      <Td className="max-w-[420px]">
                        <button
                          type="button"
                          onClick={() => onOpen(e)}
                          className="block max-w-full truncate rounded-[6px] text-left font-medium text-ink hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
                        >
                          {e.title}
                        </button>
                        {e.steps[0] && <span className="mt-0.5 block truncate text-copy text-secondary">{e.steps[0]}</span>}
                        {e.synonyms.length > 0 && (
                          <span className="meta mt-1 block truncate">Also: {e.synonyms.join(', ')}</span>
                        )}
                      </Td>
                      <Td className="text-body">{e.body_region_label}</Td>
                      <Td className="text-body">{e.category_label}</Td>
                      <Td>
                        <DemoCell exercise={e} />
                      </Td>
                      <Td className="text-right">
                        <span className={`chip ${chip.pill}`}>{chip.label}</span>
                      </Td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <GroupFooter>
        {tab === 'standard'
          ? 'Standard wording is shared across clinics and cannot be edited here. Open one to preview what the patient reads.'
          : 'Steps and precautions are what patients see, so keep them plain. Archived exercises stay on any plan that already uses them.'}
      </GroupFooter>
    </section>
  )
}

function DemoCell({ exercise }: { exercise: Exercise }) {
  const m = exercise.media
  if (m?.playable) return <span className="inline-flex items-center gap-1.5 text-body"><Film aria-hidden size={14} /> Approved clip</span>
  if (m) return <span className="text-secondary">{m.approval_status === 'rejected' ? 'Clip needs replacing' : 'Clip in review'}</span>
  return <span className="text-secondary">Coming soon</span>
}

function Th({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <th scope="col" className={`px-2 py-2.5 text-label font-medium tracking-label text-secondary first:pl-4 last:pr-4 ${className}`}>
      {children}
    </th>
  )
}

function Td({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <td className={`px-2 py-3 align-top first:pl-4 last:pr-4 ${className}`}>{children}</td>
}
