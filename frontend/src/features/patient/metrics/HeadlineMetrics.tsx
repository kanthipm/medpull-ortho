import { ChevronRight, LayoutGrid } from 'lucide-react'
import type { ReactNode } from 'react'
import type { CareMetric } from '../../../api/care'
import { useCareMetrics } from '../../../api/care'
import ConfidenceChip from '../../../components/ConfidenceChip'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay, SkeletonCard } from '../../../components/Skeleton'
import Tile from '../../../components/Tile'
import { MiniChart, latestLabel } from './CareChart'
import { GUARDED_NOTE, statusChipText } from './labels'
import { careMetricTile, tileChipClass } from './MetricCard'

/** Inline (span-only) twin of MetaDots, since the tile is a <button>. */
function MetaLine({ parts }: { parts: ReactNode[] }) {
  const kept = parts.filter((p) => p != null && p !== false && p !== '')
  if (kept.length === 0) return null
  return (
    <span className="meta flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
      {kept.map((p, i) => (
        <span key={i} className="contents">
          {i > 0 && <span aria-hidden>·</span>}
          <span>{p}</span>
        </span>
      ))}
    </span>
  )
}

/** The headline metrics — the pathway's priority picks (the API has already
 *  chosen applicable ones), drawn like the app's "Your portfolio" card: one
 *  white card holding soft filled tiles. Each tile is a button that opens
 *  Full stats on that metric's card; the card header's "Full stats" does the
 *  same for the first tile.
 *
 *  The grid is `auto-fill` rather than a fixed column count, so the same
 *  component reads well in the page's 360px side column (one or two tiles
 *  across) and full width (three across). Contrast on --soft is documented in
 *  MetricCard.tsx; the mini chart sits in an opaque --panel well. */

function HeadlineTile({ m, onOpen }: { m: CareMetric; onOpen: (metricId: string) => void }) {
  const nodata = m.status === 'nodata'
  const tile = careMetricTile(m)
  const when = latestLabel(m.chart)
  return (
    <button
      type="button"
      onClick={() => onOpen(m.id)}
      className="group/tile flex h-full w-full cursor-pointer flex-col rounded-control border border-transparent bg-soft p-3.5 text-left transition-[border-color,transform] duration-state ease-apple hover:border-line focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:scale-press motion-reduce:active:scale-100"
    >
      <span className="flex w-full items-start gap-2">
        <Tile family={tile.family} icon={tile.icon} size="sm" className="mt-0.5 shrink-0" />
        <span className="min-w-0 flex-1 text-copy font-medium text-ink">{m.name}</span>
        <ChevronRight
          aria-hidden
          size={16}
          className="mt-0.5 shrink-0 text-secondary transition-transform duration-state ease-apple group-hover/tile:translate-x-0.5 motion-reduce:transform-none"
        />
      </span>

      <span className={`chip mt-2 self-start ${tileChipClass(m.status)}`}>{statusChipText(m)}</span>

      <span className="mt-2 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className="text-title font-medium tabular-nums text-ink">{m.value ?? '—'}</span>
        {m.unit && <span className="text-copy text-secondary">{m.unit}</span>}
      </span>
      {(m.value_label || when) && (
        <span className="meta mt-0.5 block">
          {[m.value_label, when].filter(Boolean).join(' · ')}
        </span>
      )}
      {m.delta_text && <span className="meta block">{m.delta_text}</span>}

      <span className="mt-2.5 block rounded-control-sm bg-panel px-1.5">
        <MiniChart spec={m.chart} />
      </span>

      <span className="mt-2.5 line-clamp-3 text-copy text-body">
        {nodata ? (m.unlock ?? m.finding) : m.finding}
      </span>

      <span className="mt-auto block pt-2.5">
        <MetaLine
          parts={[
            m.confidence !== 'high' && <ConfidenceChip level={m.confidence} variant="meta" />,
            m.coverage_text,
            m.guarded && <span className="text-risk-med-ink">{GUARDED_NOTE}</span>,
          ]}
        />
      </span>
      <span className="sr-only">. Open in Full stats</span>
    </button>
  )
}

const TITLE = 'Headline metrics'
const ICON = <Tile family="blue" size="sm" icon={<LayoutGrid />} />

export default function HeadlineMetrics({
  patientId,
  refreshing,
  onOpen,
}: {
  patientId: string
  refreshing: boolean
  onOpen: (metricId: string) => void
}) {
  const { data, isLoading, isError } = useCareMetrics(patientId)

  if (isLoading) {
    return <SkeletonCard lines={5} />
  }

  const byId = new Map((data?.metrics ?? []).map((m) => [m.id, m]))
  const tiles = (data?.headline ?? [])
    .map((id) => byId.get(id))
    .filter((m): m is CareMetric => !!m)

  if (isError || tiles.length === 0) {
    return (
      <SectionCard title={TITLE} icon={ICON}>
        <p className="text-copy text-secondary">
          {isError
            ? 'Care metrics are not available for this patient yet.'
            : 'No headline metrics for this pathway yet. Full stats lists every metric and what unlocks it.'}
        </p>
      </SectionCard>
    )
  }

  return (
    <SectionCard
      title={TITLE}
      icon={ICON}
      action={
        <button type="button" className="btn-plain btn-sm" onClick={() => onOpen(tiles[0].id)}>
          Full stats
        </button>
      }
    >
      <RefreshOverlay show={refreshing} />
      <div className="grid grid-cols-[repeat(auto-fill,minmax(10.5rem,1fr))] gap-2.5">
        {tiles.map((m) => (
          <HeadlineTile key={m.id} m={m} onOpen={onOpen} />
        ))}
      </div>
    </SectionCard>
  )
}
