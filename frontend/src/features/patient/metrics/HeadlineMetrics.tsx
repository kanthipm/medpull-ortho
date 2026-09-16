import type { CareMetric } from '../../../api/care'
import { useCareMetrics } from '../../../api/care'
import ConfidenceChip from '../../../components/ConfidenceChip'
import { RefreshOverlay, SkeletonCard } from '../../../components/Skeleton'
import { METRIC_STATUS } from '../../../lib/risk'
import { MiniChart } from './CareChart'
import { GUARDED_NOTE, statusChipText } from './labels'

/** The three headline tiles above Full stats — the pathway's priority picks
 *  (the API has already chosen applicable ones). Each tile is a button that
 *  opens Full stats on that metric's card. */

function HeadlineTile({ m, onOpen }: { m: CareMetric; onOpen: (metricId: string) => void }) {
  const s = METRIC_STATUS[m.status] ?? METRIC_STATUS.nodata
  const nodata = m.status === 'nodata'
  return (
    <button
      type="button"
      onClick={() => onOpen(m.id)}
      aria-label={`${m.name}: open in Full stats`}
      className="panel border-line-strong group relative flex h-full w-full cursor-pointer flex-col overflow-hidden p-5 pl-[22px] text-left transition-[background-color] duration-150 hover:bg-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
    >
      <span aria-hidden className={`absolute inset-y-0 left-0 w-[2px] ${s.spine}`} />
      <span className="flex items-start justify-between gap-2">
        <span className="text-copy-lg font-medium text-ink">{m.name}</span>
        <span className={`chip shrink-0 ${s.pill}`}>{statusChipText(m)}</span>
      </span>

      <span className="mt-2.5 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className="font-mono text-title font-medium tabular-nums text-ink">
          {m.value ?? '—'}
        </span>
        {m.unit && <span className="text-label font-medium text-muted">{m.unit}</span>}
      </span>
      {m.value_label && <span className="mt-1 block text-label font-medium text-muted">{m.value_label}</span>}
      {m.delta_text && (
        <span className="mt-1 block text-label font-medium text-muted">{m.delta_text}</span>
      )}

      <span className="mt-2 line-clamp-3 text-copy text-body">
        {nodata ? (m.unlock ?? m.finding) : m.finding}
      </span>

      <span className="mt-2.5 block">
        <MiniChart spec={m.chart} />
      </span>

      <span className="mt-auto flex flex-wrap items-center gap-x-1.5 gap-y-1 border-t border-line pt-2 text-label text-muted">
        <ConfidenceChip level={m.confidence} showHigh />
        {m.coverage_text && <span>{m.coverage_text}</span>}
        {m.guarded && <span className="text-risk-med-ink">· {GUARDED_NOTE}</span>}
      </span>
    </button>
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

  if (isLoading) {
    return (
      <div className="grid gap-3 sm:grid-cols-3">
        <SkeletonCard lines={5} />
        <SkeletonCard lines={5} />
        <SkeletonCard lines={5} />
      </div>
    )
  }

  const byId = new Map((data?.metrics ?? []).map((m) => [m.id, m]))
  const tiles = (data?.headline ?? [])
    .map((id) => byId.get(id))
    .filter((m): m is CareMetric => !!m)

  if (isError || tiles.length === 0) {
    return (
      <div className="panel px-5 py-4">
        <p className="text-label font-medium text-muted">
          {isError
            ? 'Care metrics are not available for this patient yet.'
            : 'No headline metrics for this pathway yet — Full stats lists every metric and what unlocks it.'}
        </p>
      </div>
    )
  }

  return (
    <div className="relative">
      <RefreshOverlay show={refreshing} />
      <div className="grid gap-3 sm:grid-cols-3">
        {tiles.map((m) => (
          <HeadlineTile key={m.id} m={m} onOpen={onOpen} />
        ))}
      </div>
    </div>
  )
}
