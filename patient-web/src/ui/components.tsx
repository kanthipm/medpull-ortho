/* The shared components, in the medpull.org language (UI/Components.swift).
   The rules these enforce: a card is the site's glass card; the primary
   action is the near-black capsule with a lime dot; icon tiles and avatars
   are grainy earthy gradients with white marks, hue names a category and
   never a state; sage is a fill and sage text is brand-ink. */

import {
  createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState,
  type CSSProperties, type MouseEventHandler, type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import type { Tone } from '../core/models'
import { Sym } from './icons'

export type Category = 'blue' | 'teal' | 'indigo' | 'violet'
export type Gradient = 'sage' | 'meadow' | 'amber' | 'clay' | 'dusk' | 'lilac' | 'mint'

export const cx = (...parts: Array<string | false | null | undefined>) => parts.filter(Boolean).join(' ')

// MARK: - Tint context

const OnTintContext = createContext(false)
export const useOnTint = () => useContext(OnTintContext)

// MARK: - Card

/** The site's glass card: a white gradient, a light-catching rim and the
 *  layered glass shadow. `padding: 0` for a card of rows (`.card-flush`);
 *  `tint` for the narrative wash. */
export function Card({
  padding = 16, tint = false, className, style, children, onClick, as,
}: {
  padding?: number
  tint?: boolean
  className?: string
  style?: CSSProperties
  children: ReactNode
  onClick?: MouseEventHandler<HTMLElement>
  as?: 'div' | 'button'
}) {
  const cls = cx('card', padding === 0 && 'card-flush', tint && 'card-tint on-tint', className)
  const st = padding !== 16 && padding !== 0 ? { ...style, padding } : style
  const body = (
    <OnTintContext.Provider value={tint}>{children}</OnTintContext.Provider>
  )
  if (as === 'button') {
    return (
      <button type="button" className={cx(cls, 'card-button')} style={st} onClick={onClick}>
        {body}
      </button>
    )
  }
  return (
    <div className={cls} style={st} onClick={onClick}>
      {body}
    </div>
  )
}

/** A whole card as a button: the gated 0.97 press scale, nothing else. */
export function CardButton({ onClick, children, className, ariaLabel }: {
  onClick: () => void; children: ReactNode; className?: string; ariaLabel?: string
}) {
  return (
    <button type="button" className={cx('card-button', className)} onClick={onClick} aria-label={ariaLabel}>
      {children}
    </button>
  )
}

/** A card's header row: the title and an optional trailing text action. */
export function CardHeader({ title, actionTitle, onAction }: {
  title: string; actionTitle?: string; onAction?: () => void
}) {
  return (
    <div className={cx('card-header', actionTitle && onAction && 'has-action')}>
      <h3>{title}</h3>
      <span className="spacer" />
      {actionTitle && onAction && (
        <MPButton kind="plain" bare onClick={onAction}>{actionTitle}</MPButton>
      )}
    </div>
  )
}

/** An inset hairline between rows in a card, aligned to the row text.
 *  `leading` defaults to a row that starts with a 30pt icon tile. */
export function InsetDivider({ leading = 60 }: { leading?: number }) {
  return <hr className="inset-divider" style={{ ['--leading' as string]: `${leading}px` }} aria-hidden="true" />
}

// MARK: - Tiles and dots

/** The site's gradient glyph square: a white glyph on a grainy gradient. */
export function IconTile({ name, family = 'blue', size = 30 }: { name: string; family?: Category; size?: number }) {
  return (
    <span className={cx('tile grain', `fam-${family}`)} style={{ ['--side' as string]: `${size}px` }} aria-hidden="true">
      <Sym name={name} size={Math.round((size * 16) / 30)} weight="medium" />
    </span>
  )
}

/** The site's lime accent dot with its halo. */
export function LimeDot({ size = 8 }: { size?: number }) {
  return <i className="lime-dot" style={{ ['--size' as string]: `${size}px` }} aria-hidden="true" />
}

// MARK: - Gradient tile

/** The site's signature card: a grainy gradient, white type in the dark
 *  top band (kicker, big light number, a side note), white line art in the
 *  middle, and an ink caption on solid glass at the bottom. */
export function GradientTile({
  gradient, kicker, value, unit, side, valueSize = 44, art, caption, onClick, ariaLabel,
}: {
  gradient: Gradient
  kicker: string
  value?: string | null
  unit?: string | null
  side?: [string, string] | null
  valueSize?: number
  art: ReactNode
  caption?: ReactNode
  onClick?: () => void
  ariaLabel?: string
}) {
  const body = (
    <>
      <div className="gtile-top">
        <div className="stack-4" style={{ minWidth: 0 }}>
          <span className="gtile-kicker">{kicker}</span>
          {value != null && (
            <span className="gtile-figure">
              <span className="gtile-value" style={{ ['--value-size' as string]: `${valueSize}px` }}>{value}</span>
              {unit && <span className="gtile-unit">{unit}</span>}
            </span>
          )}
        </div>
        {side && (
          <div className="gtile-side">
            <b>{side[0]}</b>
            <span>{side[1]}</span>
          </div>
        )}
      </div>
      <div className="gtile-art" aria-hidden="true">{art}</div>
      {caption && <div className="gtile-cap glass-solid">{caption}</div>}
    </>
  )
  if (onClick) {
    return (
      <button type="button" className={cx('gtile card-button', `g-${gradient}`)} onClick={onClick} aria-label={ariaLabel}>
        {body}
      </button>
    )
  }
  return <article className={cx('gtile', `g-${gradient}`)}>{body}</article>
}

// MARK: - Buttons

export type ButtonKind = 'filled' | 'tinted' | 'gray' | 'plain' | 'destructive' | 'destructiveFilled'
export type ControlSize = 'small' | 'regular' | 'large' | 'extraLarge'

const kindClass: Record<ButtonKind, string> = {
  filled: 'btn-filled',
  tinted: 'btn-tinted',
  gray: 'btn-gray',
  plain: 'btn-plain',
  destructive: 'btn-destructive',
  destructiveFilled: 'btn-destructive-filled',
}
const sizeClass: Record<ControlSize, string> = {
  small: 'btn-sm', regular: '', large: 'btn-lg', extraLarge: 'btn-xl',
}

/** The button style behind every MedPull button. */
export function MPButton({
  kind = 'tinted', size = 'regular', fullWidth = false, bare = false, disabled, onClick, children,
  className, type = 'button', ariaLabel, title,
}: {
  kind?: ButtonKind
  size?: ControlSize
  fullWidth?: boolean
  bare?: boolean
  disabled?: boolean
  onClick?: MouseEventHandler<HTMLButtonElement>
  children: ReactNode
  className?: string
  type?: 'button' | 'submit'
  ariaLabel?: string
  title?: string
}) {
  return (
    <button
      type={type}
      className={cx('btn', kindClass[kind], sizeClass[size], fullWidth && 'btn-full', bare && 'btn-bare', className)}
      disabled={disabled}
      onClick={onClick}
      aria-label={ariaLabel}
      title={title}
    >
      {children}
    </button>
  )
}

/** The one full-width commit button: the near-black capsule with the
 *  site's lime dot, 52pt. `loading` keeps the fill with a spinner and
 *  swallows taps; `disabled` uses the disabled token pair. */
export function PrimaryButton({ title, icon, loading = false, disabled = false, onClick, type = 'button' }: {
  title: string; icon?: string; loading?: boolean; disabled?: boolean; onClick?: () => void
  type?: 'button' | 'submit'
}) {
  return (
    <MPButton
      kind="filled" size="large" fullWidth disabled={disabled} type={type}
      onClick={() => { if (!loading) onClick?.() }}
      ariaLabel={loading ? `${title}, working` : title}
    >
      {loading ? <Spinner /> : (
        <>
          {!disabled && (icon ? <Sym name={icon} size={17} weight="semibold" /> : <LimeDot size={7} />)}
          <span>{title}</span>
        </>
      )}
    </MPButton>
  )
}

/** The quieter full-width button: the white glass capsule, 52pt. */
export function SecondaryButton({ title, icon, loading = false, disabled = false, onClick }: {
  title: string; icon?: string; loading?: boolean; disabled?: boolean; onClick?: () => void
}) {
  return (
    <MPButton kind="gray" size="large" fullWidth disabled={disabled} onClick={() => { if (!loading) onClick?.() }}
      ariaLabel={loading ? `${title}, working` : title}>
      {loading ? <Spinner /> : (
        <>
          {icon && <Sym name={icon} size={17} weight="semibold" />}
          <span>{title}</span>
        </>
      )}
    </MPButton>
  )
}

/** The check-in answer: the site's quick reply. A white capsule with a
 *  ring and a soft lift; picked, the sage bubble with white text and a check. */
export function Chip({ label, selected, onClick, disabled }: {
  label: string; selected: boolean; onClick: () => void; disabled?: boolean
}) {
  return (
    <button type="button" className="chip" aria-pressed={selected} onClick={onClick} disabled={disabled}>
      {selected && <span className="chip-check"><Sym name="checkmark" size={13} weight="semibold" /></span>}
      <span>{label}</span>
    </button>
  )
}

// MARK: - Pills and avatars

/** A state pill, the site's: a capsule on the tone's tint, a dot and the
 *  word. Missing data gets a hollow dot. */
export function StatusPill({ text, tone }: { text: string; tone: Tone }) {
  return (
    <span className={cx('pill', `tone-${tone}`)}>
      <i className="tone-dot" aria-hidden="true" />
      <span>{text}</span>
    </span>
  )
}

/** An avatar disc: the site's grainy gradient avatar with white initials,
 *  its tone picked from the initials so a person keeps their colour. */
export function Initials({ text, size = 40, tone = 'brand', style = 'filled' }: {
  text: string; size?: number; tone?: Tone; style?: 'filled' | 'soft'
}) {
  const soft = style === 'soft' && tone !== 'brand' && tone !== 'high'
  let cls: string
  if (soft) cls = `soft tone-${tone}`
  else if (tone === 'high') cls = 'av-high'
  else {
    let h = 0
    for (const ch of text) h = (h * 31 + ch.codePointAt(0)!) & 0xffff
    cls = `av-${h % 5}`
  }
  return (
    <span className={cx('initials', cls)} style={{ ['--side' as string]: `${size}px` }} aria-hidden="true">
      <span style={{ position: 'relative', zIndex: 2 }}>{text}</span>
    </span>
  )
}

// MARK: - Empty, error, field

/** The in-card empty state: a quiet gradient glyph and one line of ink. */
export function EmptyRow({ icon, title, detail }: { icon: string; title: string; detail?: string }) {
  return (
    <div className="empty-row">
      <IconTile name={icon} family="teal" size={40} />
      <span className="t-copy-lg-m c-ink">{title}</span>
      {detail && <span className="t-copy secondary">{detail}</span>}
    </div>
  )
}

/** An inline error, on the amber status tint. */
export function ErrorBanner({ text }: { text: string }) {
  return (
    <div className="banner" role="alert">
      <Sym name="exclamationmark.triangle.fill" size={16} />
      <span>{text}</span>
    </div>
  )
}

export function Spinner({ size = 20, className }: { size?: number; className?: string }) {
  return <span className={cx('spinner', className)} style={{ ['--size' as string]: `${size}px` }} role="status" aria-label="Working" />
}

/** The iOS switch, sage when on. */
export function Toggle({ checked, onChange, disabled, label }: {
  checked: boolean; onChange: (on: boolean) => void; disabled?: boolean; label: string
}) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} className="switch"
      disabled={disabled} onClick={() => onChange(!checked)} />
  )
}

