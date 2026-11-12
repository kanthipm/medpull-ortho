import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson } from './client'
import { invalidateSchedule } from './hep'

/** The clinic's between-visits record (backend `app/pt`; contract in
 *  docs/dev/pt.md): what a chart keeps beyond the exercise calendar, the
 *  clinic's own settings and rules, the questions its people asked, and the
 *  trainer's page.
 *
 *  Every write to a chart answers with the whole chart bundle, so one
 *  mutation (`usePtAction`) carries all of them and puts the answer straight
 *  into the cache. */

// --- shapes -------------------------------------------------------------------------

export interface PtMember {
  id: string
  name: string
  role: string
}

export interface PtInstrument {
  key: string
  name: string
  short: string
  mode: 'asked' | 'entered'
  low: number
  high: number
  higher_is_better: boolean
  about: string
  threshold: number | null
  threshold_is_clinic: boolean
  threshold_kind: string
  source: string
  note: string
}

export interface PtTestKind {
  key: string
  label: string
  unit: string
  sided: boolean
  entered_by: 'clinic' | 'patient'
  hold: boolean
}

export interface PtCatalog {
  clinic: string
  areas: string[]
  midline: string[]
  sides: string[]
  tests: PtTestKind[]
  holds: string[]
  instruments: PtInstrument[]
  visit_kinds: { key: string; label: string }[]
  care_team: PtMember[]
}

export interface PtArea {
  id: number
  region: string
  label: string
  source: 'evaluation' | 'reported'
  noted_on: string
  note: string
  seen_on: string | null
  new: boolean
}

export interface PtMorning {
  id: number
  session_day: string
  morning: string
  asked_at: string | null
  answered_at: string | null
  pain: number | null
  stiffer: boolean | null
  ceiling: number
  settled: boolean | null
  read: 'waiting' | 'settled' | 'not settled'
}

export interface PtChange {
  delta: number
  direction: 'better' | 'worse' | 'no change'
  past_threshold: boolean
}

export interface PtScoreRead {
  first: number
  first_on: string
  latest: number
  latest_on: string
  count: number
  threshold: number | null
  change: PtChange | null
}

export interface PtGoal {
  id: number
  text: string
  active: boolean
  created_by: string
  created_at: string | null
  ratings: { on: string; score: number; source: string }[]
  first: number | null
  latest: number | null
  latest_on: string | null
  change: number | null
}

export interface PtWeek {
  id: number
  week_start: string
  asked_at: string | null
  answered_at: string | null
  went: 'better' | 'same' | 'worse' | null
  change_note: string
}

export interface PtCriterion {
  text: string
  met: boolean
  met_at: string | null
  met_by: string | null
  met_by_name: string | null
}

export interface PtPhase {
  id: number
  position: number
  name: string
  goal: string
  status: 'upcoming' | 'current' | 'done'
  started_on: string | null
  ended_on: string | null
  advanced_by_name: string | null
  criteria: PtCriterion[]
  met: number
  of: number
}

export interface PtPhases {
  protocol_name: string | null
  phases: PtPhase[]
  current: PtPhase | null
  number: number | null
  count: number
  finished: boolean
}

export interface PtTestResult {
  id: number
  side: 'left' | 'right' | 'both' | 'na'
  value: number
  unit: string
  note: string
  source: 'clinic' | 'patient'
  entered_by_name: string | null
}

export interface PtTest {
  kind: string
  label: string
  unit: string
  hold: boolean
  sided: boolean
  days: { on: string; results: PtTestResult[]; left_of_right_pct: number | null }[]
  series: { on: string; value: number }[]
  first: number
  latest: number
  latest_on: string
  change: number | null
}

export interface PtMeasure extends PtInstrument {
  scores: { id: number; on: string; total: number; source: string }[]
  read: PtScoreRead | null
  schedule: { every_days: number; next_due: string; active: boolean } | null
}

export interface PtHandoff {
  id: number
  trainer_name: string
  limits: string[]
  report_back: string
  include_week: boolean
  status: 'draft' | 'awaiting' | 'active' | 'declined' | 'revoked'
  url: string | null
  requested_at: string | null
  authorised_at: string | null
  revoked_at: string | null
  updated_at: string | null
  last_opened_at: string | null
  open_count: number
  created_by_name: string | null
}

