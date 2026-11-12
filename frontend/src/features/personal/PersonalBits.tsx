import { Eye } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import type { Panel, PersonalOverview, Writing } from '../../api/personal'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import { SkeletonCard } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { narrativeSource, shortDate } from '../../lib/format'
import { PANEL_GLYPH, panelChip, providerName, values } from './personalFormat'

/** The pieces the three Personal pages share: the member's head, a panel as
 *  a card, a small line of daily values, a written paragraph with who wrote
 *  it, and the loading and failure states. */

/** The page head for a member's space, in the shell's sky window. It says
 *  whose space this is, that the console is looking at it and not editing
 *  it, and where their data comes from. */
export function MemberHead({ overview, children }: { overview: PersonalOverview; children?: ReactNode }) {
  const m = overview.member
  const facts = [
    m.age ? `${m.age}` : null,
    m.goal_label,
    m.sport,
    m.joined_on ? `member since ${shortDate(m.joined_on)}` : null,
  ].filter(Boolean)
  return (
    <header data-hero className="rise pb-2 pt-3" style={{ '--rise-delay': '0ms' } as CSSProperties}>
      <p className="badge-ring">
        <Eye aria-hidden /> {m.name.split(' ')[0]}’s own space, as their phone shows it
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-3">
        <Avatar name={m.name} size="xl" className="shrink-0 shadow-soft ring-4 ring-panel" />
        <div className="min-w-0 flex-1 basis-[260px]">
          <h1 className="display-title text-display text-ink">{m.name}</h1>
          <p className="mt-1 text-copy text-body">{facts.join(' · ')}</p>
          <p className="mt-1 text-copy text-body">
            {m.devices.length > 0
              ? m.devices.map((d) => d.model ?? providerName(d.provider)).join(' · ')
              : 'No device connected'}
            {m.detail ? ` · ${m.detail}` : ''}
          </p>
        </div>
        {children}
      </div>
    </header>
  )
}

/** A run of daily values as one line: the shape of the last weeks, with the
 *  latest point marked. Drawn in the series colour on a card, or in white
 *  on a gradient tile. The numbers themselves are always printed by the
 *  caller; this is the shape, not the reading. */
export function MiniLine({
  points,
  height = 44,
  onTile = false,
  label,
  reference,
}: {
  points: number[]
  height?: number
  onTile?: boolean
  /** What the line shows, for a screen reader. */
  label: string
  /** A level to draw as a dashed rule: the member's own norm, a target. */
  reference?: number | null
}) {
  if (points.length < 2) {
    return (
      <span className={`block text-label ${onTile ? 'text-white/90' : 'text-secondary'}`} style={{ height }}>
        Not enough days yet
      </span>
    )
  }
  const width = 240
  const pad = 4
  const all = reference != null ? [...points, reference] : points
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const span = hi - lo || 1
  const x = (i: number) => pad + (i / (points.length - 1)) * (width - pad * 2)
  const y = (v: number) => pad + (1 - (v - lo) / span) * (height - pad * 2)
  const path = points.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const stroke = onTile ? '#fff' : 'rgb(var(--chart-s1))'
  const last = points[points.length - 1]
  return (
    <svg
      role="img"
      aria-label={label}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="block w-full"
      style={{ height }}
    >
      {reference != null && (
        <line
          x1={pad}
          x2={width - pad}
          y1={y(reference)}
          y2={y(reference)}
          stroke={onTile ? 'rgb(255 255 255 / 0.7)' : 'rgb(var(--chart-ref-line))'}
          strokeWidth={1}
          strokeDasharray="3 3"
          vectorEffect="non-scaling-stroke"
        />
      )}
      <path d={path} fill="none" stroke={stroke} strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
      <circle cx={x(points.length - 1)} cy={y(last)} r={2.5} fill={stroke} />
    </svg>
  )
}

/** One readout as a card: what it is, where it stands in words, its number,
 *  the line under it, the shape of the last weeks and what it means. With
 *  `detail` it also carries its small figures, how it is worked out and what
 *  it was worked out from. */
export function PanelCard({ panel, detail = false }: { panel: Panel; detail?: boolean }) {
  const glyph = PANEL_GLYPH[panel.key]
  const Icon = glyph?.icon
  const series = values(panel.series)
  return (
    <article className="flex flex-col rounded-control bg-soft p-4" aria-label={panel.title}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          {Icon && <Tile size="sm" family={glyph.family} icon={<Icon />} />}
          <h3 className="truncate text-copy-lg font-medium text-ink">{panel.title}</h3>
        </div>
        <span className={`chip shrink-0 ${panelChip(panel.status)}`}>{panel.status_text}</span>
      </div>
      <p className="mt-3 flex flex-wrap items-baseline gap-x-1.5">
        <span className="big-num text-[2rem] text-ink">{panel.headline}</span>
        {panel.unit && <span className="text-copy text-secondary">{panel.unit}</span>}
      </p>
      {panel.sub && <p className="meta mt-0.5">{panel.sub}</p>}
      {series.length > 1 && (
        <div className="mt-3 rounded-control-sm bg-panel px-2 py-1.5">
          <MiniLine points={series} label={`${panel.title} over the last ${series.length} days`} />
        </div>
      )}
      <p className="mt-3 text-copy text-ink">{panel.finding}</p>
      {detail && (
        <>
          {panel.stats && panel.stats.length > 0 && (
            <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
              {panel.stats.map((s) => (
                <div key={s.label}>
                  <dt className="text-label text-secondary">{s.label}</dt>
                  <dd className="text-copy font-medium tabular-nums text-ink">
                    {s.value}
                    {s.unit && <span className="font-normal text-secondary"> {s.unit}</span>}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          <p className="meta mt-3">How: {panel.method}</p>
          <p className="meta mt-1">
            From {panel.coverage} · confidence {panel.confidence}
          </p>
        </>
      )}
    </article>
  )
}

/** A paragraph the app wrote for the member, with who wrote it and the line
 *  the app itself prints under it. */
export function WritingBlock({ writing, text }: { writing: Writing; text: string }) {
  const by = narrativeSource(writing.provider)
  return (
    <>
      <p className="max-w-[70ch] text-copy-lg text-ink">{text}</p>
      <p className="meta mt-3">
        {[by, writing.guardrail].filter(Boolean).join(' · ')}
      </p>
    </>
  )
}

export function PersonalState({
  loading,
  error,
  onRetry,
  children,
}: {
  loading: boolean
  error: boolean
  onRetry: () => void
  children: ReactNode
}) {
  if (loading) {
    return (
      <div className="space-y-stack pt-6" role="status" aria-label="Loading the member’s space">
        <SkeletonCard lines={3} />
        <SkeletonCard rows={4} />
      </div>
    )
  }
  if (error) {
    return (
      <EmptyState
        className="mt-8"
        icon={<Eye />}
        family="indigo"
        title="This member’s space couldn’t be opened"
        action={
          <button type="button" className="btn-tinted" onClick={onRetry}>
            Try again
          </button>
        }
      >
        The console opens demo members only. A real member’s space is theirs alone and is never
        shown here.
      </EmptyState>
    )
  }
  return <>{children}</>
}