/** The system segmented control. */
export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string
}) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

// MARK: - Screen backgrounds

/** The site's canvas: warm white with soft colour fog that drifts slowly,
 *  grain, and a faint dot grid at the top. */
export function FogBackground({ height = 520 }: { height?: number }) {
  return (
    <div className="fog" style={{ ['--fog-h' as string]: `${height}px` }} aria-hidden="true">
      <i /><i /><i /><i /><i />
    </div>
  )
}

/** The site's entrance: fade in and rise 18pt, staggered by `index`. */
export function Rise({ index = 0, children, className, id }: {
  index?: number; children: ReactNode; className?: string; id?: string
}) {
  return (
    <div className={cx('rise', className)} style={{ ['--i' as string]: index }} id={id}>
      {children}
    </div>
  )
}

// MARK: - Navigation chrome

export type NavBarProps = {
  title?: string
  /** Whether the inline title is drawn (Today hides it until the greeting
   *  scrolls off; a large-title screen hides it until the large title does). */
  titleHidden?: boolean
  leading?: ReactNode
  trailing?: ReactNode
  principal?: ReactNode
  /** True once content has scrolled under the bar: the hard scroll edge. */
  scrolled?: boolean
  back?: { label: string; onClick: () => void }
}

/** The navigation bar: a back button or leading slot, the inline title (or
 *  a principal view), a trailing slot. Transparent until content scrolls
 *  under it. */
