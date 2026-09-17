import type { CareMetric } from '../../../api/care'
import ConfidenceChip from '../../../components/ConfidenceChip'
import Tile from '../../../components/Tile'
import DotLine from '../DotLine'
import CareChart from './CareChart'
import { latestLabel } from './chartText'
import { GUARDED_NOTE, statusChipText, taskKindLabel, tileChipClass } from './labels'
import { careMetricTile } from './metricTiles'

/* ════════════════════════════════════════════════════════════════════════
   METRIC TILES — the app's "Your portfolio" tiles, at console size.

   A soft filled tile (--soft, 12px corners) inside a white card: category
   Tile + name, the state chip, a large tabular value with its unit, and a
   date line. Every text pair was computed on --soft (light / dark):
     ink       16.202 / 16.060     value, name
     body       6.367 /  6.211     finding
     muted      4.755 /  4.582     .meta / text-secondary
     brand-ink  5.066 /  6.336     next step
     risk-med   5.127 /  9.005     guarded note
   The chip carries its own opaque tint, so the clinical state never sits on
   a wash. The CHART sits in an opaque --panel well (rounded-control-sm), which
   is where the chart tokens were measured: s1 4.602 / 6.783, ref line
   5.393 / 3.631, axis 5.393 / 4.906. On bare --soft the dark ref line
   (3.392) and the heat grid's seq-3 step would sit closer to the 3:1 floor,
   so the well is load-bearing, not decoration.

   One exception to "chip from METRIC_STATUS": light --risk-missing-tint IS
   --soft, so a "Needs data" chip would lose its capsule on the tile. On a
   soft tile it is drawn panel-filled instead (missing ink on panel 7.222 /
   6.650).
   ════════════════════════════════════════════════════════════════════════ */

/** Full stats tile for one care metric. `id="metric-M12"` is the anchor the
 *  headline tiles scroll to (Full stats rings it on arrival). */
export default function MetricCard({ m }: { m: CareMetric }) {
  const nodata = m.status === 'nodata'
  const tile = careMetricTile(m)
  const when = latestLabel(m.chart)
  const valueId = `metric-${m.id}-name`
  return (
    <article
      id={`metric-${m.id}`}
      aria-labelledby={valueId}
      className="flex scroll-mt-24 flex-col rounded-control bg-soft p-4 transition-shadow duration-300"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <Tile family={tile.family} icon={tile.icon} />
          <div className="min-w-0">
            <h4 id={valueId} className="text-copy-lg font-medium text-ink">
              {m.name}
            </h4>
            <p className="meta tabular-nums">{m.id}</p>
          </div>
        </div>
        <span className={`chip shrink-0 ${tileChipClass(m.status)}`}>{statusChipText(m)}</span>
      </div>

      <p className="mt-3 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className="text-title font-medium tabular-nums text-ink">{m.value ?? '—'}</span>
        {m.unit && <span className="text-copy text-secondary">{m.unit}</span>}
        {m.value_label && <span className="text-copy text-secondary">{m.value_label}</span>}
      </p>
      <DotLine as="p" className="meta mt-0.5" parts={[when, m.delta_text]} />

      <div className="mt-3 rounded-control-sm bg-panel p-2">
        <CareChart spec={m.chart} sigma={m.unit === 'σ' ? m.value_num : null} />
      </div>

      {nodata ? (
        <div className="mt-3">
          <p className="text-copy text-body">{m.unlock ?? m.finding}</p>
          {m.feeds_from_tasks.length > 0 && (
            <div className="mt-2.5">
              <p className="meta mb-1.5">What unlocks it</p>
              <ul className="flex flex-wrap gap-1.5">
                {m.feeds_from_tasks.map((k) => (
                  <li key={k} className="chip bg-brand-tint text-on-brand-tint">
                    {taskKindLabel(k)}
                  </li>
                ))}
              </ul>
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

      <div className="mt-auto space-y-1 pt-3">
        {m.method && <p className="meta">{m.method}</p>}
        <DotLine
          as="p"
          className="meta"
          parts={[
            m.inputs.length > 0 && m.inputs.join(', '),
            m.coverage_text,
            m.confidence !== 'high' && <ConfidenceChip level={m.confidence} variant="meta" />,
            m.guarded && (
              <span
                className="text-risk-med-ink"
                title="Guarded metric: the engine phrases it as a signal to review, never a verdict."
              >
                {GUARDED_NOTE}
              </span>
            ),
          ]}
        />
      </div>
    </article>
  )
}
