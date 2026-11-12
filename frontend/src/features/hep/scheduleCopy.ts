import type { Assignment, AssignmentState, AssignmentStatus, LoadUnit, Requirement } from '../../api/hep'
import { REQUIREMENTS, isoDate } from '../../api/hep'
import { signedPct } from '../../lib/format'
import { PRIORITY, type Priority } from '../../lib/risk'
import { titleCase } from './planCopy'
import { loadKg, loadText } from './units'

/** Copy and date helpers for the exercise schedule, kept out of the
 *  component modules so fast refresh keeps working. Dates are YYYY-MM-DD in
 *  the browser's local calendar throughout; the routes take the same. */

// --- dates ------------------------------------------------------------------------

/** Local midnight for a date-only string. A bare "2026-11-09" handed to
 *  `new Date` parses as UTC midnight and prints as the 8th in the Americas. */
export function parseIso(iso: string): Date {
  const [y, m, d] = iso.split('-').map(Number)
  return new Date(y, m - 1, d)
}

export function addDays(iso: string, n: number): string {
  const d = parseIso(iso)
  d.setDate(d.getDate() + n)
  return isoDate(d)
}

/** The Monday on or before `iso`: the week the grid shows. */
export function mondayOf(iso: string): string {
  const back = (parseIso(iso).getDay() + 6) % 7 // Mon 0 … Sun 6
  return addDays(iso, -back)
}

export function weekDays(start: string, n = 7): string[] {
  return Array.from({ length: n }, (_, i) => addDays(start, i))
}

/** "Mon" */
export function weekdayShort(iso: string): string {
  return parseIso(iso).toLocaleDateString([], { weekday: 'short' })
}

/** "9" */
export function dayOfMonth(iso: string): string {
  return String(parseIso(iso).getDate())
}

/** "Nov 9" */
export function monthDay(iso: string): string {
  return parseIso(iso).toLocaleDateString([], { month: 'short', day: 'numeric' })
}

/** "Monday, November 9" */
export function longDay(iso: string): string {
  return parseIso(iso).toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })
}

/** "Mon 9" — a day as a checkbox or option label. */
export function shortDay(iso: string): string {
  return `${weekdayShort(iso)} ${dayOfMonth(iso)}`
}

/** "Nov 9 – 15", "Nov 30 – Dec 6"; the year only when it is not this one. */
export function rangeLabel(days: string[]): string {
  if (days.length === 0) return ''
  const a = parseIso(days[0])
  const b = parseIso(days[days.length - 1])
  const sameMonth = a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear()
  const left = a.toLocaleDateString([], { month: 'short', day: 'numeric' })
  const right = sameMonth
    ? String(b.getDate())
    : b.toLocaleDateString([], { month: 'short', day: 'numeric' })
  const year = b.getFullYear() !== new Date().getFullYear() ? `, ${b.getFullYear()}` : ''
  return `${left} – ${right}${year}`
}

/** The first day of the month `iso` falls in. */
export function firstOfMonth(iso: string): string {
  const d = parseIso(iso)
  return isoDate(new Date(d.getFullYear(), d.getMonth(), 1))
}

/** The first day of the month `n` months from the one `iso` falls in. */
export function addMonths(iso: string, n: number): string {
  const d = parseIso(iso)
  return isoDate(new Date(d.getFullYear(), d.getMonth() + n, 1))
}

/** "November 2026" */
export function monthLabel(iso: string): string {
  return parseIso(iso).toLocaleDateString([], { month: 'long', year: 'numeric' })
}

export function sameMonth(a: string, b: string): boolean {
  return a.slice(0, 7) === b.slice(0, 7)
}

/** The server takes dates within −60…+90 days of today. */
export const ASSIGN_PAST_DAYS = 60
export const ASSIGN_FUTURE_DAYS = 90

export function assignable(iso: string, today: string): boolean {
  return iso >= addDays(today, -ASSIGN_PAST_DAYS) && iso <= addDays(today, ASSIGN_FUTURE_DAYS)
}

