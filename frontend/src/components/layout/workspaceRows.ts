import {
  rememberedSubject,
  type Version,
  type WorkspaceTeam,
  type Workspaces,
} from '../../api/workspaces'

/** What the workspace menu lists and what its trigger says, worked out from
 *  the server's workspaces and where the console is now. Pure functions, kept
 *  out of WorkspaceMenu.tsx so that file exports components only.
 *
 *  To add a row to the menu, add it here: a row in an existing group is one
 *  more entry in that group's `rows`; a new kind of workspace is a new group
 *  in `workspaceGroups` (and a line in `workspacePlace` for the trigger). The
 *  links under the divider (Demo screen, Integrations, Settings, Sign out)
 *  are in WorkspaceMenu.tsx. */

/** Where the console is: the version on screen, the member or team in the
 *  address, and the clinic it is acting for (null: all of them). */
export interface WorkspaceAt {
  version: Version
  subject: string | null
  clinic: string | null
}

export interface WorkspaceRow {
  key: string
  /** A real address, so the row can be opened in a new tab. */
  to: string
  title: string
  detail: string | null
  current: boolean
  /** Set on a staff console's clinic rows: choosing the row makes this the
   *  acting clinic (`null`: all clinics) before going to the worklist. */
  clinic?: string | null
}

export interface WorkspaceGroup {
  version: Version
  label: string
  rows: WorkspaceRow[]
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`

const enc = encodeURIComponent

/** A team as the bar names it: the server's short name ("Rice MBB"), else
 *  the program and the team ("Rice Men's Basketball"). */
function teamLabel(team: WorkspaceTeam): string {
  return team.short_name ?? [team.org_name, team.name].filter(Boolean).join(' ')
}

/** The menu's groups, in the versions' order. A version this console may not
 *  use, or one with no rows, is left out. */
export function workspaceGroups(
  workspaces: Workspaces,
  staff: boolean,
  at: WorkspaceAt,
): WorkspaceGroup[] {
  const groups: WorkspaceGroup[] = []
  const allowed = (version: Version) => workspaces.versions.includes(version)

  if (allowed('clinic')) {
    const inClinic = at.version === 'clinic'
    const rows: WorkspaceRow[] = workspaces.clinics.map((clinic) => ({
      key: `clinic:${clinic.id}`,
      // an org credential is its clinic already; only staff carry a choice
      to: staff ? `/?clinic=${enc(clinic.id)}` : '/',
      title: clinic.name,
      detail: clinic.charts == null ? null : plural(clinic.charts, 'chart', 'charts'),
      current: inClinic && (staff ? at.clinic === clinic.id : true),
      ...(staff ? { clinic: clinic.id } : {}),
    }))
    if (staff) {
      rows.unshift({
        key: 'clinic:all',
        to: '/?clinic=all',
        title: 'All clinics',
        detail:
          workspaces.charts == null
            ? 'Every clinic’s charts on one worklist'
            : plural(workspaces.charts, 'chart', 'charts'),
        current: inClinic && at.clinic == null,
        clinic: null,
      })
    }
    if (rows.length > 0) groups.push({ version: 'clinic', label: 'Clinic', rows })
  }

  if (allowed('personal') && workspaces.members.length > 0) {
    groups.push({
      version: 'personal',
      label: 'Personal',
      rows: workspaces.members.map((member) => ({
        key: `member:${member.id}`,
        to: `/personal/${enc(member.id)}`,
        title: member.name,
        detail: member.goal,
        current: at.version === 'personal' && at.subject === member.id,
      })),
    })
  }

  if (allowed('sports') && workspaces.teams.length > 0) {
    groups.push({
      version: 'sports',
      label: 'Sports teams',
      rows: workspaces.teams.map((team) => ({
        key: `team:${team.id}`,
        to: `/sports/teams/${enc(team.id)}`,
        title: team.name,
        detail:
          [team.org_name, team.roster == null ? null : plural(team.roster, 'athlete', 'athletes')]
            .filter(Boolean)
            .join(' · ') || null,
        current: at.version === 'sports' && at.subject === team.id,
      })),
    })
  }

  return groups
}

/** What the trigger says after the version's name: the clinic, the member or
 *  the team on screen. Null when the address names none the menu knows. */
export function workspacePlace(
  workspaces: Workspaces,
  staff: boolean,
  at: WorkspaceAt,
): string | null {
  if (at.version === 'clinic') {
    const clinic = staff
      ? workspaces.clinics.find((c) => c.id === at.clinic)
      : workspaces.clinics[0]
    if (clinic) return clinic.short_name ?? clinic.name
    return staff ? 'All clinics' : null
  }
  if (at.version === 'personal') {
    return workspaces.members.find((m) => m.id === at.subject)?.name ?? null
  }
  const team = workspaces.teams.find((t) => t.id === at.subject)
  return team ? teamLabel(team) : null
}

/** Who a bare `/personal` or `/sports` opens: the member or team that was
 *  open last on this browser if the menu still lists them, else the first
 *  row, else no one. */
export function landingSubject(
  workspaces: Workspaces,
  version: Exclude<Version, 'clinic'>,
): string | null {
  const rows = version === 'personal' ? workspaces.members : workspaces.teams
  const last = rememberedSubject(version)
  return rows.find((row) => row.id === last)?.id ?? rows[0]?.id ?? null
}
