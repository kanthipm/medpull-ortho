import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { InvalidateQueryFilters, QueryClient, QueryKey } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import type { CareMetricsResponse } from './care'
import { fetchJson } from './client'
import { patientKeys, SEEDED } from './keys'
import type { NextStepsResponse, PlanResponse } from './plan'
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
  Health,
} from './types'

/** The pages that carry live numbers refresh themselves every five minutes
 *  while open; everything else rides on the client's 5-minute staleTime. */
const LIVE_REFETCH_MS = 5 * 60_000

export function fetchWorklist() {
  return fetchJson<WorklistResponse>('/api/worklist')
}

export function useWorklist() {
  return useQuery({
    queryKey: ['worklist'],
    queryFn: fetchWorklist,
    refetchInterval: LIVE_REFETCH_MS,
  })
}

/** `GET /api/patients/{id}/overview`: the record plus everything the patient
 *  page's cards read, each part byte-identical to its own route. */
export interface PatientOverview {
  detail: PatientDetail
  care_metrics: CareMetricsResponse
  next_steps: NextStepsResponse
  plan: PlanResponse
  checkins: { checkins: Checkin[] }
  timeline: { events: TimelineEvent[] }
  messages: { messages: PatientMessage[] }
  wearables: PatientWearables
}

/** The patient page's eight reads in one request. The seven sub-resources
 *  are written straight into their own cache entries (`patientKeys`), so the
 *  hooks below find them fresh when their cards mount and issue nothing; the
 *  record is what the detail query itself holds. Opening a patient used to
 *  fan out into eleven requests in two waves, which on Lambda competes with
 *  every phone for the function's reserved concurrency. */
async function loadPatientOverview(qc: QueryClient, id: string): Promise<PatientDetail> {
  const o = await fetchJson<PatientOverview>(`/api/patients/${id}/overview`)
  qc.setQueryData(patientKeys.careMetrics(id), o.care_metrics)
  qc.setQueryData(patientKeys.nextSteps(id), o.next_steps)
  qc.setQueryData(patientKeys.plan(id), o.plan)
  qc.setQueryData(patientKeys.checkins(id), o.checkins)
  qc.setQueryData(patientKeys.timeline(id), o.timeline)
  qc.setQueryData(patientKeys.messages(id), o.messages)
  qc.setQueryData(patientKeys.wearables(id), o.wearables)
  return o.detail
}

export function usePatient(id: string) {
  const qc = useQueryClient()
  return useQuery({
    queryKey: patientKeys.detail(id),
    queryFn: () => loadPatientOverview(qc, id),
    refetchInterval: LIVE_REFETCH_MS,
  })
}

/** Warm the whole patient page before the row is clicked, so every card
 *  paints from the cache. Fired on hover/focus of a worklist row;
 *  prefetchQuery is a no-op while the cache is fresh. */
export function usePrefetchPatient() {
  const qc = useQueryClient()
  return (id: string) => {
    void qc.prefetchQuery({
      queryKey: patientKeys.detail(id),
      queryFn: () => loadPatientOverview(qc, id),
    })
  }
}

export function usePatientMetrics(id: string, enabled = true) {
  return useQuery({
    queryKey: ['patient', id, 'metrics'],
    queryFn: () => fetchJson<PatientMetrics>(`/api/patients/${id}/metrics`),
    enabled,
    refetchInterval: LIVE_REFETCH_MS,
  })
}

export interface WarmNarrativesResult {
  generated: { kind: string; patient_id: string | null; provider: string }[]
  spent: number
  /** Narratives still rules-based after this pass. */
  pending: number
  elapsed_ms: number
}

/** `POST /api/narratives/warm` — the one call allowed to spend model time.
 *  Page reads answer from the cache or the deterministic renderer at once
 *  and report `narratives_pending`; this fills the model versions in the
 *  background and the caller refetches the page when it lands. Bounded
 *  server-side at ~20 s, so the ordinary 30 s fetch deadline covers it. */
export function useWarmNarratives() {
  return useMutation({
    mutationFn: (body: { patient_id?: string; worklist?: boolean; budget?: number }) =>
      fetchJson<WarmNarrativesResult>('/api/narratives/warm', {
        method: 'POST',
        body: JSON.stringify(body),
      }),
  })
}

/** Drive the warm call for one page: when `pending > 0`, call once, refetch
 *  the given keys when it returns, and go again while the server still
 *  reports pending work — at most `MAX_ROUNDS`, never two in flight at once,
 *  and never again for the same page unless the data turns stale on its
 *  own. Returns whether a warm is in flight (the "Writing…" shimmer). */
const MAX_ROUNDS = 3

export function useNarrativeWarming(
  pending: number | undefined,
  body: { patient_id?: string; worklist?: boolean },
  keys: QueryKey[],
): boolean {
  const qc = useQueryClient()
  const warm = useWarmNarratives()
  const inFlight = useRef(false)
  // rounds spent, keyed by the page they were spent on, so a new patient
  // starts afresh and a return to the old one does not start over
  const rounds = useRef<{ page: string; n: number }>({ page: '', n: 0 })
  const pageKey = JSON.stringify(body)
  const [busy, setBusy] = useState(false)
  const keysKey = JSON.stringify(keys)

  useEffect(() => {
    if (!pending || pending <= 0) return
    if (rounds.current.page !== pageKey) rounds.current = { page: pageKey, n: 0 }
    if (inFlight.current || rounds.current.n >= MAX_ROUNDS) return
    inFlight.current = true
    rounds.current.n += 1
    setBusy(true)
    warm.mutate(body, {
      onSuccess: () => {
        // Exact, not by prefix: a warm rewrites narratives, which live on the
        // record and the worklist. The patient record's refetch is the
        // overview read, which re-seeds the cards' caches anyway, so a prefix
        // sweep here only added eight requests per round for the same bytes.
        for (const queryKey of JSON.parse(keysKey) as QueryKey[]) {
          void qc.invalidateQueries({ queryKey, exact: true })
        }
      },
      onSettled: () => {
        inFlight.current = false
        setBusy(false)
      },
    })
    // `warm` and `body` are stable for a page; the deps that matter are the
    // pending count the server reported and which page this is.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, pageKey, keysKey])

  return busy
}

export function usePatientTimeline(id: string) {
  return useQuery({
    queryKey: patientKeys.timeline(id),
    queryFn: () => fetchJson<{ events: TimelineEvent[] }>(`/api/patients/${id}/timeline`),
    ...SEEDED,
  })
}

export function usePatientCheckins(id: string) {
  return useQuery({
    queryKey: patientKeys.checkins(id),
    queryFn: () => fetchJson<{ checkins: Checkin[] }>(`/api/patients/${id}/checkins`),
    ...SEEDED,
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
    queryKey: patientKeys.wearables(id),
    queryFn: () => fetchJson<PatientWearables>(`/api/patients/${id}/wearables`),
    ...SEEDED,
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
    queryKey: patientKeys.messages(id),
    queryFn: () => fetchJson<{ messages: PatientMessage[] }>(`/api/patients/${id}/messages`),
    refetchInterval: 30_000,
    ...SEEDED,
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

/** Which deployment this is. Fetched once; it cannot change under a page. */
export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => fetchJson<Health>('/api/health'),
    staleTime: Infinity,
  })
}

/** True on the public demo stack only, and false until the server has said. */
export function useIsDemo(): boolean {
  return useHealth().data?.demo === true
}
