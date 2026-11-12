import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { consoleAuthHeaders, fetchJson } from './client'
import type { MetricInsight } from './types'

/** The Data tab's reads (backend/app/api/data.py). Every one is a GET the
 *  server answers without recomputing or writing; the roster reads follow the
 *  console's scope and the acting clinic, a chart's reads are clinic charts
 *  only. */

// --- the dictionary ---------------------------------------------------------------

export type MetricTier = 'scored' | 'display' | 'stored' | 'declared'

export interface CatalogMetric {
  key: string
  label: string
  family: string
  unit: string
  storage_unit: string
  tier: MetricTier
  scored_on: string | null
  guarded: boolean
  aggregation: 'mean' | 'additive'
  adverse: 'up' | 'down' | null
  reference: string | null
  recency_days: number | null
  plausible: [number, number] | null
  providers: string[]
  in_house: boolean
  method: string | null
  method_version: string | null
  measured_by: string | null
  computed: boolean
  what: string | null
  care_metrics: string[]
}

export interface CatalogCareMetric {
  id: string
  key: string
  name: string
  family: string
  family_name: string
  unit: string
  guarded: boolean
  what: string | null
  method: string | null
  inputs: string[]
  inputs_text: string | null
  shows_after?: string | null
  needs?: string | null
}

export interface CatalogSource {
  key: string
  name: string
  rank: number
  rank_label: string
}

export interface DataCatalog {
  versions: { engine: string; care: string; mobility: string }
  tiers: { key: MetricTier; label: string; description: string }[]
  families: { key: string; name: string; stored_in: string; metrics: string[] }[]
  metrics: CatalogMetric[]
  sources: CatalogSource[]
  precedence: { rule: string; ranks: { rank: number; label: string }[] }
  aggregation: { mean: string; additive: string }
  care_families: { key: string; name: string; metric_ids: string[] }[]
  care_metrics: CatalogCareMetric[]
}

export function useDataCatalog() {
  return useQuery({
    queryKey: ['data', 'catalog'],
    queryFn: () => fetchJson<DataCatalog>('/api/data/catalog'),
    staleTime: Infinity,
  })
}

// --- the roster -------------------------------------------------------------------

export interface CoverageCell {
  days: number
  rows: number
  last: string | null
  sources: string[]
}

export interface CoveragePatient {
  id: string
  name: string
  initials: string
  pathway: string
  hospital: { id: string; name: string | null } | null
  device: { provider: string; model: string | null; status: string; last_sync_at: string | null } | null
  risk_level: 'high' | 'medium' | 'low' | 'missing_data' | null
  confidence: { score: number; level: string } | null
  assessed_at: string | null
  cells: Record<string, CoverageCell>
  checkins: { count: number; last_at: string | null }
  exercises: { assigned: number; done: number; last_at: string | null }
}

export interface DataCoverage {
  as_of: string
  days: number
  since: string
  families: { key: string; name: string; patients: number }[]
  patients: CoveragePatient[]
}

export function useDataCoverage(days: number) {
  return useQuery({
    queryKey: ['data', 'coverage', days],
    queryFn: () => fetchJson<DataCoverage>(`/api/data/coverage?days=${days}`),
  })
}

// --- one chart: sources and the stored read -----------------------------------------

export interface PatientHeader {
  id: string
  name: string
  initials: string
  pathway: string
  hospital: { id: string; name: string } | null
  mode: string
  day_zero: string
  postop_day: number
}

export interface MetricSourceRow {
  key: string
  name: string
  rank: number
  count: number
  first: string | null
  last: string | null
}

export interface SummaryMetric {
  metric_type: string
  label: string
  family: string
  unit: string
  tier: MetricTier
  in_house: boolean
  computed: boolean
  count: number
  days: number
  first: string | null
  last: string | null
  sources: MetricSourceRow[]
  availability: string | null
  availability_note: string | null
}

export interface RiskReason {
  code: string
  text: string
  metric_type: string | null
  severity: number
}

export interface StoredAssessment {
  computed_at: string
  engine_version: string
  current: boolean
  /** "device": read from a wearable; "reported": from check-ins alone. */
  basis: string
  risk: { level: 'high' | 'medium' | 'low' | 'missing_data'; score: number; reasons: RiskReason[] }
  composite: {
    index: number | null
    level: string
    drivers: { metric_type: string; label: string; contribution: number; direction: string }[]
  } | null
  confidence: {
    score: number
    level: string
    days_with_data: number
    window_days: number
    dark_metrics: string[]
    panel: string[]
  } | null
  trajectory: {
    state: string
    pct: number | null
    change_point_day: number | null
    actual: { day: number; v: number }[]
    expected: { day: number; lo: number; mid: number; hi: number }[]
  } | null
}

