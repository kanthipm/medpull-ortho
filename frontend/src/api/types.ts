import type { ConfidenceLevel, MetricStatus, Priority, TrajectoryState, Urgency } from '../lib/risk'

export interface DataConfidence {
  score: number
  level: ConfidenceLevel
  days_with_data?: number
}

export interface Trajectory {
  state: TrajectoryState
  pct: number | null
}

export interface WorklistPatient {
  id: string
  name: string
  initials: string
  priority: Priority
  reason: string
  procedure_display: string
  postop_day: number
  days_since_discharge: number
  last_checkin_at: string | null
  assigned_provider: { name: string; role: string }
  data_confidence: DataConfidence
  trajectory: Trajectory
  rtm: { days: number; target: number; eligible: boolean; enrolled: boolean }
}

export interface WorklistResponse {
  as_of: string
  stats: { total: number; high: number; medium: number; missing: number; low: number }
  briefing: { text: string; generated_at: string; provider: string }
  patients: WorklistPatient[]
}

export interface RiskReason {
  code: string
  text: string
  severity: number
}

export interface SuggestedAction {
  title: string
  detail: string
  urgency: Urgency
}

export interface PatientDetail {
  id: string
  name: string
  initials: string
  age: number
  sex: string
  procedure_display: string
  postop_day: number
  surgery_date: string
  discharge_date: string
  surgeon: string
  assigned_provider: string
  device: { provider: string; model: string; last_sync_at: string | null } | null
  risk: { level: Priority; score: number; reasons: RiskReason[]; computed_at: string }
  data_confidence: DataConfidence
  trajectory: Trajectory
  summary: { text: string; generated_at: string; provider: string }
  actions: SuggestedAction[]
  rtm: { days_with_data: number; window_days: number; target: number; qualifies: boolean; enrolled: boolean }
  last_checkin_at: string | null
}

export interface MetricInsight {
  metric_key: string
  name: string
  status: MetricStatus
  status_text: string
  finding: string
  confidence: ConfidenceLevel
  coverage_text: string
  next_step: string | null
  guarded: boolean
  unit: string
  series: { date: string; value: number }[]
  baseline_mean: number | null
}

export interface PatientMetrics {
  data_confidence: DataConfidence
  trajectory: Trajectory & {
    change_point_day: number | null
    actual: { day: number; v: number }[]
    expected: { day: number; lo: number; mid: number; hi: number }[]
    // true when the index carries no pre-op norm: the verdict is about pace
    // rather than capacity, and `ahead` is withheld
    anchored: boolean
  }
  composite: {
    index: number
    level: string
    drivers: { metric_type: string; label: string; contribution: number; direction: string }[]
  }
  metrics: MetricInsight[]
  adherence: { rate: number; verified: number; assigned: number; self_attested: number; days: number[] }
}

export interface TimelineEvent {
  date: string
  kind: 'surgery' | 'discharge' | 'checkin' | 'flag' | 'change_point' | 'today'
  label: string
}

export interface CheckinMessage {
  who: 'patient' | 'copilot'
  text: string
}

export interface CheckinDigest {
  highlight: string | null
  topics: string[]
  tone: 'worse' | 'better' | 'steady' | null
}

export interface Checkin {
  id: number
  occurred_at: string
  channel: string
  messages: CheckinMessage[]
  digest: CheckinDigest
}

export interface AppNotification {
  id: number
  patient_id: string
  patient_name: string
  kind: string
  title: string
  body: string
  channel: string
  status: string
  created_at: string
}

export interface IntegrationProvider {
  key: string
  name: string
  status: 'mock_connected' | 'coming_soon'
  capabilities: string[]
  connected_patients: number
  gait_capable: boolean
}

export interface NotificationPreference {
  channel: string
  enabled: boolean
  min_priority: string
  available: boolean
}

export interface RtmBillingCode {
  cpt: string
  eligible: boolean
  note: string
  units: number
}

export interface RtmReadiness {
  month: string
  enrollment: {
    education_complete: boolean
    consent_complete: boolean
    baseline_complete: boolean
    complete: boolean
    pathway: string | null
  }
  monitoring: {
    days: number
    target: number
    window_days: number
    eligible: boolean
    enrolled: boolean
  }
  treatment_management: {
    minutes: number
    interactive_communication: boolean
    // the period the minutes were counted over — `billable_from` is the
    // enrollment date once enrolled, since pre-enrollment minutes are real
    // work but not billable work
    counted_from: string
    counted_to: string
    billable_from: string | null
  }
  documentation_ready: boolean
  billing: RtmBillingCode[]
  ready_to_bill: boolean
  suggested_action: string
  estimated_value: number
  recent_interactions: { kind: string; detail: string; occurred_at: string }[]
}

export interface RtmDocument {
  id: number
  kind: 'encounter_note' | 'monthly_summary'
  title: string
  body: string
  status: 'draft' | 'approved'
  provider: string
  created_at: string
  approved_at: string | null
}

export interface PracticeOverview {
  rtm_patients: number
  needs_review: number
  ready_to_bill: number
  therapy_adherence_pct: number | null
  estimated_revenue: number
}
