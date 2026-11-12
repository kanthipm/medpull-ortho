/* Wire types for /api/mobile, one for one with Core/Models.swift. Keys are
   snake_case on the wire; the client converts (api.ts), so these read like
   the Swift structs. Timestamps stay strings and are parsed on demand
   (Dates.parse) because the backend writes naive ISO-8601 with microseconds. */

export type Hospital = {
  id: string
  name: string
  system: string | null
  city: string
  state: string
}

export type Candidate = {
  patientId: string
  displayName: string
  procedureDisplay: string
  surgeryMonth: string
  confidence: string
  phoneMatch: boolean
  hasPhoneOnFile: boolean
}

export type EnrollResponse = {
  status: string
  verificationId?: number | null
  phoneMasked?: string | null
  expiresAt?: string | null
  verified?: boolean | null
  sessionToken?: string | null
  me?: Me | null
  /** Text-first (`verification_required` only). `codeSent` false means the
   *  server could not text this number yet — on Sendblue's free plan a number
   *  has to text the line once — and `textTo` / `textBody` are the one tap
   *  that fixes it. Absent from an older server: the code was sent. */
  codeSent?: boolean | null
  textFirst?: boolean | null
  textTo?: string | null
  textBody?: string | null
}

/** `GET /api/mobile/enroll/verification/{id}`: what the app polls while the
 *  person texts MedPull for the first time. */
export type VerificationStatus = {
  verificationId: number
  /** waiting_for_text | code_sent | expired | verified */
  status: string
  codeSent?: boolean | null
  textFirst?: boolean | null
  textTo?: string | null
  textBody?: string | null
  phoneMasked?: string | null
}

/** The code is on its way (or already used): the step can show the field. */
export const codeIsOut = (s: VerificationStatus) => s.status === 'code_sent' || s.status === 'verified'

export type CareTeamMember = { name: string; role: string }

export type PatientProfile = {
  id: string
  name: string
  firstName: string
  initials: string
  /** "recovery" (had surgery, followed along a curve), "general" (joined
   *  the hospital's programme; no operation) or "personal". */
  mode: string
  accountKind?: string | null
  procedureDisplay: string
  surgeryDate: string | null
  joinedDate: string
  postopDay: number | null
  daysEnrolled: number
  carePathway: string | null
  phoneMasked: string | null
  email?: string | null
  hospital: Hospital | null
  careTeam: CareTeamMember[]
}

export const isRecovery = (p: PatientProfile) => p.mode === 'recovery'
export const isPersonalProfile = (p: PatientProfile) =>
  p.mode === 'personal' || p.accountKind === 'personal'

export type Trajectory = { state: string; pct: number | null }

export type Recovery = {
  level: string
  label: string
  blurb: string
  trajectory: Trajectory
  daysWithData: number | null
  daysUntilFullPicture: number | null
  computedAt: string | null
}

export type AppleHealthStatus = { connected: boolean; lastSyncAt: string | null }

export type WearableDevice = {
  provider: string
  model: string
  status: string
  lastSyncAt: string | null
}

export type WearableSummary = {
  aggregatorConfigured: boolean
  connectionStatus: string | null
  appleHealth: AppleHealthStatus
  devices: WearableDevice[]
  lastDataAt: string | null
}

export type Features = {
  sms: boolean
  appleHealth: boolean
  deepLinkScheme: string
  beta?: boolean | null
  consentVersion?: string | null
}

export const isBeta = (f: Features) => f.beta ?? true

export type ConsentStatus = {
  version: string | null
  acceptedAt: string | null
  scopes: Record<string, boolean> | null
  currentVersion: string
  needsConsent: boolean
}

export type SpaceProfile = {
  patientId: string
  kind: string
  label: string
  detail: string
  current: boolean
}

export type Me = {
  patient: PatientProfile
  recovery: Recovery
  tasksOpen: number
  unreadMessages: number
  wearables: WearableSummary
  features: Features
  profiles?: SpaceProfile[] | null
  subscription?: unknown
  consent?: ConsentStatus | null
}

export const needsConsent = (me: Me | null | undefined) => me?.consent?.needsConsent ?? false

export type Procedure = { id: string; label: string }

// MARK: - Portfolio

export type PortfolioPoint = {
  /** The server's calendar day, "yyyy-MM-dd". */
  date: string
  value: number
}

/** `date` parsed to local midnight of that day, so charts plot on a real
 *  time axis. A string the parser does not know falls back to the distant
 *  past rather than failing. */
export function pointDay(p: PortfolioPoint): Date {
  return Dates.parse(p.date) ?? new Date(0)
}

export type PortfolioMetric = {
  key: string
  label: string
  /** The unit exactly as the server sent it ("h" for sleep). */
  unit: string
  latest: PortfolioPoint
  series: PortfolioPoint[]
  daysWithData: number
}

/** Metrics sent in hours and shown as a duration. */
const durationKeys = new Set(['sleep_duration'])
/** Metrics that are whole counts: grouped ("4,820"), never a decimal. */
const countKeys = new Set([
  'steps', 'active_energy', 'exercise_session', 'bp_systolic', 'bp_diastolic', 'blood_glucose',
])

