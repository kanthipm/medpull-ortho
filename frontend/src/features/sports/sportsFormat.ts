import type { Availability, ReadinessBand, TeamEvent } from '../../api/sports'
import type { ReadoutTone } from '../../components/MetricCluster'
import type { MetricStatus } from '../../lib/risk'

/* Number and date copy for the team pages. No components here, so React
   Fast Refresh keeps the page modules components-only. */

/** The console's dash for a number that is not there. */
export const DASH = '—'
const MINUS = '−'

function places(v: number, dp: number): string {
  return Math.abs(v).toLocaleString(undefined, {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  })
}

/** Tabular figure with a true minus (U+2212, R19); "—" for null. */
export function fmt(v: number | null | undefined, dp = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH
  return `${v < 0 ? MINUS : ''}${places(v, dp)}`
}

/** "+2.1 bpm" / "−0.3 bpm" / "0.0 bpm": a change, signed. */
export function signed(v: number | null | undefined, dp = 0, unit = ''): string {
  if (v == null || !Number.isFinite(v)) return DASH
  const r = Number(v.toFixed(dp))
  const sign = r > 0 ? '+' : r < 0 ? MINUS : ''
  return `${sign}${places(r, dp)}${unit}`
}

/** A z-score as "±x.x SD". */
export function sd(z: number | null | undefined): string {
  return signed(z, 1, ' SD')
}

/** A percentage change as "+22%". */
export function pct(v: number | null | undefined): string {
  return signed(v, 0, '%')
}

/** "79th", "1st", "22nd". */
export function ordinal(n: number): string {
  const r = n % 100
  const suffix = r >= 11 && r <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] ?? 'th'
  return `${n}${suffix}`
}

export const TONE_TEXT: Record<ReadoutTone, string> = {
  high: 'text-risk-high-ink',
  med: 'text-risk-med-ink',
  low: 'text-risk-low-ink',
  missing: 'text-risk-missing-ink',
}

/** Weekly load step: over 15% is the published risk step, over 10% worth a
 *  look. A drop carries no tone. */
export function loadTone(changePct: number | null | undefined): ReadoutTone | undefined {
  if (changePct == null) return undefined
  if (changePct > 15) return 'high'
  if (changePct > 10) return 'med'
  return undefined
}

export function bandTone(band: ReadinessBand | null | undefined): ReadoutTone | undefined {
  if (band === 'red') return 'high'
  if (band === 'amber') return 'med'
  if (band === 'green') return 'low'
  return undefined
}

/** The band in words, so a toned score never rests on colour alone. */
export const BAND_WORD: Record<ReadinessBand, string> = {
  green: 'Ready',
  amber: 'Steady',
  red: 'Run down',
}

export function statusTone(status: MetricStatus | null | undefined): ReadoutTone | undefined {
  if (status === 'flag') return 'high'
  if (status === 'watch') return 'med'
  return undefined
}

/** A z-score's tone: one SD off is the edge of the engine's band. */
export function zTone(z: number | null | undefined): ReadoutTone | undefined {
  if (z == null) return undefined
  if (z <= -1) return 'high'
  if (z <= -0.5) return 'med'
  return undefined
}

/** Limb symmetry: 90% is the return-to-sport gate, 85% the phase gate. */
export function lsiTone(lsi: number | null | undefined): ReadoutTone | undefined {
  if (lsi == null) return undefined
  if (lsi >= 90) return 'low'
  if (lsi >= 85) return 'med'
  return 'high'
}

export const AVAILABILITY_LABEL: Record<Availability, string> = {
  available: 'Available',
  modified: 'Modified',
  out: 'Out',
}

/* ── Dates. Date-only strings are anchored to local midnight so "2026-10-19"
   never renders as the 18th in the Americas. ─────────────────────────── */

function local(iso: string): Date {
  return new Date(/^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso)
}

export function toIso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

export function addDays(iso: string, n: number): string {
  const d = local(iso)
  d.setDate(d.getDate() + n)
  return toIso(d)
}

export function daysBetween(fromIso: string, toIsoDate: string): number {
  return Math.round((local(toIsoDate).getTime() - local(fromIso).getTime()) / 86_400_000)
}

export function weekday(iso: string, style: 'short' | 'long' = 'short'): string {
  return local(iso).toLocaleDateString([], { weekday: style })
}

export function longDateOf(iso: string): string {
  return local(iso).toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })
}

/** "Feb 14, 2027" — for a projected date that may be next season. */
export function dateWithYear(iso: string): string {
  return local(iso).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
}

/** "3:30 PM" from the API's "15:30". */
export function timeLabel(hhmm: string | null | undefined): string | null {
  if (!hhmm) return null
  const [h, m] = hhmm.split(':').map(Number)
  if (!Number.isFinite(h)) return hhmm
  return new Date(2000, 0, 1, h, Number.isFinite(m) ? m : 0).toLocaleTimeString([], {
    hour: 'numeric',
    minute: '2-digit',
  })
}

/** "Week 24" from 23.9 weeks since surgery. */
export function weekLabel(weeks: number): string {
  return `Week ${Math.max(1, Math.floor(weeks) + 1)}`
}

