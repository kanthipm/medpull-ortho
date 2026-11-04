/* The list vocabulary the screens share (UI/Rows.swift). Rows are quiet: a
   small monochrome glyph on a soft tint, ink text, a figure, a chevron.
   Colour marks a category (the glyph) or a state (a dot beside a word),
   never both, and nothing in a row is a gradient. */

import type { ReactNode } from 'react'
import type { Tone } from '../core/models'
import { cx, InsetDivider, MPButton, type Category } from './components'
import { Sym } from './icons'

/** A category glyph: an SF Symbol in the category's ink on its tint disc. */
export function Glyph({ name, family = 'teal', size = 32 }: { name: string; family?: Category; size?: number }) {
  return (
    <span className={cx('glyph', `fam-${family}`)} style={{ ['--side' as string]: `${size}px` }} aria-hidden="true">
      <Sym name={name} size={Math.round(size * 0.46)} weight="medium" />
    </span>
  )
}

/** A section title on the canvas: 20/500 ink, an optional note in body on
 *  the same baseline, an optional trailing action. */
export function SectionTitle({ title, note, actionTitle, onAction }: {
  title: string; note?: string | null; actionTitle?: string; onAction?: () => void
}) {
  return (
    <div className="section-title">
      <h2>{title}</h2>
      {note && <span className="note">{note}</span>}
      <span className="spacer" />
      {actionTitle && onAction && <MPButton kind="plain" bare onClick={onAction}>{actionTitle}</MPButton>}
    </div>
  )
}

/** A header row INSIDE a card: 15/500 ink title, a muted note, a trailing
 *  action. The card's first row. */
export function CardTitleRow({ title, note, actionTitle, onAction }: {
  title: string; note?: string | null; actionTitle?: string; onAction?: () => void
}) {
  return (
    <div className="card-title-row">
      <h3>{title}</h3>
      {note && <span className="note">{note}</span>}
      <span className="spacer" />
      {actionTitle && onAction && <MPButton kind="plain" bare onClick={onAction}>{actionTitle}</MPButton>}
    </div>
  )
}

/** A state as a dot and a word, no fill. For a row; the pill is for a hero. */
export function StateLabel({ text, tone, wrap = false }: { text: string; tone: Tone; wrap?: boolean }) {
  return (
    <span className={cx('state', `tone-${tone}`, wrap && 'wrap')}>
      <i className="tone-dot" aria-hidden="true" />
      <span>{text}</span>
    </span>
  )
}

/** Two weeks in 60 points: a line for a sampled reading, bars for a daily
 *  total. Ink, with the newest mark in the brand fill. Decorative. */
export function Sparkline({ values, bars = false, width = 60, height = 24 }: {
  values: number[]; bars?: boolean; width?: number; height?: number
}) {
  if (values.length < 2) return null
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const base = bars ? 0 : lo
  const span = Math.max(hi - base, 0.0001)
  const n = values.length
  let body: ReactNode
  if (bars) {
    const gap = 2
    const w = Math.max(1, (width - gap * (n - 1)) / n)
    body = values.map((v, i) => {
      const h = Math.max(1.5, ((v - base) / span) * height)
      return (
        <rect key={i} x={i * (w + gap)} y={height - h} width={w} height={h} rx={1}
          fill={i === n - 1 ? 'rgb(var(--brand))' : 'rgb(var(--ink) / 0.55)'} />
      )
    })
  } else {
    const pts = values.map((v, i) => {
      const x = (i / (n - 1)) * width
      const y = height - ((v - base) / span) * (height - 4) - 2
      return [x, y] as const
    })
    const d = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`).join('')
    const last = pts[pts.length - 1]
    body = (
      <>
        <path d={d} fill="none" stroke="rgb(var(--ink) / 0.55)" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={width} cy={last[1]} r={3} fill="rgb(var(--brand))" />
      </>
    )
  }
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" style={{ overflow: 'visible', flexShrink: 0 }}>
      {body}
    </svg>
  )
}

export function Chevron({ size = 13 }: { size?: number }) {
  return <span className="chevron" aria-hidden="true"><Sym name="chevron.right" size={size} weight="semibold" /></span>
}

/** A navigation row: glyph, title, one-line subtitle, trailing content, a
 *  chevron. The tap target is the whole row. */
export function ListRow({
  title, subtitle, symbol, family = 'teal', chevron = true, trailing, onClick, disabled, className,
}: {
  title: string
  subtitle?: string | null
  symbol?: string
  family?: Category
  chevron?: boolean
  trailing?: ReactNode
  onClick?: () => void
  disabled?: boolean
  className?: string
}) {
  const body = (
    <>
      {symbol && <Glyph name={symbol} family={family} />}
      <span className="row-main">
        <span className="row-title">{title}</span>
        {subtitle && <span className="row-sub clamp-2">{subtitle}</span>}
      </span>
      {trailing && <span className="row-trailing">{trailing}</span>}
      {chevron && <Chevron />}
    </>
  )
  if (onClick) {
    return (
      <button type="button" className={cx('row row-button', className)} onClick={onClick} disabled={disabled}>
        {body}
      </button>
    )
  }
  return <div className={cx('row', className)}>{body}</div>
}

/** The divider between two rows that start with a 32pt glyph. */
export function RowDivider({ glyph = true }: { glyph?: boolean }) {
  return <InsetDivider leading={glyph ? 16 + 32 + 12 : 16} />
}

/** A figure with its unit, for a row's trailing edge: 16/500 tabular
 *  figures and a 12pt unit. */
export function RowFigure({ value, unit, minWidth }: { value: string; unit?: string | null; minWidth?: number }) {
  return (
    <span className="row-figure" style={minWidth ? { minWidth, justifyContent: 'flex-end' } : undefined}>
      <b>{value}</b>
      {unit && <span>{unit}</span>}
    </span>
  )
}

/** A big figure for a detail screen or a hero caption: the display face,
 *  light, with the unit beside it. */
export function BigFigure({ value, unit, size = 44 }: { value: string; unit?: string | null; size?: number }) {
  return (
    <span className="big-figure" style={{ ['--size' as string]: `${size}px` }}>
      <b>{value}</b>
      {unit && <span>{unit}</span>}
    </span>
  )
}
