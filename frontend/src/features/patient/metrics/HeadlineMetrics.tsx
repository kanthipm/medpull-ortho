import { ChevronRight } from 'lucide-react'
import type { CSSProperties } from 'react'
import type { CareMetric } from '../../../api/care'
import { useCareMetrics } from '../../../api/care'
import ConfidenceChip from '../../../components/ConfidenceChip'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay, SkeletonCard } from '../../../components/Skeleton'
import type { TileFamily } from '../../../components/Tile'
import DotLine from '../DotLine'
import { latestLabel } from './chartText'
import { GUARDED_NOTE, statusChipText, tileChipClass } from './labels'
import { careMetricTile } from './metricTiles'
import TileArt from './TileArt'
import { valueParts } from './valueParts'

/** The headline metrics — the pathway's priority picks — as the medpull.org
 *  bento: grainy gradient tiles, the number in light Outfit, the metric's own
 *  chart as white line art, and a solid-glass caption with the status chip
 *  and the finding. The first tile spans two columns, like the site's
 *  "Daily steps" tile.
 *
 *  Hue follows the metric's category, never its state: activity and function
 *  sage, engagement amber, sleep and trajectory lilac, vitals and symptoms
 *  clay. The state is the chip, in words, on the opaque caption. White text
 *  only sits in the dark top band of each gradient (7.1:1 or better).
 *
 *  Each tile is a button that opens Full stats on that metric's card. */

const GRADIENT: Record<TileFamily, string> = {
  teal: 'g-sage',
  blue: 'g-amber',
  indigo: 'g-lilac',
  violet: 'g-clay',
  'risk-high': 'g-dusk',
  frost: 'g-mint',
}

function HeadlineTile({
  m,
  index,
  wide,
  onOpen,
}: {
  m: CareMetric
  index: number
  wide: boolean
  onOpen: (metricId: string) => void
}) {
  const nodata = m.status === 'nodata'
  const tile = careMetricTile(m)
  const when = latestLabel(m.chart)
  const { value, unit } = valueParts(m)
  return (
    <button
      type="button"
      onClick={() => onOpen(m.id)}
      data-loop
      style={{ '--d': index } as CSSProperties}
      className={`gtile ${GRADIENT[tile.family]} spotlight reveal group/tile min-h-[22rem] w-full cursor-pointer text-left transition-[transform,box-shadow] duration-spring ease-spring hover:-translate-y-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus active:scale-[.985] motion-reduce:transform-none ${
        wide ? 'lg:col-span-2' : ''
      }`}
    >
      <span className="gtile-top">
        <span className="min-w-0">
          <span className="gtile-kicker block">{m.name}</span>
          <span className="gtile-num big-num">
            {value}
            {unit && <small>{unit}</small>}
          </span>
          {m.value_label && <span className="mt-1 block text-label text-white/90">{m.value_label}</span>}
        </span>
        {when && (
          <span className="gtile-side shrink-0">
            <b>{when.replace(/^Post-op day /i, 'Day ').replace(/^D(\d+)$/, 'Day $1')}</b>
            latest
          </span>
        )}
      </span>

      <span className="gtile-art">
        {nodata ? (
          <span className="text-copy text-white/90">Not enough data yet</span>
        ) : (
          <TileArt spec={m.chart} sigma={m.unit === 'σ' ? m.value_num : null} />
        )}
      </span>

      <span className="gtile-cap block">
        <span className="flex items-center justify-between gap-2">
          <span className={`chip ${tileChipClass(m.status)}`}>{statusChipText(m)}</span>
          <ChevronRight
            aria-hidden
            size={16}
            className="shrink-0 text-secondary transition-transform duration-spring ease-spring group-hover/tile:translate-x-0.5 motion-reduce:transform-none"
          />
        </span>
        <span className={`mt-2 block text-copy text-body ${wide ? 'line-clamp-2' : 'line-clamp-3'}`}>
          {nodata ? (m.unlock ?? m.finding) : m.finding}
        </span>
        <DotLine
          className="meta mt-1.5 block"
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
      <SectionCard title={TITLE}>
        <p className="text-copy text-secondary">
          {isError
            ? 'Care metrics aren’t available for this patient yet.'
            : 'No headline metrics for this pathway yet. Full stats lists every metric and what it needs.'}
        </p>
      </SectionCard>
    )
  }

  return (
    <section aria-labelledby="headline-metrics" className="relative">
      <div className="mb-3 flex items-end justify-between gap-3 px-1">
        <h2 id="headline-metrics" className="text-subhead font-medium text-ink">
          {TITLE}
        </h2>
        <button type="button" className="btn-plain btn-sm -mr-2" onClick={() => onOpen(tiles[0].id)}>
          Full stats <ChevronRight aria-hidden size={14} />
        </button>
      </div>
      <RefreshOverlay show={refreshing} />
      <div
        className={`grid gap-3 sm:grid-cols-2 ${tiles.length >= 3 ? 'lg:grid-cols-4' : 'lg:grid-cols-3'}`}
      >
        {tiles.map((m, i) => (
          <HeadlineTile
            key={m.id}
            m={m}
            index={i}
            wide={i === 0 && tiles.length !== 2}
            onOpen={onOpen}
          />
        ))}
      </div>
    </section>
  )
}
