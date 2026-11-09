import { useId } from 'react'
import type { Requirement } from '../../api/hep'
import SegmentedControl from '../../components/SegmentedControl'
import { REQUIREMENT_OPTIONS, WEEKDAYS, requirementOf } from './scheduleCopy'

/** The small label over a field, as every exercise form writes it. */
export const LABEL = 'mb-1 block px-1 text-label font-medium tracking-label text-secondary'

/** A count as a field — sets, reps, a hold in seconds, a target RPE — or,
 *  with `step`, a weight in kilograms. Kept as a string while editing so a
 *  cleared field does not snap back to 0. */
export function NumberField({
  id,
  label,
  value,
  onChange,
  disabled = false,
  min = 0,
  max = 999,
  step,
  placeholder,
}: {
  id: string
  label: string
  value: string
  onChange: (v: string) => void
  disabled?: boolean
  min?: number
  max?: number
  /** `0.5` for kilograms; whole numbers otherwise. */
  step?: number
  placeholder?: string
}) {
  return (
    <div>
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      <input
        id={id}
        type="number"
        inputMode={step ? 'decimal' : 'numeric'}
        min={min}
        max={max}
        step={step}
        placeholder={placeholder}
        className="field !min-h-10 !py-1.5 tabular-nums"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

/** "Clip of their attempt" / "Wearable on": off, optional or required, as
 *  a small segmented control under its label. The three words are the
 *  state; the thumb only echoes it. */
export function RequirementControl({
  label,
  value,
  onChange,
  disabled = false,
  hint,
  className = '',
}: {
  label: string
  value: string
  onChange: (v: Requirement) => void
  disabled?: boolean
  /** One line of meta under the control. */
  hint?: string
  className?: string
}) {
  const labelId = useId()
  return (
    <div className={className}>
      <span id={labelId} className={LABEL}>
        {label}
      </span>
      <SegmentedControl<Requirement>
        options={REQUIREMENT_OPTIONS.map((o) => ({ ...o, disabled }))}
        value={requirementOf(value)}
        onChange={onChange}
        size="sm"
        role="radiogroup"
        aria-labelledby={labelId}
        fullWidth
      />
      {hint && <p className="meta mt-1 px-1">{hint}</p>}
    </div>
  )
}

/** The days of the week an exercise lands on, Monday first, as seven
 *  checkboxes drawn as capsules. None checked reads "Every day" and is sent
 *  as null, which the server treats the same way. */
export function WeekdayPicker({
  label = 'Days',
  value,
  onChange,
  disabled = false,
}: {
  label?: string
  value: number[] | null
  onChange: (v: number[] | null) => void
  disabled?: boolean
}) {
  const chosen = value ?? []
  const toggle = (d: number) => {
    const next = chosen.includes(d) ? chosen.filter((x) => x !== d) : [...chosen, d].sort((a, b) => a - b)
    onChange(next.length === 0 || next.length === 7 ? null : next)
  }
  return (
    <fieldset disabled={disabled}>
      <legend className={LABEL}>
        {label} <span className="font-normal">{chosen.length === 0 ? '— every day' : ''}</span>
      </legend>
      <div className="flex flex-wrap gap-1.5">
        {WEEKDAYS.map((w) => {
          const on = chosen.includes(w.key)
          return (
            <label
              key={w.key}
              className={`inline-flex min-h-8 min-w-11 cursor-pointer select-none items-center justify-center gap-1.5 rounded-pill px-2.5 text-label font-medium ring-1 ring-inset transition-colors duration-state ease-apple has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus ${
                disabled
                  ? 'cursor-not-allowed text-disabled-ink ring-hairline'
                  : on
                    ? 'bg-brand-tint text-brand-ink ring-brand-tint-strong'
                    : 'bg-panel/70 text-ink ring-line-strong/60 hover:bg-panel'
              }`}
            >
              <input
                type="checkbox"
                className="sr-only"
                checked={on}
                disabled={disabled}
                onChange={() => toggle(w.key)}
              />
              <span aria-hidden>{w.short}</span>
              <span className="sr-only">{w.long}</span>
            </label>
          )
        })}
      </div>
    </fieldset>
  )
}
