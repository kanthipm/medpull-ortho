import type { ReactNode } from 'react'

/** Icon tile families — the site's gradient glyph squares (white glyph on a
 *  grainy gradient). The names are the old category slots:
 *    blue    -> amber  communication, check-ins, engagement (Phone, MessageSquare, Bell)
 *    teal    -> sage   activity, mobility, AI narrative   (Footprints, Activity, Sparkles)
 *    indigo  -> lilac  sleep and trajectory             (Moon, TrendingUp)
 *    violet  -> clay   vitals, medication, wound, plan  (HeartPulse, Pill, Bandage, ClipboardList)
 *    risk-high -> dusk escalate only                    (TriangleAlert)
 *    frost   a white app-icon tile with an ink glyph, for the fog window.
 *  Always decorative: the row title carries the meaning. */
export type TileFamily = 'blue' | 'teal' | 'indigo' | 'violet' | 'risk-high' | 'frost'

const FAMILY: Record<TileFamily, string> = {
  blue: 'tile-blue',
  teal: 'tile-teal',
  indigo: 'tile-indigo',
  violet: 'tile-violet',
  'risk-high': 'tile-risk-high',
  frost: 'tile-frost',
}

/** A leading icon tile, like the app's TaskRow.
 *
 *    <Tile family="blue" icon={<Phone />} />            30px, 9px corners, 16px glyph
 *    <Tile family="teal" icon={<Sparkles />} size="lg" /> 44px, 13px corners, 20px glyph
 *    <Tile family="teal" icon={<Sparkles />} size="sm" /> 22px, 7px corners, 12px glyph (inline labels) */
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
        ? '!h-[22px] !w-[22px] !rounded-[7px] [&_svg]:!h-3 [&_svg]:!w-3'
        : ''
  return (
    <span aria-hidden className={`tile ${FAMILY[family]} ${sizeClass} ${className}`}>
      {icon}
    </span>
  )
}
