/* How the Progress tab sorts every signal the server can send: four groups
   a patient recognises, each with a glyph family. Hue is the category,
   never the state (Features/Progress/ProgressModel.swift). */

import { Dates, DOT, hideUnit, latestText, pointDay, type PatientMetric, type PortfolioMetric, type Tone, toneForMetricState } from '../../core/models'
import type { Category } from '../../ui/components'

export type SignalGroup = 'movement' | 'activity' | 'rest' | 'body'
export const signalGroups: SignalGroup[] = ['movement', 'activity', 'rest', 'body']

export const groupTitle: Record<SignalGroup, string> = {
  movement: 'Movement', activity: 'Activity', rest: 'Rest', body: 'Body',
}

export const groupBlurb: Record<SignalGroup, string> = {
  movement: 'How you walk and move. Measured by your phone and watch.',
  activity: 'How much you move each day.',
  rest: 'How you sleep and recover overnight.',
  body: 'Vitals and other readings.',
}

export const groupFamily: Record<SignalGroup, Category> = {
  movement: 'teal', activity: 'blue', rest: 'indigo', body: 'violet',
}

export function groupFor(key: string): SignalGroup {
  switch (key) {
    case 'walking_speed': case 'step_length': case 'cadence': case 'walking_asymmetry_pct':
    case 'double_support_pct': case 'walking_steadiness': case 'stair_speed_up': case 'stair_speed_down':
    case 'six_min_walk': case 'rom_flexion': case 'rom_extension': case 'rom_abduction':
      return 'movement'
    case 'steps': case 'exercise_session': case 'active_energy': case 'calories':
      return 'activity'
    case 'sleep_duration': case 'hrv_rmssd': case 'hrv_sdnn': case 'resting_hr': case 'stress_index': case 'respiratory_rate':
      return 'rest'
    default:
      return 'body'
  }
}

/** The order rows take inside a group: the reading a patient asks about
 *  first comes first. */
const order = [
  'walking_speed', 'six_min_walk', 'step_length', 'cadence', 'walking_steadiness',
  'walking_asymmetry_pct', 'double_support_pct', 'stair_speed_up', 'stair_speed_down',
  'rom_flexion', 'rom_extension', 'rom_abduction',
  'steps', 'exercise_session', 'active_energy', 'calories',
  'sleep_duration', 'resting_hr', 'hrv_rmssd', 'hrv_sdnn', 'stress_index', 'respiratory_rate',
  'skin_temp', 'skin_temp_delta', 'spo2', 'pain_nrs', 'body_weight', 'bp_systolic', 'bp_diastolic',
  'blood_glucose', 'vo2_max', 'hr_recovery_1min',
]

export function rank(key: string): number {
  const i = order.indexOf(key)
  return i < 0 ? order.length : i
}

/** The signals MedPull measures itself with the phone, as the Measure tab
 *  lists them. */
export const MeasuredSignals = {
  guidedWalk: ['walking_speed', 'step_length', 'cadence', 'walking_asymmetry_pct', 'double_support_pct', 'walking_steadiness'],
  sixMinuteWalk: ['six_min_walk'],
  rangeOfMotion: ['rom_flexion', 'rom_extension', 'rom_abduction'],
  get all(): string[] { return [...this.guidedWalk, ...this.sixMinuteWalk, ...this.rangeOfMotion] },
}

/** The SF Symbol for this signal's glyph. */
export function metricSymbol(key: string): string {
  switch (key) {
    case 'steps': return 'figure.walk'
    case 'walking_speed': return 'figure.walk.motion'
    case 'step_length': return 'ruler'
    case 'cadence': return 'metronome'
    case 'walking_asymmetry_pct': case 'double_support_pct': return 'figure.walk.arrival'
    case 'walking_steadiness': return 'figure.stand'
    case 'stair_speed_up': case 'stair_speed_down': return 'stairs'
    case 'six_min_walk': return 'timer'
    case 'rom_flexion': case 'rom_extension': case 'rom_abduction': return 'angle'
    case 'exercise_session': return 'figure.run'
    case 'active_energy': case 'calories': return 'flame.fill'
    case 'sleep_duration': return 'bed.double.fill'
    case 'resting_hr': return 'heart.fill'
    case 'hrv_rmssd': case 'hrv_sdnn': return 'waveform.path.ecg'
    case 'stress_index': return 'wind'
    case 'spo2': return 'lungs.fill'
    case 'respiratory_rate': return 'wind'
    case 'bp_systolic': case 'bp_diastolic': return 'heart.text.square.fill'
    case 'blood_glucose': return 'drop.fill'
    case 'body_weight': return 'scalemass.fill'
    case 'pain_nrs': return 'bandage.fill'
    case 'skin_temp': case 'skin_temp_delta': return 'thermometer.medium'
    case 'vo2_max': return 'lungs.fill'
    case 'hr_recovery_1min': return 'arrow.down.heart.fill'
    default: return 'chart.xyaxis.line'
  }
}

export const metricFamily = (m: PortfolioMetric): Category => groupFamily[groupFor(m.key)]

/** Whether MedPull's own engine produces this signal. */
export const isMeasured = (m: PortfolioMetric) => MeasuredSignals.all.includes(m.key)

/** "Bend" rather than "Flexion": the Measure tab's name for the ROM
 *  signals says which joint movement they are. */
export function displayLabel(m: PortfolioMetric): string {
  switch (m.key) {
    case 'rom_flexion': return 'Bend'
    case 'rom_extension': return 'Straightening'
    case 'rom_abduction': return 'Arm lift'
    default: return m.label
  }
}

// MARK: - The care team's metrics

