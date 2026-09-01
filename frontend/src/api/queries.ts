import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { QueryKey } from '@tanstack/react-query'
import { fetchJson } from './client'
import type {
  AppNotification,
  Checkin,
  IntegrationProvider,
  NotificationPreference,
  PatientDetail,
  PatientMetrics,
  PracticeOverview,
  RtmDocument,
  RtmReadiness,
  TimelineEvent,
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
    queryFn: () => fetchJson<{ providers: IntegrationProvider[] }>('/api/integrations'),
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