const grouped = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 })
const oneDecimal = new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 })

/** True when the figure spells its own units, so no unit label follows it. */
export const hideUnit = (m: PortfolioMetric) => durationKeys.has(m.key)

/** The unit to print after a figure: empty for a duration (sleep), whose
 *  figure already carries its units. */
export const unitOf = (m: PortfolioMetric) => (durationKeys.has(m.key) ? '' : m.unit)

/** Any value of this metric in its display form: steps read "4,820";
 *  sleep reads "6 hr, 24 min". */
export function metricText(m: PortfolioMetric, value: number): string {
  if (durationKeys.has(m.key)) return duration(value, 'abbreviated')
  if (countKeys.has(m.key)) return grouped.format(Math.round(value))
  return value === Math.round(value) ? grouped.format(value) : oneDecimal.format(value)
}

export const latestText = (m: PortfolioMetric) => metricText(m, m.latest.value)

/** The same value for a screen reader, with units spelled out. */
export function spokenText(m: PortfolioMetric, value: number): string {
  if (durationKeys.has(m.key)) return duration(value, 'wide')
  return `${metricText(m, value)} ${unitOf(m)}`.trim()
}

/** A short axis label: "6 hr" for sleep, the grouped number otherwise. */
export function axisText(m: PortfolioMetric, value: number): string {
  if (durationKeys.has(m.key)) return `${Math.round(value)} hr`
  return value === Math.round(value) ? grouped.format(value) : oneDecimal.format(value)
}

/** Hours to "6 hr, 24 min", rounded to the minute first (6.999 h reads
 *  "7 hr", not "6 hr, 60 min"). */
function duration(hours: number, width: 'abbreviated' | 'wide'): string {
  const minutes = Math.round(hours * 60)
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const parts: string[] = []
  if (width === 'wide') {
    if (h > 0) parts.push(`${h} ${h === 1 ? 'hour' : 'hours'}`)
    if (m > 0 || h === 0) parts.push(`${m} ${m === 1 ? 'minute' : 'minutes'}`)
  } else {
    if (h > 0) parts.push(`${h} hr`)
    if (m > 0 || h === 0) parts.push(`${m} min`)
  }
  return parts.join(', ')
}

/** Daily totals chart as bars from zero; sampled measurements as a line on
 *  a domain that does not include zero. */
export const isDailyTotal = (m: PortfolioMetric) =>
  ['steps', 'active_energy', 'exercise_session'].includes(m.key)

/** The series' mean, for the chart's dashed average rule. */
export function metricAverage(m: PortfolioMetric): number | null {
  if (m.series.length === 0) return null
  return m.series.reduce((a, p) => a + p.value, 0) / m.series.length
}

export type PortfolioResponse = { days: number; since: string; metrics: PortfolioMetric[] }

// MARK: - The patient's own metrics (GET /api/mobile/metrics)

export type MetricReadiness = {
  ready: boolean
  stage: string
  have: number
  need: number
  firm: number
  left: number
  firmLeft: number
  unit: string
  note: string | null
}

function unitWord(r: MetricReadiness, n: number): string {
  if (n === 1 && r.unit.endsWith('s')) return r.unit.slice(0, -1)
  return r.unit
}

/** "Needs 5 days of steps; you have 3." for the info sheet. */
export function readinessSentence(r: MetricReadiness | null | undefined): string | null {
  if (!r) return null
  const what = r.note ? ` of ${r.note}` : ''
  if (r.ready) {
    if (r.stage === 'provisional' && r.firmLeft > 0) {
      return `Showing from ${r.have} ${unitWord(r, r.have)}${what}; settles after ${r.firm}.`
    }
    return null
  }
  return `Needs ${r.need} ${unitWord(r, r.need)}${what}; you have ${r.have}.`
}

export type MetricExplain = { title: string; what: string; why: string; help: string }
export type MetricChartPoint = { x: number; y: number }
export type PatientMetricChart = { kind: string; points: MetricChartPoint[]; xLabel: string | null }

export type PatientMetric = {
  id: string
  key: string | null
  title: string
  state: string
  stateLabel: string
  headline: string
  value: string | null
  unit: string | null
  readiness: MetricReadiness | null
  daysLeftText: string | null
  explain: MetricExplain | null
  chart: PatientMetricChart | null
}

export const isWaiting = (m: PatientMetric) => m.state === 'waiting'

export type PatientSignal = {
  key: string
  title: string
  state: string
  stateLabel: string
  headline: string
  latest: PortfolioPoint | null
  unit: string | null
  readiness: MetricReadiness | null
  daysLeftText: string | null
  explain: MetricExplain | null
  series: PortfolioPoint[] | null
}

export type PatientMetricOverall = {
  blurb: string | null
  daysUntilFullPicture: number | null
  showing: number
  waiting: number
}

export type PatientMetricTrajectory = {
  state: string | null
  pct: number | null
  readiness: MetricReadiness | null
  daysLeftText: string | null
  explain: MetricExplain | null
}

