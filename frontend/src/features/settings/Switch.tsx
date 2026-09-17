import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import Tile from '../../components/Tile'

/** iOS-style switch for the settings pages.
 *
 *  Track 46x28 capsule, knob 24px white with the contact shadow, sliding on
 *  the spring. State is never colour alone: the knob POSITION is the state,
 *  and role="switch" + aria-checked announce it.
 *
 *  On, the track is the site's sage (6.44 against the white knob). Off, a
 *  warm fill with an inset --line-strong ring (3.39:1 on panel), so the
 *  track's edge — and the knob inside it — stay identifiable. Disabled keeps
 *  the ring and a white knob at half strength; it never turns dark. Focus is
 *  the 2px ink ring, 2px out. */
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
      className={`relative inline-flex h-7 w-[46px] shrink-0 cursor-pointer items-center rounded-pill transition-[background-color,box-shadow] duration-state ease-apple focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus disabled:cursor-not-allowed forced-colors:border forced-colors:border-[ButtonText] ${
        checked && !disabled
          ? 'bg-brand shadow-[inset_0_1px_2px_rgb(0_0_0_/_.12)]'
          : 'bg-[rgb(var(--fill-strong))] shadow-[inset_0_0_0_1px_rgb(var(--line-strong)_/_.8)]'
      } ${disabled ? 'opacity-60' : ''} ${className}`}
    >
      {/* Before/after the tap the thumb is the only moving part. */}
      <span
        aria-hidden
        className={`absolute left-[2px] top-[2px] h-6 w-6 rounded-pill bg-white shadow-knob forced-colors:bg-[ButtonText] ${
          armed ? 'transition-transform duration-spring ease-spring' : ''
        } ${checked ? 'translate-x-[18px]' : 'translate-x-0'}`}
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

/** The large gradient glyph beside the page title: 56px, 16px corners, a
 *  26px white glyph (the site's panel glyph). */
const HERO_TILE =
  '!h-14 !w-14 !rounded-[16px] [&_svg]:!h-[26px] [&_svg]:!w-[26px] [&_svg]:[stroke-width:1.75]'

/** Page head shared by the settings and integrations pages, in the fog
 *  window (AppShell sizes the window to this `[data-hero]` element): a
 *  gradient glyph, the title in light display type, an intro in --body, and
 *  a floating cluster of gradient tiles on the right at >= 1024px
 *  (decorative, no text). */
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
        <Tile family="teal" icon={icon} className={HERO_TILE} />
        <h1 className="display-title min-w-0 text-display text-ink">{title}</h1>
      </div>
      {children && <p className="mt-4 max-w-[30rem] text-lede text-body">{children}</p>}
      {decor && <HeroDecor icons={decor} />}
    </header>
  )
}

/** The site's floating glyph cluster: three grainy gradient tiles that
 *  drift gently (transform only, paused off screen, still under Reduce
 *  Motion) above a ground shadow. Decorative (aria-hidden), desktop only,
 *  gone in forced colours. */
function HeroDecor({ icons }: { icons: [ReactNode, ReactNode, ReactNode] }) {
  const [main, top, bottom] = icons
  return (
    <div
      aria-hidden
      data-loop
      className="pointer-events-none absolute right-6 top-1/2 isolate hidden h-40 w-64 -translate-y-1/2 lg:block forced-colors:hidden"
    >
      <span className="ground-shadow absolute left-[76px] top-[34px]">
        <span className="float-y block" style={{ '--t': '6s' } as CSSProperties}>
          <Tile
            family="teal"
            icon={main}
            className="!h-[88px] !w-[88px] !rounded-[26px] [&_svg]:!h-10 [&_svg]:!w-10 [&_svg]:[stroke-width:1.5]"
          />
        </span>
      </span>
      <span
        className="float-y absolute left-[184px] top-0"
        style={{ '--t': '7s', '--dl': '-2s' } as CSSProperties}
      >
        <Tile
          family="blue"
          icon={top}
          className="!h-14 !w-14 rotate-[8deg] !rounded-[16px] [&_svg]:!h-6 [&_svg]:!w-6"
        />
      </span>
      <span
        className="float-y absolute left-2 top-[100px]"
        style={{ '--t': '8s', '--dl': '-4s' } as CSSProperties}
      >
        <Tile
          family="indigo"
          icon={bottom}
          className="!h-12 !w-12 -rotate-[8deg] !rounded-[14px] [&_svg]:!h-5 [&_svg]:!w-5"
        />
      </span>
    </div>
  )
}
