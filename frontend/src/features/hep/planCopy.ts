import type { Exercise, Plan, PlanItem, PlanItemBody, PlanStatus } from '../../api/hep'

/** Copy and helpers for the plan editor, kept out of the component modules. */

export const PLAN_STATUS: Record<PlanStatus, { label: string; pill: string }> = {
  draft: { label: 'Draft', pill: 'bg-soft text-secondary' },
  active: { label: 'Published', pill: 'bg-risk-low-tint text-risk-low-ink' },
  superseded: { label: 'Replaced', pill: 'bg-risk-missing-tint text-risk-missing-ink' },
  archived: { label: 'Archived', pill: 'bg-risk-missing-tint text-risk-missing-ink' },
}

export function planStatus(status: string) {
  return PLAN_STATUS[status as PlanStatus] ?? { label: status, pill: 'bg-soft text-secondary' }
}

/** One row in the editor tray: the exercise as the clinician sees it plus
 *  the dose. Numbers are kept as strings while editing so a cleared field
 *  does not snap back to 0. */
export interface EditorItem {
  exercise_id: number
  title: string
  body_region_label: string
  category_label: string
  steps: string[]
  equipment: string
  library_precautions: string
  media_playable: boolean
  sets: string
  reps: string
  hold_seconds: string
  frequency: string
  side: string
  clinician_instructions: string
  precautions_override: string
  /** True when the library wording moved on after this plan was published. */
  library_changed?: boolean
}

export function itemFromExercise(e: Exercise): EditorItem {
  return {
    exercise_id: e.id,
    title: e.title,
    body_region_label: e.body_region_label,
    category_label: e.category_label,
    steps: e.steps,
    equipment: e.equipment,
    library_precautions: e.precautions,
    media_playable: Boolean(e.media?.playable),
    sets: '',
    reps: '',
    hold_seconds: '',
    frequency: 'daily',
    side: 'not_applicable',
    clinician_instructions: '',
    precautions_override: '',
  }
}

export function itemFromPlan(i: PlanItem): EditorItem {
  return {
    exercise_id: i.exercise_id,
    title: i.title,
    body_region_label: i.library_current?.body_region_label ?? titleCase(i.body_region ?? ''),
    category_label: i.library_current?.category_label ?? titleCase(i.category ?? ''),
    steps: i.steps,
    equipment: i.equipment,
    library_precautions: i.library_precautions,
    media_playable: Boolean(i.media?.playable),
    sets: i.sets == null ? '' : String(i.sets),
    reps: i.reps == null ? '' : String(i.reps),
    hold_seconds: i.hold_seconds == null ? '' : String(i.hold_seconds),
    frequency: i.frequency,
    side: i.side,
    clinician_instructions: i.clinician_instructions,
    precautions_override: i.precautions_override,
    library_changed: i.library_changed,
  }
}

function num(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? Math.round(n) : null
}

export function toItemBody(i: EditorItem): PlanItemBody {
  return {
    exercise_id: i.exercise_id,
    sets: num(i.sets),
    reps: num(i.reps),
    hold_seconds: num(i.hold_seconds),
    frequency: i.frequency,
    side: i.side,
    clinician_instructions: i.clinician_instructions.trim(),
    precautions_override: i.precautions_override.trim(),
  }
}

/** Mirrors `app/hep/plans.py:dose_line` so the tray reads like the app. */
export function doseLine(i: EditorItem, frequencyLabel: string, sideLabel: string): string {
  const sets = num(i.sets)
  const reps = num(i.reps)
  const hold = num(i.hold_seconds)
  const parts: string[] = []
  if (sets && reps) parts.push(`${sets} sets × ${reps} reps`)
  else if (sets) parts.push(`${sets} sets`)
  else if (reps) parts.push(`${reps} reps`)
  if (hold) parts.push(`hold ${hold} s`)
  parts.push(frequencyLabel)
  if (i.side !== 'not_applicable' && sideLabel) parts.push(sideLabel)
  return parts.filter(Boolean).join(' · ')
}

export function titleCase(s: string): string {
  return s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** A stable string of what the server would receive, for dirty tracking. */
export function serialize(plan: {
  title: string
  notes: string
  patient_id: string | null
  assigned_by: string
  items: EditorItem[]
}): string {
  return JSON.stringify({
    title: plan.title.trim(),
    notes: plan.notes.trim(),
    patient_id: plan.patient_id,
    assigned_by: plan.assigned_by,
    items: plan.items.map(toItemBody),
  })
}

export function editable(plan: Plan | null | undefined): boolean {
  return !plan || plan.status === 'draft' || plan.status === 'active'
}
