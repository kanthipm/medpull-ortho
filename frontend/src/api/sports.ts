import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson } from './client'
import type { MetricStatus } from '../lib/risk'

/** The team console's contract with the sports API (`/api/sports/teams…`).
 *  Typed from the live responses; what the pages do not read stays loose
 *  (`unknown` / index signatures) so a backend addition never breaks the
 *  build. Nulls are common everywhere a device has not reported. */

export type Availability = 'available' | 'modified' | 'out'
export type ReadinessBand = 'green' | 'amber' | 'red'
export type FlagStatus = 'watch' | 'flag'
export type EvidenceGrade = 'A' | 'B' | 'C'

export const STATUS_OPTIONS: { key: Availability; label: string }[] = [
  { key: 'available', label: 'Available' },
  { key: 'modified', label: 'Modified' },
  { key: 'out', label: 'Out' },
]

/** The staff guardrail, verbatim on both team pages. */
export const STAFF_GUARDRAIL =
  'Monitoring for staff review — return-to-play decisions belong to the medical staff.'

/* ── Teams index ──────────────────────────────────────────────────────── */

export interface SportsTeam {
  id: string
  org_id: string
  name: string
  sport: string
  sport_label: string
  sex: string
  season: string
  phase: string
  /** Linked athletes; only on the index listing. */
  roster?: number
}

export interface SportsOrg {
  id: string
  name: string
  short_name: string
  kind: string
  city: string | null
  state: string | null
  conference: string | null
  level: string
  level_label: string
  colors: { primary: string; secondary: string } | null
  requires_code: boolean
  teams: SportsTeam[]
}

export interface TeamsResponse {
  orgs: SportsOrg[]
}

/* ── Team dashboard ───────────────────────────────────────────────────── */

export interface AthleteFlag {
  key: string
  status: FlagStatus
  text: string
}

export interface Verdict {
  kind: string
  title: string
  score: number | null
  reason: string
  detail: string
  reasons: string[]
}

export interface RehabCriterion {
  measure_key: string
  label: string
  op: string
  target: number | null
  use: string
  met: boolean
  value: number | null
  value_text: string | null
  rts: boolean
  measure_label: string
  unit: string
  date: string | null
  sides: Record<string, number> | null
}

export interface RehabPhase {
  number: number
  name: string
  window: string
  of: number
  goals: string[]
  avoid: string[]
  criteria: RehabCriterion[]
  met: number
  total: number
  override: number | null
}

export interface RehabRtsSummary {
  met: number | null
  total: number | null
  pct: number | null
  projected: string | null
}

/** The rehab line on a roster row: enough for the injury board. */
export interface InjurySummary {
  id: number
  label: string
  side: string | null
  weeks: number
  phase: RehabPhase | null
  rts: RehabRtsSummary
}

export interface RosterAthlete {
  id: string
  name: string
  first_name: string
  initials: string
  position: string | null
  jersey: string | null
  class_year: string | null
  availability: Availability
  availability_label: string
  status_note: string | null
  verdict: Verdict
  readiness: number | null
  readiness_band: ReadinessBand | null
  readiness_status: MetricStatus | null
  /** The last 14 readiness scores, oldest first. */
  readiness_series: (number | null)[]
  sleep_hours: number | null
  sleep_need: number | null
  sleep_debt: number | null
  hrv_z: number | null
  hrv_latest: number | null
  hrv_baseline: number | null
  rhr_delta: number | null
  rhr_latest: number | null
  wellness_z: number | null
  hooper: number | null
  wellness_answered_today: boolean
  soreness: number | null
  load_week: number | null
  load_change_pct: number | null
  monotony: number | null
  acwr: number | null
  jumps_week: number | null
  cmj: number | null
  cmj_change_pct: number | null
  neuromuscular: MetricStatus
  flags: AthleteFlag[]
  /** 0 calm, 1 something to watch, 2 flagged. */
  severity: number
  staff_action: string | null
  injuries: InjurySummary[]
  days_with_data: number
}

export interface TeamEvent {
  id: number
  date: string
  start_time: string | null
  kind: string
  title: string
  opponent: string | null
  home: boolean | null
  location: string | null
  note: string | null
}

export interface TeamLoadPoint {
  date: string
  load_per_athlete: number
  jumps_per_athlete: number
}

export interface StaffMember {
  id: string
  name: string
  role: string
  role_label: string
  athlete_facing: boolean
}

export interface InjuryBoardRow extends InjurySummary {
  athlete_id: string
  name: string
  position: string | null
}

export interface TeamSummary {
  roster: number
  available: number
  modified: number
  out: number
  mean_readiness: number | null
  answered_today: number
  flags: number
}

export interface TeamDashboard {
  team: SportsTeam
  org: SportsOrg | null
  as_of: string
  summary: TeamSummary
  briefing: { headline: string; text: string }
  attention: RosterAthlete[]
  roster: RosterAthlete[]
  injuries: InjuryBoardRow[]
  /** A week back to two weeks ahead. */
  events: TeamEvent[]
  /** Per-athlete session load by day, 28 days (rest days are absent). */
  load: TeamLoadPoint[]
  staff: StaffMember[]
  guardrail: string
}

