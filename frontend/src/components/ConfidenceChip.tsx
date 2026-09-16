import { CONFIDENCE_LABEL, type ConfidenceLevel } from '../lib/risk'

const STYLES: Record<ConfidenceLevel, string> = {
  high: 'bg-risk-low-bg text-risk-low',
  med: 'bg-risk-med-bg text-risk-med',
  low: 'bg-risk-missing-bg text-risk-missing',
}

/** Confidence chip. High confidence is the norm, so it renders nothing unless
 *  asked — the chip flags reduced trust, not normalcy. */
export default function ConfidenceChip({
  level,
  showHigh = false,
  className = '',
}: {
  level: ConfidenceLevel
  showHigh?: boolean
  className?: string
}) {
  if (level === 'high' && !showHigh) return null
  return (
    <span
      className={`chip max-w-full overflow-hidden ${STYLES[level]} ${className}`}
    >
      <span className="truncate">{CONFIDENCE_LABEL[level]}</span>
    </span>
  )
}
