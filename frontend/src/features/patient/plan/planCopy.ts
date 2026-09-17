import type {
  DraftTask,
  KindInfo,
  NextStep,
  ParamField,
  PlanTask,
  RecordStatus,
  TaskPhase,
  TaskSchedule,
  TaskTemplate,
} from '../../../api/plan'
import { PHASES, SCHEDULES } from '../../../api/plan'
import type { TaskStatus } from '../../../api/types'
import type { TileFamily } from '../../../components/Tile'
import {
  Bandage,
  BedDouble,
  Dumbbell,
  Footprints,
  ListChecks,
  MessageCircle,
  Pill,
  type LucideIcon,
} from 'lucide-react'

/** Copy and lookup helpers for the care-plan UI. Kept out of the component
 *  modules so fast-refresh keeps working, and so Tailwind sees every class
 *  string as a literal (it purges concatenated names). */

export const PHASE_LABEL: Record<TaskPhase, string> = Object.fromEntries(
  PHASES.map((p) => [p.key, p.label]),
) as Record<TaskPhase, string>

export const SCHEDULE_LABEL: Record<TaskSchedule, string> = Object.fromEntries(
  SCHEDULES.map((s) => [s.key, s.label]),
) as Record<TaskSchedule, string>

export function phaseLabel(phase: string | null | undefined): string {
  return PHASE_LABEL[(phase ?? 'ongoing') as TaskPhase] ?? titleCase(phase ?? 'ongoing')
}

export function scheduleLabel(schedule: string | null | undefined): string {
  return SCHEDULE_LABEL[(schedule ?? 'daily') as TaskSchedule] ?? titleCase(schedule ?? 'daily')
}

/** Their lifecycle status, as a chip. */
export const TASK_STATUS = {
  pending: { label: 'Pending', pill: 'bg-soft text-muted' },
  sent: { label: 'Sent', pill: 'bg-brand-tint text-on-brand-tint' },
  done: { label: 'Done', pill: 'bg-risk-low-tint text-risk-low-ink' },
  skipped: { label: 'Skipped', pill: 'bg-risk-missing-tint text-risk-missing-ink' },
} as const satisfies Record<TaskStatus, unknown>

/** One day of the 14-day strip. Each state is its own SHAPE, so hue is never
 *  the only carrier (R20), matching components/AdherenceDots:
 *    verified       filled brand dot
 *    self-attested  brand ring (2px)
 *    missed         hollow --line-strong square
 *    pending        flat --line dash
 *    none           invisible (keeps the 14 cells aligned)
 *  #1976D2 as a graphic is 4.602:1 on light --panel and 3.736:1 on dark
 *  --panel; --line-strong is 3.834 / 5.671. All clear 1.4.11's 3:1. The
 *  legend in TasksSection draws these same classes. */
export const RECORD_DOT: Record<RecordStatus, { cls: string; label: string }> = {
  verified: { cls: 'h-2 w-2 rounded-pill bg-brand', label: 'Verified by data' },
  self_attested: { cls: 'h-2 w-2 rounded-pill border-2 border-brand', label: 'Self-reported' },
  missed: { cls: 'h-2 w-2 rounded-[2px] border border-line-strong', label: 'Missed' },
  pending: { cls: 'h-[2px] w-2 rounded-pill bg-line', label: 'Pending' },
  none: { cls: 'h-2 w-2 opacity-0', label: 'Not scheduled' },
}

/** The leading tile for a task, by their task kind — the same mapping as the
 *  app's TaskListRow (ios/.../TasksView.swift): movement is teal, meds and
 *  wounds violet, sleep indigo, check-ins and everything else blue. */
export const TASK_KIND_TILE: Record<string, { icon: LucideIcon; family: TileFamily }> = {
  checkin: { icon: MessageCircle, family: 'blue' },
  exercise: { icon: Dumbbell, family: 'teal' },
  walk: { icon: Footprints, family: 'teal' },
  medication: { icon: Pill, family: 'violet' },
  wound_check: { icon: Bandage, family: 'violet' },
  sleep: { icon: BedDouble, family: 'indigo' },
  custom: { icon: ListChecks, family: 'blue' },
}

export function taskKindTile(kind: string | null | undefined) {
  return TASK_KIND_TILE[kind ?? 'custom'] ?? TASK_KIND_TILE.custom
}

export const USE_CASE_LABEL: Record<string, string> = {
  UC1: 'Knee replacement',
  UC2: 'Hip replacement',
  UC3: 'ACL reconstruction',
  UC4: 'Shoulder & rotator cuff',
  UC5: 'Lumbar spine',
  UC6: 'Lower-limb fracture',
  UC7: 'Every recovery',
  UC8: 'Heart failure',
  UC9: 'COPD',
  UC10: 'Diabetes',
  UC11: 'Hypertension',
  UC12: 'Chronic pain & deconditioning',
  custom: 'Custom',
}

