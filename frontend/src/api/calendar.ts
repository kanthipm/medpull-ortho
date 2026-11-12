import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchJson } from './client'
import {
  invalidateSchedule,
  todayIso,
  type Adherence,
  type Assignment,
  type AssignmentPatch,
  type AssignmentState,
  type CalendarMark,
  type CalendarVisit,
  type HepClinic,
  type LoadUnit,
  type LoadWeek,
  type ReviewReason,
  type SchedulePatientSummary,
  type TextOutcome,
} from './hep'
import type { PtBetweenWeek } from './pt'

/** The calendar's wider reads and the writes that work on more than one
 *  day: the month, the week in review, one exercise over time, a repeat as
 *  one thing, a copy onto other days, an undo of a day logged in the room,
 *  the clinic's unit, and the text that carries today's plan. The week grid
 *  itself, and a single day's writes, are in `hep.ts`. */

// --- the clinic ---------------------------------------------------------------------

/** The clinic the calendar is acting for (the one picked in the workspace
 *  menu, else the server's default) and the unit it reads loads in. */
export function useHepClinic(enabled = true) {
  return useQuery({
    queryKey: ['hep', 'clinic'],
    queryFn: () => fetchJson<HepClinic>('/api/hep/clinic'),
    enabled,
    staleTime: 60_000,
  })
}

/** Pounds or kilograms for the acting clinic: a display choice. Every load
 *  is stored, sent and received in kilograms whatever it says, and every
 *  line the server words (a dose, "35 lb done, 25 lb prescribed") follows. */
export function useSetLoadUnit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (unit: LoadUnit) =>
      fetchJson<HepClinic>('/api/hep/clinic', {
        method: 'PATCH',
        body: JSON.stringify({ load_unit: unit }),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['hep'] })
      void qc.invalidateQueries({ queryKey: ['patient'] })
    },
  })
}

// --- the month ----------------------------------------------------------------------

/** One row on one day of the month, compact: no steps and no clip URLs. */
export interface CalendarItem {
  id: number
  patient_id: string
  exercise_id: number
  title: string
  scheduled_for: string
  sort_order: number
  series_id: string | null
  status: string
  state: AssignmentState | string
  dose: string
  load_kg: number | null
  rpe_target: number | null
  video_requirement: string
  pain_after: number | null
  effort: number | null
  over: boolean
  under: boolean
  line: string | null
  awaiting_review: boolean
  review_reason: ReviewReason | null
  has_clip: boolean
  reviewed: boolean
}

export interface CalendarDay {
  date: string
  assigned: number
  done: number
  skipped: number
  missed: number
  open: number
  over: number
  awaiting_review: number
  items: CalendarItem[]
}

export interface CalendarPatient extends SchedulePatientSummary {
  adherence: Adherence | null
  load_week: LoadWeek | null
  awaiting_review: number
  over_week?: number
  days: CalendarDay[]
}

/** GET /api/hep/calendar — six weeks from the Monday on or before `start`. */
export interface CalendarResponse {
  start: string
  days: string[]
  today: string
  clinic: HepClinic | null
  patients: CalendarPatient[]
  /** The clinic visits and rest days in the window (app/pt). */
  visits?: CalendarVisit[]
  marks?: CalendarMark[]
}

export function useCalendarMonth(start: string, options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ['hep', 'calendar', { start, today: todayIso() }],
    queryFn: () =>
      fetchJson<CalendarResponse>(
        `/api/hep/calendar?start=${encodeURIComponent(start)}&today=${todayIso()}`,
      ),
    enabled: options.enabled ?? true,
    placeholderData: (prev) => prev,
  })
}

// --- the week in review -------------------------------------------------------------

export interface WeekOver {
  assignment_id: number
  exercise_id: number
  title: string
  day: string
  /** "35 lb done, 25 lb prescribed · effort 8, target 7", in the clinic's unit. */
  line: string
  reviewed: boolean
}

/** Why a lifter is near the top of the week in review. */
export type WeekAttention = 'over' | 'review' | 'missed' | 'pain' | 'next_week' | string

export interface WeekEntry {
  patient: SchedulePatientSummary & {
    adherence: Adherence | null
    load_week: LoadWeek | null
    awaiting_review: number
    over_week?: number
  }
  /** The week on the page: `open` is still ahead, `missed` is behind. */
  week: { assigned: number; done: number; skipped: number; missed: number; open: number; pct: number }
  pain: {
    before_avg: number | null
    after_avg: number | null
    after_max: number | null
    by_day: {
      date: string
      done: number
      before_avg: number | null
      after_avg: number | null
      after_max: number | null
    }[]
  }
  effort: {
    avg: number | null
    target_avg: number | null
    avg_where_targeted: number | null
    days_over_target: number
  }
  /** Kilograms moved (load × reps × sets). */
  load: {
    done: number
    planned: number
    last_week_done: number
    change_pct: number | null
    planned_vs_last_week_pct: number | null
  }
  over: WeekOver[]
  awaiting_review: number
  last_patient_message_at: string | null
  next_week: {
    start: string
    assigned: number
    planned_load: number
    /** Whether anything is on next week yet. */
    set: boolean
    change_pct: number | null
  }
  attention: WeekAttention[]
  /** What the clinic's between-visits record says about the same week:
   *  the lifter's own word on it, the mornings after loaded sessions, the
   *  next visit and the phase they are in. Null on a server before it. */
  between_visits?: PtBetweenWeek | null
}

/** GET /api/hep/week — one entry per lifter, those with something to look at first. */
export interface WeekResponse {
  start: string
  days: string[]
  today: string
  clinic: HepClinic | null
  patients: WeekEntry[]
  visits?: CalendarVisit[]
  marks?: CalendarMark[]
}