export type PatientMetricsResponse = {
  postopDay: number | null
  mode: string
  overall: PatientMetricOverall
  trajectory: PatientMetricTrajectory | null
  metrics: PatientMetric[]
  signals: PatientSignal[]
}

export function signalFor(r: PatientMetricsResponse | null, key: string): PatientSignal | null {
  return r?.signals.find((s) => s.key === key) ?? null
}

// MARK: - Tones

export type Tone = 'low' | 'med' | 'high' | 'missing' | 'brand'

export function toneForLevel(level: string): Tone {
  switch (level) {
    case 'low': return 'low'
    case 'medium': return 'med'
    case 'high': return 'high'
    default: return 'missing'
  }
}

/** The tone a patient-facing state takes. `reviewing` is sage, not clay:
 *  "your care team is taking a look" is reassurance, never an alarm. */
export function toneForMetricState(state: string): Tone {
  switch (state) {
    case 'good': return 'low'
    case 'watch': return 'med'
    case 'reviewing': return 'brand'
    default: return 'missing'
  }
}

// MARK: - Tasks

export type Question = {
  id: string
  prompt: string
  kind: string
  options: string[] | null
  min: number | null
  max: number | null
}

export type RecoveryTask = {
  id: number
  kind: string
  kindLabel: string
  title: string
  why: string
  status: string
  createdAt: string | null
  dueAt: string | null
  sentAt: string | null
  completedAt: string | null
  completedVia: string | null
  questions: Question[]
  inSmsConversation: boolean
  recurring?: boolean | null
  schedule?: string | null
  lastDoneOn?: string | null
}

export const isOpenTask = (t: RecoveryTask) => t.status === 'pending' || t.status === 'sent'

/** "Daily", "Twice a day"… shown beside the kind. Null for a one-off. */
export function scheduleLabel(t: RecoveryTask): string | null {
  if (t.recurring !== true) return null
  switch (t.schedule) {
    case 'daily': return 'Daily'
    case 'am_pm': return 'Twice a day'
    case 'weekly': return 'Weekly'
    case 'ongoing': return 'Ongoing'
    default: return null
  }
}

export type TasksResponse = { open: RecoveryTask[]; recent: RecoveryTask[] }
export type CompleteResponse = { ok: boolean; task: RecoveryTask }

/** Answers are mixed: numbers for scale/number questions, strings otherwise. */
export type AnswerValue = number | string
export type Answers = Record<string, AnswerValue>

// MARK: - The exercise schedule (docs/dev/hep-schedule.md)

/** The therapist's demonstration of an exercise: the clinic's own clip when
 *  it has one, else the library's. `url` is playable as sent (presigned on
 *  AWS; an API path under this session on a laptop). */
export type ExerciseVideo = {
  id: number
  kind: string
  /** "clinic" or "library". */
  source: string
  url: string | null
  posterUrl: string | null
  contentType: string
  durationMs: number | null
  uploadedBy: string | null
  uploadedByName: string | null
  createdAt: string | null
}

/** What the patient sent back: the attachment view with its link. */
export type ExerciseClip = ChatAttachment & { url?: string | null }

/** What the therapist asks for with an exercise — a clip of the attempt,
 *  the watch on: `off`, `optional` or `required`. */
export type Requirement = 'off' | 'optional' | 'required'

/** The server's default is "optional", and so is a row from a server
 *  that does not send the setting yet. */
export function requirementOf(raw: string | null | undefined): Requirement {
  return raw === 'off' || raw === 'required' ? raw : 'optional'
}

/** The session around a completion (second pass): when it ran and for how
 *  long, the pain before, whether the watch was on and what it saw. Null
 *  until the patient starts the exercise. */
export type ExerciseSession = {
  startedAt: string | null
  endedAt: string | null
  durationS: number | null
  painBefore: number | null
  wearableWorn: boolean | null
  hrAvg: number | null
  hrMax: number | null
}

/** The therapist's look at a completion: when, who, what she said. */
export type ExerciseReview = {
  at: string | null
  by: string | null
  byName: string | null
  note: string | null
}

export type ExerciseCompletion = {
  completedAt: string
  painAfter: number | null
  note: string | null
  /** "app" (the patient) or "console" (the therapist logged it). */
  source: string
  video: ExerciseClip | null
  /** How hard it was, 0–10 (`effortWord`). Second pass; absent before. */
  effort?: number | null
  setsDone?: number | null
  repsDone?: number | null
  loadDoneKg?: number | null
  /** Null until the therapist has looked at it. */
  review?: ExerciseReview | null
  /** What was done went past the therapist's ceiling (docs/dev/pt.md). */
  pastCeiling?: boolean | null
}

