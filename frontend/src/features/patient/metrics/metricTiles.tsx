import {
  Activity,
  Armchair,
  ClipboardCheck,
  ClipboardList,
  Droplet,
  Footprints,
  Gauge,
  HeartPulse,
  Moon,
  Mountain,
  Radar,
  Scale,
  SignalHigh,
  Spline,
  Stethoscope,
  SunMoon,
  Thermometer,
  Timer,
  TrendingUp,
  UserX,
  Waves,
  Wind,
} from 'lucide-react'
import type { ReactNode } from 'react'
import type { CareMetric } from '../../../api/care'
import type { TileFamily } from '../../../components/Tile'

/* Category tiles for care metrics, care families and wearable signals.
   Kept out of MetricCard.tsx so that file exports components only
   (react-refresh/only-export-components). */

export type TileSpec = { family: TileFamily; icon: ReactNode }

/** Category tile per care metric. Hue is category only (never risk):
 *  activity / walking / asymmetry teal; sleep / HRV / trajectory indigo;
 *  vitals / temperature / BP / symptoms violet; engagement blue. */
const METRIC_TILES: Record<string, TileSpec> = {
  M1: { family: 'teal', icon: <Activity /> },
  M2: { family: 'teal', icon: <Footprints /> },
  M3: { family: 'teal', icon: <Scale /> },
  M4: { family: 'teal', icon: <Gauge /> },
  M5: { family: 'teal', icon: <Timer /> },
  M6: { family: 'teal', icon: <Armchair /> },
  M7: { family: 'teal', icon: <Footprints /> },
  M8: { family: 'teal', icon: <Mountain /> },
  M9: { family: 'indigo', icon: <Moon /> },
  M10: { family: 'indigo', icon: <Waves /> },
  M11: { family: 'indigo', icon: <SunMoon /> },
  M12: { family: 'violet', icon: <Radar /> },
  M13: { family: 'violet', icon: <Thermometer /> },
  M14: { family: 'blue', icon: <ClipboardCheck /> },
  M15: { family: 'blue', icon: <UserX /> },
  M16: { family: 'blue', icon: <SignalHigh /> },
  M17: { family: 'indigo', icon: <TrendingUp /> },
  M18: { family: 'indigo', icon: <Spline /> },
  C1: { family: 'violet', icon: <Scale /> },
  C2: { family: 'violet', icon: <Wind /> },
  C3: { family: 'violet', icon: <Droplet /> },
  C4: { family: 'violet', icon: <HeartPulse /> },
  C5: { family: 'violet', icon: <Stethoscope /> },
  C6: { family: 'teal', icon: <Armchair /> },
}

const FAMILY_TILES: Record<string, TileSpec> = {
  load: { family: 'teal', icon: <Activity /> },
  function: { family: 'teal', icon: <Footprints /> },
  quality: { family: 'indigo', icon: <Moon /> },
  surveillance: { family: 'violet', icon: <HeartPulse /> },
  metabolic: { family: 'violet', icon: <Droplet /> },
  symptoms: { family: 'violet', icon: <ClipboardList /> },
  engagement: { family: 'blue', icon: <ClipboardCheck /> },
  trajectory: { family: 'indigo', icon: <TrendingUp /> },
}

/** Category tile for a care metric (by id, then by family). */
export function careMetricTile(m: Pick<CareMetric, 'id' | 'family'>): TileSpec {
  return METRIC_TILES[m.id] ?? FAMILY_TILES[m.family] ?? { family: 'blue', icon: <Activity /> }
}

/** Category tile for a care family header. */
export function familyTile(key: string): TileSpec {
  return FAMILY_TILES[key] ?? { family: 'blue', icon: <Activity /> }
}

/** Category tile for a wearable signal (`MetricInsight.metric_key`). */
const SIGNAL_TILES: Record<string, TileSpec> = {
  steps: { family: 'teal', icon: <Footprints /> },
  walking_speed: { family: 'teal', icon: <Gauge /> },
  walking_asymmetry_pct: { family: 'teal', icon: <Scale /> },
  sleep_duration: { family: 'indigo', icon: <Moon /> },
  hrv_rmssd: { family: 'indigo', icon: <Waves /> },
  hrv_sdnn: { family: 'indigo', icon: <Waves /> },
  resting_hr: { family: 'violet', icon: <HeartPulse /> },
  skin_temp: { family: 'violet', icon: <Thermometer /> },
  skin_temp_delta: { family: 'violet', icon: <Thermometer /> },
  spo2: { family: 'violet', icon: <Droplet /> },
  respiratory_rate: { family: 'violet', icon: <Wind /> },
}

export function signalTile(metricKey: string): TileSpec {
  return SIGNAL_TILES[metricKey] ?? { family: 'teal', icon: <Activity /> }
}
