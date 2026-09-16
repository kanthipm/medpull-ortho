import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { InvalidateQueryFilters, QueryKey } from '@tanstack/react-query'
import { fetchJson } from './client'
import type {
  AppNotification,
  AssignTaskResult,
  MessagePatientResult,
  PatientMessage,
  PatientTask,
  TaskKind,
  Checkin,
  IntegrationsResponse,
  JunctionBackfill,
  JunctionLink,
  JunctionStatus,
  NotificationPreference,
  PatientDetail,
  PatientMetrics,
  PatientWearables,
  TimelineEvent,
  WearableConnection,
  WorklistResponse,
  AppLinkCandidates,
  AppLinkResult,
  ContactResult,
} from './types'

export function useWorklist() {
  return useQuery({
    queryKey: ['worklist'],
    queryFn: () => fetchJson<WorklistResponse>('/api/worklist'),
  })
}

export function usePatient(id: string) {
  return useQuery({
    queryKey: ['patient', id],
    queryFn: () => fetchJson<PatientDetail>(`/api/patients/${id}`),
  })
}

export function usePatientMetrics(id: string, enabled = true) {
  return useQuery({
    queryKey: ['patient', id, 'metrics'],
    queryFn: () => fetchJson<PatientMetrics>(`/api/patients/${id}/metrics`),
    enabled,
  })
}

export function usePatientTimeline(id: string) {
  return useQuery({
    queryKey: ['patient', id, 'timeline'],
    queryFn: () => fetchJson<{ events: TimelineEvent[] }>(`/api/patients/${id}/timeline`),
  })
}

export function usePatientCheckins(id: string) {
  return useQuery({
    queryKey: ['patient', id, 'checkins'],
    queryFn: () => fetchJson<{ checkins: Checkin[] }>(`/api/patients/${id}/checkins`),
  })
}

export function useNotifications() {
  return useQuery({
    queryKey: ['notifications'],
    queryFn: () => fetchJson<{ notifications: AppNotification[] }>('/api/notifications?status=all'),
    refetchInterval: 60_000,
  })
}

export function useMarkNotificationRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => fetchJson(`/api/notifications/${id}/read`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => fetchJson('/api/notifications/read-all', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
}

export function useIntegrations() {
  return useQuery({
    queryKey: ['integrations'],
    queryFn: () => fetchJson<IntegrationsResponse>('/api/integrations'),
  })
}

export function useJunctionStatus(enabled = true) {
  return useQuery({
    queryKey: ['integrations', 'junction'],
    queryFn: () => fetchJson<JunctionStatus>('/api/integrations/junction/status?limit=10'),
    refetchInterval: 60_000,
    enabled,
  })
}

/** Caches a change to a patient's wearable connection moves: the card
 *  itself, the patient record (its device line reads the newest Device row —
 *  exact, so the metrics/timeline/check-in sub-queries under the same prefix
 *  are left alone), and the Integrations page's per-brand patient counts and
 *  aggregator status. */
export function wearableFilters(id: string): InvalidateQueryFilters[] {
  return [
    { queryKey: ['patient', id, 'wearables'] },
    { queryKey: ['patient', id], exact: true },
    { queryKey: ['integrations'] },
  ]
}

export function usePatientWearables(id: string) {
  return useQuery({
    queryKey: ['patient', id, 'wearables'],
    queryFn: () => fetchJson<PatientWearables>(`/api/patients/${id}/wearables`),
  })
}

export function useRefreshWearables(id: string) {
  const qc = useQueryClient()
  return useMutation({
    // a POST: the re-sync rewrites the snapshot and Device rows, and on AWS
    // only a mutating request runs under the write lock
    mutationFn: () =>
      fetchJson<PatientWearables>(`/api/patients/${id}/wearables/junction/refresh`, {
        method: 'POST',
      }),
    // The response already IS the refreshed card, so it seeds the cache and
    // only the neighbours are refetched.
    onSuccess: (data) => {
      qc.setQueryData(['patient', id, 'wearables'], data)
      for (const filter of wearableFilters(id).slice(1)) qc.invalidateQueries(filter)
    },
  })
}

export function useCreateJunctionLink(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      fetchJson<JunctionLink>(`/api/patients/${id}/wearables/junction/link`, { method: 'POST' }),
    onSuccess: () => {
      for (const filter of wearableFilters(id)) qc.invalidateQueries(filter)
    },
  })
}

export function useJunctionBackfill(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (options: { refresh: boolean }) =>
      fetchJson<JunctionBackfill>(`/api/patients/${id}/wearables/junction/backfill`, {
        method: 'POST',
        body: JSON.stringify(options),
      }),
    // a back-fill that landed rows recomputed the patient server-side, so the
    // same caches a Refresh analysis moves are stale — recomputeKeys' prefix
    // on ['patient', id] deliberately sweeps the metric cards up too
    onSuccess: () => {
      for (const filter of wearableFilters(id)) qc.invalidateQueries(filter)
      for (const queryKey of recomputeKeys(id)) qc.invalidateQueries({ queryKey })
    },
  })
}

export function useDisconnectJunction(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      fetchJson<{ ok: boolean; remote: string; connection: WearableConnection }>(
        `/api/patients/${id}/wearables/junction`,
        { method: 'DELETE' },
      ),
    onSuccess: () => {
      for (const filter of wearableFilters(id)) qc.invalidateQueries(filter)
    },
  })
}

