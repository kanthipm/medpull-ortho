import type { Exercise, LoadUnit, Requirement, Template, TemplateItem, TemplateItemBody } from '../../api/hep'
import { countOf, doseText, fieldOf, requirementOf, vocabLabel } from './scheduleCopy'
import { loadField, loadKg } from './units'

/** Copy and helpers for the Programs pages, kept out of the component
 *  modules so fast refresh keeps working. A program is a template: a
 *  clinic's pattern of exercises by weekday that `apply` puts on a
 *  patient's calendar from a start date. */

/** One row in the editor: the exercise as the clinician sees it plus its
 *  dose and requirements. Numbers are strings while editing so a cleared
 *  field does not snap back to 0. `load_kg` holds what the load field shows,
 *  which is in the clinic's own unit; it is turned into kilograms on the
 *  way out (`toItemBody`) and back on the way in (`itemFromTemplate`). */
export interface ProgramItem {
  exercise_id: number
  exercise_key: string | null
  title: string
  body_region_label: string
  category_label: string
  media_playable: boolean
  /** Monday 0 … Sunday 6; null for every day. */
  weekdays: number[] | null
  sets: string
  reps: string
  hold_seconds: string
  load_kg: string
  rpe_target: string
  side: string
  clinician_instructions: string
  video_requirement: Requirement
  wearable_requirement: Requirement
}

export interface ProgramDraft {
  name: string
  description: string
  weeks: string
  items: ProgramItem[]
}

export const DEFAULT_WEEKS = 4

export function blankProgram(): ProgramDraft {
  return { name: '', description: '', weeks: String(DEFAULT_WEEKS), items: [] }
}

export function itemFromExercise(e: Exercise): ProgramItem {
  return {
    exercise_id: e.id,
    exercise_key: e.key,
    title: e.title,
    body_region_label: e.body_region_label,
    category_label: e.category_label,
    media_playable: Boolean(e.clinic_media?.playable || e.media?.playable),
    weekdays: null,
    sets: '',
    reps: '',
    hold_seconds: '',
    load_kg: '',
    rpe_target: '',
    side: 'not_applicable',
    clinician_instructions: '',
    video_requirement: 'optional',
    wearable_requirement: 'optional',
  }
}

/** A saved item back into the editor. The template payload carries no
 *  region or clip, so those read from the library when it is loaded. */
export function itemFromTemplate(i: TemplateItem, library?: Exercise, unit: LoadUnit = 'kg'): ProgramItem {
  return {
    exercise_id: i.exercise_id,
    exercise_key: i.exercise_key ?? library?.key ?? null,
    title: i.title || library?.title || `Exercise ${i.exercise_id}`,
    body_region_label: library?.body_region_label ?? '',
    category_label: library?.category_label ?? '',
    media_playable: Boolean(library?.clinic_media?.playable || library?.media?.playable),
    weekdays: i.weekdays && i.weekdays.length > 0 && i.weekdays.length < 7 ? [...i.weekdays].sort((a, b) => a - b) : null,
    sets: fieldOf(i.sets),
    reps: fieldOf(i.reps),
    hold_seconds: fieldOf(i.hold_seconds),
    load_kg: loadField(i.load_kg, unit),
    rpe_target: fieldOf(i.rpe_target),
    side: i.side || 'not_applicable',
    clinician_instructions: i.clinician_instructions ?? '',
    video_requirement: requirementOf(i.video_requirement),
    wearable_requirement: requirementOf(i.wearable_requirement),
  }
}

export function draftFromTemplate(t: Template, library: Exercise[] = [], unit: LoadUnit = 'kg'): ProgramDraft {
  const byId = new Map(library.map((e) => [e.id, e]))
  return {
    name: t.name,
    description: t.description ?? '',
    weeks: String(t.weeks),
    items: t.items.map((i) => itemFromTemplate(i, byId.get(i.exercise_id), unit)),
  }
}

export function toItemBody(i: ProgramItem, unit: LoadUnit = 'kg'): TemplateItemBody {
  return {
    exercise_id: i.exercise_id,
    exercise_key: i.exercise_key ?? undefined,
    title: i.title,
    weekdays: i.weekdays && i.weekdays.length > 0 && i.weekdays.length < 7 ? i.weekdays : null,
    sets: countOf(i.sets),
    reps: countOf(i.reps),
    hold_seconds: countOf(i.hold_seconds),
    side: i.side,
    load_kg: loadKg(i.load_kg, unit),
    rpe_target: countOf(i.rpe_target),
    clinician_instructions: i.clinician_instructions.trim(),
    video_requirement: i.video_requirement,
    wearable_requirement: i.wearable_requirement,
  }
}

/** What the server would receive, as a stable string, for dirty tracking. */
export function serializeProgram(d: ProgramDraft, unit: LoadUnit = 'kg'): string {
  return JSON.stringify({
    name: d.name.trim(),
    description: d.description.trim(),
    weeks: countOf(d.weeks),
    items: d.items.map((i) => toItemBody(i, unit)),
  })
}

/** The dose line of an editor row, as the patient will read it. */
export function editorItemDose(
  i: ProgramItem,
  sides: { key: string; label: string }[],
  unit: LoadUnit = 'kg',
): string {
  return doseText({
    sets: i.sets,
    reps: i.reps,
    hold: i.hold_seconds,
    load: i.load_kg,
    side: i.side,
    sideLabel: vocabLabel(sides, i.side),
    unit,
  })
}

/** The dose line of a saved item (the apply dialog, the programs list). */
export function programItemDose(i: TemplateItem, unit: LoadUnit = 'kg'): string {
  return doseText({
    sets: fieldOf(i.sets),
    reps: fieldOf(i.reps),
    hold: fieldOf(i.hold_seconds),
    load: loadField(i.load_kg, unit),
    side: i.side,
    sideLabel: SIDE_LABEL[i.side] ?? '',
    unit,
  })
}

const SIDE_LABEL: Record<string, string> = { left: 'Left', right: 'Right', both: 'Both', not_applicable: '' }