/* ── Athlete detail ───────────────────────────────────────────────────── */

export interface SeriesPoint {
  date: string
  value: number
}

export interface PanelStat {
  label: string
  value: string
  unit: string
}

/** One recovery panel (sleep, HRV, resting heart rate, …). */
export interface Panel {
  key: string
  title: string
  status: MetricStatus
  status_text: string
  headline: string
  unit: string
  sub: string
  finding: string
  method: string
  confidence: string
  coverage: string
  series: SeriesPoint[]
  stats: PanelStat[]
  extra: Record<string, unknown>
}

export interface ReadinessComponent {
  key: string
  label: string
  z: number
  weight: number
  value: string
  text: string
  contribution: number
}

export interface ReadinessExtra {
  band: ReadinessBand | null
  components: ReadinessComponent[]
  score: number | null
  need_hours: number | null
}

export type ReadinessPanel = Omit<Panel, 'extra'> & { extra: ReadinessExtra }

export interface Suggestion {
  key: string
  title: string
  why: string
  actions: string[]
  evidence: EvidenceGrade | string
  priority: number
  category: string
  source: string | null
}

export interface WellnessItem {
  key: string
  label: string
  value: number | null
  date: string | null
  /** Already signed so negative is always worse. */
  z: number | null
  direction: 'good' | 'bad'
  state: MetricStatus
  series: SeriesPoint[]
}

export interface Wellness {
  key: string
  title: string
  status: MetricStatus
  status_text: string
  composite_z: number | null
  hooper: number | null
  answered_today: number
  latest_date: string | null
  finding: string
  method: string
  notes: { date: string; text: string }[]
  items: WellnessItem[]
}

export interface LoadSummary {
  source: string
  week_load: number | null
  prior_week_load: number | null
  prior_mean_load: number | null
  change_pct: number | null
  minutes_week: number | null
  sessions_week: number | null
  games_week: number | null
  by_kind: Record<string, number>
  monotony: number | null
  strain: number | null
  acwr: number | null
  status: MetricStatus
  status_text: string
  finding: string
  last_session: string | null
  series: SeriesPoint[]
  method: string
}

export interface NeuroSignal {
  label: string
  pct: number
  value: string
  baseline: string
}

export interface Neuromuscular {
  status: MetricStatus
  status_text: string
  finding: string
  signals: NeuroSignal[]
  source: string | null
  latest_date?: string | null
}

export interface AthleteRecovery {
  as_of: string
  days_with_data: number
  verdict: Verdict
  readiness: ReadinessPanel | null
  panels: {
    sleep?: Panel | null
    hrv?: Panel | null
    resting_hr?: Panel | null
    [key: string]: Panel | null | undefined
  }
  wellness: Wellness | null
  load: LoadSummary | null
  suggestions: Suggestion[]
  [key: string]: unknown
}

export interface PerfBand {
  percentile: number
  word: string
  reference: string
  p25: number
  p50: number
  p75: number
  p90: number
}

export interface PerfHeadline {
  key: string
  label: string
  unit: string
  logged: boolean
  latest_text: string | null
  band: PerfBand | null
  trend: { pct: number; better: boolean } | null
  days_ago: number | null
  phone: boolean
  sided: boolean
}

export interface Asymmetry {
  key: string
  label: string
  asymmetry: { pct: number; weaker: string; lsi: number }
  status: MetricStatus
}

export interface AthletePerformance {
  as_of: string
  logged: number
  available: number
  overall_percentile: number | null
  neuromuscular: Neuromuscular
  asymmetries: Asymmetry[]
  headline: PerfHeadline[]
  [key: string]: unknown
}

export interface RehabFocus {
  kind: 'measure' | 'time' | 'block' | string
  title: string
  why: string
  actions: string[]
  measure_key?: string
  missing?: boolean
}

export interface RehabMeasure {
  key: string
  label: string
  unit: string
  sided: boolean
  kind: string
  higher_is_better: boolean
  decimals?: number
  logged: boolean
  latest: number | null
  latest_date: string | null
  uninvolved_latest: number | null
  lsi: number | null
  involved: SeriesPoint[]
  uninvolved: SeriesPoint[]
  protocol?: string
  why?: string
}

export interface RehabRts extends RehabRtsSummary {
  known?: number
  criteria: RehabCriterion[]
  window?: [string, string] | null
  typical_weeks?: [number, number] | null
  reinjury_note?: string | null
}