export function useNotificationPreferences() {
  return useQuery({
    queryKey: ['notification-preferences'],
    queryFn: () => fetchJson<NotificationPreference[]>('/api/notification-preferences'),
  })
}

export function useUpdateNotificationPreferences() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (prefs: { channel: string; enabled: boolean; min_priority: string }[]) =>
      fetchJson<NotificationPreference[]>('/api/notification-preferences', {
        method: 'PUT',
        body: JSON.stringify(prefs),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notification-preferences'] }),
  })
}

export interface AskResult {
  answer: string
  patient_ids: string[]
  provider: string
  generated_at: string
}

export function useAsk() {
  return useMutation({
    mutationFn: (question: string) =>
      fetchJson<AskResult>('/api/ask', { method: 'POST', body: JSON.stringify({ question }) }),
  })
}

export function useDraftMessage(id: string) {
  return useMutation({
    mutationFn: () =>
      fetchJson<{ message: string; provider: string }>(
        `/api/patients/${id}/actions/draft-message`,
        { method: 'POST' },
      ),
  })
}

export interface AssignTaskBody {
  title: string
  why?: string
  kind?: TaskKind
  due_at?: string | null
  /** Text the patient about it (default true; needs Sendblue + a phone on file). */
  notify?: boolean
}

export function useAssignTask(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AssignTaskBody) =>
      fetchJson<AssignTaskResult>(`/api/patients/${id}/actions/assign-task`, {
        method: 'POST',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patient', id, 'tasks'] })
      qc.invalidateQueries({ queryKey: ['patient', id, 'messages'] })
    },
  })
}

/** Write to the patient's thread. A string is still accepted, because most
 *  callers only ever send words; attachment ids ride along as an object. */
export function useMessagePatient(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: string | { text: string; attachment_ids?: number[] }) =>
      fetchJson<MessagePatientResult>(`/api/patients/${id}/actions/message`, {
        method: 'POST',
        body: JSON.stringify(typeof input === 'string' ? { text: input } : input),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['patient', id, 'messages'] }),
  })
}

/** Take back a file the clinic sent. The bytes go; the line stays and says
 *  a file was withdrawn, so a reply to it still makes sense. */
export function useWithdrawAttachment(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (attachmentId: number) =>
      fetchJson<{ ok: boolean }>(`/api/patients/${id}/attachments/${attachmentId}`, {
        method: 'DELETE',
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['patient', id, 'messages'] }),
  })
}

export function usePatientTasks(id: string) {
  return useQuery({
    queryKey: ['patient', id, 'tasks'],
    queryFn: () => fetchJson<{ tasks: PatientTask[] }>(`/api/patients/${id}/tasks`),
  })
}

export function usePatientMessages(id: string) {
  return useQuery({
    queryKey: ['patient', id, 'messages'],
    queryFn: () => fetchJson<{ messages: PatientMessage[] }>(`/api/patients/${id}/messages`),
    refetchInterval: 30_000,
  })
}

export function useMarkPatientMessagesRead(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => fetchJson(`/api/patients/${id}/messages/read`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['patient', id, 'messages'] }),
  })
}

/** The number the console texts. A number already on another chart is a 409
 *  unless `force` moves it here; the server keeps one number per patient. */
export function useUpdateContact(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { phone: string | null; force?: boolean }) =>
      fetchJson<ContactResult>(`/api/patients/${id}/contact`, {
        method: 'PATCH',
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patient', id] })
      qc.invalidateQueries({ queryKey: ['worklist'] })
    },
  })
}

export function useAppLinkCandidates(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ['patient', id, 'app-link-candidates'],
    queryFn: () => fetchJson<AppLinkCandidates>(`/api/patients/${id}/app-link/candidates`),
    enabled,
  })
}

/** Fold an app sign-up (another patient record) into this chart. The other
 *  record is deleted server-side, so every cache that could name it goes. */
export function useLinkApp(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (fromPatientId: string) =>
      fetchJson<AppLinkResult>(`/api/patients/${id}/app-link`, {
        method: 'POST',
        body: JSON.stringify({ from_patient_id: fromPatientId }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patient'] })
      qc.invalidateQueries({ queryKey: ['worklist'] })
      qc.invalidateQueries({ queryKey: ['notifications'] })
    },
  })
}

export function useEscalate(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () =>
      fetchJson<{ ok: boolean }>(`/api/patients/${id}/actions/escalate`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['notifications'] }),
  })
}

/** Caches a recompute moves: the patient record, its worklist row and the
 *  headline above it, and the bell, since a recompute that flips a patient to high writes a notification
 *  server-side. */
export function recomputeKeys(id: string): QueryKey[] {
  return [
    ['patient', id],
    ['worklist'],
    ['notifications'],
  ]
}

export function useRecompute(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => fetchJson(`/api/patients/${id}/recompute`, { method: 'POST' }),
    // awaited on purpose: the mutation stays pending until the refetched
    // analysis has landed, which is what the refresh shimmer waits on
    onSuccess: () =>
      Promise.all(recomputeKeys(id).map((queryKey) => qc.invalidateQueries({ queryKey }))),
  })
}