export interface PtVisit {
  id: number
  patient_id: string
  on: string
  at: string | null
  kind: 'visit' | 'evaluation' | 'test_day'
  kind_label: string
  note: string
  created_by_name: string | null
}

export interface PtMark {
  id: number
  patient_id: string
  day: string
  kind: 'rest'
  note: string
}

export interface PtSent {
  sent: boolean
  detail: string
  reused: boolean
}

export interface PtChart {
  patient_id: string
  settings: {
    morning_check: { on: boolean; ceiling: number; own: boolean }
    week_checkin: { on: boolean; own: boolean }
  }
  areas: { evaluation: PtArea[]; reported: PtArea[]; areas: string[]; midline: string[] }
  morning: {
    recent: PtMorning[]
    answered: number
    settled: number
    last: PtMorning | null
    can_ask: boolean
  }
  function: { goals: PtGoal[]; max_goals: number; score: PtScoreRead | null }
  week: { latest: PtWeek | null; history: PtWeek[]; this_week: string }
  phases: PtPhases
  tests: { tests: PtTest[]; kinds: PtTestKind[] }
  outcomes: { measures: PtMeasure[]; instruments: PtInstrument[] }
  handoff: PtHandoff | null
  visits: {
    last: PtVisit | null
    next: PtVisit | null
    upcoming: PtVisit[]
    past: PtVisit[]
    days_since_last: number | null
    days_to_next: number | null
  }
  asks: { task_id: number; qset: string; title: string; asked_at: string | null; texted: boolean }[]
  /** Present on the answer to a write that asked the person something. */
  sent?: PtSent
}

export interface PtFlagThreshold {
  key: string
  value: number
  default: number
  low: number
  high: number
  whole: boolean
  changed: boolean
}

export interface PtFlagRule {
  code: string
  name: string
  inputs: string
  rule: string
  thresholds: PtFlagThreshold[]
  fired: { today: number; chart_days: number; charts: number; window_days: number }
}

export interface PtSettings {
  flags: Record<string, number>
  exercise_guard: number
  triage_words: string[]
  morning_check: { on: boolean; ceiling: number }
  week_checkin: { on: boolean }
  outcome_thresholds: Record<string, number>
}

export interface PtRedFlag {
  id: number
  key: string
  label: string
  phrases: string[]
  text: string
  status: 'draft' | 'approved'
  approved_by: string | null
  approved_at: string | null
  updated_at: string | null
  sends: string
  sends_own_words: boolean
}

export interface PtProtocol {
  id: number
  name: string
  description: string
  phases: { name: string; goal: string; criteria: string[] }[]
  created_by: string
  created_at: string | null
}

export interface PtQuestion {
  id: number
  patient_id: string
  patient_name: string
  initials: string
  text: string
  channel: string
  created_at: string
  triage: 'today' | 'weekly' | null
  sorted_by: 'rule' | 'clinician'
  sorted_by_name: string | null
  red_flag: string | null
  done: boolean
  done_at: string | null
}

export interface PtClipComment {
  id: number
  assignment_id: number
  at_ms: number | null
  text: string
  by: string
  by_name: string | null
  created_at: string | null
  voice: { id: number; url?: string | null; content_type: string } | null
}

export interface PtEarlierClip {
  assignment_id: number
  day: string
  pain_after: number | null
  effort: number | null
  load: string | null
  review_note: string
  video: { id: number; url?: string | null; content_type: string } | null
}

export interface PtBetweenWeek {
  week_checkin: PtWeek | null
  mornings: { asked: number; answered: number; settled: number; not_settled: number }
  next_visit: PtVisit | null
  phase: { name: string; number: number; count: number; met: number; of: number } | null
}

export interface PtHandoffPage {
  person: string
  clinic: string
  from: string | null
  trainer_name: string
  limits: string[]
  report_back: string
  phase: { name: string; goal: string; number: number; count: number } | null
  week: { day: string; title: string; dose: string; ceiling: string; instructions: string }[]
  week_start: string
  updated_at: string | null
  authorised_on: string | null
}