export const PATHWAY_NAME: Record<string, string> = {
  ortho_tka: 'Knee replacement',
  ortho_tha: 'Hip replacement',
  ortho_acl: 'ACL reconstruction',
  ortho_meniscus: 'Meniscus repair',
  ortho_ankle: 'Ankle',
  ortho_shoulder: 'Shoulder',
  ortho_spine: 'Spine',
  heart_failure: 'Heart failure',
  copd: 'COPD',
  diabetes: 'Diabetes',
  hypertension: 'Hypertension',
  chronic_pain: 'Chronic pain',
  general_recovery: 'General recovery',
  ortho: 'Orthopedic',
  cardiac: 'Cardiac',
  pulmonary: 'Pulmonary',
  metabolic: 'Metabolic',
  pain: 'Pain',
  general: 'General',
}

export function ucLabel(key: string | null | undefined): string {
  if (!key) return 'Custom'
  return USE_CASE_LABEL[key] ?? titleCase(key)
}

export function pathwayName(key: string): string {
  return PATHWAY_NAME[key] ?? titleCase(key)
}

export function titleCase(key: string): string {
  const words = key.replace(/[_-]+/g, ' ').trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

export function kindInfo(kinds: KindInfo[] | undefined, kind: string | null | undefined) {
  return kinds?.find((k) => k.kind === kind)
}

export function kindLabel(kinds: KindInfo[] | undefined, kind: string | null | undefined): string {
  return kindInfo(kinds, kind)?.label ?? titleCase(kind ?? 'custom')
}

/** "verified by step data" — the chip on a plan row. Prefers the server's
 *  label on the task, then the kind catalog, then a plain fallback. */
export function verifiedByLabel(
  kinds: KindInfo[] | undefined,
  task: { verified_by?: string | null; verify_kind?: string | null },
): string {
  const fromKinds = kindInfo(kinds, task.verify_kind)?.verified_by
  const label = task.verified_by || fromKinds || 'self-report'
  return /^verified by/i.test(label) ? label : `verified by ${label}`
}

/** Is a template applicable to this pathway? Empty = every pathway; keys
 *  may name a pathway or its domain. */
export function templateFitsPathway(
  t: { pathways: string[] },
  pathway: { key: string; domain: string } | null | undefined,
): boolean {
  if (!t.pathways || t.pathways.length === 0) return true
  if (!pathway) return false
  return t.pathways.includes(pathway.key) || t.pathways.includes(pathway.domain)
}

export function defaultParams(schema: ParamField[] | undefined): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of schema ?? []) out[f.name] = f.default
  return out
}

/** A draft row from a library template — the library's copy, our defaults. */
export function draftFromTemplate(t: TaskTemplate): DraftTask {
  return {
    template_id: t.id,
    template_key: t.key,
    title: t.title,
    why: t.why,
    clinical_target: t.clinical_target ?? '',
    task_kind: t.task_kind ?? 'custom',
    verify_kind: t.verify_kind ?? 'custom',
    params: { ...(t.params ?? {}) },
    schedule: t.schedule ?? 'daily',
    phase: t.phase ?? 'ongoing',
    feeds: [...(t.feeds ?? [])],
    due_at: null,
    save_as_template: false,
    pin: false,
    source_template_key: t.key,
  }
}

/** A blank custom row. */
export function blankDraft(kinds: KindInfo[] | undefined): DraftTask {
  const custom = kindInfo(kinds, 'custom')
  return {
    template_id: null,
    template_key: null,
    title: '',
    why: '',
    clinical_target: '',
    task_kind: custom?.task_kind ?? 'custom',
    verify_kind: 'custom',
    params: defaultParams(custom?.params_schema),
    schedule: 'daily',
    phase: 'ongoing',
    feeds: [],
    due_at: null,
    save_as_template: false,
    pin: false,
  }
}

/** The AI builder's rows arrive PlanItem-like but may be missing fields —
 *  fill what the editor needs so every row renders and submits. */
export function normalizeDraft(d: Partial<DraftTask>, kinds: KindInfo[] | undefined): DraftTask {
  const base = blankDraft(kinds)
  const verify = d.verify_kind ?? base.verify_kind
  const info = kindInfo(kinds, verify)
  return {
    ...base,
    ...d,
    verify_kind: verify,
    task_kind: d.task_kind ?? info?.task_kind ?? base.task_kind,
    params: { ...defaultParams(info?.params_schema), ...(d.params ?? {}) },
    feeds: d.feeds ?? [],
    clinical_target: d.clinical_target ?? '',
    why: d.why ?? '',
    title: d.title ?? '',
    save_as_template: d.save_as_template ?? false,
    pin: d.pin ?? false,
    due_at: d.due_at ?? null,
  }
}

/** Strip the library toggles before POSTing: the server's PlanItem is the
 *  editor row minus the builder's rationale. */
export function toPlanItem(d: DraftTask) {
  const { rationale: _r, source_template_key: _s, ...item } = d
  void _r
  void _s
  return item
}