/** One exercise on one of this patient's days. */
export type ExerciseAssignment = {
  id: number
  patientId: string
  exerciseId: number
  exerciseKey: string
  title: string
  bodyRegion: string
  bodyRegionLabel: string
  category: string
  categoryLabel: string
  steps: string[]
  equipment: string
  precautions: string
  /** "yyyy-MM-dd". */
  scheduledFor: string
  sortOrder: number
  sets: number | null
  reps: number | null
  holdSeconds: number | null
  side: string
  sideLabel: string
  /** "3 sets × 10 reps · 12 kg · Left", built by the server. */
  dose: string
  /** The therapist's note to the patient, in her words. */
  clinicianInstructions: string
  assignedBy: string
  assignedByName: string
  /** assigned | done | skipped */
  status: string
  video: ExerciseVideo | null
  completion: ExerciseCompletion | null
  skipReason: string | null
  createdAt: string | null
  updatedAt: string | null
  // The second pass (docs/dev/hep-schedule.md, "Second pass"): the lifter's
  // dose, what the therapist asks for, and the session once it has begun.
  // Optional so a first-pass server still reads.
  loadKg?: number | null
  /** The effort she is aiming for, 0–10. */
  rpeTarget?: number | null
  videoRequirement?: string | null
  wearableRequirement?: string | null
  session?: ExerciseSession | null
  // Between visits (docs/dev/pt.md): the dose's ceiling. Optional so a
  // server without the module still reads.
  /** The most load she allows, in kilograms like `loadKg`. */
  loadMaxKg?: number | null
  /** The effort to stop at, 0–10. */
  rpeMax?: number | null
  /** The ceiling as a sentence in the clinic's unit — "Stop at RPE 8 · do
   *  not exceed 30 lb" — or "" when the therapist wrote none. */
  ceiling?: string | null
}

export const isOpenAssignment = (a: ExerciseAssignment) => a.status === 'assigned'
export const isDoneAssignment = (a: ExerciseAssignment) => a.status === 'done'

/** The therapist's ceiling on a dose, in her words; null when she wrote none. */
export function ceilingOf(a: ExerciseAssignment): string | null {
  return (a.ceiling ?? '').trim() || null
}

export const videoRequirement = (a: ExerciseAssignment): Requirement => requirementOf(a.videoRequirement)
export const wearableRequirement = (a: ExerciseAssignment): Requirement => requirementOf(a.wearableRequirement)

/** Done, with a clip the therapist has not looked at yet. */
export function awaitingReview(a: ExerciseAssignment): boolean {
  const c = a.completion
  return isDoneAssignment(a) && !!c?.video && !c.video.withdrawn && !c.review
}

/** Whether a set is one timed hold (Wall Sits, 3 × 30 s) rather than a
 *  count of reps: the session then times the hold and skips the rest
 *  between sets. Reps with a hold on each ("10 reps, hold 5 s") count reps. */
export function holdIsUnit(a: ExerciseAssignment): boolean {
  return (a.holdSeconds ?? 0) > 0 && !((a.reps ?? 0) > 0)
}

/** The session's length in seconds: the server's figure, else the clock. */
export function sessionSeconds(a: ExerciseAssignment): number | null {
  const s = a.session
  if (!s) return null
  if (s.durationS != null) return s.durationS
  const from = Dates.parse(s.startedAt)
  const to = Dates.parse(s.endedAt)
  if (!from || !to) return null
  return Math.max(0, Math.round((to.getTime() - from.getTime()) / 1000))
}

/** One day of the week strip around the requested date. */
export type ExerciseDay = { date: string; assigned: number; done: number; skipped?: number }

/** One day of the program: its exercises and the counts the dots draw.
 *  `assigned` is every row on the day; `missed` the ones still to do once
 *  the day has passed. */
export type ProgramDay = {
  date: string
  items: ExerciseAssignment[]
  assigned: number
  done: number
  skipped: number
  missed: number
}

/** `GET /mobile/exercises/program`: the fourteen days around today. */
/** The clinic a calendar belongs to and the unit it reads loads in. Loads
 *  travel in kilograms whatever this says; the app converts for the eye. */
export type LoadUnit = 'kg' | 'lb'
export type ExerciseClinic = { id: string; name: string; loadUnit?: LoadUnit | null }

/** A visit at the clinic (docs/dev/pt.md). `at` is "HH:mm" on the clinic's
 *  clock, or null for a day with no time; `kind` is `visit`, `evaluation`
 *  or `test_day`, worded by the server in `kindLabel`. */
export type ClinicVisit = {
  /** "yyyy-MM-dd". */
  on: string
  at: string | null
  kind: string
  kindLabel: string
}

/** A rest day the clinic set on purpose, with its note or "". */
export type RestDay = { day: string; note: string }

export type ProgramResponse = {
  start: string
  days: ProgramDay[]
  clinic: ExerciseClinic | null
  /** The window's clinic visits and rest days; absent from a server
   *  without the between-visits module. */
  visits?: ClinicVisit[] | null
  restDays?: RestDay[] | null
}

/** Whether there is a program to show: any exercise on any of the days, or
 *  a visit or a rest day marked on one. */
export function hasProgram(p: ProgramResponse | null | undefined): p is ProgramResponse {
  if (!p) return false
  return p.days.some((d) => d.items.length > 0 || d.assigned > 0)
    || (p.visits?.length ?? 0) > 0 || (p.restDays?.length ?? 0) > 0
}

