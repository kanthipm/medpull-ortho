/** Where the Calendar's pages live. The one place that knows these paths:
 *  every link to an exercise page, inside this feature or from a chart, reads
 *  them here, and `App.tsx` registers the routes (and forwards the old
 *  `/exercise-…` addresses) to match.
 *
 *    /calendar                 the schedule: every lifter's week on one grid
 *    /calendar/week            one lifter's week in review, and next week's draft
 *    /calendar/review          clips waiting on the therapist
 *    /calendar/programs[/:id]  the clinic's programs, and the editor
 *    /calendar/library         the exercises a clinic prescribes from
 *    /calendar/plans[/:id]     home exercise plans, and the editor
 *    /demo/hirt                the room's screen (demo stack), under the same tab
 *
 *  `:id` is `new` for a program or plan that has not been saved yet. */

type Id = string | number

const enc = (id: Id) => encodeURIComponent(String(id))

export const CALENDAR = {
  schedule: '/calendar',
  week: '/calendar/week',
  review: '/calendar/review',
  programs: '/calendar/programs',
  program: (id: Id) => `/calendar/programs/${enc(id)}`,
  newProgram: '/calendar/programs/new',
  library: '/calendar/library',
  plans: '/calendar/plans',
  plan: (id: Id) => `/calendar/plans/${enc(id)}`,
  newPlan: '/calendar/plans/new',
  demoScreen: '/demo/hirt',
} as const

export type CalendarSection = 'schedule' | 'week' | 'review' | 'programs' | 'library' | 'plans'

/** The sub-nav section a Calendar path belongs to. The schedule is the
 *  landing page, so it is what is left when no deeper section matches. */
export function calendarSection(pathname: string): CalendarSection {
  const at = (prefix: string) => pathname === prefix || pathname.startsWith(`${prefix}/`)
  if (at(CALENDAR.week)) return 'week'
  if (at(CALENDAR.review)) return 'review'
  if (at(CALENDAR.programs)) return 'programs'
  if (at(CALENDAR.library)) return 'library'
  if (at(CALENDAR.plans)) return 'plans'
  return 'schedule'
}
