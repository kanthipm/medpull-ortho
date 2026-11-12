import {
  Activity,
  BatteryCharging,
  Dumbbell,
  Flame,
  HeartPulse,
  Moon,
  Scale,
  SmilePlus,
  Sunrise,
  TrendingUp,
  Waves,
  type LucideIcon,
} from 'lucide-react'
import type { DayValue, Panel, Trend } from '../../api/personal'
import type { TileFamily } from '../../components/Tile'
import { METRIC_STATUS, type MetricStatus } from '../../lib/risk'

/** Words, glyphs and small formatters the Personal pages share, kept out of
 *  the component files so those export components only. */

/** The verdict's gradient: the kind, never the mood. The words are on the
 *  tile and in its caption, so the hue is never the only thing saying it. */
export const VERDICT_TILE: Record<string, string> = {
  push: 'g-sage',
  steady: 'g-lilac',
  easy: 'g-amber',
  rest: 'g-clay',
  unknown: 'g-dusk',
}

export const VERDICT_WORD: Record<string, string> = {
  push: 'A day to do more',
  steady: 'A day as planned',
  easy: 'A day to do less',
  rest: 'A day off',
  unknown: 'Still learning',
}

export const PANEL_GLYPH: Record<string, { icon: LucideIcon; family: TileFamily }> = {
  readiness: { icon: BatteryCharging, family: 'teal' },
  sleep: { icon: Moon, family: 'indigo' },
  rhythm: { icon: Sunrise, family: 'indigo' },
  hrv: { icon: Waves, family: 'violet' },
  resting_hr: { icon: HeartPulse, family: 'violet' },
  body: { icon: Scale, family: 'violet' },
  activity: { icon: Activity, family: 'teal' },
  load: { icon: Dumbbell, family: 'teal' },
  fitness: { icon: TrendingUp, family: 'teal' },
  overreach: { icon: Flame, family: 'blue' },
  subjective: { icon: SmilePlus, family: 'blue' },
}

export function panelChip(status: string): string {
  return (METRIC_STATUS[status as MetricStatus] ?? METRIC_STATUS.nodata).pill
}

/** A number as short as it can honestly be: whole when it is one, else one
 *  place; thousands separated. */
export function short(n: number | null | undefined, places = 1): string {
  if (n == null || !Number.isFinite(n)) return '—'
  const fixed = Number(n.toFixed(places))
  return Math.abs(fixed) >= 1000 ? Math.round(fixed).toLocaleString() : String(fixed)
}

/** "7 h 06 min" from decimal hours. */
export function hoursMinutes(hours: number | null | undefined): string {
  if (hours == null || !Number.isFinite(hours)) return '—'
  const whole = Math.floor(hours)
  const minutes = Math.round((hours - whole) * 60)
  if (minutes === 60) return `${whole + 1} h`
  return `${whole} h ${String(minutes).padStart(2, '0')} min`
}

/** A weekly value in the unit its trend names. */
export function trendValue(key: string, value: number | null | undefined, unit: string): string {
  if (value == null) return '—'
  if (key === 'sleep') return hoursMinutes(value)
  return `${short(value, key === 'steps' || key === 'load' ? 0 : 1)}${unit ? ` ${unit}` : ''}`
}

/** The six weekly trends in the order the pages show them. */
export const TREND_ORDER = ['readiness', 'sleep', 'hrv', 'resting_hr', 'load', 'steps'] as const

/** Which way is the kinder direction for a metric, where there is one. A
 *  change is described ("up", "down"); only these get a calm or a watch tone,
 *  and load and steps get neither: more is not better by itself. */
export const KIND_DIRECTION: Record<string, 'up' | 'down' | undefined> = {
  readiness: 'up',
  sleep: 'up',
  hrv: 'up',
  resting_hr: 'down',
}

export function changeTone(key: string, pct: number | null | undefined): 'good' | 'watch' | 'plain' {
  const kind = KIND_DIRECTION[key]
  if (!kind || pct == null || Math.abs(pct) < 3) return 'plain'
  const up = pct > 0
  return (kind === 'up') === up ? 'good' : 'watch'
}

export function signed(pct: number | null | undefined): string {
  if (pct == null || !Number.isFinite(pct)) return '—'
  const rounded = Math.round(pct)
  return `${rounded > 0 ? '+' : rounded < 0 ? '−' : ''}${Math.abs(rounded)}%`
}

export function values(series: DayValue[] | undefined): number[] {
  return (series ?? []).map((p) => p.value).filter((v): v is number => v != null && Number.isFinite(v))
}

/** The weeks of a trend that carry a value, for a chart that must not draw
 *  an empty week as zero. */
export function trendWeeks(trend: Trend | undefined): { week: string; value: number }[] {
  return (trend?.weeks ?? []).flatMap((w) => (w.value == null ? [] : [{ week: w.week, value: w.value }]))
}

export function panelsInOrder(sections: string[], panels: Record<string, Panel>): Panel[] {
  const seen = new Set<string>()
  const out: Panel[] = []
  for (const key of [...sections, ...Object.keys(panels)]) {
    const panel = panels[key]
    if (panel && !seen.has(key)) {
      seen.add(key)
      out.push(panel)
    }
  }
  return out
}

const PROVIDER: Record<string, string> = {
  apple: 'Apple Health',
  oura: 'Oura',
  whoop: 'WHOOP',
  garmin: 'Garmin',
  fitbit: 'Fitbit',
  withings: 'Withings',
  polar: 'Polar',
  medpull: 'MedPull',
}

export function providerName(key: string | null | undefined): string {
  if (!key) return 'Unknown'
  return PROVIDER[key] ?? key.charAt(0).toUpperCase() + key.slice(1)
}
