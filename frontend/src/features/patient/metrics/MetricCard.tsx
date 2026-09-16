import type { CareMetric } from '../../../api/care'
import ConfidenceChip from '../../../components/ConfidenceChip'
import { METRIC_STATUS } from '../../../lib/risk'
import CareChart from './CareChart'
import { GUARDED_NOTE, statusChipText, taskKindLabel } from './labels'

/** Full stats card for one care metric. `id="metric-M12"` is the anchor the
 *  headline tiles scroll to (Full stats pulses its outline on arrival). */
export default function MetricCard({ m }: { m: CareMetric }) {
  const s = METRIC_STATUS[m.status] ?? METRIC_STATUS.nodata
  const nodata = m.status === 'nodata'
  return (
    <article
      id={`metric-${m.id}`}
      className="panel relative flex scroll-mt-24 flex-col overflow-hidden p-5 pl-[22px] transition-shadow duration-300"
    >
      <span aria-hidden className={`absolute inset-y-0 left-0 w-[4px] ${s.spine}`} />
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span className="chip bg-soft font-mono tabular-nums text-muted">{m.id}</span>
          <span className="text-copy-lg font-medium text-ink">{m.name}</span>
        </div>
        <span className={`chip shrink-0 ${s.pill}`}>{statusChipText(m)}</span>
      </div>

      <div className="mt-2.5 flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <span className="text-title font-medium tabular-nums text-ink">
          {m.value ?? '—'}
        </span>
        {m.unit && <span className="text-label font-medium text-muted">{m.unit}</span>}
        {m.value_label && <span className="text-label font-medium text-muted">{m.value_label}</span>}
      </div>
      {m.delta_text && <p className="mt-1 text-label font-medium text-muted">{m.delta_text}</p>}

      <div className="mt-3">
        <CareChart spec={m.chart} />
      </div>

      {nodata ? (
        <div className="mt-3">
          <p className="text-copy text-body">{m.unlock ?? m.finding}</p>
          {m.feeds_from_tasks.length > 0 && (
            <div className="mt-2">
              <p className="mb-1.5 text-label font-medium text-muted">What unlocks it</p>
              <div className="flex flex-wrap gap-1.5">
                {m.feeds_from_tasks.map((k) => (
                  <span key={k} className="chip bg-brand-tint text-on-brand-tint">
                    {taskKindLabel(k)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="mt-3 text-copy text-body">{m.finding}</p>
      )}

      {m.next_step && !nodata && (
        <p className="mt-2 flex items-start gap-1.5 text-copy font-medium text-brand-ink">
          <span aria-hidden>→</span> {m.next_step}
        </p>
      )}

      <div className="mt-auto pt-3">
        <div className="border-t border-line pt-2 text-label text-muted">
          {m.method && <p>{m.method}</p>}
          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1">
            {m.inputs.length > 0 && <span>{m.inputs.join(', ')}</span>}
            {m.inputs.length > 0 && m.coverage_text && <span aria-hidden>·</span>}
            {m.coverage_text && <span>{m.coverage_text}</span>}
            <ConfidenceChip level={m.confidence} showHigh />
            {m.guarded && (
              <span className="text-risk-med-ink" title="Guarded metric: the engine phrases it as a signal to review, never a verdict.">
                · {GUARDED_NOTE}
              </span>
            )}
          </p>
        </div>
      </div>
    </article>
  )
}