export function NavBar({ title, titleHidden, leading, trailing, principal, scrolled, back }: NavBarProps) {
  return (
    <header className="navbar" data-scrolled={scrolled ? 'true' : 'false'}>
      <div className="navbar-leading">
        {back && (
          <button type="button" className="nav-back" onClick={back.onClick}>
            <Sym name="chevron.left" size={22} weight="semibold" />
            <span>{back.label}</span>
          </button>
        )}
        {leading}
      </div>
      {principal ?? (
        <h1 className="navbar-title" style={{ opacity: titleHidden ? 0 : 1 }} aria-hidden={titleHidden || undefined}>
          {title}
        </h1>
      )}
      <div className="navbar-trailing">{trailing}</div>
    </header>
  )
}

/** iOS 26's close control on a sheet: a round glass X. */
export function CloseButton({ onClick, label = 'Close' }: { onClick: () => void; label?: string }) {
  return (
    <button type="button" className="nav-close" onClick={onClick} aria-label={label}>
      <Sym name="xmark" size={15} weight="semibold" />
    </button>
  )
}

export function NavTextButton({ onClick, children, disabled }: { onClick: () => void; children: ReactNode; disabled?: boolean }) {
  return <button type="button" className="nav-text-btn" onClick={onClick} disabled={disabled}>{children}</button>
}

