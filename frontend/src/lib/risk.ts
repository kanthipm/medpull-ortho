export type Priority = 'high' | 'medium' | 'low' | 'missing_data'
export type TrajectoryState = 'behind' | 'on' | 'ahead' | 'unknown'
export type ConfidenceLevel = 'high' | 'med' | 'low'
export type Urgency = 'today' | 'this_week' | 'routine'

/** The risk recipes that drive every status pill, dot and avatar in the
 *  console. Four tiers x their roles, and the class strings here are the only
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
 *    dot / avatar (ink on --panel)   light    dark
 *      high                          5.622   7.563
 *      medium                        5.815   9.641
 *      low                           5.369   9.035
 *      missing                       7.222   6.650
 *
 *  `-ink` is the only risk token that may carry text or a mark; `-tint` is the
 *  only one that may be a background. The bare `risk-*` / `risk-*-bg` aliases
 *  these used to name are deleted from the token set.
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
 *  `avatar` (R1). A white-initials disc on the risk ink was computed and
 *  REJECTED: #FFF on #C62828 is 5.622 light but #FFF on #FF8A87 is 2.273 dark.
 *  So a high-risk avatar is a PANEL disc with risk-high ink (5.622 / 7.563),
 *  which also keeps it off the row's own tint. Every other tier returns '' and
 *  keeps the default brand-tint `.avatar` (7.454 / 5.624). Use as
 *  `avatar ${PRIORITY[tier].avatar}`.
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
