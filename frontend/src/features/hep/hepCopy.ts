import type { ExerciseBody, ExerciseStatus } from '../../api/hep'

/** Copy and helpers for the exercise library, kept out of the component
 *  modules so fast refresh keeps working. */

export const STATUS_CHIP: Record<ExerciseStatus, { label: string; pill: string }> = {
  draft: { label: 'Draft', pill: 'bg-soft text-secondary' },
  review: { label: 'In review', pill: 'bg-risk-med-tint text-risk-med-ink' },
  approved: { label: 'Approved', pill: 'bg-risk-low-tint text-risk-low-ink' },
  archived: { label: 'Archived', pill: 'bg-risk-missing-tint text-risk-missing-ink' },
}

export function statusChip(status: string) {
  return STATUS_CHIP[status as ExerciseStatus] ?? { label: status, pill: 'bg-soft text-secondary' }
}

export interface ExerciseDraft {
  title: string
  body_region: string
  category: string
  steps: string
  synonyms: string
  equipment: string
  precautions: string
}

export function blankExercise(region = 'knee', category = 'mobility'): ExerciseDraft {
  return { title: '', body_region: region, category, steps: '', synonyms: '', equipment: '', precautions: '' }
}

export function toBody(d: ExerciseDraft): ExerciseBody {
  return {
    title: d.title.trim(),
    body_region: d.body_region,
    category: d.category,
    instructions: d.steps
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
      .join('\n'),
    synonyms: d.synonyms
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
    equipment: d.equipment.trim(),
    precautions: d.precautions.trim(),
  }
}

/** The same warning the care-plan forms give: patient-facing wording must not
 *  read as a diagnosis (the server refuses it with 422). */
export function diagnosticWarning(text: string): string | null {
  return /\b(detect|diagnos)/i.test(text)
    ? 'Avoid "detect" or "diagnose" — patients read this text.'
    : null
}