// --- reads --------------------------------------------------------------------------

const json = (body: unknown) => JSON.stringify(body ?? {})

export function usePtCatalog(enabled = true) {
  return useQuery({
    queryKey: ['pt', 'catalog'],
    queryFn: () => fetchJson<PtCatalog>('/api/pt/catalog'),
    enabled,
    staleTime: 5 * 60_000,
  })
}

export function usePtChart(patientId: string, enabled = true) {
  return useQuery({
    queryKey: ['pt', 'chart', patientId],
    queryFn: () => fetchJson<PtChart>(`/api/pt/patients/${encodeURIComponent(patientId)}`),
    enabled,
  })
}

export function usePtSettings() {
  return useQuery({
    queryKey: ['pt', 'settings'],
    queryFn: () =>
      fetchJson<{ clinic: string; settings: PtSettings; defaults: PtSettings }>('/api/pt/settings'),
  })
}

export function usePtFlags() {
  return useQuery({
    queryKey: ['pt', 'flags'],
    queryFn: () => fetchJson<{ clinic: string; flags: PtFlagRule[] }>('/api/pt/flags'),
  })
}

export function useRedFlags() {
  return useQuery({
    queryKey: ['pt', 'red-flags'],
    queryFn: () =>
      fetchJson<{ clinic: string; entries: PtRedFlag[]; standing_reply: string }>('/api/pt/red-flags'),
  })
}

export function useProtocols(enabled = true) {
  return useQuery({
    queryKey: ['pt', 'protocols'],
    queryFn: () => fetchJson<{ clinic: string; protocols: PtProtocol[] }>('/api/pt/protocols'),
    enabled,
  })
}

export function useQuestions(enabled = true) {
  return useQuery({
    queryKey: ['pt', 'questions'],
    queryFn: () =>
      fetchJson<{ today: PtQuestion[]; weekly: PtQuestion[]; done: PtQuestion[]; words: string[] }>(
        '/api/pt/questions',
      ),
    enabled,
    refetchInterval: 60_000,
  })
}

export function useClipDetail(assignmentId: number | null) {
  return useQuery({
    queryKey: ['pt', 'clip', assignmentId],
    queryFn: () =>
      fetchJson<{ comments: PtClipComment[]; earlier: PtEarlierClip[] }>(
        `/api/pt/assignments/${assignmentId}/clip`,
      ),
    enabled: assignmentId != null,
  })
}

/** The trainer's page: no console credential, the link is the permission. */
export function useHandoffPage(token: string | undefined) {
  return useQuery({
    queryKey: ['pt', 'handoff-page', token],
    queryFn: () => fetchJson<PtHandoffPage>(`/api/handoff/${encodeURIComponent(token ?? '')}`),
    enabled: !!token,
    retry: false,
  })
}

// --- writes -------------------------------------------------------------------------

export interface PtActionInput {
  /** Path under `/api/pt/patients/{id}`, with its leading slash. */
  path: string
  method?: 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  body?: unknown
}

/** One write to a chart's record. The server answers with the chart as it
 *  now stands, which goes straight into the cache. Writes that touch the
 *  calendar (a visit) or what a chart is scored on (an area, a phase) also
 *  refresh those. */
export function usePtAction(patientId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ path, method = 'POST', body }: PtActionInput) =>
      fetchJson<PtChart>(`/api/pt/patients/${encodeURIComponent(patientId)}${path}`, {
        method,
        body: method === 'DELETE' ? undefined : json(body),
      }),
    onSuccess: (chart, input) => {
      qc.setQueryData(['pt', 'chart', patientId], chart)
      if (input.path.startsWith('/visits') || input.path.startsWith('/marks')) invalidateSchedule(qc)
      if (input.path.startsWith('/areas')) {
        void qc.invalidateQueries({ queryKey: ['patient', patientId] })
        void qc.invalidateQueries({ queryKey: ['worklist'] })
      }
    },
  })
}