/** "Visit 9:30 AM", "Test day 9:30 AM": a visit as a day's marker. */
export function visitLabel(v: ClinicVisit): string {
  const time = Dates.clockTime(v.at)
  const label = v.kindLabel || 'Visit'
  return time ? `${label} ${time}` : label
}

/** "Test day · Sat, Nov 14 · 9:30 AM", after the words "Next visit". A
 *  plain visit does not say "visit" twice; today and tomorrow are named. */
export function nextVisitDetail(v: ClinicVisit): string {
  const n = Dates.daysAgo(v.on)
  const day = n === 0 ? 'Today' : n === -1 ? 'Tomorrow' : `${Dates.shortDay(v.on)}, ${Dates.monthDay(v.on)}`
  return [v.kind === 'visit' ? null : v.kindLabel, day, Dates.clockTime(v.at)].filter((p): p is string => !!p).join(DOT)
}

/** What the patient sends with "Start": the pain right now and whether the
 *  watch is on. Either can be left unanswered. */
export type ExerciseStartBody = {
  painBefore: number | null
  wearableWorn: boolean | null
}

export type ExercisesResponse = {
  date: string
  items: ExerciseAssignment[]
  /** Earlier days this week whose exercises are still to do. */
  overdue?: ExerciseAssignment[]
  week: ExerciseDay[]
  clinic: ExerciseClinic | null
  /** Today is a rest day the clinic set on purpose (docs/dev/pt.md). */
  restDay?: { note: string } | null
  /** The next visit at the clinic, from today on. */
  nextVisit?: ClinicVisit | null
}

/** Whether Today shows the schedule at all: a patient with no schedule
 *  never sees an empty card, and neither does one whose server has no
 *  schedule yet. A rest day inside a scheduled week does show, so the
 *  person knows nothing is missing; so does a day the clinic marked as
 *  rest, or a visit ahead, with no exercise around it. */
export function hasExerciseSchedule(feed: ExercisesResponse | null): feed is ExercisesResponse {
  if (!feed) return false
  return feed.items.length > 0 || (feed.overdue?.length ?? 0) > 0 || feed.week.some((d) => d.assigned > 0)
    || !!feed.restDay || !!feed.nextVisit
}

// MARK: - Between visits (docs/dev/pt.md, "What the phone gets")

/** Where the person is in the clinic's protocol: "Phase 2 of 4". */
export type ProgramPhase = { name: string; goal: string; number: number; count: number }

/** One of the person's own goals, rated 0–10: the first rating and the
 *  latest, null until it has been rated. */
export type FunctionGoal = {
  id: number
  text: string
  first: number | null
  latest: number | null
  ratings?: { on: string; score: number; source: string }[]
}

/** Sharing training limits with a trainer: asked (`awaiting`) or agreed
 *  (`active`). */
export type TrainerHandoff = { trainerName: string; status: string }

/** `GET /mobile/pt`: the person's own read of their program. A record with
 *  no program answers the same shape, empty. */
export type ProgramSummary = {
  nextVisit?: ClinicVisit | null
  restDay?: { note: string } | null
  phase?: ProgramPhase | null
  goals?: FunctionGoal[] | null
  handoff?: TrainerHandoff | null
}

/** The one line about the trainer, or null for a state with nothing to say. */
export function handoffLine(h: TrainerHandoff | null | undefined): string | null {
  if (!h) return null
  const trainer = h.trainerName?.trim() || 'your trainer'
  if (h.status === 'active') return `Your training limits are shared with ${trainer}.`
  if (h.status === 'awaiting') return `Your therapist asked to share your training limits with ${trainer}. Answer it in your tasks.`
  return null
}

/** Whether there is anything of the program to show: a phase, a goal, or
 *  a line about the trainer. */
export function hasProgramSummary(p: ProgramSummary | null | undefined): p is ProgramSummary {
  return !!p && (!!p.phase || (p.goals?.length ?? 0) > 0 || handoffLine(p.handoff) != null)
}

/** "6", or "4 → 6" when the first rating was different; null before any. */
export function goalRating(g: FunctionGoal): string | null {
  if (g.latest == null) return null
  return g.first != null && g.first !== g.latest ? `${g.first} → ${g.latest}` : String(g.latest)
}

/** What the patient sends with "Mark done" or a session's "Finish": the
 *  clip is the staged upload (ticket + storage POST), confirmed by the
 *  server with the completion. The rest is the second pass: how hard it
 *  was, what was done, and the session's clock — the phone's own. */
export type ExerciseCompletionBody = {
  painAfter: number | null
  note: string
  video: StagedUpload | null
  /** 0–10, in the words of `effortWord`. */
  effort?: number | null
  setsDone?: number | null
  repsDone?: number | null
  loadDoneKg?: number | null
  wearableWorn?: boolean | null
  /** ISO 8601 with the local offset (`Dates.iso`). Null when the exercise
   *  was marked done without a session. */
  startedAt?: string | null
  endedAt?: string | null
}

/** How hard it was, in the words a lifter would use, from nothing to all
 *  out. The therapist's `rpeTarget` is on the same ladder. */
