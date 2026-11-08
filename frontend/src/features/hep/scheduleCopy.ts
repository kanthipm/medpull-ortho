import type { Assignment, AssignmentStatus } from '../../api/hep'
import { isoDate } from '../../api/hep'
import { PRIORITY, type Priority } from '../../lib/risk'
import { titleCase } from './planCopy'

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

/** The server takes dates within −60…+90 days of today. */
export const ASSIGN_PAST_DAYS = 60
export const ASSIGN_FUTURE_DAYS = 90

export function assignable(iso: string, today: string): boolean {
  return iso >= addDays(today, -ASSIGN_PAST_DAYS) && iso <= addDays(today, ASSIGN_FUTURE_DAYS)
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

/** The accessible name of a chip: everything its marks say. */
export function assignmentSummary(a: Assignment): string {
  const parts = [a.title]
  if (a.dose) parts.push(a.dose)
  if (a.status === 'done') {
    parts.push('done')
    if (a.completion?.pain_after != null) parts.push(`pain ${a.completion.pain_after} of 10`)
  } else if (a.status === 'skipped') {
    parts.push('skipped')
  }
  if (a.video) parts.push('has a clip')
  return parts.join(', ')
}

// --- the dose while it is being edited -------------------------------------------------

/** A whole number from a field, or null when it is empty. */
export function countOf(s: string): number | null {
  const t = s.trim()
  if (!t) return null
  const n = Number(t)
  return Number.isFinite(n) ? Math.round(n) : null
}

/** Mirrors `plans.dose_line` without the frequency — what the chip and the
 *  patient read: "3 sets × 10 reps · hold 5 s · Left". */
export function doseText(
  sets: string,
  reps: string,
  hold: string,
  side: string,
  sideLabel: string,
): string {
  const s = countOf(sets)
  const r = countOf(reps)
  const h = countOf(hold)
  const parts: string[] = []
  if (s && r) parts.push(`${s} sets × ${r} reps`)
  else if (s) parts.push(`${s} sets`)
  else if (r) parts.push(`${r} reps`)
  if (h) parts.push(`hold ${h} s`)
  if (side !== 'not_applicable' && sideLabel) parts.push(sideLabel)
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
