/** Content width per page (R3). The sky window, the ambient echo and the bar
 *  background stay full-bleed; the content column, the bar's inner row and
 *  the sky window's frame all use the page's own cap (the tokens are
 *  `--page-worklist`, `--page-patient`, `--page-settings` and
 *  `--container-max` in index.css).
 *
 *    worklist  1120px   the clinic worklist ('/')
 *    patient   1240px   two-column pages: a chart, a team board, a member's
 *                       pages, the program and plan editors, one chart's data
 *    settings   980px   single-column lists: settings, integrations, and the
 *                       Calendar's review queue, programs, library and plans
 *    wide      --container-max   grids that want every column: the schedule,
 *                       a lifter's week, the data roster, a team's data; and
 *                       any path with no rule below
 *    full      the whole viewport, a small gutter ('/demo/…' — the demo
 *              screen's schedule-and-phone layout; the bar keeps `wide`)
 *
 *  A new page gets its width here, by path, in the block for its version.
 *  Kept out of AppShell.tsx so that file exports components only. */
export type PageWidth = 'worklist' | 'patient' | 'settings' | 'wide' | 'full'

const under = (pathname: string, prefix: string) =>
  pathname === prefix || pathname.startsWith(`${prefix}/`)

export function pageWidthFor(pathname: string): PageWidth {
  if (pathname === '/') return 'worklist'
  if (pathname.startsWith('/demo/')) return 'full'
  if (pathname.startsWith('/patients/')) return 'patient'

  // Clinic · Calendar
  if (under(pathname, '/calendar')) {
    // the week grid, and one lifter's week beside next week's draft
    if (pathname === '/calendar' || under(pathname, '/calendar/week')) return 'wide'
    // the plan and program editors are two columns, like the patient page
    if (/^\/calendar\/(plans|programs)\/[^/]+/.test(pathname)) return 'patient'
    return 'settings'
  }

  // Clinic · Data
  if (under(pathname, '/data')) {
    // one chart's data reads like the chart; the dictionary is a wide table
    if (pathname.startsWith('/data/patients/') || under(pathname, '/data/dictionary')) return 'patient'
    return 'wide'
  }

  // Sports: the board, an athlete and the calendar share the board's width;
  // the data page is a roster-wide table
  if (under(pathname, '/sports')) {
    return /^\/sports\/teams\/[^/]+\/data(\/|$)/.test(pathname) ? 'wide' : 'patient'
  }

  // Personal: a member's pages are two columns
  if (under(pathname, '/personal')) return 'patient'

  if (under(pathname, '/settings') || under(pathname, '/integrations')) return 'settings'
  return 'wide'
}

export const PAGE_CLASS: Record<PageWidth, string> = {
  worklist: 'page page-worklist',
  patient: 'page page-patient',
  settings: 'page page-settings',
  wide: 'page',
  full: 'page page-full',
}
