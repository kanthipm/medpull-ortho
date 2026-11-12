import { BookOpenText, Layers, Search } from 'lucide-react'
import { useMemo, useState, type CSSProperties } from 'react'
import { useDataCatalog, type CatalogMetric, type DataCatalog } from '../../api/data'
import SectionCard from '../../components/SectionCard'
import Tile from '../../components/Tile'
import { SettingsHero } from '../settings/Switch'
import { TierChip, ViewState } from './DataBits'
import DataNav from './DataNav'
import { FAMILY_GLYPH, sourceName } from './dataFormat'

/** `/data/dictionary` — every metric MedPull stores or computes, with its
 *  unit, where it comes from, how a day's value is formed and how it is
 *  used; the care metrics with what each measures; and the order sources are
 *  preferred in. Built by the server from the code, so it cannot drift from
 *  what the engine does. */

function matches(text: string, ...fields: (string | null | undefined)[]): boolean {
  if (!text) return true
  const needle = text.toLowerCase()
  return fields.some((f) => (f ?? '').toLowerCase().includes(needle))
}

function MetricEntry({ m }: { m: CatalogMetric }) {
  const sources = m.providers.map(sourceName)
  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="text-copy font-medium text-ink">
          {m.label} <span className="meta">{m.unit}</span>
        </p>
        <TierChip tier={m.tier} />
      </div>
      {m.what && <p className="mt-1 text-copy text-ink">{m.what}</p>}
      <p className="meta mt-1">
        {m.aggregation === 'additive' ? 'A day is its total' : 'A day is the mean of its readings'}
        {m.adverse ? ` · a ${m.adverse === 'up' ? 'rise' : 'fall'} is the direction to notice` : ''}
        {m.reference === 'baseline'
          ? ' · read against the person’s own baseline'
          : m.reference
            ? ' · read against the expected recovery curve'
            : ''}
        {m.care_metrics.length > 0 ? ` · feeds ${m.care_metrics.join(', ')}` : ''}
      </p>
      {(m.in_house || m.computed) && m.method && (
        <p className="meta mt-1">
          Computed by MedPull{m.method_version ? ` (${m.method_version})` : ''}: {m.method}
        </p>
      )}
      <p className="meta mt-1">
        {sources.length > 0
          ? `From ${sources.join(', ')}`
          : m.computed
            ? 'Derived each night from the signals above; never stored as a reading'
            : 'Nothing writes this yet'}
        {m.measured_by ? ` · recorded during ${m.measured_by}` : ''}
      </p>
    </li>
  )
}

function Metrics({ catalog, text }: { catalog: DataCatalog; text: string }) {
  const byKey = new Map(catalog.metrics.map((m) => [m.key, m]))
  const families = catalog.families
    .map((f) => ({
      ...f,
      rows: f.metrics
        .map((key) => byKey.get(key))
        .filter((m): m is CatalogMetric => !!m && matches(text, m.label, m.key, m.what, m.method)),
    }))
    .filter((f) => f.rows.length > 0)
  if (families.length === 0) {
    return (
      <SectionCard title="Metrics">
        <p className="text-copy text-secondary">No metric matches “{text}”.</p>
      </SectionCard>
    )
  }
  return (
    <>
      {families.map((f, i) => {
        const glyph = FAMILY_GLYPH[f.key]
        const Icon = glyph?.icon ?? Layers
        return (
          <SectionCard
            key={f.key}
            id={`family-${f.key}`}
            title={f.name}
            icon={<Tile size="sm" family={glyph?.family ?? 'teal'} icon={<Icon />} />}
            aside={`${f.rows.length} ${f.rows.length === 1 ? 'metric' : 'metrics'}`}
            className="rise scroll-mt-24"
            style={{ '--rise-delay': `${60 + i * 40}ms` } as CSSProperties}
          >
            <ul className="divide-y divide-hairline">
              {f.rows.map((m) => (
                <MetricEntry key={m.key} m={m} />
              ))}
            </ul>
          </SectionCard>
        )
      })}
    </>
  )
}

