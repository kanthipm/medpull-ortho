export type Priority = 'high' | 'medium' | 'low' | 'missing_data'
export type TrajectoryState = 'behind' | 'on' | 'ahead' | 'unknown'
export type ConfidenceLevel = 'high' | 'med' | 'low'
export type Urgency = 'today' | 'this_week' | 'routine'

/** The risk recipes that drive every status pill, dot and avatar in the
 *  console. Four tiers x their roles, and the class strings here are the only
 *  place the colour is chosen.
 *
 *  The tokens are the medpull.org status pills (alert, watch, ok, missing),
 *  deepened so every pill clears AA in BOTH modes:
 *
 *    pill (ink on its own tint)      light    dark
 *      high      #B04A26 / #FBECE6   4.73    6.12
 *      medium    #7C5D0A / #F8F0D8   5.38    7.49
 *      low       #43712F / #E7EFE1   4.90    7.41
 *      missing   #4C5680 / #E8EAF3   5.93    6.22
 *
 *  `-ink` is the only risk token that may carry text or a mark; `-tint` is the
 *  only one that may be a background.
 *
 *  COLOUR NEVER CARRIES THE STATE ALONE. Every recipe below is a `pill`, and a
 *  pill always renders its `label` (or the engine's `status_text`) as words, so
 *  the tier survives greyscale, 8% deuteranopia and a monochrome print. `dot`
 *  is a redundant encoding of a state that is already spelled out next to it —
 *  the worklist tier header pairs the dot with `PRIORITY[tier].label`,
 *  PriorityBadge puts the dot inside the labelled pill, and the patient page's
 *  "Today" / "This week" subheaders pair `URGENCY[u].dot` with the word.
 *  If a new call site wants one of these without the word, it needs an icon
 *  instead; it does not get to ship colour on its own.
 *
 *  PILLS are capsules now (`.chip` is rounded-pill) and appear ONCE per view
 *  for a given fact (R7): the worklist tier header replaces the per-row badge,
 *  and the patient header carries the one risk pill. They always sit on their
 *  own opaque tint, never on glass or the ambient wash.
 *
 *  `avatar` (R1). A high-risk patient gets the clay gradient disc
 *  (`.avatar-risk`); every other tier keeps its name-picked gradient.
 *
 *  `normal-case tracking-label` is part of every pill recipe ON PURPOSE. Some
 *  call sites still append `uppercase tracking-[.03em]` next to these strings,
 *  and at 12px uppercase is slower to read and spends the screen's single
 *  uppercase slot on a chip. Tailwind emits `normal-case` after `uppercase`
 *  and named letter-spacings after arbitrary ones, so these two win on source
 *  order regardless of where they sit in the className string. (The 12px rung
 *  tracks at 0.) */

/** Labels are SPEC.md's three recovery states — On Track, Needs Review, High
 *  Risk — read onto the engine's four tiers, calm to urgent. `missing_data`
 *  is not a recovery state but the absence of one, so it keeps its own label
 *  rather than borrowing a verdict the coverage gate refused to make. */
export const PRIORITY = {
  high: {
    label: 'High risk',
    dot: 'bg-risk-high-ink',
    pill: 'bg-risk-high-tint text-risk-high-ink normal-case tracking-label',
    avatar: 'avatar-risk',
    order: 0,
  },
  medium: {
    label: 'Needs review',
    dot: 'bg-risk-med-ink',
    pill: 'bg-risk-med-tint text-risk-med-ink normal-case tracking-label',
    avatar: '',
    order: 1,
  },
  missing_data: {
    label: 'Missing data',
    dot: 'bg-risk-missing-ink',
    pill: 'bg-risk-missing-tint text-risk-missing-ink normal-case tracking-label',
    avatar: '',
    order: 2,
  },
  low: {
    label: 'On track',
    dot: 'bg-risk-low-ink',
    pill: 'bg-risk-low-tint text-risk-low-ink normal-case tracking-label',
    avatar: '',
    order: 3,
  },
} as const satisfies Record<Priority, unknown>

export const TRAJECTORY_LABEL: Record<TrajectoryState, string> = {
  behind: 'Behind expected curve',
  on: 'On expected curve',
  ahead: 'Ahead of expected curve',
  unknown: 'Trajectory not yet established',
}

/** Next-step urgency. On the patient page these are SUBHEADERS (`dot` + the
 *  word), not a pill on every row (R7). `pill` stays for anywhere a single
 *  step is shown out of its group. */
export const URGENCY = {
  today: {
    label: 'Today',
    dot: 'bg-risk-high-ink',
    pill: 'bg-risk-high-tint text-risk-high-ink normal-case tracking-label',
  },
  this_week: {
    label: 'This week',
    dot: 'bg-risk-med-ink',
    pill: 'bg-risk-med-tint text-risk-med-ink normal-case tracking-label',
  },
  routine: {
    label: 'Routine',
    dot: 'bg-risk-missing-ink',
    pill: 'bg-risk-missing-tint text-risk-missing-ink normal-case tracking-label',
  },
} as const satisfies Record<Urgency, unknown>

export const CONFIDENCE_LABEL: Record<ConfidenceLevel, string> = {
  high: 'High confidence',
  med: 'Moderate confidence',
  low: 'Low confidence',
}

export type MetricStatus = 'flag' | 'watch' | 'ok' | 'nodata'

export const METRIC_STATUS = {
  flag: {
    label: 'Flag',
    pill: 'bg-risk-high-tint text-risk-high-ink normal-case tracking-label',
  },
  watch: {
    label: 'Watch',
    pill: 'bg-risk-med-tint text-risk-med-ink normal-case tracking-label',
  },
  ok: {
    label: 'OK',
    pill: 'bg-risk-low-tint text-risk-low-ink normal-case tracking-label',
  },
  nodata: {
    label: 'No data',
    pill: 'bg-risk-missing-tint text-risk-missing-ink normal-case tracking-label',
  },
} as const satisfies Record<MetricStatus, unknown>
