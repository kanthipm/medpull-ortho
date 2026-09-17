import { PRIORITY, type Priority } from '../lib/risk'

/** Up to two initials from a display name ("Marcus Reyes" -> "MR"). */
export function initialsOf(name: string): string {
  const parts = name
    .replace(/[^\p{L}\p{N}\s'-]/gu, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (parts.length === 0) return '?'
  const first = parts[0][0] ?? ''
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? '') : ''
  return (first + last).toUpperCase()
}

const SIZE = {
  sm: 'h-7 w-7 text-label', // 28px
  md: '', // 32px — the recipe default, 12/500 initials
  lg: 'h-10 w-10 text-copy', // 40px
  xl: 'h-14 w-14 text-copy-lg', // 56px — patient header
} as const

/** Initials disc.
 *
 *  Default: brand-tint disc, on-brand-tint initials (7.454 light / 5.624
 *  dark). `tier="high"` (R1) switches to `.avatar-risk`: a PANEL disc with
 *  risk-high-ink initials (5.622 light / 7.563 dark), so on a risk-tinted
 *  row the avatar never shares the row's fill. White on a filled risk disc
 *  was computed and rejected: 5.622 light but 2.273 dark (#FFF on #FF8A87).
 *
 *  Decorative by default (the name is next to it). Pass `label` when the
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
      className={`avatar ${risk} ${SIZE[size]} ${className}`}
      aria-hidden={label ? undefined : true}
      role={label ? 'img' : undefined}
      aria-label={label}
    >
      {initialsOf(name)}
    </span>
  )
}
