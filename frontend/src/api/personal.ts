import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson } from './client'

/** The console's read-only view of a demo member's space in MedPull
 *  Personal (`/api/console/personal/*`, demo stack and staff only). The
 *  payloads are the ones the member's own phone receives, read through the
 *  same functions, so a page built on them shows what the app shows. A real
 *  subscriber's space is never served here: the server answers 404 for
 *  anyone the showcase did not write. */

export type PanelStatus = 'ok' | 'watch' | 'flag' | 'nodata' | string

export interface PanelStat {
  label: string
  value: string
  unit: string
}

export interface DayValue {
  date: string
  value: number | null
}

/** One readout on the member's dashboard: its number, what it means, how it
 *  is worked out, and the days behind it. */
export interface Panel {
  key: string
  title: string
  status: PanelStatus
  status_text: string
  headline: string
  unit: string
  sub: string
  finding: string
  method: string
  confidence: string
  coverage: string
  stats?: PanelStat[]
  series?: DayValue[]
  extra?: Record<string, unknown>
}

/** What goes into the readiness number: each signal's z-score against the
 *  member's own baseline, its weight and what it added or took away. */
export interface ReadinessComponent {
  key: string
  label: string
  z: number
  weight: number
  value: string
  text: string
  contribution: number
}

export interface Verdict {
  kind: 'push' | 'steady' | 'easy' | 'rest' | 'unknown' | string
  title: string
  reason: string
  detail: string
}

export interface WeekMetric {
  unit: string
  this: number | null
  last: number | null
  delta_pct: number | null
}

export interface WeekBlock {
  start: string
  end: string
  metrics: Record<string, WeekMetric>
  readiness_days: { best: DayValue | null; worst: DayValue | null }
  sessions: number
  session_minutes: number
  streaks: { checkin_days: number; sleep_on_need_days: number }
  highlights: string[]
}

export interface Trend {
  label: string
  unit: string
  weeks: { week: string; value: number | null; days: number }[]
  change_pct: number | null
  weeks_with_data: number
}

export interface Dashboard {
  as_of: string
  goal: string
  days_with_data: number
  verdict: Verdict
  /** The order the member's own Today lists the panels in, by goal. */
  sections: string[]
  panels: Record<string, Panel>
  trends: Record<string, Trend>
  week: WeekBlock
}

/** A paragraph the app writes for the member: the morning brief, a deep
 *  dive, the weekly review. `provider` says who wrote it. */
export interface Writing {
  headline?: string
  title?: string
  brief?: string
  body?: string
  domain?: string
  guardrail: string
  provider: string
  generated_at: string
}

export interface PlanItem {
  id: number
  kind: string
  kind_label: string
  title: string
  why: string
  status: string
  recurring: boolean
  schedule: string
  last_done_on: string | null
  due_at: string | null
  completed_at: string | null
}

export interface ThreadLine {
  id: number
  sender: 'patient' | 'copilot' | 'care_team' | string
  authored_by: string | null
  author_name: string | null
  channel: string
  text: string
  created_at: string
  action: { kind: string; label: string } | null
}

export interface DailyLog {
  date: string
  mood: number | null
  sleep_quality: number | null
  soreness: number | null
  energy: number | null
}

export interface MemberDevice {
  provider: string
  model: string | null
  connected_at: string | null
  last_sync_at: string | null
}

export interface PersonalOverview {
  member: {
    id: string
    name: string
    initials: string
    age: number | null
    goal: string
    goal_label: string
    sport: string | null
    tagline: string
    detail: string
    hero: boolean
    joined_on: string | null
    devices: MemberDevice[]
  }
  profile: {
    goal: string
    goal_label: string
    sport: string | null
    weekly_target_minutes: number | null
    sleep_target_hours: number | null
    injury: string | null
    anchor_date: string | null
    units: string
    sms_briefs: boolean
    brief_hour: number | null
  }
  subscription: { state: string; entitled: boolean; days_left: number | null }
  dashboard: Dashboard
  brief: Writing
  /** The care section a recovery goal adds; null for every other goal. */
  care: Record<string, unknown> | null
  plan: { open: PlanItem[]; recent: PlanItem[] }
  thread: ThreadLine[]
  logs: DailyLog[]
  notes: { date: string; text: string; source: string }[]
}

export function usePersonalOverview(memberId: string) {
  return useQuery({
    queryKey: ['personal', memberId, 'overview'],
    queryFn: () => fetchJson<PersonalOverview>(`/api/console/personal/${encodeURIComponent(memberId)}/overview`),
    enabled: !!memberId,
    staleTime: 30_000,
  })
}

export interface PersonalWeek {
  week: WeekBlock
  trends: Record<string, Trend>
  review: Writing
}

export function usePersonalWeek(memberId: string) {
  return useQuery({
    queryKey: ['personal', memberId, 'week'],
    queryFn: () => fetchJson<PersonalWeek>(`/api/console/personal/${encodeURIComponent(memberId)}/week`),
    enabled: !!memberId,
    staleTime: 30_000,
  })
}

/** One raw daily signal as the member's "all metrics" screen lists it. */
export interface SignalRow {
  key: string
  label: string
  unit: string
  latest: DayValue | null
  series: DayValue[]
  days_with_data?: number
  baseline?: number | null
  source?: string | null
}

export interface PersonalSignals {
  days: number
  since: string
  metrics: SignalRow[]
}

export function usePersonalSignals(memberId: string, days: number) {
  return useQuery({
    queryKey: ['personal', memberId, 'signals', days],
    queryFn: () =>
      fetchJson<PersonalSignals>(`/api/console/personal/${encodeURIComponent(memberId)}/signals?days=${days}`),
    enabled: !!memberId,
    placeholderData: (prev) => prev,
  })
}

export type DeepDive = 'recovery' | 'training' | 'sleep'

export function usePersonalInsight(memberId: string, domain: DeepDive) {
  return useQuery({
    queryKey: ['personal', memberId, 'insight', domain],
    queryFn: () =>
      fetchJson<Writing>(`/api/console/personal/${encodeURIComponent(memberId)}/insights/${domain}`),
    enabled: !!memberId,
    staleTime: 60_000,
  })
}

/** One turn with the member's coach, as the member. Both lines land on the
 *  member's thread, which comes back whole. */
export function useCoachTurn(memberId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (text: string) =>
      fetchJson<{ reply: string | null; provider: string | null; flagged: boolean; thread: ThreadLine[] }>(
        `/api/console/personal/${encodeURIComponent(memberId)}/coach`,
        { method: 'POST', body: JSON.stringify({ text }), timeoutMs: 45_000 },
      ),
    onSuccess: (r) => {
      qc.setQueryData<PersonalOverview>(['personal', memberId, 'overview'], (prev) =>
        prev ? { ...prev, thread: r.thread } : prev,
      )
    },
  })
}

/** Everything the member's account holds, as their own "Export my data"
 *  produces it: fetched on demand and handed to the browser as a file. */
export async function downloadMemberExport(memberId: string): Promise<void> {
  const bundle = await fetchJson<unknown>(`/api/console/personal/${encodeURIComponent(memberId)}/export`)
  const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${memberId}-export.json`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
