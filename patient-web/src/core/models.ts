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
}

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

// MARK: - Thread

export type MessageAction = { kind: string; taskId: number | null; label: string }
export const opensTask = (a: MessageAction | null | undefined) =>
  a && a.kind === 'open_task' ? a.taskId : null

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
