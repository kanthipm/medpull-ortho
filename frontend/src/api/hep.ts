import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, consoleAuthHeaders, fetchJson } from './client'

/** Home exercise program contract (`app/hep/api.py`): the exercise library a
 *  clinic assigns from. Standard exercises are shared and read-only; custom
 *  ones belong to the clinic. Plans are the standing prescription; the
 *  schedule (docs/dev/hep-schedule.md, the section at the end of this file)
 *  is one exercise on one patient's day. */

export type BodyRegion = 'knee' | 'hip' | 'ankle' | 'shoulder' | 'back_core' | 'full_body'
export type ExerciseCategory = 'mobility' | 'strengthening' | 'balance' | 'functional'
export type ExerciseOrigin = 'standard' | 'custom'
export type ExerciseStatus = 'draft' | 'review' | 'approved' | 'archived'
export type MediaApproval = 'pending' | 'approved' | 'rejected'

export interface ExerciseMedia {
  id: number
  kind: 'video' | 'image' | string
  approval_status: MediaApproval | string
  /** True only once a reviewer approved the clip; then `url` is set. */
  playable: boolean
  url: string | null
  poster_url: string | null
  width: number | null
  height: number | null
  duration_ms: number | null
  reviewed_by: string | null
  reviewed_at: string | null
  version: number
}

export interface Exercise {
  id: number
  key: string | null
  origin: ExerciseOrigin | string
  clinic_id: string | null
  title: string
  synonyms: string[]
  body_region: BodyRegion | string
  body_region_label: string
  category: ExerciseCategory | string
  category_label: string
  /** Newline-separated steps; `steps` is the same split for rendering. */
  instructions: string
  steps: string[]
  equipment: string
  precautions: string
  status: ExerciseStatus | string
  version: number
  usage_count: number
  /** The library's clip. */
  media: ExerciseMedia | null
  /** The clinic's own demonstration of this exercise, approved on upload;
   *  it wins over `media` wherever the exercise is shown to the clinic or
   *  its patients. Absent on a server that predates the schedule. */
  clinic_media?: ClinicMedia | null
  created_by: string
  created_at: string | null
  updated_at: string | null
}

/** `media`'s shape, from the clinic: `source` says so, and who filmed it. */
export interface ClinicMedia extends ExerciseMedia {
  source: 'clinic' | string
  uploaded_by?: string | null
  uploaded_by_name?: string | null
  created_at?: string | null
}

export interface Vocab {
  key: string
  label: string
}

export interface ExercisesResponse {
  exercises: Exercise[]
  clinic: { id: string; name: string }
  regions: Vocab[]
  categories: Vocab[]
  statuses: string[]
}

export interface ExerciseFilters {
  q?: string
  region?: string
  category?: string
  origin?: ExerciseOrigin
  include_archived?: boolean
}

export interface ExerciseBody {
  title: string
  body_region: string
  category: string
  instructions: string
  synonyms: string[]
  equipment: string
  precautions: string
}

export type ExercisePatch = Partial<ExerciseBody> & { status?: ExerciseStatus }

function query(filters: ExerciseFilters): string {
  const p = new URLSearchParams()
  if (filters.q?.trim()) p.set('q', filters.q.trim())
  if (filters.region) p.set('region', filters.region)
  if (filters.category) p.set('category', filters.category)
  if (filters.origin) p.set('origin', filters.origin)
  if (filters.include_archived) p.set('include_archived', 'true')
  const s = p.toString()
  return s ? `?${s}` : ''
}

export function useExercises(filters: ExerciseFilters = {}) {
  return useQuery({
    queryKey: ['hep', 'exercises', filters],
    queryFn: () => fetchJson<ExercisesResponse>(`/api/hep/exercises${query(filters)}`),
    placeholderData: (prev) => prev,
  })
}

export function useCreateExercise() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ExerciseBody) =>
      fetchJson<Exercise>('/api/hep/exercises/custom', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['hep', 'exercises'] }),
  })
}

