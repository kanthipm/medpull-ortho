import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson } from './client'
import type { PatientDetail, TaskStatus, WorklistPatient } from './types'
import type { Urgency } from '../lib/risk'

/** Care-plan contract (`app/api/plan.py`): the task-template library, the AI
 *  task builder, a patient's plan (their `AdherenceTask` rows plus our
 *  `payload["care"]` verification semantics and 14-day records), message
 *  templates and drafts, and the action planner's next steps. Kept apart
 *  from `queries.ts`/`types.ts` on purpose — another session owns those. The
 *  thread itself (their `GET /messages`, `POST /actions/message`) is read
 *  through their hooks in `queries.ts`; nothing here duplicates them. */

// --- vocabulary --------------------------------------------------------------

export type TaskPhase = 'early' | 'mid' | 'late' | 'ongoing'
export type TaskSchedule = 'daily' | 'am_pm' | 'weekly' | 'once' | 'ongoing'
/** Their lifecycle kind — what the SMS/app conversation asks. */
export type TheirTaskKind = 'checkin' | 'exercise' | 'walk' | 'medication' | 'wound_check' | 'custom'
/** Our verification kind — what data (or self-report) marks a day done. */
export type VerifyKind = string

export const PHASES: { key: TaskPhase; label: string }[] = [
  { key: 'early', label: 'Early' },
  { key: 'mid', label: 'Mid' },
  { key: 'late', label: 'Late' },
  { key: 'ongoing', label: 'Ongoing' },
]

export const SCHEDULES: { key: TaskSchedule; label: string }[] = [
  { key: 'daily', label: 'Daily' },
  { key: 'am_pm', label: 'Morning & evening' },
  { key: 'weekly', label: 'Weekly' },
  { key: 'once', label: 'Once' },
  { key: 'ongoing', label: 'Ongoing' },
]

export const THEIR_KINDS: { key: TheirTaskKind; label: string }[] = [
  { key: 'checkin', label: 'Daily check-in' },
  { key: 'exercise', label: 'Exercises' },
  { key: 'walk', label: 'Walk' },
  { key: 'medication', label: 'Medication' },
  { key: 'wound_check', label: 'Incision check' },
  { key: 'custom', label: 'Task' },
]

export interface ParamField {
  name: string
  type: 'int' | 'float' | 'str' | 'bool' | 'list' | 'enum' | string
  default: unknown
  label: string
  options?: string[]
  min?: number
  max?: number
}

export interface KindInfo {
  kind: VerifyKind
  label: string
  verified_by: string
  params_schema: ParamField[]
  /** Their lifecycle kind this verify kind maps to by default. */
  task_kind: TheirTaskKind
  /** What the check-in asks when data cannot confirm it; null = nothing. */
  checkin?: 'yes_no' | 'count' | null
  data_verified?: boolean
}

// --- task templates ----------------------------------------------------------

export interface TaskTemplate {
  id: number
  key: string | null
  title: string
  why: string
  clinical_target: string
  verify_kind: VerifyKind
  task_kind: TheirTaskKind
  params: Record<string, unknown>
  schedule: TaskSchedule
  phase: TaskPhase
  feeds: string[]
  /** Pathway keys or domains; [] = every pathway. */
  pathways: string[]
  use_case: string
  source: 'library' | 'custom' | 'ai' | string
  pinned: boolean
  archived: boolean
  usage_count: number
  /** Derived by the router from `verify_kind`; the kind catalog is the fallback. */
  verified_by?: string
  created_by?: string
  created_at?: string
}

export interface TaskTemplatesResponse {
  templates: TaskTemplate[]
  kinds: KindInfo[]
  /** Every pathway the library knows, for the settings form's chips. */
  pathways?: { key: string; name: string; domain: string }[]
}

export interface TaskTemplateBody {
  title: string
  why: string
  clinical_target?: string
  verify_kind: VerifyKind
  task_kind?: TheirTaskKind
  params?: Record<string, unknown>
  schedule?: TaskSchedule
  phase?: TaskPhase
  feeds?: string[]
  pathways?: string[]
  use_case?: string
  pinned?: boolean
}

