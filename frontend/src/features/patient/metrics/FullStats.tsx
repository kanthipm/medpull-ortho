import { ChevronRight } from 'lucide-react'
import { useEffect, useId, useState } from 'react'
import type { CSSProperties } from 'react'
import type { CareMetric, CareMetricsResponse } from '../../../api/care'
import { useCareMetrics } from '../../../api/care'
import { usePatientMetrics } from '../../../api/queries'
import Disclosure from '../../../components/Disclosure'
import SectionCard from '../../../components/SectionCard'
import SegmentedControl from '../../../components/SegmentedControl'
import { RefreshOverlay, SkeletonCard } from '../../../components/Skeleton'
import Tile from '../../../components/Tile'
import MetricCard from './MetricCard'
import { familyTile } from './metricTiles'
import RawDataTable from './RawDataTable'
import SignalsBody from './SignalsBody'

/** "Full stats" — the expandable zone under the headline tiles. Open state
 *  and the focused metric are owned by the page so a tile can open it and
 *  land on its card. Tabs: Metrics (the care catalog by family), Signals
 *  (the former Supporting signals body, still lazy), Raw data. */

type Tab = 'metrics' | 'signals' | 'raw'
const TABS = [
  { key: 'metrics' as const, label: 'Metrics' },
  { key: 'signals' as const, label: 'Signals' },
  { key: 'raw' as const, label: 'Raw data' },
]

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

function MetricsTab({ data, refreshing }: { data: CareMetricsResponse; refreshing: boolean }) {
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

export default function FullStats({
  patientId,
  refreshing,
  open,
  onOpenChange,
  focusMetricId,
  onFocusHandled,
}: {
  patientId: string
  refreshing: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Metric id to scroll to on the Metrics tab; the page sets it when a
   *  headline tile is clicked and clears it via `onFocusHandled`. */
  focusMetricId: string | null
  onFocusHandled?: () => void
}) {
  const [tab, setTab] = useState<Tab>('metrics')
  // A new focus request lands on the Metrics tab — adjusted during render
  // (the prev-prop pattern) rather than in an effect, so there is no
  // intermediate paint of the wrong tab.
  const [prevFocus, setPrevFocus] = useState<string | null>(null)
  if (focusMetricId !== prevFocus) {
    setPrevFocus(focusMetricId)
    if (focusMetricId) setTab('metrics')
  }
  const care = useCareMetrics(patientId)
  // lazy on purpose: the Signals payload is the old full-detail request
  const signals = usePatientMetrics(patientId, open && tab === 'signals')

  // Scroll to the focused card and pulse its outline. The pulse is a direct
  // DOM touch (the effect's job), not React state, and clears itself.
  useEffect(() => {
    if (!focusMetricId || !open || tab !== 'metrics' || !care.data) return
    const el = document.getElementById(`metric-${focusMetricId}`)
    if (!el) return
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.style.boxShadow = '0 0 0 3px rgb(var(--focus))'
    window.setTimeout(() => {
      el.style.boxShadow = ''
    }, 1800)
    onFocusHandled?.()
  }, [focusMetricId, open, tab, care.data, onFocusHandled])

  const applicable = care.data?.metrics.filter((m) => m.applicable !== false) ?? []
  const flagged = applicable.filter((m) => m.status === 'flag').length
  const regionId = useId()
  const hint = care.data
    ? `${applicable.length} metrics · ${flagged} flagged · signals · raw data`
    : 'Metrics · signals · raw data'

  return (
    <div>
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        aria-expanded={open}
        aria-controls={open ? regionId : undefined}
        className="-mx-2 flex min-h-11 w-[calc(100%+1rem)] cursor-pointer items-center gap-2.5 rounded-control px-2 text-left transition-colors duration-state ease-apple hover:bg-panel focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        <span className="text-lede font-semibold text-ink">Full stats</span>
        <span className="meta min-w-0 flex-1 truncate">{hint}</span>
        <ChevronRight
          aria-hidden
          size={18}
          className={`shrink-0 text-secondary transition-transform duration-state ease-apple motion-reduce:transition-none ${open ? 'rotate-90' : ''}`}
        />
      </button>

      {open && (
        <div id={regionId} className="rise mt-2" style={{ '--rise-delay': '0ms' } as CSSProperties}>
          <SegmentedControl<Tab>
            options={TABS}
            value={tab}
            onChange={setTab}
            aria-label="Full stats view"
            className="mb-stack"
          />

          {tab === 'metrics' && (
            <>
              {care.isLoading && <SkeletonCard lines={4} />}
              {care.isError && (
                <p className="text-copy text-secondary">
                  Care metrics are not available for this patient yet.
                </p>
              )}
              {care.data && (
                <MetricsTab data={care.data} refreshing={refreshing} />
              )}
            </>
          )}

          {tab === 'signals' && (
            <>
              {signals.isLoading && <SkeletonCard lines={4} />}
              {signals.isError && (
                <p className="text-copy text-secondary">Signals could not be loaded.</p>
              )}
              {signals.data && <SignalsBody data={signals.data} refreshing={refreshing} />}
            </>
          )}

          {tab === 'raw' && (
            <RawDataTable patientId={patientId} enabled={open && tab === 'raw'} refreshing={refreshing} />
          )}
        </div>
      )}
    </div>
  )
}
