import type { CSSProperties } from 'react'
import type { CareMetric, CareMetricsResponse } from '../../../api/care'
import Disclosure from '../../../components/Disclosure'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay } from '../../../components/Skeleton'
import Tile from '../../../components/Tile'
import MetricCard from './MetricCard'
import { familyTile } from './metricTiles'

/** The care catalog for one chart, by family: every applicable metric as a
 *  card with its value, chart, finding, method and inputs, and the ones this
 *  pathway does not use folded away at the end. Rendered by the Data tab's
 *  "Care metrics" view. */

type Family = { key: string; name: string; templates: string[]; metrics: CareMetric[] }

/** Families in API order, each holding only its applicable metrics; metrics
 *  the families skip land in an "Other" family; `applicable === false` ones
 *  go to the collapsed tail. */
function groupMetrics(data: CareMetricsResponse) {
  const byId = new Map(data.metrics.map((m) => [m.id, m]))
  const placed = new Set<string>()
  const families: Family[] = data.families.map((f) => {
    const metrics = f.metric_ids
      .map((id) => byId.get(id))
      .filter((m): m is CareMetric => !!m && m.applicable !== false)
    for (const m of metrics) placed.add(m.id)
    return { key: f.key, name: f.name, templates: templatesOf(metrics), metrics }
  })
  const orphans = data.metrics.filter((m) => !placed.has(m.id) && m.applicable !== false)
  if (orphans.length > 0) {
    families.push({ key: 'other', name: 'Other metrics', templates: templatesOf(orphans), metrics: orphans })
  }
  const notApplicable = data.metrics.filter((m) => m.applicable === false)
  return { families: families.filter((f) => f.metrics.length > 0), notApplicable }
}

function templatesOf(metrics: CareMetric[]): string[] {
  return [...new Set(metrics.map((m) => m.template).filter(Boolean))]
}

export default function MetricsTab({ data, refreshing }: { data: CareMetricsResponse; refreshing: boolean }) {
  const { families, notApplicable } = groupMetrics(data)
  return (
    <div className="space-y-stack">
      {families.map((f) => {
        const tile = familyTile(f.key)
        const flagged = f.metrics.filter((m) => m.status === 'flag').length
        // Templates are neutral metadata: a .meta line, not chips.
        const aside = [
          `${f.metrics.length} metric${f.metrics.length === 1 ? '' : 's'}`,
          flagged > 0 ? `${flagged} flagged` : null,
          ...f.templates,
        ]
          .filter(Boolean)
          .join(' · ')
        return (
          <SectionCard
            key={f.key}
            title={f.name}
            icon={<Tile size="sm" family={tile.family} icon={tile.icon} />}
            aside={aside}
          >
            <RefreshOverlay show={refreshing} />
            <div className="grid gap-3 sm:grid-cols-2">
              {f.metrics.map((m) => (
                <MetricCard key={m.id} m={m} />
              ))}
            </div>
          </SectionCard>
        )
      })}

      {notApplicable.length > 0 && (
        <SectionCard>
          <Disclosure
            label="Not used on this pathway"
            hint={`${notApplicable.length} metric${notApplicable.length === 1 ? '' : 's'}`}
          >
            <ul className="card-group mt-1 bg-soft" style={{ '--row-inset': '16px' } as CSSProperties}>
              {notApplicable.map((m) => (
                <li
                  key={m.id}
                  id={`metric-${m.id}`}
                  className="scroll-mt-24 px-4 py-2.5 transition-shadow duration-300"
                >
                  <p className="text-copy font-medium text-ink">
                    {m.name} <span className="meta tabular-nums">{m.id}</span>
                  </p>
                  <p className="meta">
                    {m.status_text || 'Not used on this pathway'}
                    {m.domains.length > 0 && <> · {m.domains.join(', ')}</>}
                  </p>
                </li>
              ))}
            </ul>
          </Disclosure>
        </SectionCard>
      )}
    </div>
  )
}
