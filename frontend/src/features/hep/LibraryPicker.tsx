import { Check, Plus, Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import type { Exercise, Vocab } from '../../api/hep'
import { useExercises } from '../../api/hep'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard } from '../../components/Skeleton'

/** The library as a picker: search by name or what an exercise is also
 *  called, narrow by region and category, and take a row.
 *
 *  `add` (the plan editor's tray): a row already in `chosen` reads "Added"
 *  and is disabled. `pick` (the schedule's AssignDialog): one exercise at a
 *  time; `chosen` holds the ones already on that day, which read
 *  `chosenLabel` and are disabled. `flat` drops the card surface so the
 *  picker can sit inside a dialog. */
export default function LibraryPicker({
  options,
  chosen,
  onAdd,
  mode = 'add',
  flat = false,
  listClassName = 'max-h-[520px]',
  chosenLabel = 'Added',
  autoFocus = false,
}: {
  options: { regions: Vocab[]; categories: Vocab[] }
  chosen: number[]
  onAdd: (e: Exercise) => void
  mode?: 'add' | 'pick'
  flat?: boolean
  /** The list's height cap (a Tailwind max-h class). */
  listClassName?: string
  /** What a row in `chosen` says in place of the button text. */
  chosenLabel?: string
  autoFocus?: boolean
}) {
  const [q, setQ] = useState('')
  const [region, setRegion] = useState('')
  const [category, setCategory] = useState('')
  const library = useExercises({ q, region: region || undefined, category: category || undefined })
  const rows = useMemo(() => library.data?.exercises ?? [], [library.data])
  const matches = library.data ? `${rows.length} match${rows.length === 1 ? '' : 'es'}` : undefined

  const controls = (
    <div className={`space-y-2 ${flat ? '' : 'px-4 pb-3'}`}>
      <label className="relative block">
        <span className="sr-only">Search the library</span>
        <Search aria-hidden size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
        <input type="search" className="field !pl-10" value={q} onChange={(e) => setQ(e.target.value)}
          autoFocus={autoFocus} placeholder="Search by name or what it’s also called" />
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label>
          <span className="sr-only">Body region</span>
          <select className="field cursor-pointer" value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">All regions</option>
            {options.regions.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
        </label>
        <label>
          <span className="sr-only">Category</span>
          <select className="field cursor-pointer" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            {options.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </label>
      </div>
    </div>
  )

  const list = (
    <div className={`${listClassName} overflow-y-auto border-t border-hairline ${flat ? 'mt-3' : ''}`}>
      {library.isLoading ? (
        <div className="p-4"><SkeletonCard rows={4} /></div>
      ) : library.isError ? (
        <p className="px-4 py-6 text-center text-copy text-secondary">The library couldn’t be loaded.</p>
      ) : rows.length === 0 ? (
        <p className="px-4 py-6 text-center text-copy text-secondary">Nothing matches.</p>
      ) : (
        <ul className="divide-y divide-hairline" aria-label="Exercises">
          {rows.map((e) => {
            const taken = chosen.includes(e.id)
            const clip = e.clinic_media?.playable ? ' · Your clip' : e.media?.playable ? ' · Clip' : ''
            return (
              <li key={e.id} className={`flex items-center gap-3 py-2.5 ${flat ? 'px-1' : 'px-4'}`}>
                <div className="min-w-0 flex-1">
                  <span className="block truncate text-copy font-medium text-ink">{e.title}</span>
                  <span className="meta block truncate">
                    {e.body_region_label} · {e.category_label}
                    {e.origin === 'custom' ? ' · Yours' : ''}
                    {clip}
                  </span>
                </div>
                <button type="button" className={`btn-sm ${taken ? 'btn-gray' : 'btn-tinted'}`} disabled={taken}
                  aria-label={taken ? `${e.title}: ${chosenLabel}` : `${mode === 'pick' ? 'Choose' : 'Add'} ${e.title}`}
                  onClick={() => onAdd(e)}>
                  {taken ? <Check size={14} /> : <Plus size={14} />}
                  {taken ? chosenLabel : mode === 'pick' ? 'Choose' : 'Add'}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )

  if (flat) {
    return (
      <div>
        {controls}
        {list}
        {matches && <p className="meta mt-2 px-1">{matches}</p>}
      </div>
    )
  }
  return (
    <SectionCard title="Library" aside={matches} flush>
      {controls}
      {list}
    </SectionCard>
  )
}
