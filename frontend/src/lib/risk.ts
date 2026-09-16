export type Priority = 'high' | 'medium' | 'low' | 'missing_data'
export type TrajectoryState = 'behind' | 'on' | 'ahead' | 'unknown'
export type ConfidenceLevel = 'high' | 'med' | 'low'
export type Urgency = 'today' | 'this_week' | 'routine'

/** The twelve risk recipes that drive every status pill, dot and spine in the
 *  console. Four tiers x three roles, and the class strings here are the only
 *  place the colour is chosen.
 *
 *  WHY THE TOKENS CHANGED. These were the Material defaults (`risk-high` =
 *  #EF6C00 on `risk-high-bg` = #FFF3E0 and its neighbours), and every one of
 *  them failed WCAG 1.4.3 as a 12px pill label — #EF6C00 on #FFF3E0 measures
 *  2.81:1. The pairs below are the redesigned `-ink` / `-tint` tokens and every
 *  one clears AA in BOTH modes, recomputed here from sRGB relative luminance:
 *
 *    pill (ink on its own tint)      light    dark
 *      high      #C62828 / #FBEAEA   4.835   5.701
 *      medium    #9A5300 / #FBF0E1   5.165   6.890
 *      low       #1B7A43 / #E6F4EB   4.731   6.484
 *      missing   #4E5865 / #EDF1F6   6.367   5.093
 *    dot + spine (ink on --panel)    light    dark
 *      high                          5.622   7.563
 *      medium                        5.815   9.641
 *      low                           5.369   9.035
 *      missing                       7.222   6.650
 *
 *  `-ink` is the only risk token that may carry text or a mark; `-tint` is the
 *  only one that may be a background. The bare `risk-high` / `risk-high-bg`
 *  aliases these used to name are retired and die in the Cleanup phase, so
 *  nothing here reads them any more.
 *
 *  COLOUR NEVER CARRIES THE STATE ALONE. Every recipe below is a `pill`, and a
 *  pill always renders its `label` (or the engine's `status_text`) as words, so
 *  the tier survives greyscale, 8% deuteranopia and a monochrome print. `dot`
 *  and `spine` are redundant encodings of a state that is already spelled out
 *  next to them — WorklistPage pairs the dot with `PRIORITY[tier].label`,
 *  PriorityBadge puts the dot inside the labelled pill, and MetricCard /
 *  SignalsBody put the 4px spine on a card whose own pill names the status.
 *  If a new call site wants one of these without the word, it needs an icon
 *  instead; it does not get to ship colour on its own.
 *
 *  `normal-case tracking-ui` is part of every pill recipe ON PURPOSE. Five call
 *  sites (MetricCard, SignalsBody, HeadlineMetrics and NextSteps x2) append
 *  `uppercase tracking-[.03em]` next to these strings, and at 12px uppercase is
 *  slower to read and spends the screen's single uppercase slot on a chip.
 *  Tailwind emits `normal-case` after `uppercase` and named letter-spacings
 *  after arbitrary ones, so these two win on source order regardless of where
 *  they sit in the className string. The call sites should drop their own two
 *  classes in the sweep; until they do, this is what makes the pills sentence
 *  case. */

/** Labels are SPEC.md's three recovery states — On Track, Needs Review, High
 *  Risk — read onto the engine's four tiers, calm to urgent. `missing_data`
 *  is not a recovery state but the absence of one, so it keeps its own label
 *  rather than borrowing a verdict the coverage gate refused to make. */
export const PRIORITY = {
  high: {
    label: 'High risk',
    dot: 'bg-risk-high-ink',
    pill: 'bg-risk-high-tint text-risk-high-ink normal-case tracking-ui',
    spine: 'bg-risk-high-ink',
    order: 0,
  },
  medium: {
    label: 'Needs review',
    dot: 'bg-risk-med-ink',
    pill: 'bg-risk-med-tint text-risk-med-ink normal-case tracking-ui',
    spine: 'bg-risk-med-ink',
    order: 1,
  },
  missing_data: {
    label: 'Missing data',
    dot: 'bg-risk-missing-ink',
    pill: 'bg-risk-missing-tint text-risk-missing-ink normal-case tracking-ui',
    spine: 'bg-risk-missing-ink',
    order: 2,
  },
  low: {
    label: 'On track',
    dot: 'bg-risk-low-ink',
    pill: 'bg-risk-low-tint text-risk-low-ink normal-case tracking-ui',
    spine: 'bg-risk-low-ink',
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
  today: {
    label: 'Today',
    pill: 'bg-risk-high-tint text-risk-high-ink normal-case tracking-ui',
  },
  this_week: {
    label: 'This week',
    pill: 'bg-risk-med-tint text-risk-med-ink normal-case tracking-ui',
  },
  routine: {
    label: 'Routine',
    pill: 'bg-risk-missing-tint text-risk-missing-ink normal-case tracking-ui',
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
    pill: 'bg-risk-high-tint text-risk-high-ink normal-case tracking-ui',
    spine: 'bg-risk-high-ink',
  },
  watch: {
    label: 'Watch',
    pill: 'bg-risk-med-tint text-risk-med-ink normal-case tracking-ui',
    spine: 'bg-risk-med-ink',
  },
  ok: {
    label: 'OK',
    pill: 'bg-risk-low-tint text-risk-low-ink normal-case tracking-ui',
    spine: 'bg-risk-low-ink',
  },
  nodata: {
    label: 'No data',
    pill: 'bg-risk-missing-tint text-risk-missing-ink normal-case tracking-ui',
    spine: 'bg-risk-missing-ink',
  },
} as const satisfies Record<MetricStatus, unknown>
