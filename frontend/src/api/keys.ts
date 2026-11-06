import type { QueryKey } from '@tanstack/react-query'

/** Cache keys for the patient page. Every per-resource key sits under the
 *  patient's own prefix, so a Refresh analysis (`recomputeKeys`) sweeps them
 *  all — and `usePatient` seeds every one of them from the single overview
 *  read (`GET /api/patients/{id}/overview`). Named here, in one place, so the
 *  seed and the hooks can never disagree about a key. */
export const patientKeys = {
  detail: (id: string): QueryKey => ['patient', id],
  careMetrics: (id: string): QueryKey => ['patient', id, 'care-metrics'],
  nextSteps: (id: string): QueryKey => ['patient', id, 'next-steps'],
  plan: (id: string): QueryKey => ['patient', id, 'plan'],
  checkins: (id: string): QueryKey => ['patient', id, 'checkins'],
  timeline: (id: string): QueryKey => ['patient', id, 'timeline'],
  messages: (id: string): QueryKey => ['patient', id, 'messages'],
  wearables: (id: string): QueryKey => ['patient', id, 'wearables'],
}

/** Options for a query the overview read seeds. It does not fetch merely
 *  because it mounted or the window regained focus — the overview's own
 *  refetch re-seeds it, and every mutation that moves it still invalidates it
 *  — but it fetches as before when the cache is empty (a page reached without
 *  the seed) and on its own refetchInterval. Without this, opening a patient
 *  fanned out into eleven requests at once, and the API's reserved
 *  concurrency is shared with every phone that is refreshing. */
export const SEEDED = { refetchOnMount: false, refetchOnWindowFocus: false } as const
