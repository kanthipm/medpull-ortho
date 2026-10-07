import type { Readiness } from '../../../api/care'
import { readinessKind, unitWord } from './readinessText'

/* "x days left" — the countdown every metric carries until it can say
   something (engine/readiness.py). Three states a card can be in:

     collecting, left > 0     a countdown: the big number is the days left,
                              and the meta says what has to arrive
     collecting, left = 0     have > 0 → the source went quiet ("Waiting on
                              new data"); have = 0 → nothing reports this
                              yet ("Needs a source")
     provisional              shown, but thin: an "Early read" chip beside
                              the status chip, with how many more units
                              settle it

   Words, never colour alone: the early-read chip is the risk-med tint with
   its own text, like every other pill in the console. */

/** The early-read chip, rendered next to the status chip when the reading
 *  rests on a thin reference. Nothing otherwise. */
export function EarlyReadChip({ r, className = '' }: { r: Readiness | null | undefined; className?: string }) {
  if (readinessKind(r) !== 'provisional') return null
  return (
    <span className={`chip bg-risk-med-tint text-risk-med-ink normal-case tracking-label ${className}`}>
      Early read · firms up in {r!.firm_left} more {unitWord(r!.unit, r!.firm_left)}
    </span>
  )
}

/** The value slot of a card that is still collecting: the days left as the
 *  big figure ("2" / "more days"), or the waiting / needs-a-source words.
 *  `onTile` draws it in white on a gradient tile's dark band. */
export function ReadinessValue({
  r,
  onTile = false,
  size = 'text-[2.25rem]',
}: {
  r: Readiness
  onTile?: boolean
  size?: string
}) {
  const kind = readinessKind(r)
  const ink = onTile ? 'text-white' : 'text-ink'
  const soft = onTile ? 'text-white/90' : 'text-secondary'
  if (kind === 'countdown') {
    return (
      <span className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className={`big-num ${size} ${ink}`}>{r.left}</span>
        <span className={`text-copy ${soft}`}>more {unitWord(r.unit, r.left)}</span>
      </span>
    )
  }
  return (
    <span className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
      <span className={`big-num ${size} ${ink}`}>—</span>
      <span className={`text-copy ${soft}`}>
        {kind === 'waiting' ? 'waiting on new data' : 'needs a source'}
      </span>
    </span>
  )
}