/** `in_season` -> "In season". */
export function words(key: string | null | undefined): string {
  if (!key) return ''
  const w = key.replace(/[_-]+/g, ' ').trim()
  return w.charAt(0).toUpperCase() + w.slice(1)
}

export function isGame(e: TeamEvent): boolean {
  return e.kind === 'game' || e.kind === 'match'
}

/** The next game on or after `asOf`, if the schedule has one. */
export function nextGame(events: TeamEvent[], asOf: string): TeamEvent | null {
  return (
    [...events]
      .filter((e) => isGame(e) && e.date >= asOf)
      .sort((a, b) => a.date.localeCompare(b.date) || (a.start_time ?? '').localeCompare(b.start_time ?? ''))[0] ?? null
  )
}

/** "vs Prairie View A&M" / "at Bayou State" / the title when no opponent. */
export function opponentLine(e: TeamEvent): string {
  if (!e.opponent) return e.title
  return `${e.home === false ? 'at' : 'vs'} ${e.opponent}`
}

/** A reading out of the loose `extra` records, or null. */
export function numberOf(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/** "Today", "Yesterday", else "Mon, Sep 14" (with the year when it differs). */
export function dayLabel(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const today = new Date()
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const diff = Math.round((startOf(today) - startOf(d)) / 86_400_000)
  if (diff === 0) return 'Today'
  if (diff === 1) return 'Yesterday'
  return d.toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...(d.getFullYear() !== today.getFullYear() ? { year: 'numeric' } : {}),
  })
}

/** Mean per calendar day over the `days` ending on `asOf`, rest days as 0 —
 *  the dashed reference LoadBars draws. */
export function meanPerDay(
  data: { date: string; value: number | null }[],
  asOf: string,
  days = 28,
): number {
  const start = addDays(asOf, -(days - 1))
  const total = data
    .filter((p) => p.date >= start && p.date <= asOf)
    .reduce((a, p) => a + (p.value ?? 0), 0)
  return total / days
}

/* ── The calendar's event kinds. Hue by category, never by state: games clay,
   team work sage, the weight room amber, light or no days lilac. The kind's
   word is always printed beside its mark. ─────────────────────────────── */

export const EVENT_KIND: Record<string, { label: string; dot: string; family: 'violet' | 'teal' | 'blue' | 'indigo' }> = {
  game: { label: 'Game', dot: 'bg-cat-violet-ink', family: 'violet' },
  match: { label: 'Match', dot: 'bg-cat-violet-ink', family: 'violet' },
  practice: { label: 'Practice', dot: 'bg-cat-teal-ink', family: 'teal' },
  training: { label: 'Training', dot: 'bg-cat-teal-ink', family: 'teal' },
  conditioning: { label: 'Conditioning', dot: 'bg-cat-teal-ink', family: 'teal' },
  lift: { label: 'Lift', dot: 'bg-cat-blue-ink', family: 'blue' },
  shootaround: { label: 'Shootaround', dot: 'bg-cat-indigo-ink', family: 'indigo' },
  recovery: { label: 'Recovery', dot: 'bg-cat-indigo-ink', family: 'indigo' },
  travel: { label: 'Travel', dot: 'bg-cat-indigo-ink', family: 'indigo' },
  off: { label: 'Day off', dot: 'bg-line-strong', family: 'indigo' },
}

export function eventKind(kind: string) {
  return EVENT_KIND[kind] ?? { label: words(kind), dot: 'bg-line-strong', family: 'teal' as const }
}

/** "3:30 PM · vs Prairie View A&M" / "Practice": one event in a line. */
export function eventLine(e: TeamEvent): string {
  const when = timeLabel(e.start_time)
  const what = e.opponent ? opponentLine(e) : e.title
  return [when, what].filter(Boolean).join(' · ')
}

/** The first day of the month `iso` falls in, and of the one `n` months on. */
export function monthStart(iso: string, n = 0): string {
  const d = local(iso)
  return toIso(new Date(d.getFullYear(), d.getMonth() + n, 1))
}

/** The Monday on or before `iso`. */
export function weekStart(iso: string): string {
  return addDays(iso, -((local(iso).getDay() + 6) % 7))
}

/** "November 2026" */
export function monthName(iso: string): string {
  return local(iso).toLocaleDateString([], { month: 'long', year: 'numeric' })
}

export function dayNumber(iso: string): number {
  return local(iso).getDate()
}

export function inMonth(iso: string, month: string): boolean {
  return iso.slice(0, 7) === month.slice(0, 7)
}

/** A sortable column of the roster's data table. */
export type SortDir = 'asc' | 'desc'

export function compareNullable(a: number | null | undefined, b: number | null | undefined, dir: SortDir): number {
  // A missing reading sorts last whichever way the column runs.
  const an = a == null || !Number.isFinite(a)
  const bn = b == null || !Number.isFinite(b)
  if (an && bn) return 0
  if (an) return 1
  if (bn) return -1
  return dir === 'asc' ? (a as number) - (b as number) : (b as number) - (a as number)
}
