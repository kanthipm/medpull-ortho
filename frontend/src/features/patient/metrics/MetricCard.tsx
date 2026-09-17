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
import ConfidenceChip from '../../../components/ConfidenceChip'
import Tile, { type TileFamily } from '../../../components/Tile'
import { METRIC_STATUS } from '../../../lib/risk'
import CareChart, { latestLabel } from './CareChart'
import { GUARDED_NOTE, statusChipText, taskKindLabel } from './labels'

/* ════════════════════════════════════════════════════════════════════════
   METRIC TILES — the app's "Your portfolio" tiles, at console size.

   A soft filled tile (--soft, 12px corners) inside a white card: category
   Tile + name, the state chip, a large tabular value with its unit, and a
   date line. Every text pair was computed on --soft (light / dark):
     ink       16.202 / 16.060     value, name
     body       6.367 /  6.211     finding
     muted      4.755 /  4.582     .meta / text-secondary
     brand-ink  5.066 /  6.336     next step
     risk-med   5.127 /  9.005     guarded note
   The chip carries its own opaque tint, so the clinical state never sits on
   a wash. The CHART sits in an opaque --panel well (rounded-control-sm), which
   is where the chart tokens were measured: s1 4.602 / 6.783, ref line
   5.393 / 3.631, axis 5.393 / 4.906. On bare --soft the dark ref line
   (3.392) and the heat grid's seq-3 step would sit closer to the 3:1 floor,
   so the well is load-bearing, not decoration.

   One exception to "chip from METRIC_STATUS": light --risk-missing-tint IS
   --soft, so a "Needs data" chip would lose its capsule on the tile. On a
   soft tile it is drawn panel-filled instead (missing ink on panel 7.222 /
   6.650).
   ════════════════════════════════════════════════════════════════════════ */

type TileSpec = { family: TileFamily; icon: ReactNode }

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

/** State chip for a soft tile (see the missing-tint note above). */
export function tileChipClass(status: CareMetric['status']): string {
  if (status === 'nodata') return 'bg-panel text-risk-missing-ink normal-case tracking-label'
  return (METRIC_STATUS[status] ?? METRIC_STATUS.nodata).pill
}

/** A `.meta` line of parts joined by spaced separator dots. Falsy parts are
 *  dropped, so no dot is ever left dangling (e.g. when high confidence
 *  renders nothing). */
export function MetaDots({ parts, className = '' }: { parts: ReactNode[]; className?: string }) {
  const kept = parts.filter((p) => p != null && p !== false && p !== '')
  if (kept.length === 0) return null
  return (
    <p className={`meta flex flex-wrap items-center gap-x-1.5 gap-y-0.5 ${className}`}>
      {kept.map((p, i) => (
        <span key={i} className="contents">
          {i > 0 && <span aria-hidden>·</span>}
          <span>{p}</span>
        </span>
      ))}
    </p>
  )
}

/** Full stats tile for one care metric. `id="metric-M12"` is the anchor the
 *  headline tiles scroll to (Full stats rings it on arrival). */
export default function MetricCard({ m }: { m: CareMetric }) {
  const nodata = m.status === 'nodata'
  const tile = careMetricTile(m)
  const when = latestLabel(m.chart)
  const valueId = `metric-${m.id}-name`
  return (
    <article
      id={`metric-${m.id}`}
      aria-labelledby={valueId}
      className="flex scroll-mt-24 flex-col rounded-control bg-soft p-4 transition-shadow duration-300"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <Tile family={tile.family} icon={tile.icon} />
          <div className="min-w-0">
            <h4 id={valueId} className="text-copy-lg font-medium text-ink">
              {m.name}
            </h4>
            <p className="meta tabular-nums">{m.id}</p>
          </div>
        </div>
        <span className={`chip shrink-0 ${tileChipClass(m.status)}`}>{statusChipText(m)}</span>
      </div>

      <p className="mt-3 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className="text-title font-medium tabular-nums text-ink">{m.value ?? '—'}</span>
        {m.unit && <span className="text-copy text-secondary">{m.unit}</span>}
        {m.value_label && <span className="text-copy text-secondary">{m.value_label}</span>}
      </p>
      {(when || m.delta_text) && (
        <p className="meta mt-0.5">
          {[when, m.delta_text].filter(Boolean).join(' · ')}
        </p>
      )}

      <div className="mt-3 rounded-control-sm bg-panel p-2">
        <CareChart spec={m.chart} />
      </div>

      {nodata ? (
        <div className="mt-3">
          <p className="text-copy text-body">{m.unlock ?? m.finding}</p>
          {m.feeds_from_tasks.length > 0 && (
            <div className="mt-2.5">
              <p className="meta mb-1.5">What unlocks it</p>
              <ul className="flex flex-wrap gap-1.5">
                {m.feeds_from_tasks.map((k) => (
                  <li key={k} className="chip bg-brand-tint text-on-brand-tint">
                    {taskKindLabel(k)}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <p className="mt-3 text-copy text-body">{m.finding}</p>
      )}

      {m.next_step && !nodata && (
        <p className="mt-2 flex items-start gap-1.5 text-copy font-medium text-brand-ink">
          <span aria-hidden>→</span> {m.next_step}
        </p>
      )}

      <div className="mt-auto space-y-1 pt-3">
        {m.method && <p className="meta">{m.method}</p>}
        <MetaDots
          parts={[
            m.inputs.length > 0 && m.inputs.join(', '),
            m.coverage_text,
            m.confidence !== 'high' && <ConfidenceChip level={m.confidence} variant="meta" />,
            m.guarded && (
              <span
                className="text-risk-med-ink"
                title="Guarded metric: the engine phrases it as a signal to review, never a verdict."
              >
                {GUARDED_NOTE}
              </span>
            ),
          ]}
        />
      </div>
    </article>
  )
}
