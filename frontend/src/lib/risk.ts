export type Priority = 'high' | 'medium' | 'low' | 'missing_data'
export type TrajectoryState = 'behind' | 'on' | 'ahead' | 'unknown'
export type ConfidenceLevel = 'high' | 'med' | 'low'
export type Urgency = 'today' | 'this_week' | 'routine'

/** Risk tokens ported from the orthopedic-demo design system. Color appears
 *  only in pills, spines, and status accents — everything else stays ink.
 *
 *  Labels are SPEC.md's three recovery states — On Track, Needs Review, High
 *  Risk — read onto the engine's four tiers, calm to urgent. `missing_data`
 *  is not a recovery state but the absence of one, so it keeps its own label
 *  rather than borrowing a verdict the coverage gate refused to make. */
export const PRIORITY = {
  high: {
    label: 'High risk',
    dot: 'bg-risk-high',
    pill: 'bg-risk-high-bg text-risk-high',
    spine: 'bg-risk-high',
    order: 0,
  },
  medium: {
    label: 'Needs review',
    dot: 'bg-risk-med',
    pill: 'bg-risk-med-bg text-risk-med',
    spine: 'bg-risk-med',
    order: 1,
  },
  missing_data: {
    label: 'Missing data',
    dot: 'bg-risk-missing',
    pill: 'bg-risk-missing-bg text-risk-missing',
    spine: 'bg-risk-missing',
    order: 2,
  },
  low: {
    label: 'On track',
    dot: 'bg-risk-low',
    pill: 'bg-risk-low-bg text-risk-low',
    spine: 'bg-risk-low',
    order: 3,
  },
} as const satisfies Record<Priority, unknown>

export const TRAJECTORY_LABEL: Record<TrajectoryState, string> = {
  behind: 'Behind expected curve',
  on: 'On expected curve',
  ahead: 'Ahead of expected curve',
  unknown: 'Trajectory not yet established',
}

export const URGENCY = {
  today: { label: 'Today', pill: 'bg-risk-high-bg text-risk-high' },
  this_week: { label: 'This week', pill: 'bg-risk-med-bg text-risk-med' },
  routine: { label: 'Routine', pill: 'bg-risk-missing-bg text-risk-missing' },
} as const satisfies Record<Urgency, unknown>

export const CONFIDENCE_LABEL: Record<ConfidenceLevel, string> = {
  high: 'High confidence',
  med: 'Moderate confidence',
  low: 'Low confidence',
}

export type MetricStatus = 'flag' | 'watch' | 'ok' | 'nodata'

export const METRIC_STATUS = {
  flag: { label: 'Flag', pill: 'bg-risk-high-bg text-risk-high', spine: 'bg-risk-high' },
  watch: { label: 'Watch', pill: 'bg-risk-med-bg text-risk-med', spine: 'bg-risk-med' },
  ok: { label: 'OK', pill: 'bg-risk-low-bg text-risk-low', spine: 'bg-risk-low' },
  nodata: { label: 'No data', pill: 'bg-risk-missing-bg text-risk-missing', spine: 'bg-risk-missing' },
} as const satisfies Record<MetricStatus, unknown>
