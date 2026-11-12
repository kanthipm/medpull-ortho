import {
  Activity,
  ClipboardList,
  Dumbbell,
  Footprints,
  HeartPulse,
  Moon,
  Scale,
  Weight,
  type LucideIcon,
} from 'lucide-react'
import type { MetricTier } from '../../api/data'
import type { TileFamily } from '../../components/Tile'

/** Words, glyphs and small formatters the Data tab's pages share. Kept out of
 *  the component files so those export components only. */

/** The five tiers the tab is organised in, always in this order and with
 *  these names: where a number came from, top to bottom. */
export const TIERS = [
  {
    key: 'sources',
    step: 1,
    name: 'Sources',
    line: 'The devices, apps and check-ins that feed each person, and how complete each is.',
  },
  {
    key: 'raw',
    step: 2,
    name: 'Raw readings',
    line: 'Every stored reading with where and when it came from.',
  },
  {
    key: 'signals',
    step: 3,
    name: 'Daily signals',
    line: 'One value a day per signal, against the person’s own baseline.',
  },
  {
    key: 'medpull',
    step: 4,
    name: 'Computed by MedPull',
    line: 'Gait, stairs, walk tests, range of motion and stress, worked out from the phone’s own sensors and from check-ins.',
  },
  {
    key: 'care',
    step: 5,
    name: 'Care metrics and the risk read',
    line: 'What all of it adds up to: the care metrics, and the reasons behind a tier.',
  },
] as const

export type DataView = 'sources' | 'raw' | 'signals' | 'medpull' | 'care' | 'sleep' | 'reported'

export const VIEWS: { key: DataView; label: string }[] = [
  { key: 'sources', label: 'Sources' },
  { key: 'raw', label: 'Raw' },
  { key: 'signals', label: 'Signals' },
  { key: 'medpull', label: 'MedPull' },
  { key: 'care', label: 'Care metrics' },
  { key: 'sleep', label: 'Sleep' },
  { key: 'reported', label: 'Reported' },
]

export function isDataView(value: string | null): value is DataView {
  return VIEWS.some((v) => v.key === value)
}

/** The address of one chart's explorer, on a view and optionally on one care
 *  metric's card (`?metric=M12`, which the care view scrolls to). */
export function dataPath(patientId: string, view?: DataView, metricId?: string): string {
  const query = new URLSearchParams()
  if (view && view !== 'sources') query.set('view', view)
  if (metricId) query.set('metric', metricId)
  const text = query.toString()
  return `/data/patients/${encodeURIComponent(patientId)}${text ? `?${text}` : ''}`
}

/** Where a family's cell on the roster lands in the chart's explorer. */
export const FAMILY_VIEW: Record<string, DataView> = {
  sleep: 'sleep',
  cardiac: 'signals',
  activity: 'signals',
  mobility: 'medpull',
  body: 'raw',
  reported: 'reported',
  training_load: 'reported',
  exercise_sessions: 'reported',
}

export const FAMILY_GLYPH: Record<string, { icon: LucideIcon; family: TileFamily; short: string }> = {
  sleep: { icon: Moon, family: 'indigo', short: 'Sleep' },
  cardiac: { icon: HeartPulse, family: 'violet', short: 'Heart' },
  activity: { icon: Activity, family: 'teal', short: 'Activity' },
  mobility: { icon: Footprints, family: 'blue', short: 'Mobility' },
  body: { icon: Scale, family: 'violet', short: 'Body' },
  reported: { icon: ClipboardList, family: 'blue', short: 'Reported' },
  training_load: { icon: Weight, family: 'teal', short: 'Load' },
  exercise_sessions: { icon: Dumbbell, family: 'indigo', short: 'Exercises' },
}

export const TIER_LABEL: Record<MetricTier, string> = {
  scored: 'In the risk read',
  display: 'Shown only',
  stored: 'Stored',
  declared: 'Not written yet',
}

export const TIER_CLASS: Record<MetricTier, string> = {
  scored: 'bg-risk-low-tint text-risk-low-ink',
  display: 'bg-risk-missing-tint text-risk-missing-ink',
  stored: 'bg-soft text-body',
  declared: 'bg-soft text-secondary',
}

const SOURCE_NAME: Record<string, string> = {
  medpull: 'MedPull',
  apple: 'Apple Health',
  fitbit: 'Fitbit',
  garmin: 'Garmin',
  oura: 'Oura',
  whoop: 'WHOOP',
  withings: 'Withings',
  dexcom: 'Dexcom',
  polar: 'Polar',
  samsung: 'Samsung Health',
  junction: 'Junction',
  health_connect: 'Health Connect',
  google_health: 'Google Health',
  patient_reported: 'Reported',
  clinician_entered: 'Clinician',
  mock: 'Demo feed',
  terra: 'Terra',
  app: 'App',
  sms: 'Text',
  console: 'Console',
}

export function sourceName(key: string | null | undefined): string {
  if (!key) return '—'
  return SOURCE_NAME[key] ?? key.replace(/_/g, ' ')
}

/** A number as a reader wants it: whole when it is, else one or two places. */
export function num(value: number | null | undefined, places?: number): string {
  if (value == null || !Number.isFinite(value)) return '—'
  if (places != null) return value.toFixed(places)
  const abs = Math.abs(value)
  if (Number.isInteger(value)) return value.toLocaleString()
  if (abs >= 100) return Math.round(value).toLocaleString()
  if (abs >= 10) return value.toFixed(1)
  return value.toFixed(2).replace(/0$/, '')
}

/** How long ago a calendar day was, against the day the read is as of. */
export function dayAge(iso: string | null, asOf: string): string {
  if (!iso) return 'never'
  const days = Math.round((Date.parse(`${asOf}T00:00:00`) - Date.parse(`${iso}T00:00:00`)) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  return `${days} days ago`
}

export function clock(iso: string | null): string {
  if (!iso) return '—'
  const at = new Date(iso)
  return Number.isNaN(at.getTime())
    ? '—'
    : at.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export function hoursText(hours: number | null | undefined): string {
  if (hours == null || !Number.isFinite(hours)) return '—'
  const whole = Math.floor(hours)
  const minutes = Math.round((hours - whole) * 60)
  if (minutes === 60) return `${whole + 1} h`
  if (whole === 0) return `${minutes} min`
  return minutes === 0 ? `${whole} h` : `${whole} h ${minutes} min`
}

/** Kilograms as the clinic reads loads. Stored and sent values stay kilograms. */
export function loadText(kg: number | null | undefined, unit: 'kg' | 'lb'): string {
  if (kg == null || !Number.isFinite(kg)) return '—'
  if (unit === 'lb') return `${(Math.round((kg * 2.20462) / 2.5) * 2.5).toLocaleString()} lb`
  return `${(Number.isInteger(kg) ? kg : Number(kg.toFixed(1))).toLocaleString()} kg`
}