// --- dragging a chip ---------------------------------------------------------------

/** The type a dragged chip carries: `{id, patientId, date, done}` as JSON. */
export const DRAG_TYPE = 'application/x-medpull-assignment'

export interface DraggedChip {
  id: number
  patientId: string
  date: string
  /** A done or skipped day: it stays where it is and can only be copied. */
  done: boolean
}

export function readDragged(raw: string): DraggedChip | null {
  try {
    const v = JSON.parse(raw) as Partial<DraggedChip>
    if (typeof v.id !== 'number' || typeof v.patientId !== 'string' || typeof v.date !== 'string') return null
    return { id: v.id, patientId: v.patientId, date: v.date, done: v.done === true }
  } catch {
    return null
  }
}

// --- status ------------------------------------------------------------------------

export const STATUS_CHIP: Record<AssignmentStatus, { label: string; pill: string }> = {
  assigned: { label: 'Assigned', pill: 'bg-soft text-secondary' },
  done: { label: 'Done', pill: 'bg-risk-low-tint text-risk-low-ink' },
  skipped: { label: 'Skipped', pill: 'bg-risk-missing-tint text-risk-missing-ink' },
}

export function statusChip(status: string) {
  return STATUS_CHIP[status as AssignmentStatus] ?? { label: titleCase(status), pill: 'bg-soft text-secondary' }
}

/** Where a row stands on its day. The server works it out from the status
 *  and the clinician's own `today`; a server from before the field leaves
 *  the status, which says three of the six. */
export function stateOf(a: { state?: string; status: string }): AssignmentState {
  const state = a.state as AssignmentState | undefined
  if (state && state in STATE_CHIP) return state
  if (a.status === 'done') return 'done'
  if (a.status === 'skipped') return 'skipped'
  return 'upcoming'
}

export const STATE_CHIP: Record<AssignmentState, { label: string; pill: string }> = {
  upcoming: { label: 'Assigned', pill: 'bg-soft text-secondary' },
  due: { label: 'Due today', pill: 'bg-brand-tint text-brand-ink' },
  in_progress: { label: 'In progress', pill: 'bg-brand-tint text-brand-ink' },
  done: { label: 'Done', pill: 'bg-risk-low-tint text-risk-low-ink' },
  skipped: { label: 'Skipped', pill: 'bg-risk-missing-tint text-risk-missing-ink' },
  missed: { label: 'Missed', pill: 'bg-risk-med-tint text-risk-med-ink' },
}

/** Whether the server says a done row waits for a look, and why. Falls back
 *  to the first definition (a clip nobody has answered) on an older server. */
export function reviewReason(a: Assignment): 'clip' | 'over' | null {
  const c = a.completion
  if (a.status !== 'done' || !c) return null
  if (c.awaiting_review === false) return null
  if (c.review_reason) return c.review_reason
  return c.video && !c.review ? 'clip' : null
}

/** Pain after the exercise: 5 and up takes the warning tone. The number is
 *  always printed beside it, so the tone never carries the state alone. */
export function painChipClass(pain: number): string {
  return pain >= 5 ? 'bg-risk-med-tint text-risk-med-ink' : 'bg-risk-low-tint text-risk-low-ink'
}

/** `risk_tier` is the engine's lower-case tier, so it maps onto the console's
 *  recipes when it is one of them. */
export function tierKey(tier: string | null | undefined): Priority | undefined {
  return tier && tier in PRIORITY ? (tier as Priority) : undefined
}

export function tierChip(tier: string | null | undefined): { label: string; pill: string } | null {
  if (!tier) return null
  const key = tierKey(tier)
  if (key) return { label: PRIORITY[key].label, pill: PRIORITY[key].pill }
  return { label: titleCase(tier), pill: 'bg-soft text-secondary' }
}

/** Where a completion came from, in a sentence. */
export function completionSource(source: string | null | undefined): string {
  if (source === 'console') return 'logged in the room'
  if (source === 'app') return 'from their phone'
  return source ? titleCase(source) : ''
}

