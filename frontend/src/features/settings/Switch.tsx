import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import Tile from '../../components/Tile'

/** iOS-style switch for the settings pages (W6).
 *
 *  Track 44x26 capsule, knob 22px white with the knob contact shadow, sliding
 *  on --ease-spring (Reduce Motion shortens it through the token). State is
 *  never colour alone: the knob POSITION is the state, and role="switch" +
 *  aria-checked announce it.
 *
 *  Contrast (WCAG 1.4.11, 3:1 for control parts), light / dark:
 *    on  track --brand on --panel           4.602 / 3.736; knob on it 4.602
 *    off track --line-strong on --panel     3.834 / 5.671; knob on it 3.834 / 3.032
 *    disabled: --disabled-fill track keeps an inset --line-strong edge
 *              (3.834 / 5.671 on panel; the fill alone is 1.134 / 1.071),
 *              knob --disabled-ink (4.755 / 4.582 on the fill).
 *    focus ring --focus on --panel          4.602 / 6.783, 2px offset. */
export default function Switch({
  checked,
  onChange,
  disabled = false,
  busy = false,
  id,
  'aria-label': ariaLabel,
  'aria-labelledby': ariaLabelledby,
  'aria-describedby': ariaDescribedby,
  className = '',
}: {
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  /** A save is in flight: ignore clicks without greying the switch out. */
  busy?: boolean
  id?: string
  'aria-label'?: string
  'aria-labelledby'?: string
  'aria-describedby'?: string
  className?: string
}) {
  // Skip the slide on first paint so a page load does not animate every knob.
  const [armed, setArmed] = useState(false)
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      aria-label={ariaLabel}
      aria-labelledby={ariaLabelledby}
      aria-describedby={ariaDescribedby}
      aria-busy={busy || undefined}
      disabled={disabled}
      onClick={() => {
        if (busy) return
        setArmed(true)
        onChange(!checked)
      }}
      className={`relative inline-flex h-[26px] w-11 shrink-0 cursor-pointer items-center rounded-pill transition-colors duration-state ease-apple focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed forced-colors:border forced-colors:border-[ButtonText] ${
        disabled
          ? 'bg-disabled-fill shadow-[inset_0_0_0_1px_rgb(var(--line-strong))]'
          : checked
            ? 'bg-brand'
            : 'bg-line-strong'
      } ${className}`}
    >
      {/* Before/after the tap the thumb is the only moving part. */}
      <span
        aria-hidden
        className={`absolute left-[2px] top-[2px] h-[22px] w-[22px] rounded-pill shadow-knob forced-colors:bg-[ButtonText] ${
          armed ? 'transition-transform duration-spring ease-spring' : ''
        } ${disabled ? 'bg-disabled-ink' : 'bg-n-0'} ${
          checked ? 'translate-x-[18px]' : 'translate-x-0'
        }`}
      />
    </button>
  )
}

/** One settings row whose trailing control is a Switch. The text column is
 *  the switch's label (click it to toggle), like an iOS settings cell. */
export function SwitchRow({
  id,
  leading,
  title,
  detail,
  checked,
  onChange,
  disabled,
  busy,
  badge,
}: {
  id: string
  leading?: ReactNode
  title: string
  detail?: ReactNode
  checked: boolean
  onChange: (next: boolean) => void
  disabled?: boolean
  busy?: boolean
  /** A state chip after the title, e.g. "Coming soon". */
  badge?: ReactNode
}) {
  const labelId = `${id}-label`
  const detailId = `${id}-detail`
  return (
    <li className="card-row grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3">
      {leading ? <span className="flex shrink-0 items-center">{leading}</span> : <span />}
      <div className="min-w-0">
        <label
          htmlFor={id}
          id={labelId}
          className={`flex flex-wrap items-center gap-2 text-copy-lg font-medium text-ink ${
            disabled ? 'cursor-default' : 'cursor-pointer'
          }`}
        >
          {title}
          {badge}
        </label>
        {detail && (
          <p id={detailId} className="mt-0.5 text-copy text-secondary">
            {detail}
          </p>
        )}
      </div>
      <Switch
        id={id}
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        busy={busy}
        aria-labelledby={labelId}
        aria-describedby={detail ? detailId : undefined}
      />
    </li>
  )
}

/** iOS grouped-list section header / footer (sentence case, secondary).
 *  `onSky`: the group's header sits in the sky window's tail (the first
 *  group under a page head), so it takes the `.on-sky` text scope: --muted
 *  on the sky's most saturated point is 4.497 light / 3.500 dark, --body is
 *  6.022 / 4.745. */
