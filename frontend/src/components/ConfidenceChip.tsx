import { CONFIDENCE_LABEL, type ConfidenceLevel } from '../lib/risk'

/** Solid `-tint` / `-ink` pairs (light / dark):
 *    high  low-risk green  4.731 / 6.484
 *    med   medium amber    5.165 / 6.890
 *    low   missing grey    6.367 / 5.093
 *  The old `bg-risk-*-bg text-risk-*` aliases are no longer read here. */
const STYLES: Record<ConfidenceLevel, string> = {
  high: 'bg-risk-low-tint text-risk-low-ink',
  med: 'bg-risk-med-tint text-risk-med-ink',
  low: 'bg-risk-missing-tint text-risk-missing-ink',
}

/** Confidence chip. High confidence is the norm, so it renders nothing unless
 *  asked — the chip flags reduced trust, not normalcy.
 *
 *  `variant="meta"` renders the same words as a plain `.meta` line fragment
 *  instead of a capsule — use it where the chip would sit next to other
 *  state and a pill would be clutter (R4: low confidence is meta text on the
 *  worklist). */
export default function ConfidenceChip({
  level,
  showHigh = false,
  variant = 'chip',
  className = '',
}: {
  level: ConfidenceLevel
  showHigh?: boolean
  variant?: 'chip' | 'meta'
  className?: string
}) {
  if (level === 'high' && !showHigh) return null
  if (variant === 'meta') {
    return <span className={`meta ${className}`}>{CONFIDENCE_LABEL[level]}</span>
  }
  return (
    <span className={`chip max-w-full overflow-hidden ${STYLES[level]} ${className}`}>
      <span className="truncate">{CONFIDENCE_LABEL[level]}</span>
    </span>
  )
}