export function useUpdateExercise() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: ExercisePatch & { id: number }) =>
      fetchJson<Exercise>(`/api/hep/exercises/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['hep', 'exercises'] }),
  })
}

// --- plans -------------------------------------------------------------------

export type PlanStatus = 'draft' | 'active' | 'superseded' | 'archived'
export type Frequency =
  | 'daily'
  | 'twice_daily'
  | 'three_times_daily'
  | 'every_other_day'
  | 'three_per_week'
  | 'weekly'
export type Side = 'left' | 'right' | 'both' | 'not_applicable'

export interface PlanItem {
  id: number
  exercise_id: number
  exercise_version: number
  /** True once published: the text below is frozen, not the live library. */
  snapshotted: boolean
  sort_order: number
  title: string
  key: string | null
  body_region: string | null
  category: string | null
  steps: string[]
  equipment: string
  /** The precaution the patient reads: the override when set, else the library's. */
  precautions: string
  library_precautions: string
  sets: number | null
  reps: number | null
  hold_seconds: number | null
  frequency: Frequency | string
  frequency_label: string
  side: Side | string
  side_label: string
  clinician_instructions: string
  precautions_override: string
  /** One line: "3 sets × 10 reps · Twice a day · Left". */
  dose: string
  media: ExerciseMedia | null
  library_current: Exercise | null
  library_changed: boolean
}

export interface Plan {
  id: number
  clinic_id: string
  title: string
  notes: string
  status: PlanStatus | string
  version: number
  patient: { id: string; name: string } | null
  invitation_id: number | null
  assigned_by: string
  assigned_by_name: string | null
  exercise_count: number
  /** Null on list rows (fetched without items). */
  items: PlanItem[] | null
  published_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface PlanItemBody {
  exercise_id: number
  sets?: number | null
  reps?: number | null
  hold_seconds?: number | null
  frequency?: string
  side?: string
  clinician_instructions?: string
  precautions_override?: string
}

export interface PlanCreateBody {
  patient_id?: string | null
  title?: string
  notes?: string
  items?: PlanItemBody[]
  assigned_by?: string
  actor?: string
}

export interface PlanUpdateBody {
  version: number
  patient_id?: string | null
  title?: string
  notes?: string
  items?: PlanItemBody[]
  assigned_by?: string
  actor?: string
}

export interface PublishResult {
  plan: Plan
  superseded: number[]
  invitation: { needed: boolean; status: string; detail: string }
  delivery: { channel: string; patient_has_app: boolean; detail: string }
}

export interface PatientPlans {
  active: Plan | null
  drafts: Plan[]
  history: Plan[]
}

export interface HepOptions {
  frequencies: Vocab[]
  sides: Vocab[]
  patients: { id: string; name: string; has_phone: boolean }[]
  care_team: { id: string; name: string; role: string }[]
  max_items: number
  regions: Vocab[]
  categories: Vocab[]
  statuses: string[]
}

export function useHepOptions() {
  return useQuery({
    queryKey: ['hep', 'options'],
    queryFn: () => fetchJson<HepOptions>('/api/hep/options'),
    staleTime: 5 * 60_000,
  })
}

export function usePlans(status?: string) {
  return useQuery({
    queryKey: ['hep', 'plans', { status: status ?? null }],
    queryFn: () => fetchJson<{ plans: Plan[] }>(`/api/hep/plans${status ? `?status=${status}` : ''}`),
    placeholderData: (prev) => prev,
  })
}

export function usePlan(id: number | null) {
  return useQuery({
    queryKey: ['hep', 'plan', id],
    queryFn: () => fetchJson<Plan>(`/api/hep/plans/${id}`),
    enabled: id != null,
  })
}

export function usePatientPlans(patientId: string) {
  return useQuery({
    queryKey: ['hep', 'patient-plans', patientId],
    queryFn: () => fetchJson<PatientPlans>(`/api/hep/patients/${patientId}/plans`),
  })
}

function invalidatePlans(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: ['hep', 'plans'] })
  void qc.invalidateQueries({ queryKey: ['hep', 'plan'] })
  void qc.invalidateQueries({ queryKey: ['hep', 'patient-plans'] })
  void qc.invalidateQueries({ queryKey: ['hep', 'exercises'] })
}

export function useCreatePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: PlanCreateBody) =>
      fetchJson<Plan>('/api/hep/plans', { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => invalidatePlans(qc),
  })
}

export function useUpdatePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: PlanUpdateBody & { id: number }) =>
      fetchJson<Plan>(`/api/hep/plans/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
    onSuccess: () => invalidatePlans(qc),
  })
}