const effortWords = [
  'Nothing', 'Very easy', 'Easy', 'Light', 'Some effort', 'Hard', 'Harder', 'Very hard', 'Really hard',
  'Almost all out', 'All out',
]
export function effortWord(n: number): string {
  return effortWords[Math.max(0, Math.min(10, Math.round(n)))]
}

/** "effort 7/10", beside the pain on a row or a sent line. */
export const effortLabel = (n: number | null | undefined) => (n == null ? null : `effort ${n}/10`)

/** Pounds in a kilogram: the factor the server words its own lines with. */
export const LB_PER_KG = 2.20462

const trimmed = (n: number, places: number) => String(Number(n.toFixed(places)))

/** A stored load as the clinic reads it: "12 kg", or "25 lb" where the
 *  clinic works in pounds (to a tenth, as the server prints them). */
export const loadLabel = (kg: number | null | undefined, unit: LoadUnit = 'kg') =>
  kg == null ? null : unit === 'lb' ? `${trimmed(kg * LB_PER_KG, 1)} lb` : `${trimmed(kg, 1)} kg`

/** A stored load as a field shows it, in the clinic's unit. */
export const loadField = (kg: number | null | undefined, unit: LoadUnit = 'kg') =>
  kg == null ? '' : unit === 'lb' ? trimmed(kg * LB_PER_KG, 1) : trimmed(kg, 1)

/** What a load field holds, back as kilograms (two places: as fine as a
 *  tenth of a pound). */
export const loadFromField = (value: number | null, unit: LoadUnit = 'kg') =>
  value == null ? null : Number((unit === 'lb' ? value / LB_PER_KG : value).toFixed(2))

/** "11 min", "45 s": how long a session ran. */
export function durationLabel(seconds: number | null | undefined): string | null {
  if (seconds == null || seconds < 0) return null
  if (seconds < 60) return `${Math.round(seconds)} s`
  return `${Math.round(seconds / 60)} min`
}

/** "3 × 10 · 12 kg": what was done, from the completion when it says, else
 *  the dose. Null when neither names a count. */
export function doneLine(a: ExerciseAssignment, unit: LoadUnit = 'kg'): string | null {
  const c = a.completion
  const sets = c?.setsDone ?? a.sets
  const reps = c?.repsDone ?? a.reps
  const load = c?.loadDoneKg ?? a.loadKg
  const parts: string[] = []
  if (sets != null && reps != null) parts.push(`${sets} × ${reps}`)
  else if (sets != null) parts.push(`${sets} ${sets === 1 ? 'set' : 'sets'}`)
  const kg = loadLabel(load, unit)
  if (kg) parts.push(kg)
  return parts.length ? parts.join(DOT) : null
}

/** A file that reached storage and is waiting to be claimed by the request
 *  that gives it meaning. On a deployment without an object store the bytes
 *  went through the API and were confirmed there, so `attachmentId` is set
 *  and `storageKey` is what that row was stored under, when known. */
export type StagedUpload = {
  storageKey: string | null
  attachmentId: number | null
  contentType: string
  byteSize: number
  filename: string | null
}

/** "Dr. Ashley Gregg" → "Dr. Gregg"; "Ashley Gregg" → "Ashley". The way a
 *  patient says their therapist's name. */
export function therapistShortName(name: string | null | undefined): string {
  const words = (name ?? '').trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return 'your therapist'
  if (words.length === 1) return words[0]
  if (words[0].endsWith('.')) return `${words[0]} ${words[words.length - 1]}`
  return words[0]
}

/** "pain 4/10", for a row or a sent line. */
export const painLabel = (n: number | null | undefined) => (n == null ? null : `pain ${n}/10`)

// MARK: - Thread

export type MessageAction = {
  kind: string
  taskId: number | null
  label: string
  /** Where the button opens, in the shape a redeemed link answers with: on
   *  a line a text carried with a link (`open_exercise`, `open_program`, …). */
  target?: LinkTarget | null
}
export const opensTask = (a: MessageAction | null | undefined) =>
  a && a.kind === 'open_task' ? a.taskId : null
/** The place a texted line's link opens, for a line that is not a task's. */
export const opensPlace = (a: MessageAction | null | undefined): LinkTarget | null =>
  a && a.kind !== 'open_task' && a.target ? a.target : null

export type ChatAttachment = {
  id: number
  contentType: string
  byteSize: number
  filename: string | null
  kind: string
  sha256: string | null
  uploadedBy: string
  source: string
  createdAt: string | null
  withdrawn?: boolean | null
}

export const isImage = (a: ChatAttachment) => a.kind === 'image'
export const isVideo = (a: ChatAttachment) => a.kind === 'video'
export const isAudio = (a: ChatAttachment) => a.kind === 'audio'
export const isWithdrawn = (a: ChatAttachment) => a.withdrawn === true

/** The glyph for a composer chip or a strip placeholder. */
export function attachmentSymbol(a: ChatAttachment): string {
  switch (a.kind) {
    case 'image': return 'photo'
    case 'video': return 'video'
    case 'audio': return 'waveform'
    default: return 'doc'
  }
}