export interface ReportedSignals {
  checkins_7d: number
  checkins_14d: number
  days_since_checkin: number | null
  load_ratio: number | null
  load_week_mean: number | null
  load_prior_mean: number | null
  pain_latest: number | null
  pain_prior_mean: number | null
  pain_delta: number | null
  new_pain: boolean
  program_done_7d: number | null
  program_week_days: number | null
  /** Days with a reported training load, and days the program question was
   *  answered: zero when the check-in never asks, where a "0 of 7" would be
   *  a figure about nothing. */
  load_days?: number
  program_days?: number
}

export interface DataSummary {
  patient: PatientHeader
  as_of: string
  devices: {
    id: string
    provider: string
    provider_name: string
    model: string | null
    status: string
    connected_at: string | null
    last_sync_at: string | null
    via_junction: boolean
  }[]
  connections: { provider: string; status: string; last_event_at?: string | null }[]
  app: { signed_in: boolean; last_seen_at: string | null; texts: boolean }
  metrics: SummaryMetric[]
  calendar: {
    days: number
    since: string
    until: string
    families: { key: string; name: string }[]
    by_day: { date: string; count: number; families: string[] }[]
  }
  assessment: StoredAssessment | null
  reported: ReportedSignals | null
}

export function useDataSummary(id: string) {
  return useQuery({
    queryKey: ['patient', id, 'data', 'summary'],
    queryFn: () => fetchJson<DataSummary>(`/api/patients/${encodeURIComponent(id)}/data/summary`),
  })
}

// --- one chart: raw readings ----------------------------------------------------------

export interface Reading {
  id: number
  metric_type: string
  value: number | null
  unit: string | null
  json: Record<string, unknown> | null
  start_time: string
  end_time: string | null
  local_date: string
  postop_day: number
  granularity: string
  source: string
  device: string | null
  body_site: string | null
  side: string | null
  patient_reported: boolean
  revision: number | null
  ingested_at: string | null
  used_in_series: boolean
}

export interface ReadingFilters {
  metric_type?: string
  family?: string
  source?: string
  granularity?: string
  from?: string
  to?: string
}

export interface ReadingsPage {
  patient_id: string
  limit: number
  total: number
  rows: Reading[]
  facets: {
    metric_type: { key: string; label: string; family: string | null; count: number }[]
    family: { key: string; name: string; count: number }[]
    source: { key: string; name: string; rank: number; count: number }[]
  }
  next_cursor: string | null
}

function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export function useReadings(id: string, filters: ReadingFilters, limit = 50) {
  return useInfiniteQuery({
    queryKey: ['patient', id, 'data', 'readings', filters, limit],
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      fetchJson<ReadingsPage>(
        `/api/patients/${encodeURIComponent(id)}/observations/browse${query({
          ...filters,
          limit,
          cursor: pageParam,
        })}`,
      ),
    getNextPageParam: (last) => last.next_cursor,
  })
}

// --- one chart: daily series ------------------------------------------------------------

export interface SeriesPoint {
  date: string
  day: number
  value: number
  z: number | null
  ewma_z: number | null
  expected: number | null
  source: string | null
}

export interface SeriesBaseline {
  mean: number
  sd: number
  n_days: number
  window: string
  is_preop: boolean
  provisional: boolean
  established: boolean
}

export interface DailySeries {
  metric: string
  label: string
  unit: string
  family: string
  tier: MetricTier
  aggregation: 'mean' | 'additive'
  adverse: 'up' | 'down' | null
  computed: boolean
  judged: boolean
  reference: string | null
  baseline: SeriesBaseline | null
  flagged: boolean | null
  drifting: boolean | null
  stale: boolean | null
  latest_z: number | null
  points: SeriesPoint[]
}

export interface SeriesResponse {
  patient: PatientHeader
  as_of: string
  days: number
  since: string
  series: DailySeries[]
}

export function useDailySeries(id: string, metrics: string[], days: number, enabled = true) {
  return useQuery({
    queryKey: ['patient', id, 'data', 'series', metrics.join(','), days],
    queryFn: () =>
      fetchJson<SeriesResponse>(
        `/api/patients/${encodeURIComponent(id)}/series${query({ metric: metrics.join(','), days })}`,
      ),
    enabled: enabled && metrics.length > 0,
  })
}

/** The signal cards the chart has always shown (`GET /metrics`), for the
 *  Signals view: status, finding and a short sparkline per signal. */