export function useUpdatePtSettings() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (patch: Partial<PtSettings> & { flags?: Record<string, number | null> }) =>
      fetchJson<{ settings: PtSettings; defaults: PtSettings }>('/api/pt/settings', {
        method: 'PATCH',
        body: json(patch),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pt'] })
      // A threshold changes what every chart is scored as.
      void qc.invalidateQueries({ queryKey: ['worklist'] })
      void qc.invalidateQueries({ queryKey: ['patient'] })
    },
  })
}

export function useRedFlagAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ path = '', method = 'POST', body }: { path?: string; method?: string; body?: unknown }) =>
      fetchJson<{ entries: PtRedFlag[]; standing_reply: string }>(`/api/pt/red-flags${path}`, {
        method,
        body: method === 'DELETE' ? undefined : json(body),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['pt', 'red-flags'] }),
  })
}

export function useProtocolAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ path = '', method = 'POST', body }: { path?: string; method?: string; body?: unknown }) =>
      fetchJson<{ protocols: PtProtocol[] }>(`/api/pt/protocols${path}`, {
        method,
        body: method === 'DELETE' ? undefined : json(body),
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['pt', 'protocols'] }),
  })
}

export function useMoveQuestion() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number; triage?: 'today' | 'weekly' | 'none'; done?: boolean; by?: string }) =>
      fetchJson<{ ok: boolean }>(`/api/pt/questions/${id}`, { method: 'POST', body: json(body) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['pt', 'questions'] }),
  })
}

export function useClipCommentAction(assignmentId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { remove?: number; by?: string; at_ms?: number | null; text?: string; voice_attachment_id?: number }) => {
      if (input.remove != null) {
        return fetchJson<{ comments: PtClipComment[] }>(`/api/pt/comments/${input.remove}`, {
          method: 'DELETE',
        })
      }
      return fetchJson<{ comments: PtClipComment[] }>(`/api/pt/assignments/${assignmentId}/comments`, {
        method: 'POST',
        body: json(input),
      })
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['pt', 'clip', assignmentId] }),
  })
}

export function useRemoveVisit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => fetchJson<{ ok: boolean }>(`/api/pt/visits/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['pt', 'chart'] })
      invalidateSchedule(qc)
    },
  })
}

export function useSetMark() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ patientId, ...body }: { patientId: string; day: string; note?: string }) =>
      fetchJson<{ mark: PtMark }>(`/api/pt/patients/${encodeURIComponent(patientId)}/marks`, {
        method: 'POST',
        body: json({ ...body, kind: 'rest' }),
      }),
    onSuccess: () => invalidateSchedule(qc),
  })
}

export function useClearMark() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => fetchJson<{ ok: boolean }>(`/api/pt/marks/${id}`, { method: 'DELETE' }),
    onSuccess: () => invalidateSchedule(qc),
  })
}

export interface GuardHit {
  day: string
  would_be: number
  limit: number
  patient_id: string
  patient_name: string
}

/** Before assigning: the days one more exercise would take a person past
 *  the clinic's exercise count. Writes nothing. */
export function useGuardCheck() {
  return useMutation({
    mutationFn: (body: { patient_ids: string[]; dates?: string[]; repeat?: unknown }) =>
      fetchJson<{ guard: GuardHit[]; limit: number }>('/api/hep/schedule/check', {
        method: 'POST',
        body: json(body),
      }),
  })
}

// --- words --------------------------------------------------------------------------

/** "Sat, Nov 14" from an ISO day, read as a calendar day (no timezone). */
export function dayText(iso: string | null | undefined): string {
  if (!iso) return ''
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number)
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
}

/** "9:30 AM" from "09:30". */
export function clockText(at: string | null | undefined): string {
  if (!at) return ''
  const [h, m] = at.split(':').map(Number)
  return new Date(2000, 0, 1, h, m).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
}

export function visitText(v: PtVisit | null | undefined): string {
  if (!v) return ''
  return [v.kind_label, dayText(v.on), clockText(v.at)].filter(Boolean).join(' · ')
}

export const firstName = (name: string) => name.trim().split(/\s+/)[0] || name
