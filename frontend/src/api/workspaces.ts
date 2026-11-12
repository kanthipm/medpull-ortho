import { useQuery, useQueryClient, type QueryClient, type QueryKey } from '@tanstack/react-query'
import { useSyncExternalStore } from 'react'
import { ApiError, fetchJson, getActingClinic, subscribeActingClinic } from './client'
import { CONSOLE_SESSION_KEY } from './queries'
import type { TeamsResponse } from './sports'
import type { ConsoleScopeKind, ConsoleSession } from './types'

/** What the workspace menu lists and what the shell gates on: which of the
 *  three versions this console may use, and the clinics, members and teams
 *  inside them (`GET /api/console/workspaces`).
 *
 *  A hospital credential gets its one clinic, a sports credential its teams,
 *  staff everything. A version with no rows may still be allowed: its landing
 *  page then says it has nothing to show on this deployment. */

export type Version = 'clinic' | 'personal' | 'sports'

export const VERSIONS: readonly Version[] = ['clinic', 'personal', 'sports']

export interface WorkspaceClinic {
  /** The hospital id, sent as `X-MedPull-Clinic` when chosen. */
  id: string
  name: string
  /** What the bar says after "Clinic ·"; the full name when there is none. */
  short_name: string | null
  /** Clinic charts on its roster. */
  charts: number | null
}

export interface WorkspaceMember {
  id: string
  name: string
  /** What they are working toward, in their words. */
  goal: string | null
}

export interface WorkspaceTeam {
  id: string
  name: string
  /** What the bar says after "Sports ·" ("Rice MBB"). */
  short_name: string | null
  /** The program the team belongs to ("Rice"). */
  org_name: string | null
  /** Athletes linked to the team. */
  roster: number | null
}

export interface Workspaces {
  /** `api`: the server's own list. `derived`: an older API without the
   *  route, pieced together from the session and the teams index. */
  source: 'api' | 'derived'
  versions: Version[]
  clinics: WorkspaceClinic[]
  /** Clinic charts across every hospital, for the "All clinics" row. */
  charts: number | null
  members: WorkspaceMember[]
  teams: WorkspaceTeam[]
}

export const WORKSPACES_KEY: QueryKey = ['console-workspaces']

/** The queries that describe the console itself, not a roster: they survive
 *  a change of acting clinic. */
const SHELL_KEYS: unknown[] = [WORKSPACES_KEY[0], CONSOLE_SESSION_KEY[0], 'health']

/** What a credential may open when the server does not say: staff every
 *  version, a hospital the clinic, a sports org or team the boards. The
 *  server enforces the same lines on its own routes. */
function versionsForScope(kind: ConsoleScopeKind): Version[] {
  if (kind === 'hospital') return ['clinic']
  if (kind === 'sports_org' || kind === 'team') return ['sports']
  return [...VERSIONS]
}

// --- reading the server's answer ----------------------------------------------------
//
// Read field by field rather than cast: the route is new, and a row the menu
// cannot name or link to is left out instead of rendering as a blank line.

type Loose = Record<string, unknown>

const isRecord = (v: unknown): v is Loose => typeof v === 'object' && v !== null
const text = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v.trim() : null)
const count = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

function rows<T>(v: unknown, read: (row: Loose, id: string, name: string) => T): T[] {
  if (!Array.isArray(v)) return []
  const out: T[] = []
  for (const row of v) {
    if (!isRecord(row)) continue
    const id = text(row.id)
    const name = text(row.name)
    if (id && name) out.push(read(row, id, name))
  }
  return out
}

/** A team's program is sent as `org_name`, or as an `org` that is the name
 *  or the org row itself. */
function orgName(row: Loose): string | null {
  if (text(row.org_name)) return text(row.org_name)
  if (isRecord(row.org)) return text(row.org.short_name) ?? text(row.org.name)
  return text(row.org)
}

function fromApi(raw: unknown, scope: ConsoleSession['scope']): Workspaces {
  const body = isRecord(raw) ? raw : {}
  const named = (Array.isArray(body.versions) ? body.versions : [])
    .map((v) => (isRecord(v) ? v.key : v))
    .filter((v): v is Version => VERSIONS.includes(v as Version))
  return {
    source: 'api',
    versions: named.length > 0 ? VERSIONS.filter((v) => named.includes(v)) : versionsForScope(scope.kind),
    clinics: rows(body.clinics, (row, id, name) => ({
      id,
      name,
      short_name: text(row.short_name),
      charts: count(row.patients) ?? count(row.charts),
    })),
    charts: count(body.charts),
    members: rows(body.members, (row, id, name) => ({ id, name, goal: text(row.goal) })),
    teams: rows(body.teams, (row, id, name) => ({
      id,
      name,
      short_name: text(row.short_name),
      org_name: orgName(row),
      roster: count(row.roster),
    })),
  }
}