/** A done row that waits for the therapist: a clip nobody has answered, or
 *  a session over the dose nobody has looked at. */
export function awaitingReview(a: Assignment): boolean {
  return reviewReason(a) != null
}

/** The accessible name of a chip: everything its marks say. */
export function assignmentSummary(a: Assignment): string {
  const parts = [a.title]
  if (a.dose) parts.push(a.dose)
  const state = stateOf(a)
  if (state === 'done') {
    parts.push('done')
    if (a.completion?.pain_after != null) parts.push(`pain ${a.completion.pain_after} of 10`)
    if (a.completion?.effort != null) parts.push(`effort ${a.completion.effort} of 10`)
    if (a.completion?.over) parts.push('more than prescribed')
    else if (a.completion?.under) parts.push('less than prescribed')
    if (awaitingReview(a)) parts.push('awaiting review')
  } else if (state === 'skipped') {
    parts.push('skipped')
  } else if (state === 'missed') {
    parts.push('missed')
  } else if (state === 'in_progress') {
    parts.push('in progress on their phone')
  } else if (state === 'due') {
    parts.push('due today')
  }
  if (a.series_id) parts.push('part of a repeat')
  if (a.video) parts.push('has a clip')
  return parts.join(', ')
}

// --- requirements ---------------------------------------------------------------

/** The server's default when a row predates the field or carries something
 *  the console does not know. */
export function requirementOf(value: string | null | undefined): Requirement {
  return REQUIREMENTS.includes(value as Requirement) ? (value as Requirement) : 'optional'
}

export const REQUIREMENT_LABEL: Record<Requirement, string> = {
  off: 'Off',
  optional: 'Optional',
  required: 'Required',
}

export const REQUIREMENT_OPTIONS = REQUIREMENTS.map((key) => ({ key, label: REQUIREMENT_LABEL[key] }))

/** One line under the dose: what she asked for with this exercise, or
 *  nothing when both are left optional. */
export function requirementsText(video: string, wearable: string): string {
  const parts: string[] = []
  const v = requirementOf(video)
  const w = requirementOf(wearable)
  if (v === 'required') parts.push('a clip of their attempt')
  if (w === 'required') parts.push('the wearable on')
  const asked = parts.length ? `Asks for ${parts.join(' and ')}` : ''
  const off: string[] = []
  if (v === 'off') off.push('no clip')
  if (w === 'off') off.push('no wearable')
  return [asked, off.length ? `${off.join(', ')} for this one` : ''].filter(Boolean).join(' · ')
}

// --- adherence and load ----------------------------------------------------------

/** Done over assigned for the seven days ending today: the calm tone from
 *  60%, amber under it, red under 30%. The numbers are always printed
 *  beside it, so the tone never carries the state alone. */
export function adherenceChipClass(pct: number): string {
  if (pct < 30) return 'bg-risk-high-tint text-risk-high-ink'
  if (pct < 60) return 'bg-risk-med-tint text-risk-med-ink'
  return 'bg-risk-low-tint text-risk-low-ink'
}

/** "3 of 4 · 75%" */
export function adherenceText(done: number, assigned: number, pct: number): string {
  return `${done} of ${assigned} · ${Math.round(pct)}%`
}

/** "load +12%", or nothing when there is no last week to compare with. */
export function loadTrendText(changePct: number | null | undefined): string | null {
  if (changePct == null || !Number.isFinite(changePct)) return null
  return `load ${signedPct(changePct)}`
}