export function usePublishPlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, version, actor }: { id: number; version: number; actor?: string }) =>
      fetchJson<PublishResult>(`/api/hep/plans/${id}/publish`, {
        method: 'POST',
        body: JSON.stringify({ version, actor: actor ?? 'provider' }),
      }),
    onSuccess: () => invalidatePlans(qc),
  })
}

export function useArchivePlan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, actor }: { id: number; actor?: string }) =>
      fetchJson<Plan>(`/api/hep/plans/${id}/archive`, {
        method: 'POST',
        body: JSON.stringify({ actor: actor ?? 'provider' }),
      }),
    onSuccess: () => invalidatePlans(qc),
  })
}

// --- the schedule ----------------------------------------------------------------
//
// docs/dev/hep-schedule.md. One exercise on one patient's calendar day — what
// the therapist puts on the week grid and what the patient's Today shows —
// with the clip that demonstrates it (the clinic's own when it has one, else
// the library's) and, once done, what came back: a pain score, a note, the
// patient's clip of their attempt.

export type AssignmentStatus = 'assigned' | 'done' | 'skipped'

/** The clip an assignment plays. `source` says whose it is. */
export interface AssignmentVideo {
  id: number
  kind: 'video' | 'image' | string
  source: 'clinic' | 'library' | string
  url: string | null
  poster_url: string | null
  content_type: string | null
  duration_ms: number | null
  uploaded_by: string | null
  uploaded_by_name: string | null
  created_at: string | null
}

/** The patient's clip of their attempt: the attachments view with its URL,
 *  or `url` null where the server has no link to give. */
export interface CompletionVideo {
  id: number
  kind: 'video' | 'image' | 'audio' | 'file' | string
  content_type: string
  byte_size: number
  filename: string | null
  url: string | null
  created_at: string | null
}

export interface AssignmentCompletion {
  completed_at: string
  /** 0–10, or null when the patient skipped the question. */
  pain_after: number | null
  note: string | null
  /** `app` — the patient marked it done; `console` — logged in the room. */
  source: 'app' | 'console' | string
  video: CompletionVideo | null
}

/** The one shape both clients read. */
export interface Assignment {
  id: number
  clinic_id?: string
  patient_id: string
  exercise_id: number
  exercise_key: string | null
  title: string
  body_region: string
  body_region_label: string
  category: string
  category_label: string
  steps: string[]
  equipment: string
  precautions: string
  /** YYYY-MM-DD */
  scheduled_for: string
  sort_order: number
  sets: number | null
  reps: number | null
  hold_seconds: number | null
  side: Side | string
  side_label: string
  /** "3 sets × 10 reps · Left" — `plans.dose_line` without the frequency. */
  dose: string
  clinician_instructions: string
  assigned_by: string
  assigned_by_name: string | null
  status: AssignmentStatus | string
  video: AssignmentVideo | null
  completion: AssignmentCompletion | null
  skip_reason: string | null
  created_at: string | null
  updated_at: string | null
}

export interface CareTeamMember {
  id: string
  name: string
  role: string
}

/** One row of the grid: a clinic chart and its week. */
export interface SchedulePatientSummary {
  id: string
  name: string
  initials: string
  /** `care_pathway`, else the procedure. */
  pathway: string | null
  assigned_provider_id: string | null
  assigned_provider_name: string | null
  /** The newest assessment's tier, lower-case, or null before the first. */
  risk_tier: string | null
}

