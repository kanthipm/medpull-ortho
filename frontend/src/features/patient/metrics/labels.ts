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
  const out =
    abs >= 1000
      ? Math.round(v).toLocaleString()
      : abs >= 10
        ? String(Math.round(v * 10) / 10)
        : String(Math.round(v * 100) / 100)
  // A negative reading carries a true minus (U+2212, R19), never a hyphen.
  return out.replace('-', '\u2212')
}

/** Readable names for the engine's `metric_type` keys (backend
 *  app/models/enums.py MetricType). Keys that read fine as words are left to
 *  the fallback. */
const METRIC_TYPE_LABEL: Record<string, string> = {
  resting_hr: 'Resting heart rate',
  hr_sample: 'Heart rate samples',
  hrv_rmssd: 'HRV (RMSSD)',
  hrv_sdnn: 'HRV (SDNN)',
  spo2: 'Blood oxygen',
  skin_temp: 'Skin temperature',
  skin_temp_delta: 'Skin temperature change',
  double_support_pct: 'Double support',
  walking_asymmetry_pct: 'Walking asymmetry',
  stair_speed_up: 'Stair speed up',
  stair_speed_down: 'Stair speed down',
  six_min_walk: 'Six-minute walk',
  wear_time_minutes: 'Wear time',
  pain_nrs: 'Pain score',
  prom_score: 'PROM score',
  bp_systolic: 'Blood pressure, systolic',
  bp_diastolic: 'Blood pressure, diastolic',
}

/** `metric_type` keys read as words: `hrv_rmssd` → "HRV (RMSSD)", and
 *  anything unmapped falls back to `sleep_duration` → "Sleep duration". */
export function metricTypeLabel(key: string): string {
  return METRIC_TYPE_LABEL[key] ?? taskKindLabel(key)
}
