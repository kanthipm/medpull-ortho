import { useQuery } from '@tanstack/react-query'
import { fetchJson } from './client'
import type { ConfidenceLevel, MetricStatus } from '../lib/risk'

/** Care-metrics contract (`GET /api/patients/{id}/care-metrics`): the stored
 *  analytics bundle slice for one patient — the pathway's headline picks plus
 *  every catalog metric, each a `CareMetric.to_dict()` from the engine. Kept
 *  apart from `queries.ts`/`types.ts` on purpose: another session owns those
 *  files while this page is being built. */

export type ChartKind = 'line' | 'band' | 'bars' | 'scatter' | 'dual' | 'gauge' | 'heat'

/** One chart point. Which keys are set depends on `ChartSpec.kind`:
 *  line/band `{x, y}`; bars/scatter `{x, y, label?}`; dual `{x, y, y2}`;
 *  heat `{x (day), row (task title), v (0 | 0.5 | 1 | null)}`; gauge has no
 *  points at all (its value lives in `extra`). */
export interface ChartPoint {
  x: number | string
  y?: number | null
  y2?: number | null
  label?: string
  row?: string
  v?: number | null
}

export interface ChartBand {
  x: number
  lo: number
  hi: number
}

export interface GaugeExtra {
  value: number
  min: number
  max: number
  bands: { to: number; tone: 'low' | 'med' | 'high' }[]
}

export interface ChartSpec {
  kind: ChartKind
  series: ChartPoint[]
  reference: number | null
  band: ChartBand[] | null
  x_label: string
  y_label: string
  y2_label: string
  marker_x: number | null
  fit: { x: number; y: number }[] | null
  extra: Record<string, unknown>
}

/** Component rows behind M12/M13/M14/M15/M16/M17/M18/C5. Shape varies by
 *  metric: most carry `label`; M14's rows are per-task (`title`, `task_id`,
 *  `rate`, `verified`, `self_attested`, `missed`). Not rendered yet. */
export interface MetricDriver {
  metric_type?: string
  label?: string
  title?: string
  contribution?: number
  direction?: string
  [key: string]: unknown
}

export interface CareMetric {
  id: string
  key: string
  name: string
  family: string
  template: string
  feasibility: string
  tier: number
  status: MetricStatus
  status_text: string
  value: string | null
  value_num: number | null
  unit: string
  value_label: string
  delta_text: string | null
  finding: string
  next_step: string | null
  confidence: ConfidenceLevel
  coverage_text: string
  guarded: boolean
  chart: ChartSpec | null
  method: string
  inputs: string[]
  unlock: string | null
  feeds_from_tasks: string[]
  drivers: MetricDriver[]
  /** False when the metric is not meaningful on this patient's pathway —
   *  the Full stats view folds those into a collapsed tail. */
  applicable: boolean
  domains: string[]
}

export interface CareFamily {
  key: string
  name: string
  metric_ids: string[]
}

export interface CarePathway {
  key: string
  name: string
  domain: string
}

export interface CareMetricsResponse {
  version: string
  pathway: CarePathway
  /** Metric ids in display order — the API already picks applicable ones. */
  headline: string[]
  metrics: CareMetric[]
  families: CareFamily[]
  computed_at: string
}

export interface RawDataRow {
  date: string
  start_time: string | null
  value: number | null
  unit: string
  source: string
  granularity: string
  patient_reported: boolean
  json: Record<string, unknown> | null
}

export interface RawDataType {
  metric_type: string
  unit: string
  count: number
  first: string | null
  last: string | null
  source_providers: string[]
  /** Set when this type hit the 400-row cap for the window. */
  truncated?: boolean
}

export interface RawDataResponse {
  days?: number
  metric_types: RawDataType[]
  rows: Record<string, RawDataRow[]>
  /** Some servers report the cap once for the whole payload. */
  truncated?: boolean
  checkins_count: number
  tasks_count: number
}

/** Eager on purpose: the headline tiles sit above the fold. The key lives
 *  under the `['patient', id]` prefix so a Refresh analysis sweeps it up with
 *  the rest of the page (`recomputeKeys`). */
export function useCareMetrics(id: string) {
  return useQuery({
    queryKey: ['patient', id, 'care-metrics'],
    queryFn: () => fetchJson<CareMetricsResponse>(`/api/patients/${id}/care-metrics`),
  })
}

/** Lazy: only the Raw data tab pays for the observation dump. */
export function useRawData(id: string, days: number, enabled = true) {
  return useQuery({
    queryKey: ['patient', id, 'raw-data', days],
    queryFn: () => fetchJson<RawDataResponse>(`/api/patients/${id}/raw-data?days=${days}`),
    enabled,
  })
}
