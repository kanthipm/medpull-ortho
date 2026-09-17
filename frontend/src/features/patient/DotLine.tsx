import { Fragment, type ReactNode } from 'react'

/** One line of parts joined by spaced separator dots, where a dot can never
 *  end a line (judge #10). Each separator is glued, inside a `nowrap` span,
 *  to the first word of the part AFTER it, and the only break opportunity
 *  between parts is the plain space in front of the dot. So a wrap always
 *  starts the next line with "· item", and never leaves "item ·" dangling.
 *
 *  String parts are split on " · " first, so an API string that already
 *  holds dots ("3 signals · p=0.01 · post-op day 8") gets the same rule. A
 *  count and its noun ("day 8", "3.8 σ") are held together with a no-break
 *  space, so "post-op day 8" never splits before its number.
 *
 *  Falsy parts are dropped, so no dot is ever left over when a part renders
 *  nothing. Node parts (a chip, a tinted span) are glued to their dot the
 *  same way.
 *  The dots are aria-hidden; screen readers hear the parts with a pause. */
export default function DotLine({
  parts,
  as: Tag = 'span',
  className = '',
}: {
  parts: ReactNode[]
  as?: 'span' | 'p' | 'div'
  className?: string
}) {
  const kept = parts
    .flatMap((p) => (typeof p === 'string' ? p.split(' · ') : [p]))
    .filter((p) => p != null && p !== false && p !== '' && !(typeof p === 'string' && !p.trim()))
  if (kept.length === 0) return null
  return (
    <Tag className={className}>
      {kept.map((p, i) => (
        <Fragment key={i}>
          {i > 0 && ' '}
          <Part part={p} lead={i > 0} />
        </Fragment>
      ))}
    </Tag>
  )
}

const DOT = <span aria-hidden>·{'\u00a0'}</span>

function Part({ part, lead }: { part: ReactNode; lead: boolean }) {
  if (typeof part === 'string' || typeof part === 'number') {
    const text = String(part)
      .trim()
      // "post-op day 8" is one phrase; "day 8", "week 2": the number stays
      // with its noun.
      .replace(/\b(post-?op) (day)\b/gi, '$1\u00a0$2')
      .replace(/\b(day|days|week|weeks|D) (\d)/gi, '$1\u00a0$2')
      // "3.8 σ", "12 %", "64 bpm": the unit stays with its number.
      .replace(/(\d) (σ|%|bpm|ms|°[CF]|min|h)(?![A-Za-z])/g, '$1\u00a0$2')
    const cut = text.indexOf(' ')
    const head = cut < 0 ? text : text.slice(0, cut)
    const tail = cut < 0 ? '' : text.slice(cut)
    return (
      <>
        <span className="whitespace-nowrap">
          {lead && DOT}
          {head}
        </span>
        {tail}
      </>
    )
  }
  // A node is not held on one line (a guarded note is long); the no-break
  // space after the dot glues it to the node's first glyph instead, since
  // UAX #14 never breaks after U+00A0.
  return (
    <span>
      {lead && DOT}
      {part}
    </span>
  )
}
