import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson } from './client'

/** Home exercise program contract (`app/hep/api.py`): the exercise library a
 *  clinic assigns from. Standard exercises are shared and read-only; custom
 *  ones belong to the clinic. Plans and completions join in later slices. */

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
  media: ExerciseMedia | null
  created_by: string
  created_at: string | null
  updated_at: string | null
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