export function careSymbol(id: string): string {
  switch (id) {
    case 'M1': return 'figure.walk'
    case 'M2': return 'bandage.fill'
    case 'M3': return 'figure.walk.motion'
    case 'M4': return 'gauge.with.needle'
    case 'M5': return 'timer'
    case 'M6': return 'chair'
    case 'M7': return 'speedometer'
    case 'M8': return 'stairs'
    case 'M9': return 'moon.fill'
    case 'M10': return 'waveform.path.ecg'
    case 'M11': return 'sun.horizon.fill'
    case 'M12': return 'heart.text.square.fill'
    case 'M13': return 'thermometer.medium'
    case 'M14': return 'checklist'
    case 'M17': return 'chart.line.uptrend.xyaxis'
    case 'M18': return 'arrow.triangle.branch'
    case 'C1': return 'scalemass.fill'
    case 'C2': return 'lungs.fill'
    case 'C3': return 'drop.fill'
    case 'C4': return 'heart.fill'
    case 'C5': return 'stethoscope'
    case 'C6': return 'chair'
    default: return 'chart.xyaxis.line'
  }
}

export function careFamily(id: string): Category {
  switch (id) {
    case 'M1': case 'M2': case 'M3': case 'M4': case 'M5': case 'M6': case 'M7': case 'M8': case 'C6': return 'teal'
    case 'M9': case 'M10': case 'M11': case 'M17': case 'M18': return 'indigo'
    case 'M12': case 'M13': case 'C1': case 'C2': case 'C3': case 'C4': case 'C5': return 'violet'
    default: return 'blue'
  }
}

export const careTone = (m: PatientMetric): Tone => toneForMetricState(m.state)

/** "Shows in 2 more days" / "Early read · firms up in 1 day" / null. */
export function countdown(m: PatientMetric): string | null {
  const text = m.daysLeftText
  if (!text) return null
  if (text.startsWith('early read')) return `Early read${text.slice('early read'.length)}`
  if (text.startsWith('waiting')) return 'Waiting on new data'
  return `Shows in ${text}`
}

// MARK: - Measure

export type MeasureFlow = 'guidedWalk' | 'sixMinuteWalk' | 'rangeOfMotion'
export const measureFlows: MeasureFlow[] = ['guidedWalk', 'sixMinuteWalk', 'rangeOfMotion']

export const flowTitle: Record<MeasureFlow, string> = {
  guidedWalk: 'Guided walk', sixMinuteWalk: 'Six-minute walk', rangeOfMotion: 'Range of motion',
}
export const flowSubtitle: Record<MeasureFlow, string> = {
  guidedWalk: '3 minutes, phone in your front pocket',
  sixMinuteWalk: 'How far you can walk in six minutes',
  rangeOfMotion: 'Phone on the limb, two short holds',
}
export const flowSymbol: Record<MeasureFlow, string> = {
  guidedWalk: 'figure.walk', sixMinuteWalk: 'timer', rangeOfMotion: 'angle',
}
/** What the test measures, for the Measure tab's card. */
export const flowMeasures: Record<MeasureFlow, string> = {
  guidedWalk: 'Walking speed, step length, rhythm, evenness and steadiness',
  sixMinuteWalk: 'Distance in six minutes, and how your pace holds',
  rangeOfMotion: 'How far the joint bends or straightens, in degrees',
}

/** What the Measure tab says about each test: when it was last done, from
 *  the portfolio, and whether it is due. */
export type MeasureStatus = {
  flow: MeasureFlow
  latest: PortfolioMetric | null
  lastDate: string | null
  daysSince: number | null
  cadenceDays: number
  isDue: boolean
  dueLabel: string
  lastLine: string | null
}

export function measureStatus(flow: MeasureFlow, portfolio: PortfolioMetric[]): MeasureStatus {
  const keys = flow === 'guidedWalk'
    ? ['cadence', 'walking_steadiness', 'step_length', 'walking_speed']
    : flow === 'sixMinuteWalk' ? MeasuredSignals.sixMinuteWalk : MeasuredSignals.rangeOfMotion
  // The most recently measured of the test's signals decides "last".
  const candidates = keys.map((k) => portfolio.find((m) => m.key === k)).filter((m): m is PortfolioMetric => !!m)
  const newest = candidates.reduce<PortfolioMetric | null>((best, m) =>
    !best || pointDay(m.latest) > pointDay(best.latest) ? m : best, null)
  const headline = keys.map((k) => candidates.find((m) => m.key === k)).find((m) => m) ?? newest
  const latest = flow === 'guidedWalk' ? headline : newest
  const lastDate = newest?.latest.date ?? null
  const daysSince = lastDate ? Dates.daysAgo(lastDate) : null
  // How often the care plan expects it: the six-minute walk weekly, a joint
  // test every three days, a guided walk every other day.
  const cadenceDays = flow === 'guidedWalk' ? 2 : flow === 'sixMinuteWalk' ? 7 : 3
  const isDue = daysSince == null || daysSince >= cadenceDays
  let dueLabel: string
  if (daysSince == null) dueLabel = 'Not done yet'
  else {
    const left = cadenceDays - daysSince
    dueLabel = left <= 0 ? 'Due today' : left === 1 ? 'Due tomorrow' : `Due in ${left} days`
  }
  let lastLine: string | null = null
  if (latest && lastDate) {
    const value = hideUnit(latest) ? latestText(latest) : `${latestText(latest)} ${latest.unit}`
    lastLine = `${value}${DOT}${Dates.agoWords(lastDate)}`
  }
  return { flow, latest, lastDate, daysSince, cadenceDays, isDue, dueLabel, lastLine }
}
