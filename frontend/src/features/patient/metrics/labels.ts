import type { CareMetric } from '../../../api/care'
import { METRIC_STATUS } from '../../../lib/risk'

/** Copy helpers shared by the tiles, cards and charts. Kept out of the
 *  component modules so fast-refresh keeps working (components-only files). */

/** Provider-facing label for a task kind the engine names (`log_pain_am_pm`
 *  → "Log pain am pm"): the kinds are engine keys, not copy. */
export function taskKindLabel(kind: string): string {
  const words = kind.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Chip text: flag/watch carry the engine's short status line; OK and
 *  no-data get the tier label so the chip stays a verdict, not a sentence. */
export function statusChipText(m: CareMetric): string {
  if (m.status === 'flag' || m.status === 'watch') {
    return m.status_text || METRIC_STATUS[m.status].label
  }
  if (m.status === 'nodata') return 'Needs data'
  return METRIC_STATUS[m.status]?.label ?? 'OK'
}

/** The guardrail sentence for M12/M13-style metrics — verbatim, everywhere. */
export const GUARDED_NOTE = 'for review · not a diagnosis'

/** Compact number for chart tooltips and raw rows: thousands rounded, tens
 *  to one decimal, small values to two. */
export function fmtNum(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1000) return Math.round(v).toLocaleString()
  if (abs >= 10) return String(Math.round(v * 10) / 10)
  return String(Math.round(v * 100) / 100)
}

/** `metric_type` keys read as words: `walking_asymmetry_pct` → "Walking asymmetry pct". */
export function metricTypeLabel(key: string): string {
  return taskKindLabel(key)
}