export interface SignalCards {
  metrics: MetricInsight[]
}

// --- one chart: sleep --------------------------------------------------------------------

export interface Night {
  date: string
  day: number
  duration_h: number | null
  stages: { deep: number | null; rem: number | null; light: number | null; awake: number | null } | null
  bedtime: string | null
  wake: string | null
  efficiency: number | null
  source: string | null
}

export interface SleepAverages {
  nights: number
  duration_h: number | null
  efficiency: number | null
  nights_with_stages: number
  deep_h: number | null
  deep_pct: number | null
  rem_h: number | null
  rem_pct: number | null
  light_h: number | null
  light_pct: number | null
  awake_h: number | null
  awake_pct: number | null
}

export interface SleepResponse {
  patient: PatientHeader
  as_of: string
  days: number
  nights: Night[]
  averages: SleepAverages
  last_7: SleepAverages
  consistency: {
    nights: number
    bedtime_sd_min: number | null
    wake_sd_min: number | null
    mean_bedtime: string | null
    mean_wake: string | null
  }
  baseline: SeriesBaseline | null
  derived: {
    computed_at: string | null
    nocturnal_disruption: {
      status: string
      status_text: string
      value: string | null
      value_label?: string | null
      delta_text?: string | null
      finding?: string | null
    } | null
    sleep_duration: { status: string; status_text: string; finding: string } | null
  }
}

export function useSleep(id: string, days: number) {
  return useQuery({
    queryKey: ['patient', id, 'data', 'sleep', days],
    queryFn: () =>
      fetchJson<SleepResponse>(`/api/patients/${encodeURIComponent(id)}/sleep?days=${days}`),
  })
}

// --- one chart: the reported grid ----------------------------------------------------------

export interface ReportedExerciseItem {
  id: number
  exercise_id: number
  title: string
  state: 'upcoming' | 'due' | 'in_progress' | 'done' | 'skipped' | 'missed'
  sets: number | null
  reps: number | null
  hold_seconds: number | null
  load_kg: number | null
  rpe_target: number | null
  sets_done: number | null
  reps_done: number | null
  load_done_kg: number | null
  effort: number | null
  pain_before: number | null
  pain_after: number | null
  duration_s: number | null
  note: string | null
  skip_reason: string | null
  has_clip: boolean
  reviewed: boolean
  over: boolean
  under: boolean
  line: string | null
}

export interface ReportedExerciseDay {
  assigned: number
  done: number
  skipped: number
  missed: number
  pain_before: number | null
  pain_after: number | null
  effort: number | null
  effort_target: number | null
  minutes: number | null
  load_done: number
  over: number
  clips: number
  items: ReportedExerciseItem[]
}

export interface ReportedRow {
  date: string
  day: number
  checkins: { id: number; at: string; channel: string; answers: Record<string, string | number> }[]
  answers: Record<string, string | number>
  load: number | null
  program: number | null
  exercises: ReportedExerciseDay | null
}

export interface ReportedQuestion {
  id: string
  label: string
  kind: 'scale' | 'number' | 'yes_no' | 'choice' | 'text'
  prompt: string
  options: string[] | null
}

export interface ReportedResponse {
  patient: PatientHeader
  as_of: string
  days: number
  since: string
  load_unit: 'kg' | 'lb'
  questions: ReportedQuestion[]
  rows: ReportedRow[]
  summary: {
    checkin_days: number
    pain: { latest: { value: number; date: string }; mean_7: number | null; mean_prior_7: number | null } | null
    exercises: { assigned: number; done: number; over: number; clips: number }
  }
}

export function useReported(id: string, days: number) {
  return useQuery({
    queryKey: ['patient', id, 'data', 'reported', days],
    queryFn: () =>
      fetchJson<ReportedResponse>(`/api/patients/${encodeURIComponent(id)}/reported?days=${days}`),
  })
}

// --- export ----------------------------------------------------------------------------------

/** Download one chart's data as a CSV file. A plain link cannot carry the
 *  console's token or the acting clinic, so the file is fetched and handed
 *  to the browser as a download. */
export async function downloadExport(
  id: string,
  params: Record<string, string | number | undefined>,
  fallbackName: string,
): Promise<void> {
  const res = await fetch(`/api/patients/${encodeURIComponent(id)}/data/export${query(params)}`, {
    headers: consoleAuthHeaders(),
  })
  if (!res.ok) throw new Error(`Export failed (${res.status})`)
  const named = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1]
  const url = URL.createObjectURL(await res.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = named ?? fallbackName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
