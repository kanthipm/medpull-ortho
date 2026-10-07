import { ChevronRight, Sparkles } from 'lucide-react'
import type { CSSProperties } from 'react'
import type { CareMetric } from '../../../api/care'
import { useCareMetrics } from '../../../api/care'
import { explainMetric, useExplain } from '../../../api/explain'
import ConfidenceChip from '../../../components/ConfidenceChip'
import InfoTip from '../../../components/InfoTip'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay, SkeletonCard } from '../../../components/Skeleton'
import Tile, { type TileFamily } from '../../../components/Tile'
import DotLine from '../DotLine'
import { latestLabel } from './chartText'
import { GUARDED_NOTE, statusChipText, tileChipClass } from './labels'
import { careMetricTile } from './metricTiles'
import { EarlyReadChip, ReadinessValue } from './Readiness'
import { readinessLine, showsCountdown } from './readinessText'
import TileArt from './TileArt'
import { valueParts } from './valueParts'

/** The headline metrics — the pathway's SIX fixed picks — as the medpull.org
 *  bento: grainy gradient tiles, the number in light Outfit, the metric's own
 *  chart as white line art, and a solid-glass caption with the status chip
 *  and the finding.
 *
 *  THE SQUARE. Four columns, two rows, six tiles that puzzle into one even
 *  rectangle: slot 0 is wide (two columns), slots 1–2 single, slots 3–4
 *  single, slot 5 wide, so the two rows mirror each other. Every tile in a
 *  row shares the row's height (grid stretch, the caption pinned to the
 *  bottom), and the same metric sits in the same slot for every patient on
 *  the pathway — a knee patient's load ratio is always the second tile. A
 *  tile with no data keeps its slot and counts down to its first reading
 *  instead of handing the slot to something else.
 *
 *  Below the square, "Brought to your attention" is the engine's own
 *  judgement: anything outside the six it flagged or is watching, as a
 *  compact row that opens the metric in Full stats. The square never
 *  reshuffles for it.
 *
 *  Hue follows the metric's category, never its state: activity and function
 *  sage, engagement amber, sleep and trajectory lilac, vitals and symptoms
 *  clay. The state is the chip, in words, on the opaque caption. White text
 *  only sits in the dark top band of each gradient (7.1:1 or better).
 *
 *  Each tile is a button that opens Full stats on that metric's card. The
 *  "i" that explains the metric is a SIBLING placed over the tile's top-right
 *  corner — a button inside a button is invalid, and its popover must not
 *  open Full stats underneath itself.
 *
 *  A metric that is still collecting shows the days left as its big figure
 *  ("2 / more days") instead of a dash, and the caption says what has to
 *  arrive; an early read carries the "Early read" chip beside its state. */

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
  glossary,
}: {
  m: CareMetric
  index: number
  wide: boolean
  onOpen: (metricId: string) => void
  glossary: ReturnType<typeof useExplain>['data']
}) {
  const nodata = m.status === 'nodata'
  const tile = careMetricTile(m)
  const when = latestLabel(m.chart)
  const { value, unit } = valueParts(m)
  const countdown = nodata && showsCountdown(m.readiness)
  const line = readinessLine(m.readiness)
  return (
    <div className={`relative flex ${wide ? 'sm:col-span-2' : ''}`}>
      <button
        type="button"
        onClick={() => onOpen(m.id)}
        data-loop
        style={{ '--d': index } as CSSProperties}
        className={`gtile ${GRADIENT[tile.family]} spotlight reveal group/tile min-h-[22rem] w-full cursor-pointer text-left transition-[transform,box-shadow] duration-spring ease-spring hover:-translate-y-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus active:scale-[.985] motion-reduce:transform-none`}
      >
        <span className="gtile-top">
          <span className="min-w-0 pr-9">
            <span className="gtile-kicker block">{m.name}</span>
            {countdown ? (
              <span className="mt-1.5 block">
                <ReadinessValue r={m.readiness!} onTile size="text-[48px] leading-none" />
              </span>
            ) : (
              <span className="gtile-num big-num">
                {value}
                {unit && <small>{unit}</small>}
              </span>
            )}
            {!countdown && m.value_label && (
              <span className="mt-1 block text-label text-white/90">{m.value_label}</span>
            )}
          </span>
          {when && !countdown && (
            <span className="gtile-side shrink-0">
              <b>{when.replace(/^Post-op day /i, 'Day ').replace(/^D(\d+)$/, 'Day $1')}</b>
              latest
            </span>
          )}
        </span>

        <span className="gtile-art">
          {nodata ? (
            <span className="text-copy text-white/90">
              {countdown ? 'Collecting' : 'Not enough data yet'}
            </span>
          ) : (
            <TileArt spec={m.chart} sigma={m.unit === 'σ' ? m.value_num : null} />
          )}
        </span>

        <span className="gtile-cap block">
          <span className="flex items-center justify-between gap-2">
            <span className="flex min-w-0 flex-wrap items-center gap-1.5">
              <span className={`chip ${tileChipClass(m.status)}`}>{statusChipText(m)}</span>
              <EarlyReadChip r={m.readiness} />
            </span>
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
              nodata && line,
              !nodata && m.delta_text,
              m.confidence !== 'high' && <ConfidenceChip level={m.confidence} variant="meta" />,
              m.coverage_text,
              m.guarded && <span className="text-risk-med-ink">{GUARDED_NOTE}</span>,
            ]}
          />
        </span>
        <span className="sr-only">. Open in Full stats</span>
      </button>
      <span className="absolute right-3 top-3 z-[1]">
        <InfoTip entry={explainMetric(glossary, m.id)} onTile placement="bottom-end" />
      </span>
    </div>
  )
}