/** "12 kg", "12.5 kg" */
export function kgText(kg: number): string {
  const rounded = Math.round(kg * 10) / 10
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)} kg`
}

/** "+12% vs last week", for a load written or done against the week before. */
export function changeText(changePct: number | null | undefined): string | null {
  if (changePct == null || !Number.isFinite(changePct)) return null
  return changePct === 0 ? 'level with last week' : `${signedPct(changePct)} vs last week`
}

/** "11 min", "45 s", "1 h 05 min" */
export function durationText(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  if (s < 60) return `${s} s`
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  return `${h} h ${String(m % 60).padStart(2, '0')} min`
}

/** A session's length: the server's `duration_s`, else the two ends. */
export function sessionSeconds(session: {
  duration_s: number | null
  started_at: string | null
  ended_at: string | null
} | null | undefined): number | null {
  if (!session) return null
  if (session.duration_s != null) return session.duration_s
  if (session.started_at && session.ended_at) {
    const ms = new Date(session.ended_at).getTime() - new Date(session.started_at).getTime()
    return Number.isFinite(ms) && ms >= 0 ? ms / 1000 : null
  }
  return null
}

// --- weekdays (programs) ---------------------------------------------------------

/** Monday 0 … Sunday 6, as the server's `date.weekday()` numbers them. */
export const WEEKDAYS = [
  { key: 0, short: 'Mon', long: 'Monday' },
  { key: 1, short: 'Tue', long: 'Tuesday' },
  { key: 2, short: 'Wed', long: 'Wednesday' },
  { key: 3, short: 'Thu', long: 'Thursday' },
  { key: 4, short: 'Fri', long: 'Friday' },
  { key: 5, short: 'Sat', long: 'Saturday' },
  { key: 6, short: 'Sun', long: 'Sunday' },
] as const

/** "Every day", "Mon · Wed · Fri", "Weekdays", "Weekends". */
export function weekdaysLabel(days: number[] | null | undefined): string {
  if (!days || days.length === 0 || days.length === 7) return 'Every day'
  const sorted = [...new Set(days)].sort((a, b) => a - b)
  if (sorted.join() === '0,1,2,3,4') return 'Weekdays'
  if (sorted.join() === '5,6') return 'Weekends'
  return sorted.map((d) => WEEKDAYS[d]?.short ?? String(d)).join(' · ')
}

// --- the dose while it is being edited -------------------------------------------------

/** A whole number from a field, or null when it is empty. */
export function countOf(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? Math.round(n) : null
}

/** Kilograms from a field: a decimal to one place, or null when empty. */
export function decimalOf(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? Math.round(n * 10) / 10 : null
}

/** A number back into a field, or the empty string. */
export function fieldOf(n: number | null | undefined): string {
  return n == null ? '' : String(n)
}

/** The dose while it is being edited: the fields as strings. `load` is in
 *  the clinic's own unit (`unit`, kilograms when left out). */
export interface DoseDraft {
  sets: string
  reps: string
  hold: string
  load: string
  side: string
  sideLabel: string
  unit?: LoadUnit
}

/** Mirrors `plans.dose_line` without the frequency — what the chip and the
 *  patient read: "3 sets × 10 reps · hold 5 s · 12 kg · Left". */
export function doseText(d: DoseDraft): string {
  const s = countOf(d.sets)
  const r = countOf(d.reps)
  const h = countOf(d.hold)
  const unit = d.unit ?? 'kg'
  const kg = loadKg(d.load, unit)
  const parts: string[] = []
  if (s && r) parts.push(`${s} sets × ${r} reps`)
  else if (s) parts.push(`${s} sets`)
  else if (r) parts.push(`${r} reps`)
  if (h) parts.push(`hold ${h} s`)
  if (kg) parts.push(loadText(kg, unit))
  if (d.side !== 'not_applicable' && d.sideLabel) parts.push(d.sideLabel)
  return parts.join(' · ')
}

export function vocabLabel(vocab: { key: string; label: string }[], key: string): string {
  return vocab.find((v) => v.key === key)?.label ?? titleCase(key)
}

/** Which clip the clinic sees for an exercise: its own, else the library's. */
export function clipOf<T extends { playable: boolean; url: string | null }>(
  clinic: T | null | undefined,
  library: T | null | undefined,
): { clip: T; url: string; own: boolean } | null {
  if (clinic?.playable && clinic.url) return { clip: clinic, url: clinic.url, own: true }
  if (library?.playable && library.url) return { clip: library, url: library.url, own: false }
  return null
}
