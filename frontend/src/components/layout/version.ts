import { VERSIONS, type Version } from '../../api/workspaces'

/** The three versions of the console, read from the path.
 *
 *  One app shows Clinic, Personal and Sports; which one is on screen is a
 *  function of the URL alone, so every link is deterministic and nothing is
 *  ever redirected from storage except the two bare landings (`/personal`,
 *  `/sports`), which name no one.
 *
 *    clinic     everything that is not one of the two prefixes below: the
 *               worklist at `/`, charts, the calendar, the data pages, and
 *               the pages the workspace menu opens (settings, integrations)
 *    personal   `/personal…`    one member at a time: `/personal/:memberId…`
 *    sports     `/sports…`      one team at a time:   `/sports/teams/:teamId…`
 *
 *  Each version puts three tabs in the bar, and they answer the same three
 *  questions everywhere: who needs attention now, what is planned, and what
 *  is the data underneath. To add a page under a tab, give it a path the
 *  tab's `match` already claims (anything under `/calendar`, `/data`, a
 *  member or a team); to add a tab, add it here and nowhere else.
 *
 *  Kept out of AppShell.tsx so that file exports components only. */

export type { Version }
export { VERSIONS }

export const VERSION_LABEL: Record<Version, string> = {
  clinic: 'Clinic',
  personal: 'Personal',
  sports: 'Sports',
}

/** Where each version lands. `/personal` and `/sports` forward to the member
 *  or team that was open last, else the first one. */
export const VERSION_HOME: Record<Version, string> = {
  clinic: '/',
  personal: '/personal',
  sports: '/sports',
}

const under = (pathname: string, prefix: string) =>
  pathname === prefix || pathname.startsWith(`${prefix}/`)

export function versionFor(pathname: string): Version {
  if (under(pathname, '/sports')) return 'sports'
  if (under(pathname, '/personal')) return 'personal'
  return 'clinic'
}

const SUBJECT = /^\/(?:personal|sports\/teams)\/([^/]+)(?:\/(.*))?$/

/** The member or team a path is about (the `:memberId` of
 *  `/personal/:memberId…`, the `:teamId` of `/sports/teams/:teamId…`), or
 *  null on a path that names none. Clinic paths never have one: the acting
 *  clinic is a header, not part of the address. */
export function subjectIn(pathname: string): string | null {
  const found = SUBJECT.exec(pathname)
  if (!found) return null
  try {
    return decodeURIComponent(found[1])
  } catch {
    return found[1]
  }
}

/** What follows the member or team in a path: '' on their landing page,
 *  'trends', 'athletes/<id>'. Tabs match on this, not on how the id is
 *  spelled in the address. */
function pageIn(pathname: string): string | null {
  const found = SUBJECT.exec(pathname)
  return found ? (found[2] ?? '').replace(/\/+$/, '') : null
}

function pageIs(pathname: string, page: string): boolean {
  const at = pageIn(pathname)
  return at === page || (at != null && at.startsWith(`${page}/`))
}

/** Pages opened from the workspace menu rather than from a tab. They belong
 *  to no version's tabs, so the bar lights none while one is open. */
export function isMenuPage(pathname: string): boolean {
  return under(pathname, '/settings') || under(pathname, '/integrations')
}

/** The integrations page is for MedPull staff; the server answers 403 to an
 *  org credential, so the shell does not send one there. */
export function isStaffPage(pathname: string): boolean {
  return under(pathname, '/integrations')
}

export interface VersionTab {
  key: string
  label: string
  to: string
  match: (pathname: string) => boolean
}

const enc = encodeURIComponent

/** The tabs a version shows in the bar. Personal and Sports are about one
 *  member or team (`subject`); with none in hand there is nothing for a tab
 *  to link to, and the bar shows no tabs. */
export function tabsFor(version: Version, subject: string | null): VersionTab[] {
  if (version === 'clinic') {
    return [
      {
        key: 'worklist',
        label: 'Worklist',
        to: '/',
        match: (p) => p === '/' || p.startsWith('/patients/'),
      },
      {
        key: 'calendar',
        label: 'Calendar',
        to: '/calendar',
        // the schedule and everything under it, and the demo screen built on it
        match: (p) => under(p, '/calendar') || p.startsWith('/demo/'),
      },
      { key: 'data', label: 'Data', to: '/data', match: (p) => under(p, '/data') },
    ]
  }
  if (subject == null) return []
  if (version === 'personal') {
    const base = `/personal/${enc(subject)}`
    return [
      { key: 'today', label: 'Today', to: base, match: (p) => pageIn(p) === '' },
      { key: 'trends', label: 'Trends', to: `${base}/trends`, match: (p) => pageIs(p, 'trends') },
      { key: 'data', label: 'Data', to: `${base}/data`, match: (p) => pageIs(p, 'data') },
    ]
  }
  const base = `/sports/teams/${enc(subject)}`
  return [
    {
      key: 'board',
      label: 'Board',
      to: base,
      // the board, and an athlete opened from it
      match: (p) => pageIn(p) === '' || pageIs(p, 'athletes'),
    },
    { key: 'calendar', label: 'Calendar', to: `${base}/calendar`, match: (p) => pageIs(p, 'calendar') },
    { key: 'data', label: 'Data', to: `${base}/data`, match: (p) => pageIs(p, 'data') },
  ]
}

/** The first version a credential may use, in the menu's order: where the
 *  brand goes and where a path outside the credential's versions is sent. */
export function homeFor(versions: readonly Version[]): string {
  const first = VERSIONS.find((v) => versions.includes(v))
  return first ? VERSION_HOME[first] : '/'
}