export type TaskTemplatePatch = Partial<TaskTemplateBody> & { archived?: boolean }

// --- plan items / drafts -----------------------------------------------------

export interface PlanItem {
  template_id: number | null
  template_key: string | null
  title: string
  why: string
  clinical_target: string
  task_kind: TheirTaskKind
  verify_kind: VerifyKind
  params: Record<string, unknown>
  schedule: TaskSchedule
  phase: TaskPhase
  feeds: string[]
  due_at: string | null
  save_as_template: boolean
  pin: boolean
}

export interface DraftTask extends PlanItem {
  rationale?: string
  source_template_key?: string | null
  /** "ai" when the builder drafted it; the server records it on the task. */
  assigned_by?: 'provider' | 'ai'
}

export interface DraftResponse {
  tasks: DraftTask[]
  provider: string
}

// --- a patient's plan --------------------------------------------------------

export type RecordStatus = 'verified' | 'self_attested' | 'missed' | 'pending' | 'none'

export interface PlanRecord {
  date: string
  status: RecordStatus
  source?: string | null
  count?: number | null
}

/** One task as `app/plan/service.py:task_payload` renders it: their
 *  lifecycle fields flattened next to our care semantics (`verify_kind`,
 *  `phase`, `schedule`, `template_key`) and the 14-day record strip with
 *  its counts. Only active tasks come back from `/plan`. */
export interface PlanTask {
  id: number
  title: string
  why: string
  clinical_target: string
  task_kind: TheirTaskKind | string
  kind_label: string
  verify_kind: VerifyKind | null
  params: Record<string, unknown>
  schedule: TaskSchedule
  phase: TaskPhase
  feeds: string[]
  verified_by: string
  active: boolean
  status: TaskStatus
  assigned_at: string | null
  assigned_on: string | null
  due_at: string | null
  sent_at: string | null
  completed_at: string | null
  completed_via: string | null
  template_key: string | null
  pathway: string | null
  assigned_by: 'provider' | 'ai' | 'seed' | string
  last14: PlanRecord[]
  /** verified + ½ self-attested over assigned days; null with no records. */
  rate: number | null
  verified_rate: number | null
  verified: number
  self_attested: number
  missed: number
}

export interface PlanSummary {
  active: number
  rate: number | null
  task_days?: number
  verified: number
  self_attested: number
  missed: number
  /** Optional delivery facts the section reads when the server sends them. */
  phone?: string | null
  sms_available?: boolean
}

export interface PlanResponse {
  tasks: PlanTask[]
  summary: PlanSummary
}

export interface AssignPlanBody {
  items: PlanItem[]
  notify: boolean
}

export interface PlanDelivery {
  channel: 'sms' | 'none' | string
  sent: boolean
  detail: string
}

export interface AssignPlanResponse {
  tasks: PlanTask[]
  delivery: PlanDelivery & { message_id?: number }
  summary?: PlanSummary
}

export interface RecordPlanTaskBody {
  date: string
  status: 'verified' | 'self_attested' | 'missed'
  count?: number | null
}

// --- message templates -------------------------------------------------------

export type MessageTone = 'warm' | 'direct'

export interface MessageTemplate {
  id: number
  key: string | null
  title: string
  /** May use `{first}` and `{surgeon}`. */
  body: string
  tone: MessageTone | string
  tags: string[]
  source: string
  pinned: boolean
  archived: boolean
  usage_count: number
  created_by?: string
  created_at?: string | null
}

export interface MessageTemplateBody {
  title: string
  body: string
  tone?: MessageTone
  tags?: string[]
  pinned?: boolean
}

export type MessageTemplatePatch = Partial<MessageTemplateBody> & { archived?: boolean }

export interface DraftMessageBody {
  intent?: string
  tone?: MessageTone
  template_id?: number | null
}

export interface DraftMessageResponse {
  message: string
  provider: string
}

// --- next steps --------------------------------------------------------------

export type NextStepActionType =
  | 'message'
  | 'assign_tasks'
  | 'send_checkin'
  | 'escalate'
  | 'call'
  | 'open'
  | 'acknowledge'