function CareMetrics({ catalog, text }: { catalog: DataCatalog; text: string }) {
  const rows = catalog.care_metrics.filter((m) => matches(text, m.name, m.id, m.what, m.method))
  if (rows.length === 0) return null
  const families = catalog.care_families
    .map((f) => ({ ...f, rows: rows.filter((m) => f.metric_ids.includes(m.id)) }))
    .filter((f) => f.rows.length > 0)
  return (
    <SectionCard
      id="care-metrics"
      title="Care metrics"
      aside={`${rows.length} · version ${catalog.versions.care}`}
      className="scroll-mt-24"
    >
      <div className="space-y-6">
        {families.map((f) => (
          <div key={f.key}>
            <h3 className="micro">{f.name}</h3>
            <ul className="mt-2 divide-y divide-hairline">
              {f.rows.map((m) => (
                <li key={m.id} className="py-3 first:pt-0 last:pb-0">
                  <p className="text-copy font-medium text-ink">
                    {m.name} <span className="meta tabular-nums">{m.id}</span>{' '}
                    <span className="meta">{m.unit}</span>
                  </p>
                  {m.what && <p className="mt-1 text-copy text-ink">{m.what}</p>}
                  {m.method && <p className="meta mt-1">How: {m.method}</p>}
                  {m.inputs_text && <p className="meta mt-1">Reads: {m.inputs_text}</p>}
                  {m.guarded && <p className="meta mt-1">Shown for review; never a diagnosis.</p>}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </SectionCard>
  )
}

function Sources({ catalog }: { catalog: DataCatalog }) {
  return (
    <SectionCard id="sources" title="Sources, in the order they are preferred" className="scroll-mt-24">
      <p className="text-copy text-ink">{catalog.precedence.rule}</p>
      <ol className="mt-4 space-y-3">
        {catalog.precedence.ranks.map((rank) => (
          <li key={rank.rank} className="flex gap-3">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-pill bg-soft text-label tabular-nums text-ink">
              {rank.rank + 1}
            </span>
            <span className="min-w-0">
              <span className="block text-copy font-medium text-ink">{rank.label}</span>
              <span className="meta block">
                {catalog.sources
                  .filter((s) => s.rank === rank.rank)
                  .map((s) => s.name)
                  .join(', ')}
              </span>
            </span>
          </li>
        ))}
      </ol>
      <p className="meta mt-4">
        {catalog.aggregation.mean} {catalog.aggregation.additive}
      </p>
    </SectionCard>
  )
}

export default function DataDictionaryPage() {
  const catalog = useDataCatalog()
  const [text, setText] = useState('')
  const query = text.trim()
  const anchors = useMemo(
    () => [
      ...(catalog.data?.families.filter((f) => f.metrics.length > 0) ?? []).map((f) => ({
        href: `#family-${f.key}`,
        label: FAMILY_GLYPH[f.key]?.short ?? f.name,
      })),
      { href: '#care-metrics', label: 'Care metrics' },
      { href: '#sources', label: 'Sources' },
    ],
    [catalog.data],
  )

  return (
    <div className="pb-10">
      <SettingsHero nav={<DataNav />} icon={<BookOpenText />} title="Dictionary">
        Every metric MedPull stores or computes: its unit, where it comes from, how a day’s value is
        formed, and how it is used.
      </SettingsHero>

      <div className="mt-10 space-y-stack">
        <ViewState
          loading={catalog.isLoading}
          error={catalog.isError}
          onRetry={() => void catalog.refetch()}
          what="The dictionary"
        >
          {catalog.data && (
            <>
              <div className="panel flex flex-wrap items-center gap-3 px-4 py-3">
                <label className="flex min-w-[14rem] flex-1 items-center gap-2">
                  <Search aria-hidden size={16} className="shrink-0 text-secondary" />
                  <span className="sr-only">Find a metric</span>
                  <input
                    type="search"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    placeholder="Find a metric"
                    className="h-9 min-w-0 flex-1 bg-transparent text-copy-lg text-ink placeholder:text-secondary focus:outline-none"
                  />
                </label>
                <nav aria-label="Jump to" className="flex flex-wrap gap-x-3 gap-y-1">
                  {anchors.map((a) => (
                    <a key={a.href} href={a.href} className="text-label text-body underline-offset-2 hover:underline">
                      {a.label}
                    </a>
                  ))}
                </nav>
              </div>
              <Metrics catalog={catalog.data} text={query} />
              <CareMetrics catalog={catalog.data} text={query} />
              {!query && <Sources catalog={catalog.data} />}
              <p className="meta px-1">
                Engine {catalog.data.versions.engine} · care metrics {catalog.data.versions.care} ·
                mobility {catalog.data.versions.mobility}
              </p>
            </>
          )}
        </ViewState>
      </div>
    </div>
  )
}