export function useWeekReview(start: string | null) {
  return useQuery({
    queryKey: ['hep', 'week', { start, today: todayIso() }],
    queryFn: () => {
      const p = new URLSearchParams({ today: todayIso() })
      if (start) p.set('start', start)
      return fetchJson<WeekResponse>(`/api/hep/week?${p.toString()}`)
    },
    placeholderData: (prev) => prev,
  })
}

// --- one exercise over time -------------------------------------------------------------

export interface HistoryPoint {
  id: number
  date: string
  status: string
  state: AssignmentState | string
  dose: string
  sets: number | null
  reps: number | null
  hold_seconds: number | null
  load_kg: number | null
  sets_done: number | null
  reps_done: number | null
  load_done_kg: number | null
  tonnage: number | null
  planned_tonnage: number | null
  pain_before: number | null
  pain_after: number | null
  effort: number | null
  rpe_target: number | null
  duration_s: number | null
  has_clip: boolean
  reviewed: boolean
  over: boolean
  under: boolean
  line: string | null
}

export interface HistorySummary {
  sessions: number
  sessions_done: number
  skipped: number
  missed: number
  over: number
  first_load_kg: number | null
  first_load_on: string | null
  latest_load_kg: number | null
  latest_load_on: string | null
  best_load_kg: number | null
  best_load_on: string | null
  load_change_pct: number | null
  total_tonnage: number
  pain_after_avg: number | null
  effort_avg: number | null
  last_done_on: string | null
}

/** GET /api/hep/patients/{id}/exercises/{exercise}/history — oldest first. */
export interface HistoryResponse {
  patient: { id: string; name: string }
  exercise: { id: number; key: string | null; title: string }
  from: string
  to: string
  today: string
  clinic: HepClinic | null
  points: HistoryPoint[]
  summary: HistorySummary
}

export function useExerciseHistory(patientId: string, exerciseId: number, enabled = true) {
  return useQuery({
    queryKey: ['hep', 'history', patientId, exerciseId, todayIso()],
    queryFn: () =>
      fetchJson<HistoryResponse>(
        `/api/hep/patients/${encodeURIComponent(patientId)}/exercises/${exerciseId}/history?today=${todayIso()}`,
      ),
    enabled,
  })
}

// --- writes on more than one day ---------------------------------------------------------

/** The same exercise at the same dose, note and requirements on other
 *  days, as open days of their own. All or nothing: a day that already
 *  carries the exercise is a 409 naming it. */
export function useDuplicateAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dates, actor }: { id: number; dates: string[]; actor?: string }) =>
      fetchJson<{ assignments: Assignment[] }>(`/api/hep/schedule/${id}/duplicate`, {
        method: 'POST',
        body: JSON.stringify({ dates, ...(actor ? { actor } : {}) }),
      }),
    onSuccess: () => invalidateSchedule(qc),
  })
}

/** Undo a day the console logged done. A day the patient logged themselves
 *  is their record: the server answers 409 with the words why. */
export function useReopenAssignment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, actor }: { id: number; actor?: string }) =>
      fetchJson<Assignment>(`/api/hep/schedule/${id}/reopen`, {
        method: 'POST',
        body: JSON.stringify(actor ? { actor } : {}),
      }),
    onSuccess: () => invalidateSchedule(qc),
  })
}

export type SeriesPatch = Omit<AssignmentPatch, 'scheduled_for' | 'sort_order'>

/** "This and the following": the fields sent go onto every still-open day
 *  of the repeat from `from` on. Done, skipped and earlier days keep theirs. */
export function useUpdateSeries() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ seriesId, from, ...patch }: SeriesPatch & { seriesId: string; from: string }) =>
      fetchJson<{ series_id: string; from: string; updated: number; assignments: Assignment[] }>(
        `/api/hep/series/${encodeURIComponent(seriesId)}?from=${from}`,
        { method: 'PATCH', body: JSON.stringify(patch) },
      ),
    onSuccess: () => invalidateSchedule(qc),
  })
}

/** Clear the repeat's still-open days from `from` on; `kept` counts the
 *  days of the repeat that stay (done, skipped, earlier). */
export function useDeleteSeries() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ seriesId, from }: { seriesId: string; from: string }) =>
      fetchJson<{ ok: boolean; deleted: number; kept: number }>(
        `/api/hep/series/${encodeURIComponent(seriesId)}?from=${from}`,
        { method: 'DELETE' },
      ),
    onSuccess: () => invalidateSchedule(qc),
  })
}

// --- the text ------------------------------------------------------------------------------

/** Text one lifter their plan for the day, with a link that opens the app
 *  on it. A chart that cannot be texted at all answers 409 with the reason
 *  in words (no number, a placeholder, a STOP, texting not set up). */
export function useTextToday() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ patientId, by, day }: { patientId: string; by?: string; day?: string }) =>
      fetchJson<TextOutcome>(`/api/hep/patients/${encodeURIComponent(patientId)}/text-today`, {
        method: 'POST',
        body: JSON.stringify({ ...(by ? { by } : {}), ...(day ? { day } : {}) }),
      }),
    onSuccess: (_r, v) => {
      void qc.invalidateQueries({ queryKey: ['patient', v.patientId] })
    },
  })
}

/** How many rows wait for a look, for the number beside Review: the same
 *  definition as the queue, without rendering a row. */
export function useReviewCount(days = 14) {
  return useQuery({
    queryKey: ['hep', 'review', 'count', { days }],
    queryFn: () =>
      fetchJson<{ count: number; days: number; by_reason: Record<string, number> }>(
        `/api/hep/review/count?days=${days}`,
      ),
    placeholderData: (prev) => prev,
  })
}