/** A screen: the fog canvas behind a scrolling content area under a nav
 *  bar. `onScrolled` reports when content has passed under the bar. */
export function Screen({
  children, fogHeight = 520, nav, withTabBar = false, bottom, className, scrollRef, onScroll, flat,
}: {
  children: ReactNode
  fogHeight?: number
  nav?: (scrolled: boolean) => ReactNode
  withTabBar?: boolean
  /** A bar pinned under the scroll area (a composer, a footer strip). */
  bottom?: ReactNode
  className?: string
  scrollRef?: React.RefObject<HTMLDivElement | null>
  onScroll?: (top: number) => void
  /** No fog: the plain canvas with grain (`.screen()` on the phone). */
  flat?: boolean
}) {
  const [scrolled, setScrolled] = useState(false)
  const localRef = useRef<HTMLDivElement | null>(null)
  const ref = scrollRef ?? localRef
  return (
    <div className={cx('screen', className)}>
      {!flat && <FogBackground height={fogHeight} />}
      {nav?.(scrolled)}
      <div
        ref={ref}
        className={cx('screen-scroll', withTabBar && 'with-tabbar', !nav && 'no-navbar')}
        onScroll={(e) => {
          const top = e.currentTarget.scrollTop
          const s = top > 2
          if (s !== scrolled) setScrolled(s)
          onScroll?.(top)
        }}
      >
        {children}
      </div>
      {bottom}
    </div>
  )
}

/** A sheet over the tabs: slides up, full height, with its own nav bar. */
export function Sheet({ open, onClose, children, full = false }: {
  open: boolean; onClose: () => void; children: ReactNode; full?: boolean
}) {
  const host = useSheetHost()
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  if (!open || !host) return null
  return createPortal(
    <>
      <div className="sheet-scrim" onClick={onClose} aria-hidden="true" />
      <div className={cx('sheet', full && 'full')} role="dialog" aria-modal="true">
        {children}
      </div>
    </>,
    host,
  )
}

const SheetHostContext = createContext<HTMLElement | null>(null)
export const SheetHostProvider = SheetHostContext.Provider
export const useSheetHost = () => useContext(SheetHostContext)

/** Scroll position → "the greeting has gone": the element's bottom edge
 *  has passed under the bar. */
export function useGone(ref: React.RefObject<HTMLElement | null>, scrollRef: React.RefObject<HTMLElement | null>, threshold = 8) {
  const [gone, setGone] = useState(false)
  useLayoutEffect(() => {
    const scroller = scrollRef.current
    const el = ref.current
    if (!scroller || !el) return
    const check = () => {
      const top = scroller.getBoundingClientRect().top + parseFloat(getComputedStyle(scroller).paddingTop)
      const bottom = el.getBoundingClientRect().bottom
      const g = bottom - top < threshold
      setGone((prev) => (prev === g ? prev : g))
    }
    check()
    scroller.addEventListener('scroll', check, { passive: true })
    return () => scroller.removeEventListener('scroll', check)
  }, [ref, scrollRef, threshold])
  return gone
}

/** A small menu anchored to a button (the composer's plus). */
export function Menu({ open, onClose, anchor, items }: {
  open: boolean
  onClose: () => void
  anchor: React.RefObject<HTMLElement | null>
  items: { label: string; icon: string; onSelect: () => void }[]
}) {
  const host = useSheetHost()
  const pos = useMemo(() => {
    const a = anchor.current
    const h = host
    if (!a || !h) return { left: 12, bottom: 80 }
    const ar = a.getBoundingClientRect()
    const hr = h.getBoundingClientRect()
    return { left: ar.left - hr.left, bottom: hr.bottom - ar.top + 8 }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, anchor, host])
  if (!open || !host) return null
  return createPortal(
    <>
      <div className="menu-scrim" onClick={onClose} />
      <div className="menu" style={{ left: pos.left, bottom: pos.bottom }} role="menu">
        {items.map((it) => (
          <button key={it.label} type="button" role="menuitem" onClick={() => { onClose(); it.onSelect() }}>
            <span>{it.label}</span>
            <Sym name={it.icon} size={18} weight="regular" />
          </button>
        ))}
      </div>
    </>,
    host,
  )
}