export interface SchedulePatient extends SchedulePatientSummary {
  assignments: Assignment[]
}

/** GET /api/hep/schedule */
export interface ScheduleResponse {
  start: string
  days: string[]
  today: string
  patients: SchedulePatient[]
  /** The clinic's therapists: the assigned providers of its charts. */
  care_team: CareTeamMember[]
}

/** GET /api/hep/patients/{id}/schedule */
export interface PatientScheduleResponse {
  patient: SchedulePatientSummary & { assignments?: Assignment[] }
  days: string[]
  today: string
  assignments: Assignment[]
}

export interface ScheduleCreateBody {
  patient_id: string
  exercise_id: number
  /** 1–31 dates within −60…+90 days of today; one already holding this
   *  exercise is a 409 naming the date. */
  dates: string[]
  sets?: number | null
  reps?: number | null
  hold_seconds?: number | null
  side?: string
  clinician_instructions?: string
  /** A care-team id; the server defaults to the patient's provider. */
  assigned_by?: string
}

/** PATCH /api/hep/schedule/{id} — any of these. Moving or re-dosing a done
 *  row is a 409. */
export interface AssignmentPatch {
  sets?: number | null
  reps?: number | null
  hold_seconds?: number | null
  side?: string
  clinician_instructions?: string
  scheduled_for?: string
  assigned_by?: string
  sort_order?: number
}

/** POST /api/hep/schedule/{id}/complete — the therapist logging it from
 *  the room; the row comes back with `completion.source` "console". */
export interface CompleteBody {
  pain_after: number | null
  note: string
  actor: string
}

/** POST /api/demo/patient-session — a signed-in phone for the demo screen. */
export interface DemoPatientSession {
  token: string
  patient: { id: string; name: string }
}

/** The browser's local calendar date as YYYY-MM-DD: the `today` the schedule
 *  routes take, so the grid's today is the clinician's, not the server's. */
export function isoDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

export function todayIso(): string {
  return isoDate(new Date())
}

function scheduleQuery(start: string | null, days: number, patientId?: string): string {
  const p = new URLSearchParams()
  if (start) p.set('start', start)
  p.set('days', String(days))
  p.set('today', todayIso())
  if (patientId) p.set('patient_id', patientId)
  return `?${p.toString()}`
}

/** The clinic's week: every clinic chart, one row each. `start` null lets
 *  the server pick the Monday of this week. `live` polls every 15 s, for the
 *  demo screen where a completion from the phone should show on the board
 *  without a reload. */
export function useSchedule(
  start: string | null,
  days = 7,
  patientId?: string,
  options: { live?: boolean } = {},
) {
  return useQuery({
    queryKey: ['hep', 'schedule', { start, days, patientId: patientId ?? null, today: todayIso() }],
    queryFn: () => fetchJson<ScheduleResponse>(`/api/hep/schedule${scheduleQuery(start, days, patientId)}`),
    placeholderData: (prev) => prev,
    refetchInterval: options.live ? 15_000 : undefined,
  })
}

/** One patient's week, for the patient page. */
export function usePatientSchedule(
  patientId: string,
  start: string | null,
  days = 7,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: ['hep', 'patient-schedule', patientId, { start, days, today: todayIso() }],
    queryFn: () =>
      fetchJson<PatientScheduleResponse>(
        `/api/hep/patients/${patientId}/schedule${scheduleQuery(start, days)}`,
      ),
    enabled: options.enabled ?? true,
  })
}

function invalidateSchedule(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: ['hep', 'schedule'] })
  void qc.invalidateQueries({ queryKey: ['hep', 'patient-schedule'] })
  // The demo screen listens and tells the phone frame to re-read its day.
  window.dispatchEvent(new CustomEvent('medpull:schedule-changed'))
}

export function useCreateAssignments() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: ScheduleCreateBody) =>
      fetchJson<{ assignments: Assignment[] }>('/api/hep/schedule', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidateSchedule(qc),
  })
}

