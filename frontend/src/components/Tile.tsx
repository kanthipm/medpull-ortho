import type { ReactNode } from 'react'

/** Category families (non-risk hues only; red/amber/green are risk).
 *    blue    communication and check-ins      (Phone, MessageSquare, Bell)
 *    teal    activity, mobility, AI narrative (Footprints, Activity, Sparkles)
 *    indigo  sleep and trajectory             (Moon, TrendingUp)
 *    violet  vitals, medication, wound, plan  (HeartPulse, Pill, Bandage, ClipboardList)
 *    risk-high  escalate only                 (TriangleAlert)
 *  Glyph ink on its tint, light / dark:
 *    blue 4.963 / 5.624, teal 5.171 / 8.142, indigo 6.950 / 6.721,
 *    violet 6.354 / 7.114, risk-high 4.835 / 5.701. */
export type TileFamily = 'blue' | 'teal' | 'indigo' | 'violet' | 'risk-high'

const FAMILY: Record<TileFamily, string> = {
  blue: 'tile-blue',
  teal: 'tile-teal',
  indigo: 'tile-indigo',
  violet: 'tile-violet',
  'risk-high': 'tile-risk-high',
}

/** A Health-style leading tile: a lucide glyph in a tinted rounded square,
 *  like the app's TaskRow. Decorative (aria-hidden) — the row title carries
 *  the meaning, and hue is never the only carrier.
 *
 *    <Tile family="blue" icon={<Phone />} />            28px, 8px corners, 16px glyph
 *    <Tile family="teal" icon={<Sparkles />} size="lg" /> 40px, 10px corners, 20px glyph
 *    <Tile family="teal" icon={<Sparkles />} size="sm" /> 20px, 6px corners, 12px glyph (inline labels) */
export default function Tile({
  family = 'blue',
  icon,
  size = 'md',
  className = '',
}: {
  family?: TileFamily
  icon: ReactNode
  size?: 'sm' | 'md' | 'lg'
  className?: string
}) {
  const sizeClass =
    size === 'lg'
      ? 'tile-lg'
      : size === 'sm'
        ? '!h-5 !w-5 !rounded-[6px] [&_svg]:!h-3 [&_svg]:!w-3'
        : ''
  return (
    <span aria-hidden className={`tile ${FAMILY[family]} ${sizeClass} ${className}`}>
      {icon}
    </span>
  )
}
