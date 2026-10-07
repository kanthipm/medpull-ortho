import type { Readiness } from '../../../api/care'

/* Readiness helpers (what a `Readiness` means for a card). Kept out of
   Readiness.tsx so that file exports components only (react-refresh). */

/** "days" → "day" for one; "paired days" → "paired day". */
export function unitWord(unit: string | undefined, n: number): string {
  const u = (unit || 'days').trim()
  return n === 1 && u.endsWith('s') ? u.slice(0, -1) : u
}

export type ReadinessKind = 'countdown' | 'waiting' | 'source' | 'provisional' | 'ready'

export function readinessKind(r: Readiness | null | undefined): ReadinessKind {
  if (!r) return 'ready'
  if (!r.ready) {
    if (r.left > 0) return 'countdown'
    return r.have > 0 ? 'waiting' : 'source'
  }
  return r.stage === 'provisional' && r.firm_left > 0 ? 'provisional' : 'ready'
}

/** The short line under a countdown: "Shows after 2 more days of steps". */
export function readinessLine(r: Readiness | null | undefined): string | null {
  switch (readinessKind(r)) {
    case 'countdown':
      return `Shows after ${r!.left} more ${unitWord(r!.unit, r!.left)}${
        r!.note ? ` of ${stripUnit(r!.note, r!.unit)}` : ''
      }`
    case 'waiting':
      return 'Waiting on new data from the device'
    case 'source':
      return 'Needs a source'
    case 'provisional':
      return `Early read · firms up in ${r!.firm_left} more ${unitWord(r!.unit, r!.firm_left)}`
    default:
      return null
  }
}

/** "days of steps" with unit "days" → "steps", so the sentence does not read
 *  "2 more days of days of steps". */
function stripUnit(note: string, unit: string | undefined): string {
  const u = (unit || '').trim()
  if (u && note.toLowerCase().startsWith(`${u.toLowerCase()} of `)) {
    return note.slice(u.length + 4)
  }
  return note
}


/** Whether the card should show the countdown in place of its value. */
export function showsCountdown(r: Readiness | null | undefined): r is Readiness {
  return !!r && !r.ready
}
