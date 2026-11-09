import { TrendingDown, TrendingUp } from 'lucide-react'
import { adherenceChipClass, adherenceText, loadTrendText } from './scheduleCopy'

/** "3 of 4 · 75%" — done over assigned for the seven days ending today, on
 *  a schedule row header and a worklist card. Calm from 60%, amber under it,
 *  red under 30%; the numbers are always printed, so the tone never carries
 *  the state alone. Nothing is drawn when nothing was assigned. */
export function AdherenceChip({
  done,
  assigned,
  pct,
  className = '',
}: {
  done: number
  assigned: number
  pct: number
  className?: string
}) {
  if (assigned <= 0) return null
  return (
    <span
      className={`chip tabular-nums ${adherenceChipClass(pct)} ${className}`}
      title="Exercises done in the last seven days"
    >
      {adherenceText(done, assigned, pct)}
      <span className="sr-only"> of exercises done in the last seven days</span>
    </span>
  )
}

/** "load +12%" — this week's load against last week's, with the arrow as a
 *  redundant mark. Nothing when there is no last week to compare with. */
export function LoadTrendChip({
  changePct,
  className = '',
}: {
  changePct: number | null | undefined
  className?: string
}) {
  const text = loadTrendText(changePct)
  if (text == null) return null
  const up = (changePct ?? 0) > 0
  const down = (changePct ?? 0) < 0
  return (
    <span className={`chip bg-soft tabular-nums text-secondary ${className}`} title="Load lifted this week against last week">
      {up && <TrendingUp aria-hidden size={12} />}
      {down && <TrendingDown aria-hidden size={12} />}
      {text}
      <span className="sr-only"> against last week</span>
    </span>
  )
}

/** The amber mark of a completion the therapist has not answered yet: a dot
 *  on a chip, or a dot with the count on a card ("2 clips to review"). The
 *  word is always beside it, or in the chip's accessible name. */
export function ReviewDot({ className = '' }: { className?: string }) {
  return <span aria-hidden className={`inline-block h-2 w-2 shrink-0 rounded-pill bg-risk-med-ink ${className}`} />
}

export function AwaitingReview({ count, className = '' }: { count: number; className?: string }) {
  if (count <= 0) return null
  return (
    <span className={`inline-flex items-center gap-1.5 text-label text-risk-med-ink ${className}`}>
      <ReviewDot />
      {count} clip{count === 1 ? '' : 's'} to review
    </span>
  )
}