// --- an API that predates the route -------------------------------------------------

/** The same answer from what an older API can say. The session gives the
 *  scope, and so the versions; a hospital credential's one clinic is the
 *  scope itself; the teams index gives every team with a roster. That API
 *  has no acting clinic and no members, so staff get "All clinics" alone and
 *  Personal has no rows. */
async function fromOlderApi(scope: ConsoleSession['scope']): Promise<Workspaces> {
  const versions = versionsForScope(scope.kind)
  let teams: WorkspaceTeam[] = []
  if (versions.includes('sports')) {
    try {
      const index = await fetchJson<TeamsResponse>('/api/sports/teams')
      teams = index.orgs.flatMap((org) =>
        org.teams
          .filter((team) => (team.roster ?? 0) > 0)
          .map((team) => ({
            id: team.id,
            name: team.name,
            short_name: null,
            org_name: org.short_name || org.name,
            roster: team.roster ?? null,
          })),
      )
    } catch (err) {
      // No sports routes at all on this API: the version simply has no rows.
      if (!(err instanceof ApiError) || err.status !== 404) throw err
    }
  }
  return {
    source: 'derived',
    versions,
    clinics:
      scope.kind === 'hospital' && scope.org_id
        ? [{ id: scope.org_id, name: scope.name, short_name: null, charts: null }]
        : [],
    charts: null,
    members: [],
    teams,
  }
}

const ROUTE_MISSING = Symbol('workspaces route missing')

async function fetchWorkspaces(qc: QueryClient): Promise<Workspaces> {
  // The session is the shell's own query too; this shares its one request.
  const session = qc.ensureQueryData({
    queryKey: CONSOLE_SESSION_KEY,
    queryFn: () => fetchJson<ConsoleSession>('/api/console/session'),
    staleTime: Infinity,
  })
  const [{ scope }, raw] = await Promise.all([
    session,
    fetchJson<unknown>('/api/console/workspaces').catch((err: unknown) => {
      if (err instanceof ApiError && err.status === 404) return ROUTE_MISSING
      throw err
    }),
  ])
  return raw === ROUTE_MISSING ? fromOlderApi(scope) : fromApi(raw, scope)
}

/** The workspaces this console may use. Fetched once per page load, like the
 *  session: signing in or out reloads the page, and nothing here depends on
 *  the acting clinic. */
export function useWorkspaces() {
  const qc = useQueryClient()
  return useQuery({
    queryKey: WORKSPACES_KEY,
    queryFn: () => fetchWorkspaces(qc),
    staleTime: Infinity,
  })
}

// --- the acting clinic ----------------------------------------------------------------

/** The clinic this console acts for, or null for "All clinics"; re-renders
 *  when it changes here or in another tab. */
export function useActingClinic(): string | null {
  return useSyncExternalStore(subscribeActingClinic, getActingClinic, () => null)
}

/** Drop everything cached for the old acting clinic. Every roster, chart list
 *  and schedule in the cache was read under the old header; what is on screen
 *  refetches under the new one. The shell's own queries are kept, so the bar
 *  does not blink. */
export function resetForClinicChange(qc: QueryClient) {
  void qc.resetQueries({ predicate: (query) => !SHELL_KEYS.includes(query.queryKey[0]) })
}

// --- the last member and team ---------------------------------------------------------
//
// `/personal` and `/sports` name no one; they forward to whoever was open
// last on this browser, else to the first row.

const SUBJECT_KEY: Record<Exclude<Version, 'clinic'>, string> = {
  personal: 'medpull-console.member',
  sports: 'medpull-console.team',
}

export function rememberedSubject(version: Exclude<Version, 'clinic'>): string | null {
  try {
    return window.localStorage.getItem(SUBJECT_KEY[version]) || null
  } catch {
    return null
  }
}

export function rememberSubject(version: Exclude<Version, 'clinic'>, id: string) {
  try {
    window.localStorage.setItem(SUBJECT_KEY[version], id)
  } catch {
    // storage blocked: the version opens on its first row next time
  }
}

/** Sign-out and a change of credential: the next holder starts clean. */
export function forgetWorkspaceChoices() {
  try {
    window.localStorage.removeItem(SUBJECT_KEY.personal)
    window.localStorage.removeItem(SUBJECT_KEY.sports)
  } catch {
    // nothing stored to clear
  }
}
