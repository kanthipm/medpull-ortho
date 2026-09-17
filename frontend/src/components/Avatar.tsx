import { PRIORITY, type Priority } from '../lib/risk'
import { initialsOf } from './initials'

const SIZE = {
  sm: 'h-7 w-7 text-[11px]', // 28px
  md: '', // 36px — the recipe default, 12/500 initials
  lg: 'h-11 w-11 text-copy', // 44px
  xl: 'h-16 w-16 text-lede', // 64px — patient header
} as const

const TONES = ['av-1', 'av-2', 'av-3', 'av-4', 'av-5'] as const

/** A stable gradient per name, so a patient keeps their colour everywhere. */
function toneFor(name: string): string {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.codePointAt(0)!) >>> 0
  return TONES[h % TONES.length]
}

/** Initials disc — the site's grainy gradient avatar, white initials.
 *
 *  The tone is picked from the name. `tier="high"` swaps in the clay
 *  `.avatar-risk` disc. Decorative by default (the name is next to it, so the
 *  initials never carry information on their own). Pass `label` when the
 *  avatar stands alone and must be announced. */
export default function Avatar({
  name,
  tier,
  size = 'md',
  label,
  className = '',
}: {
  name: string
  /** Risk tier of the patient; only 'high' changes the look. */
  tier?: Priority
  size?: keyof typeof SIZE
  label?: string
  className?: string
}) {
  const risk = tier ? PRIORITY[tier]?.avatar ?? '' : ''
  return (
    <span
      className={`avatar ${risk || toneFor(name)} ${SIZE[size]} ${className}`}
      aria-hidden={label ? undefined : true}
      role={label ? 'img' : undefined}
      aria-label={label}
    >
      {initialsOf(name)}
    </span>
  )
}