export interface RehabInjury {
  id: number
  injury_key: string
  label: string
  side: string | null
  body_region: string | null
  date_of_injury: string | null
  date_of_surgery: string | null
  graft: string | null
  grade: string | null
  mechanism: string | null
  status: string
  days: number
  weeks: number
  anchor: string
  target_return_date: string | null
  clinician: string | null
  note: string | null
  summary: string
  surgical: boolean
  phase: RehabPhase | null
  rts: RehabRts
  measures: RehabMeasure[]
  focus: RehabFocus[]
  sport_progression: string[]
  sources: string[]
  pain: { value: number | null; date: string | null } | null
  last_measure: string | null
  [key: string]: unknown
}

export interface AthleteRehab {
  active: RehabInjury[]
  past: unknown[]
  availability: Availability
  as_of: string
}

export interface SessionRow {
  id: number
  date: string
  kind: string
  minutes: number
  rpe: number | null
  load_au: number | null
  jumps: number | null
  player_load: number | null
  distance_m: number | null
  high_speed_m: number | null
  max_speed_kmh: number | null
  average_hr: number | null
  source: string
  note: string | null
}

export interface ThreadMessage {
  id: number
  sender: 'patient' | 'copilot' | 'care_team' | string
  authored_by: string | null
  author_name: string | null
  channel: string
  text: string
  created_at: string
  delivery_status: string | null
  delivery_detail: string | null
  read: boolean
}

export interface AthleteBrief {
  headline: string
  brief: string
  guardrail: string
  provider: string
  generated_at: string
}

export interface AthleteProfile {
  position: string | null
  jersey: string | null
  class_year: string | null
  level_label: string | null
  age: number | null
  sex: string | null
  height_cm: number | null
  weight_kg: number | null
  status: Availability
  status_label: string
  status_note: string | null
  [key: string]: unknown
}

export interface AthleteDetail {
  team: SportsTeam
  athlete: RosterAthlete
  profile: AthleteProfile
  brief: AthleteBrief
  recovery: AthleteRecovery
  performance: AthletePerformance
  rehab: AthleteRehab
  sessions: SessionRow[]
  tasks: unknown[]
  /** Oldest first. */
  thread: ThreadMessage[]
}

/* ── Queries ──────────────────────────────────────────────────────────── */

/** The team pages carry live numbers, so they refresh themselves every five
 *  minutes while open, like the worklist. */
const LIVE_REFETCH_MS = 5 * 60_000

export const sportsKeys = {
  teams: ['sports', 'teams'] as const,
  team: (teamId: string) => ['sports', 'team', teamId] as const,
  athlete: (teamId: string, id: string) => ['sports', 'team', teamId, 'athlete', id] as const,
}

const enc = encodeURIComponent

export function fetchSportsTeams() {
  return fetchJson<TeamsResponse>('/api/sports/teams')
}

export function useSportsTeams() {
  return useQuery({ queryKey: sportsKeys.teams, queryFn: fetchSportsTeams })
}

export function fetchTeamDashboard(teamId: string) {
  return fetchJson<TeamDashboard>(`/api/sports/teams/${enc(teamId)}/dashboard`)
}

export function useTeamDashboard(teamId: string) {
  return useQuery({
    queryKey: sportsKeys.team(teamId),
    queryFn: () => fetchTeamDashboard(teamId),
    enabled: teamId !== '',
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export function fetchTeamAthlete(teamId: string, id: string) {
  return fetchJson<AthleteDetail>(`/api/sports/teams/${enc(teamId)}/athletes/${enc(id)}`)
}

export function useTeamAthlete(teamId: string, id: string) {
  return useQuery({
    queryKey: sportsKeys.athlete(teamId, id),
    queryFn: () => fetchTeamAthlete(teamId, id),
    enabled: teamId !== '' && id !== '',
    refetchInterval: LIVE_REFETCH_MS,
  })
}

/** Warm an athlete page while the pointer is still on the row, so it paints
 *  from the cache on click (a no-op while the cache is fresh). */
export function usePrefetchAthlete(teamId: string) {
  const qc = useQueryClient()
  return (id: string) => {
    void qc.prefetchQuery({
      queryKey: sportsKeys.athlete(teamId, id),
      queryFn: () => fetchTeamAthlete(teamId, id),
    })
  }
}

export interface StatusResult {
  ok: boolean
  status: Availability
  status_label: string
}

/** `PATCH …/status {status, note}`. The athlete record and the team board
 *  both carry the availability, so the whole team prefix is refetched. */
export function useSetAthleteStatus(teamId: string, id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { status: Availability; note: string | null }) =>
      fetchJson<StatusResult>(`/api/sports/teams/${enc(teamId)}/athletes/${enc(id)}/status`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: sportsKeys.team(teamId) }),
  })
}

/** `POST …/message {text, staff_id}` — a line in the athlete's thread, signed
 *  by the staff member chosen in the composer. */
export function useSendStaffMessage(teamId: string, id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { text: string; staff_id: string | null }) =>
      fetchJson<{ ok: boolean; id: number }>(
        `/api/sports/teams/${enc(teamId)}/athletes/${enc(id)}/message`,
        { method: 'POST', body: JSON.stringify(body) },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: sportsKeys.athlete(teamId, id) }),
  })
}
