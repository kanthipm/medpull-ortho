import type { Vocab } from '../../api/hep'
import { diagnosticWarning, type ExerciseDraft } from './hepCopy'

const LABEL = 'mb-2 block text-copy font-medium text-body'

/** The custom-exercise fields, shared by "New exercise" and the edit view.
 *  Steps are one per line; synonyms are comma separated. */
export default function ExerciseForm({
  value,
  onChange,
  regions,
  categories,
  idPrefix = 'ex',
}: {
  value: ExerciseDraft
  onChange: (next: ExerciseDraft) => void
  regions: Vocab[]
  categories: Vocab[]
  idPrefix?: string
}) {
  const set = <K extends keyof ExerciseDraft>(key: K, v: ExerciseDraft[K]) => onChange({ ...value, [key]: v })
  const titleWarn = diagnosticWarning(value.title)
  const stepsWarn = diagnosticWarning(value.steps)
  const precWarn = diagnosticWarning(value.precautions)
  const id = (s: string) => `${idPrefix}-${s}`

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <label htmlFor={id('title')} className={LABEL}>
          Name
        </label>
        <input
          id={id('title')}
          className="field"
          value={value.title}
          onChange={(e) => set('title', e.target.value)}
          placeholder="e.g. Seated marching"
          maxLength={80}
          aria-describedby={titleWarn ? id('title-warn') : undefined}
        />
        {titleWarn && (
          <p id={id('title-warn')} className="mt-2 text-copy font-medium text-risk-med-ink">
            {titleWarn}
          </p>
        )}
      </div>
      <div>
        <label htmlFor={id('region')} className={LABEL}>
          Body region
        </label>
        <select
          id={id('region')}
          className="field cursor-pointer"
          value={value.body_region}
          onChange={(e) => set('body_region', e.target.value)}
        >
          {regions.map((r) => (
            <option key={r.key} value={r.key}>
              {r.label}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor={id('category')} className={LABEL}>
          Category
        </label>
        <select
          id={id('category')}
          className="field cursor-pointer"
          value={value.category}
          onChange={(e) => set('category', e.target.value)}
        >
          {categories.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
      </div>
      <div className="sm:col-span-2">
        <label htmlFor={id('steps')} className={LABEL}>
          Steps <span className="font-normal text-secondary">one per line, in plain words</span>
        </label>
        <textarea
          id={id('steps')}
          rows={5}
          className="field"
          value={value.steps}
          onChange={(e) => set('steps', e.target.value)}
          placeholder={'Sit tall at the front of a chair.\nLift one knee, then the other.'}
          maxLength={2000}
          aria-describedby={stepsWarn ? id('steps-warn') : undefined}
        />
        {stepsWarn && (
          <p id={id('steps-warn')} className="mt-2 text-copy font-medium text-risk-med-ink">
            {stepsWarn}
          </p>
        )}
      </div>
      <div>
        <label htmlFor={id('synonyms')} className={LABEL}>
          Also called <span className="font-normal text-secondary">comma separated</span>
        </label>
        <input
          id={id('synonyms')}
          className="field"
          value={value.synonyms}
          onChange={(e) => set('synonyms', e.target.value)}
          placeholder="seated march, high knees"
        />
      </div>
      <div>
        <label htmlFor={id('equipment')} className={LABEL}>
          Equipment
        </label>
        <input
          id={id('equipment')}
          className="field"
          value={value.equipment}
          onChange={(e) => set('equipment', e.target.value)}
          placeholder="None, or e.g. a sturdy chair"
          maxLength={120}
        />
      </div>
      <div className="sm:col-span-2">
        <label htmlFor={id('precautions')} className={LABEL}>
          Precautions
        </label>
        <textarea
          id={id('precautions')}
          rows={2}
          className="field"
          value={value.precautions}
          onChange={(e) => set('precautions', e.target.value)}
          placeholder="Hold the seat if you feel unsteady."
          maxLength={400}
          aria-describedby={precWarn ? id('prec-warn') : undefined}
        />
        {precWarn && (
          <p id={id('prec-warn')} className="mt-2 text-copy font-medium text-risk-med-ink">
            {precWarn}
          </p>
        )}
      </div>
    </div>
  )
}