/** "photo", "video", "recording" or "file", for a sentence. */
export function attachmentNoun(a: ChatAttachment): string {
  switch (a.kind) {
    case 'image': return 'photo'
    case 'video': return 'video'
    case 'audio': return 'recording'
    default: return 'file'
  }
}

export function sizeLabel(bytes: number): string {
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.floor(bytes / 1024)} KB`
  return `${bytes} B`
}

export function attachmentDisplayName(a: ChatAttachment): string {
  if (a.filename) return a.filename
  if (isAudio(a)) return 'Voice note'
  const n = attachmentNoun(a)
  return n.charAt(0).toUpperCase() + n.slice(1)
}

export type ChatMessage = {
  id: number
  sender: string
  authoredBy?: string | null
  authorName?: string | null
  channel: string
  text: string
  createdAt: string | null
  deliveryStatus: string | null
  action?: MessageAction | null
  attachments?: ChatAttachment[] | null
  read: boolean
}

export const fromClinician = (m: ChatMessage) => m.authoredBy === 'care_team'
export const filesOf = (m: ChatMessage) => m.attachments ?? []

export type MessagesResponse = { messages: ChatMessage[] }
export type SentMessageResponse = { ok: boolean; message: ChatMessage }
export type AgentResponse = { reply: string; flagged: boolean; provider: string; tasksOpen: number }

// MARK: - Wearables

export type AppleSession = { signInToken: string; userId: string; environment: string; region: string }
export type LinkResponse = { linkUrl: string; expiresAt: string | null }

/** Where a texted link leads (`/a/<token>`, `app/links.py`): the kind of
 *  place, the row it is about (an assignment for `exercise`, a task for
 *  `task` and `checkin`), and the day it names. */
export type LinkTarget = {
  kind: 'today' | 'exercise' | 'program' | 'task' | 'checkin' | 'thread' | 'measure' | 'progress' | string
  refId: string | null
  day: string | null
}
/** GET /api/links/{token}: the target and whether redeeming signs in. */
export type LinkInfo = LinkTarget & { signin: boolean; expiresAt: string | null }
/** POST /api/links/{token}/session: a session as the person it was texted
 *  to (demo stack, demo persona only), with the place to open. */
export type LinkSession = { sessionToken: string; me: Me; target: LinkTarget }
export type WearablesResponse = { summary: WearableSummary; refreshError: string | null }

export type ProgressDay = { date: string; postopDay: number; steps: number | null; sleepHours: number | null }
export type ProgressResponse = { days: ProgressDay[] }

export type GaitPoint = { metricType: string; date: string; value: number }
export type GaitUpload = { points: GaitPoint[]; deviceModel: string | null }
export type GaitUploadResponse = {
  ingested: number
  updated: number
  duplicates: number
  skippedOutOfWindow: number
  droppedImplausible: number
  rejected: number
}

export type OKResponse = { ok: boolean }

// MARK: - MedPull's own measurements (backend app/api/mobility)

export type MotionWindowUpload = {
  startedAt: string
  sampleRateHz: number
  accel: number[][]
  gyro: number[][] | null
  gravity: number[][] | null
  timestamps: number[] | null
  altitude: number[][] | null
  gpsDistanceM: number | null
  gpsAccuracyM: number | null
  pedometerSteps: number | null
  pedometerDistanceM: number | null
  pocketSide: string | null
  context: string
}

export type MotionUpload = {
  windows: MotionWindowUpload[]
  heightCm: number | null
  deviceModel: string | null
}

export type MotionWindowSummary = {
  durationS: number
  walkingS: number
  bouts: number
  steps: number
  cadenceSpm: number | null
  walkingSpeedMps: number | null
  stepLengthM: number | null
  asymmetryPct: number | null
  doubleSupportPct: number | null
  steadiness: number | null
  notes: string[]
}

export type MotionUploadResponse = {
  windows: MotionWindowSummary[]
  ingested: number
  updated: number
  duplicates: number
}

export type SixMinuteWalkUpload = {
  startedAt: string
  durationS: number
  steps: number | null
  pedometerDistanceM: number | null
  gpsDistanceM: number | null
  gpsAccuracyM: number | null
  minuteSteps: number[] | null
  heightCm: number | null
  deviceModel: string | null
  motion: MotionWindowUpload | null
}

export type SixMinuteWalkResponse = {
  distanceM: number
  method: string
  steps: number | null
  cadenceSpm: number | null
  fadePct: number | null
  motion: MotionWindowSummary | null
}

export type RangeOfMotionUpload = {
  recordedAt: string
  protocol: string
  side: string
  reference: number[][]
  movement: number[][]
  deviceModel: string | null
}

export type RangeOfMotionResponse = {
  joint: string
  movement: string
  side: string
  angleDeg: number
  steady: boolean
}

// MARK: - Consent

export type ConsentScope = { key: string; label: string; detail: string; required: boolean }

export type ConsentDocument = {
  kind: string
  version: string
  text: string
  textSha256: string
  scopes: ConsentScope[]
  beta: boolean
}

export type ConsentAcceptance = {
  version: string
  scopes: Record<string, boolean>
  signature: string | null
}

// MARK: - Typesetting

/** The separator between two facts: "Day 8 · Total Knee Replacement".
 *  Outfit draws "·" 0.13em wide with no sidebearings, so the dot is held off
 *  each word by a thin space (the CSS routes U+2009 and U+00B7 to Arial). */
export const DOT = '  ·  '
/** The same dot opening a trailing fact. */
export const DOT_LEAD = '·  '

/** Straight apostrophes turned into typographic ones for display. Server
 *  copy keeps plain ones because it is also sent by text. */
export function typeset(s: string): string {
  return s.replace(/(\w)'(\w)/g, '$1’$2')
}

// MARK: - Dates

const fractionRe = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:?\d{2})?$/
const dayRe = /^(\d{4})-(\d{2})-(\d{2})$/

export const Dates = {
  /** The backend's naive timestamps are local time, like the iPhone app
   *  reads them; a day string is local midnight of that day. */
  parse(raw: string | null | undefined): Date | null {
    if (!raw) return null
    const m = fractionRe.exec(raw)
    if (m) {
      const [, y, mo, d, h, mi, s, frac, zone] = m
      const ms = frac ? Math.round(Number(`0.${frac}`) * 1000) : 0
      if (zone) return new Date(raw.length > 26 && !frac ? raw : raw) // let the engine parse the offset
      return new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s), ms)
    }
    const d = dayRe.exec(raw)
    if (d) return new Date(Number(d[1]), Number(d[2]) - 1, Number(d[3]))
    const t = Date.parse(raw)
    return Number.isNaN(t) ? null : new Date(t)
  },

  dayString(date: Date): string {
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
  },

  /** ISO 8601 with the local offset, for the measurement uploads. */
  iso(date: Date): string {
    const off = -date.getTimezoneOffset()
    const sign = off >= 0 ? '+' : '-'
    const hh = String(Math.floor(Math.abs(off) / 60)).padStart(2, '0')
    const mm = String(Math.abs(off) % 60).padStart(2, '0')
    const p = (n: number) => String(n).padStart(2, '0')
    return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}T${p(date.getHours())}:${p(date.getMinutes())}:${p(date.getSeconds())}${sign}${hh}:${mm}`
  },

  /** "2 hr. ago", "3 days ago": the iPhone's short relative style. */
  relative(raw: string | null | undefined): string {
    const date = Dates.parse(raw)
    if (!date) return ''
    const diff = (date.getTime() - Date.now()) / 1000
    const abs = Math.abs(diff)
    const past = diff <= 0
    const say = (n: number, unit: string) => (past ? `${n} ${unit} ago` : `in ${n} ${unit}`)
    if (abs < 60) return past ? 'just now' : 'in a moment'
    if (abs < 3600) return say(Math.round(abs / 60), 'min.')
    if (abs < 86400) return say(Math.round(abs / 3600), 'hr.')
    if (abs < 7 * 86400) {
      const n = Math.round(abs / 86400)
      return say(n, n === 1 ? 'day' : 'days')
    }
    if (abs < 30 * 86400) return say(Math.round(abs / (7 * 86400)), 'wk.')
    if (abs < 365 * 86400) return say(Math.round(abs / (30 * 86400)), 'mo.')
    return say(Math.round(abs / (365 * 86400)), 'yr.')
  },

  shortDay(raw: string): string {
    const d = Dates.parse(raw)
    return d ? d.toLocaleDateString(undefined, { weekday: 'short' }) : raw
  },

  /** "Sep 29" for a server day string; the raw string if it does not parse. */
  monthDay(raw: string): string {
    const d = Dates.parse(raw)
    return d ? monthDayOf(d) : raw
  },

  /** "09:30" -> "9:30 AM" in the reader's locale; "" when there is no time. */
  clockTime(raw: string | null | undefined): string {
    const m = /^(\d{1,2}):(\d{2})/.exec(raw ?? '')
    if (!m) return ''
    return new Date(2000, 0, 1, Number(m[1]), Number(m[2])).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  },

  /** Whole days from a server day to today (0 = today), or null. */
  daysAgo(raw: string): number | null {
    const d = Dates.parse(raw)
    if (!d) return null
    const start = new Date(d.getFullYear(), d.getMonth(), d.getDate())
    const now = new Date()
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
    return Math.round((today.getTime() - start.getTime()) / 86400000)
  },

  /** "today", "yesterday", "3 days ago". */
  agoWords(raw: string): string {
    const n = Dates.daysAgo(raw)
    if (n == null) return ''
    if (n < 1) return 'today'
    if (n === 1) return 'yesterday'
    return `${n} days ago`
  },

  isToday(date: Date): boolean {
    const now = new Date()
    return date.getFullYear() === now.getFullYear() && date.getMonth() === now.getMonth()
      && date.getDate() === now.getDate()
  },

  sameDay(a: Date, b: Date): boolean {
    return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  },

  /** "2026-08-28" -> "Aug 28, 2026" in the reader's locale. */
  displayDate(iso: string): string {
    const d = Dates.parse(iso.slice(0, 10))
    return d ? d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : iso
  },
}

export function monthDayOf(d: Date): string {
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}
