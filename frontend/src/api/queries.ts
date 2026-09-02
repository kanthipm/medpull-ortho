import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { InvalidateQueryFilters, QueryKey } from '@tanstack/react-query'
import { fetchJson } from './client'
import type {
  AppNotification,
  Checkin,
  IntegrationsResponse,
  JunctionBackfill,
  JunctionLink,
  JunctionStatus,
  NotificationPreference,
  PatientDetail,
  PatientMetrics,
  PatientWearables,
  PracticeOverview,
  RtmDocument,
  RtmReadiness,
  TimelineEvent,
  WearableConnection,
  WorklistResponse,
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

export function useAssignTask(id: string) {
  return useMutation({
    mutationFn: (task: { title: string; why: string }) =>
      fetchJson<{ ok: boolean }>(`/api/patients/${id}/actions/assign-task`, {
        method: 'POST',
        body: JSON.stringify(task),
      }),
  })
}

export function useMessagePatient(id: string) {
  return useMutation({
    mutationFn: (text: string) =>
      fetchJson<{ status: string }>(`/api/patients/${id}/actions/message`, {
        method: 'POST',
        body: JSON.stringify({ text }),
      }),
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

export function useRtmStatus(id: string) {
  return useQuery({
    queryKey: ['patient', id, 'rtm'],
    queryFn: () => fetchJson<RtmReadiness>(`/api/patients/${id}/rtm`),
  })
}

export function useRtmDocuments(id: string, enabled = true) {
  return useQuery({
    queryKey: ['patient', id, 'rtm-documents'],
    queryFn: () => fetchJson<{ documents: RtmDocument[] }>(`/api/patients/${id}/rtm/documents`),
    enabled,
  })
}

export function usePracticeOverview() {
  return useQuery({
    queryKey: ['practice-overview'],
    queryFn: () => fetchJson<PracticeOverview>('/api/practice/overview'),
  })
}

/** Caches an RTM write moves: the patient's own readiness card, and the
 *  practice strip, which sums every patient's minutes into ready-to-bill and
 *  estimated revenue. */
export function rtmKeys(id: string): QueryKey[] {
  return [
    ['patient', id, 'rtm'],
    ['practice-overview'],
  ]
}

/** Caches a recompute moves: the patient record, its worklist row and the
 *  headline above it, the practice strip's needs-review count — which counts
 *  the same tier the headline does, so the two must move together — and the
 *  bell, since a recompute that flips a patient to high writes a notification
 *  server-side. */
export function recomputeKeys(id: string): QueryKey[] {
  return [
    ['patient', id],
    ['worklist'],
    ['practice-overview'],
    ['notifications'],
  ]
}

function useRtmInvalidation(id: string) {
  const qc = useQueryClient()
  return () => {
    for (const queryKey of rtmKeys(id)) qc.invalidateQueries({ queryKey })
  }
}

export function useLogCall(id: string) {
  const invalidate = useRtmInvalidation(id)
  return useMutation({
    mutationFn: (call: { minutes: number; note: string }) =>
      fetchJson<{ ok: boolean; logged_minutes: number }>(`/api/patients/${id}/actions/call`, {
        method: 'POST',
        body: JSON.stringify(call),
      }),
    onSuccess: invalidate,
  })
}

export function useScheduleFollowup(id: string) {
  const invalidate = useRtmInvalidation(id)
  return useMutation({
    mutationFn: (followup: { when: string; note: string }) =>
      fetchJson<{ ok: boolean }>(`/api/patients/${id}/actions/schedule-followup`, {
        method: 'POST',
        body: JSON.stringify(followup),
      }),
    onSuccess: invalidate,
  })
}

export function useUpdatePlan(id: string) {
  const invalidate = useRtmInvalidation(id)
  return useMutation({
    mutationFn: (summary: string) =>
      fetchJson<{ ok: boolean }>(`/api/patients/${id}/actions/update-plan`, {
        method: 'POST',
        body: JSON.stringify({ summary }),
      }),
    onSuccess: invalidate,
  })
}

export function useApproveDocument(id: string) {
  const qc = useQueryClient()
  const invalidate = useRtmInvalidation(id)
  return useMutation({
    mutationFn: (documentId: number) =>
      fetchJson<{ ok: boolean }>(`/api/patients/${id}/rtm/documents/${documentId}/approve`, {
        method: 'POST',
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['patient', id, 'rtm-documents'] })
      invalidate()
    },
  })
}

export function useRegenerateDocument(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (documentId: number) =>
      fetchJson<{ ok: boolean }>(`/api/patients/${id}/rtm/documents/${documentId}/regenerate`, {
        method: 'POST',
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['patient', id, 'rtm-documents'] }),
  })
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