export interface NextStepAction {
  type: NextStepActionType
  /** message: the composer's starting text. */
  prefill?: string
  template_key?: string | null
  /** assign_tasks: library keys the step assigns. */
  template_keys?: string[]
  /** call: E.164 for a tel: link. */
  tel?: string | null
  /** open: "full_stats:M12" | "wearables" | "plan" | "messages". */
  target?: string
  [key: string]: unknown
}

export interface NextStepState {
  status: 'open' | 'done' | 'dismissed'
  executed_at: string | null
  result: Record<string, unknown> | null
}

export interface NextStep {
  key: string
  title: string
  detail: string
  urgency: Urgency
  source: string[]
  clicks: 1 | 2
  action: NextStepAction
  state: NextStepState
}

export interface NextStepsResponse {
  steps: NextStep[]
  generated_at: string
}

export interface ExecuteNextStepResponse {
  ok: boolean
  step: NextStep
  result: Record<string, unknown> | null
}

/** The worklist row as the planner extends it (`app/api/worklist.py`). The
 *  base row type is theirs; the extension is typed here. */
export interface WorklistRowWithStep extends WorklistPatient {
  next_step?: NextStep | null
  next_steps_open?: number
}

// --- helpers -----------------------------------------------------------------

/** The detail payload predates the phone column; read it when present. */
export function patientPhone(p: PatientDetail | null | undefined): string | null {
  if (!p) return null
  const phone = (p as unknown as { phone?: string | null }).phone
  return typeof phone === 'string' && phone.trim() ? phone : null
}

export function firstNameOf(name: string): string {
  return name.trim().split(/\s+/)[0] ?? name
}

function qs(params: Record<string, string | boolean | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== '' && v !== false)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

// --- hooks: task templates ---------------------------------------------------

export function useTaskTemplates(pathway?: string, includeArchived = false) {
  return useQuery({
    queryKey: ['task-templates', pathway ?? '', includeArchived],
    queryFn: () =>
      fetchJson<TaskTemplatesResponse>(
        `/api/task-templates${qs({ pathway, include_archived: includeArchived })}`,
      ),
  })
}

export function useCreateTaskTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: TaskTemplateBody) =>
      fetchJson<TaskTemplate>('/api/task-templates', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task-templates'] }),
  })
}