/** Templates write "Dr. {surgeon}" and the surgeon's record already carries
 *  the title — same rule as the server's `fill_template`. */
function surgeonName(surgeon: string | null | undefined): string {
  return (surgeon ?? '').replace(/^Dr\.?\s+/i, '').trim()
}

/** Fill `{first}` / `{surgeon}` client-side. */
export function resolvePlaceholders(
  body: string,
  ctx: { first: string; surgeon?: string | null },
): string {
  const surgeon = surgeonName(ctx.surgeon) || 'your surgeon'
  return body.replace(/\{first\}/gi, ctx.first).replace(/\{surgeon\}/gi, surgeon)
}

/** The inverse: a message typed for one patient becomes a reusable body. */
export function templatize(
  text: string,
  ctx: { first: string; surgeon?: string | null },
): string {
  let out = text
  const surgeon = surgeonName(ctx.surgeon)
  if (surgeon) {
    out = out.split(surgeon).join('{surgeon}')
  }
  if (ctx.first.trim()) {
    out = out.replace(new RegExp(`\\b${escapeRe(ctx.first.trim())}\\b`, 'g'), '{first}')
  }
  return out
}

function escapeRe(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

const SCALE_PROMPT = /\b0\s*(?:to|-|–)\s*10\b/gi

/** Patient-facing text stays number-free. Numbers are allowed only where
 *  the title already carries them (the task's own count — "3 short walks")
 *  and in the "0 to 10" scale prompt; a percent sign is never allowed. */
export function numberWarning(text: string, title = ''): string | null {
  if (!text) return null
  if (text.includes('%')) return 'Percentages are not shown to patients — remove the % figure.'
  const allowed = new Set((title.match(/\d+(?:\.\d+)?/g) ?? []).map((n) => n))
  const stripped = text.replace(SCALE_PROMPT, '')
  const numbers = stripped.match(/\d+(?:\.\d+)?/g) ?? []
  const stray = numbers.filter((n) => !allowed.has(n))
  if (stray.length === 0) return null
  return `Patients do not see clinical numbers — "${stray[0]}" reads as a metric. Keep counts in the title only.`
}

export function taskPhase(t: PlanTask): TaskPhase {
  return (t.phase ?? 'ongoing') as TaskPhase
}

export function taskSchedule(t: PlanTask): TaskSchedule {
  return (t.schedule ?? 'daily') as TaskSchedule
}

export function taskVerifyKind(t: PlanTask): string {
  return t.verify_kind ?? 'custom'
}

/** Rates the strip shows: verified only, and verified plus self-report. */
export function planRates(tasks: PlanTask[]) {
  let verified = 0
  let self = 0
  let missed = 0
  for (const t of tasks) {
    if (!t.active) continue
    for (const r of t.last14 ?? []) {
      if (r.status === 'verified') verified += 1
      else if (r.status === 'self_attested') self += 1
      else if (r.status === 'missed') missed += 1
    }
  }
  const total = verified + self + missed
  return {
    total,
    verifiedPct: total ? Math.round((verified / total) * 100) : null,
    inclSelfPct: total ? Math.round(((verified + self) / total) * 100) : null,
  }
}

/** Today's ISO date, local — the record endpoint takes a date, not a time. */
export function todayIso(): string {
  const d = new Date()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

/** Keyword overlap for matching an AI-suggested action to a planner step:
 *  two shared content words, or one long distinctive one. */
export function titlesOverlap(a: string, b: string): boolean {
  const ta = tokens(a)
  const tb = tokens(b)
  if (ta.size === 0 || tb.size === 0) return false
  let shared = 0
  let long = false
  for (const w of ta) {
    if (tb.has(w)) {
      shared += 1
      if (w.length >= 6) long = true
    }
  }
  return shared >= 2 || long
}

const STOP = new Set([
  'the', 'and', 'for', 'with', 'about', 'their', 'this', 'that', 'from', 'today', 'patient',
  'ask', 'send', 'check', 'review', 'call', 'open', 'log', 'mark', 'week', 'days', 'day',
])

function tokens(s: string): Set<string> {
  return new Set(
    s
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, ' ')
      .split(/[\s-]+/)
      .filter((w) => w.length >= 4 && !STOP.has(w)),
  )
}

/** The step's own title as a capsule label (R4: on the worklist the button
 *  IS the next step). The planner writes imperatives ("Call the patient
 *  today", "Nudge the device sync"); the capsule drops the filler so it
 *  reads "Call today", "Nudge device sync". A call with no dial link keeps
 *  "Log call", because that is what the button then does. */
export function shortStepLabel(step: NextStep, canText: boolean): string {
  const type = step.action.type
  if (type === 'send_checkin' && !canText) return 'Open check-in link'
  return step.title
    .replace(/\s+the patient\b/i, '')
    .replace(/^(\S+)\s+the\s+/i, '$1 ')
    .trim()
}