export function useUpdateAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: AssignmentPatch & { id: number }) =>
      fetchJson<Assignment>(`/api/hep/schedule/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(patch),
      }),
    onSuccess: () => invalidateSchedule(qc),
  })
}

export function useDeleteAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) =>
      fetchJson<{ ok: boolean }>(`/api/hep/schedule/${id}`, { method: 'DELETE' }),
    onSuccess: () => invalidateSchedule(qc),
  })
}

export function useCompleteAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: CompleteBody & { id: number }) =>
      fetchJson<Assignment>(`/api/hep/schedule/${id}/complete`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => invalidateSchedule(qc),
  })
}

export function useDemoPatientSession() {
  return useMutation({
    mutationFn: (patientId: string) =>
      fetchJson<DemoPatientSession>('/api/demo/patient-session', {
        method: 'POST',
        body: JSON.stringify({ patient_id: patientId }),
      }),
  })
}

// --- the therapist's clip ----------------------------------------------------------
//
// The same two paths as a thread attachment (api/attachments.ts): with an
// object store the API presigns a POST and the bytes go straight there;
// without one the API takes the body itself. The ticket says which. A clip
// is far bigger than a photo, so the bytes go out through XMLHttpRequest,
// which reports upload progress; fetch cannot.

/** What the file input offers: the two formats a phone records and every
 *  browser plays. The server sniffs the bytes regardless. */
export const CLIP_ACCEPT = 'video/mp4,video/quicktime'

/** GET …/media/upload-ticket — the attachments ticket shape. */
interface ClipTicket {
  storage_key: string
  direct: boolean
  max_bytes: number
  upload: { url: string; fields: Record<string, string>; expires_in: number } | null
}

export interface ClipUploadProgress {
  /** `ticket` — asking for a slot; `upload` — the bytes, with `fraction`
   *  0–1; `confirm` — the server checking what landed. */
  phase: 'ticket' | 'upload' | 'confirm'
  fraction: number
}

/** A clip over a clinic's Wi-Fi: ten minutes before giving up. */
const CLIP_UPLOAD_TIMEOUT_MS = 10 * 60_000

function postBytes(
  url: string,
  body: XMLHttpRequestBodyInit,
  headers: Record<string, string>,
  onFraction: (f: number) => void,
): Promise<{ ok: boolean; status: number; text: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', url)
    xhr.timeout = CLIP_UPLOAD_TIMEOUT_MS
    for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v)
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && e.total > 0) onFraction(e.loaded / e.total)
    }
    xhr.onload = () =>
      resolve({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, text: xhr.responseText })
    xhr.onerror = () => reject(new ApiError(0, 'The upload could not reach the server'))
    xhr.ontimeout = () =>
      reject(new ApiError(0, `The upload took longer than ${CLIP_UPLOAD_TIMEOUT_MS / 60_000} minutes`, true))
    xhr.onabort = () => reject(new ApiError(0, 'The upload was cancelled'))
    xhr.send(body)
  })
}

function detailOf(text: string, fallback: string): string {
  try {
    const body = JSON.parse(text)
    if (typeof body.detail === 'string') return body.detail
  } catch {
    /* not JSON */
  }
  return fallback
}

/** A phone's `.mov` sometimes arrives with no MIME type; the extension says. */
export function clipContentType(file: File): string {
  if (file.type) return file.type
  const name = file.name.toLowerCase()
  if (name.endsWith('.mov') || name.endsWith('.qt')) return 'video/quicktime'
  if (name.endsWith('.mp4') || name.endsWith('.m4v')) return 'video/mp4'
  return 'application/octet-stream'
}

/** Put the therapist's demonstration of one exercise on the clinic's
 *  library. Returns the exercise with `clinic_media` filled; from then on the
 *  clip plays wherever that exercise is assigned. */
export async function uploadClinicClip(
  exerciseId: number,
  file: File,
  actor: string,
  onProgress: (p: ClipUploadProgress) => void = () => {},
): Promise<Exercise> {
  const base = `/api/hep/exercises/${exerciseId}/media`
  const type = clipContentType(file)
  onProgress({ phase: 'ticket', fraction: 0 })
  const ticket = await fetchJson<ClipTicket>(
    `${base}/upload-ticket?content_type=${encodeURIComponent(type)}&byte_size=${file.size}`,
  )
  if (file.size > ticket.max_bytes) {
    throw new ApiError(413, `That clip is over ${Math.floor(ticket.max_bytes / (1024 * 1024))} MB`)
  }

  if (ticket.direct || !ticket.upload) {
    // Straight to the API: a console call, so it carries the console's token.
    const res = await postBytes(
      `${base}/direct?filename=${encodeURIComponent(file.name)}&actor=${encodeURIComponent(actor)}`,
      file,
      { 'Content-Type': type, ...consoleAuthHeaders() },
      (f) => onProgress({ phase: 'upload', fraction: f }),
    )
    if (!res.ok) throw new ApiError(res.status, detailOf(res.text, res.status === 401 ? 'Sign in again' : 'The upload failed'))
    return unwrapExercise(JSON.parse(res.text))
  }

  // A presigned POST carries its own authorization in the signed fields, so
  // it goes out with no headers of ours — and the file part last, as S3
  // requires.
  const form = new FormData()
  for (const [k, v] of Object.entries(ticket.upload.fields)) form.append(k, v)
  form.append('file', file)
  const put = await postBytes(ticket.upload.url, form, {}, (f) => onProgress({ phase: 'upload', fraction: f }))
  if (!put.ok) throw new ApiError(put.status, 'The upload was refused by storage')

  onProgress({ phase: 'confirm', fraction: 1 })
  const confirmed = await fetchJson<{ exercise: Exercise }>(base, {
    method: 'POST',
    body: JSON.stringify({
      storage_key: ticket.storage_key,
      content_type: type,
      byte_size: file.size,
      filename: file.name,
      actor,
    }),
  })
  return unwrapExercise(confirmed)
}

/** The confirm answers `{ exercise }`; the direct path is documented as its
 *  twin, and a bare exercise is accepted too in case it answers plainly. */
function unwrapExercise(body: unknown): Exercise {
  const o = body as { exercise?: Exercise } & Partial<Exercise>
  if (o && typeof o === 'object' && o.exercise && typeof o.exercise === 'object') return o.exercise
  if (o && typeof o === 'object' && typeof o.id === 'number' && typeof o.title === 'string') return o as Exercise
  throw new ApiError(502, 'The server did not return the exercise')
}

function invalidateClips(qc: ReturnType<typeof useQueryClient>) {
  // The exercise rows carry clinic_media; every assignment's `video`
  // resolves through it; the plan editor's rows show whether a clip exists.
  void qc.invalidateQueries({ queryKey: ['hep', 'exercises'] })
  void qc.invalidateQueries({ queryKey: ['hep', 'plan'] })
  void qc.invalidateQueries({ queryKey: ['hep', 'patient-plans'] })
  invalidateSchedule(qc)
}

export function useUploadClinicClip() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      exerciseId,
      file,
      actor,
      onProgress,
    }: {
      exerciseId: number
      file: File
      actor: string
      onProgress?: (p: ClipUploadProgress) => void
    }) => uploadClinicClip(exerciseId, file, actor, onProgress),
    onSuccess: () => invalidateClips(qc),
  })
}

/** Take the clinic's clip down (blob and row); the library's, if any, shows
 *  again wherever the exercise is assigned. */
export function useDeleteClinicClip() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ exerciseId, mediaId }: { exerciseId: number; mediaId: number }) =>
      fetchJson<{ ok: boolean }>(`/api/hep/exercises/${exerciseId}/media/${mediaId}`, {
        method: 'DELETE',
      }),
    onSuccess: () => invalidateClips(qc),
  })
}