export function useUpdateTaskTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: TaskTemplatePatch & { id: number }) =>
      fetchJson<TaskTemplate>(`/api/task-templates/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['task-templates'] }),
  })
}

// --- hooks: builder ----------------------------------------------------------

export function useDraftTasks() {
  return useMutation({
    mutationFn: (body: { text: string; patient_id?: string; pathway?: string }) =>
      fetchJson<DraftResponse>('/api/task-builder/draft', {
        method: 'POST',
        body: JSON.stringify(body),
        timeoutMs: 45_000,
      }),
  })
}

export function useSuggestPlan(id: string) {
  return useMutation({
    mutationFn: () =>
      fetchJson<DraftResponse>(`/api/patients/${id}/plan/suggest`, {
        method: 'POST',
        timeoutMs: 45_000,
      }),
  })
}

// --- hooks: the patient's plan ----------------------------------------------

export function usePatientPlan(id: string) {
  return useQuery({
    queryKey: ['patient', id, 'plan'],
    queryFn: () => fetchJson<PlanResponse>(`/api/patients/${id}/plan`),
  })
}

/** Whether a text can reach this patient. The detail payload predates the
 *  phone column, so the plan summary is consulted too; with neither saying
 *  anything, texting is assumed unavailable — the builder then explains why
 *  its checkbox is off rather than promising a text that cannot go. */
export function usePatientDelivery(id: string, detail: PatientDetail | null | undefined) {
  const plan = usePatientPlan(id)
  const phone = patientPhone(detail) ?? plan.data?.summary?.phone ?? null
  // The chart itself says whether this server can text at all (Sendblue keys
  // present); the plan summary is a fallback for callers that have no detail.
  const configured = detail?.sms_configured ?? plan.data?.summary?.sms_available ?? true
  return { phone, smsAvailable: Boolean(configured) && phone != null }
}

/** Everything a plan write moves: the patient prefix (plan, their task list,
 *  the thread the summary text lands in, the care metrics M14/M15 refresh
 *  from), the bell, and the worklist row whose next step may change. */
function invalidatePlan(qc: ReturnType<typeof useQueryClient>, id: string) {
  qc.invalidateQueries({ queryKey: ['patient', id] })
  qc.invalidateQueries({ queryKey: ['notifications'] })
  qc.invalidateQueries({ queryKey: ['worklist'] })
  qc.invalidateQueries({ queryKey: ['task-templates'] })
}

export function useAssignPlan(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AssignPlanBody) =>
      fetchJson<AssignPlanResponse>(`/api/patients/${id}/plan`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidatePlan(qc, id),
  })
}

export function useEndPlanTask(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (taskId: number) =>
      fetchJson<{ ok: boolean; task_id: number; summary: PlanSummary }>(
        `/api/patients/${id}/plan/${taskId}/end`,
        { method: 'POST' },
      ),
    onSuccess: () => invalidatePlan(qc, id),
  })
}

export function useRecordPlanTask(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ taskId, ...body }: RecordPlanTaskBody & { taskId: number }) =>
      fetchJson<{ ok?: boolean; record?: PlanRecord }>(
        `/api/patients/${id}/plan/${taskId}/record`,
        { method: 'POST', body: JSON.stringify(body) },
      ),
    onSuccess: () => invalidatePlan(qc, id),
  })
}

// --- hooks: message templates + drafts --------------------------------------

export function useMessageTemplates(includeArchived = false) {
  return useQuery({
    queryKey: ['message-templates', includeArchived],
    queryFn: () =>
      fetchJson<{ templates: MessageTemplate[]; tones?: string[] }>(
        `/api/message-templates${qs({ include_archived: includeArchived })}`,
      ),
  })
}

export function useCreateMessageTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: MessageTemplateBody) =>
      fetchJson<MessageTemplate>('/api/message-templates', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['message-templates'] }),
  })
}

export function useUpdateMessageTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: MessageTemplatePatch & { id: number }) =>
      fetchJson<MessageTemplate>(`/api/message-templates/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['message-templates'] }),
  })
}

export function useDraftPatientMessage(id: string) {
  return useMutation({
    mutationFn: (body: DraftMessageBody) =>
      fetchJson<DraftMessageResponse>(`/api/patients/${id}/messages/draft`, {
        method: 'POST',
        body: JSON.stringify(body),
        timeoutMs: 45_000,
      }),
  })
}

// --- hooks: next steps -------------------------------------------------------

export function useNextSteps(id: string, enabled = true) {
  return useQuery({
    queryKey: ['patient', id, 'next-steps'],
    queryFn: () => fetchJson<NextStepsResponse>(`/api/patients/${id}/next-steps`),
    enabled,
  })
}

/** A step's execution can assign tasks, text the patient, or write a
 *  notification — every cache a plan write moves, plus the step list itself
 *  (under the patient prefix) and the worklist row that mirrors its top step. */
function invalidateSteps(qc: ReturnType<typeof useQueryClient>, id: string) {
  invalidatePlan(qc, id)
}

export function useExecuteNextStep(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, payload_override }: { key: string; payload_override?: Record<string, unknown> }) =>
      fetchJson<ExecuteNextStepResponse>(
        `/api/patients/${id}/next-steps/${encodeURIComponent(key)}/execute`,
        { method: 'POST', body: JSON.stringify(payload_override ? { payload_override } : {}) },
      ),
    onSuccess: () => invalidateSteps(qc, id),
  })
}

export function useCompleteNextStep(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, result }: { key: string; result: Record<string, unknown> }) =>
      fetchJson<{ ok: boolean }>(
        `/api/patients/${id}/next-steps/${encodeURIComponent(key)}/complete`,
        { method: 'POST', body: JSON.stringify({ result }) },
      ),
    onSuccess: () => invalidateSteps(qc, id),
  })
}

export function useDismissNextStep(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) =>
      fetchJson<{ ok: boolean }>(
        `/api/patients/${id}/next-steps/${encodeURIComponent(key)}/dismiss`,
        { method: 'POST' },
      ),
    onSuccess: () => invalidateSteps(qc, id),
  })
}