const TITLE = 'Headline metrics'

/** Slots 0 and 5 are the wide tiles of the 4×2 square. */
const WIDE_SLOTS = new Set([0, 5])

/** The engine's picks outside the six: one compact row per metric, the
 *  state in words, the finding on one line, opening the card in Full stats. */
function AttentionStrip({
  metrics,
  onOpen,
  glossary,
}: {
  metrics: CareMetric[]
  onOpen: (metricId: string) => void
  glossary: ReturnType<typeof useExplain>['data']
}) {
  if (metrics.length === 0) return null
  return (
    <div className="card-group mt-3">
      <div className="flex items-center gap-2 px-4 pb-1 pt-3">
        <Sparkles aria-hidden size={14} className="text-cat-teal-ink" />
        <h3 className="text-[15px] font-medium text-ink">Brought to your attention</h3>
        <span className="meta">outside the six, picked by the engine</span>
      </div>
      <ul className="divide-y divide-hairline">
        {metrics.map((m) => {
          const tile = careMetricTile(m)
          return (
            <li key={m.id} className="relative flex items-center gap-3 px-4 py-2.5">
              <Tile family={tile.family} icon={tile.icon} />
              <button
                type="button"
                onClick={() => onOpen(m.id)}
                className="stretched-link min-w-0 flex-1 text-left"
              >
                <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-copy-lg font-medium text-ink">{m.name}</span>
                  <span className={`chip ${tileChipClass(m.status)}`}>{statusChipText(m)}</span>
                </span>
                <span className="mt-0.5 line-clamp-1 block text-copy text-body">{m.finding}</span>
              </button>
              <span className="above-stretch shrink-0">
                <InfoTip entry={explainMetric(glossary, m.id)} placement="bottom-end" />
              </span>
              <ChevronRight aria-hidden size={16} className="shrink-0 text-secondary" />
            </li>
          )
        })}
      </ul>
    </div>
  )
}

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
  const { data: glossary } = useExplain()

  if (isLoading) {
    return <SkeletonCard lines={5} />
  }

  const byId = new Map((data?.metrics ?? []).map((m) => [m.id, m]))
  const tiles = (data?.headline ?? [])
    .map((id) => byId.get(id))
    .filter((m): m is CareMetric => !!m)
  const attention = (data?.attention ?? [])
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
      {/* 4×2: every tile in a row stretches to the row's height, so the two
          rows close into one rectangle. On narrow screens the wide tiles
          span the two-column grid and the rest stack two across. */}
      <div className="grid auto-rows-fr gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {tiles.map((m, i) => (
          <HeadlineTile
            key={m.id}
            m={m}
            index={i}
            wide={WIDE_SLOTS.has(i)}
            onOpen={onOpen}
            glossary={glossary}
          />
        ))}
      </div>
      <AttentionStrip metrics={attention} onOpen={onOpen} glossary={glossary} />
    </section>
  )
}