export function GroupHeader({
  id,
  children,
  aside,
  onSky = false,
}: {
  id?: string
  children: ReactNode
  aside?: ReactNode
  onSky?: boolean
}) {
  return (
    <div className={`mb-2 flex items-baseline justify-between gap-3 px-4 ${onSky ? 'on-sky' : ''}`}>
      <h2 id={id} className="text-copy font-medium text-secondary">
        {children}
      </h2>
      {aside}
    </div>
  )
}

export function GroupFooter({ children }: { children: ReactNode }) {
  return <p className="meta mt-2 px-4">{children}</p>
}

/** The large frosted tile beside the page title: 56px, 16px corners, a 28px
 *  glyph. `.tile-frost` is a sky-only recipe, and the page head is on the sky. */
const HERO_TILE =
  '!h-14 !w-14 !rounded-[16px] [&_svg]:!h-7 [&_svg]:!w-7 [&_svg]:[stroke-width:1.75]'

/** Page head shared by the settings and integrations pages. It sits in the
 *  sky window (AppShell sizes the window to this `[data-hero]` element) and
 *  follows the sky's two zones (index.css), light / dark, at each zone's most
 *  saturated point:
 *    SAFE sky (left): ink 15.324 / 12.268, body 6.022 / 4.745. The intro is
 *      --body at 18px, and `[data-hero]` turns any --muted into --body.
 *      Head text is capped at 30rem (480px), inside the 555px where the
 *      decor zone starts (58% of the window at >= 1024px).
 *    DECOR sky (right, >= 1024px): ink 8.472 / 8.433 only. The decorative
 *      tile cluster lives there: frosted tiles, --brand-ink glyph 4.637 /
 *      4.921 over the decor worst (icons need 3:1). No text.
 *  Nothing starts in the bar band: <main> begins at y 88 (80 on phones,
 *  where the band is under 10% strength and the first item is a glass
 *  control whose floor is computed over the decor worst). */
export function SettingsHero({
  nav,
  icon,
  badge,
  title,
  decor,
  children,
}: {
  /** A sub-nav above the title (a glass segmented control). */
  nav?: ReactNode
  /** The glyph for the large frosted tile beside the title. */
  icon: ReactNode
  /** A small `.badge-ring` capsule above the title (Aside's eyebrow). */
  badge?: ReactNode
  title: string
  /** Three glyphs for the decorative cluster on the right (>= 1024px). */
  decor?: [ReactNode, ReactNode, ReactNode]
  children?: ReactNode
}) {
  return (
    <header
      data-hero
      className="rise relative isolate"
      style={{ '--rise-delay': '0ms' } as CSSProperties}
    >
      {nav && <div className="mb-8">{nav}</div>}
      {badge && <p className="mb-3">{badge}</p>}
      <div className="flex max-w-[30rem] items-center gap-4">
        <Tile family="frost" icon={icon} className={HERO_TILE} />
        <h1 className="min-w-0 text-display font-semibold text-ink">{title}</h1>
      </div>
      {children && <p className="mt-4 max-w-[30rem] text-lede text-body">{children}</p>}
      {decor && <HeroDecor icons={decor} />}
    </header>
  )
}

/** Aside's floating product object, reduced to three frosted tiles resting
 *  on a ground shadow at the right of the head. Purely decorative
 *  (aria-hidden), static, desktop only, and gone in forced colours. Under
 *  Increase Contrast / reduced transparency / glass off the frost turns
 *  opaque with the rest of the glass. */
function HeroDecor({ icons }: { icons: [ReactNode, ReactNode, ReactNode] }) {
  const [main, top, bottom] = icons
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute right-6 top-1/2 isolate hidden h-40 w-64 -translate-y-1/2 lg:block forced-colors:hidden"
    >
      <span className="ground-shadow absolute left-[76px] top-[34px]">
        <Tile
          family="frost"
          icon={main}
          className="!h-[88px] !w-[88px] !rounded-[26px] [&_svg]:!h-10 [&_svg]:!w-10 [&_svg]:[stroke-width:1.5]"
        />
      </span>
      <Tile
        family="frost"
        icon={top}
        className="absolute left-[184px] top-0 !h-14 !w-14 rotate-[8deg] !rounded-[16px] [&_svg]:!h-6 [&_svg]:!w-6"
      />
      <Tile
        family="frost"
        icon={bottom}
        className="absolute left-2 top-[100px] !h-12 !w-12 -rotate-[8deg] !rounded-[14px] [&_svg]:!h-5 [&_svg]:!w-5"
      />
    </div>
  )
}
