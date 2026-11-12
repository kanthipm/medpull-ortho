import { ArrowDownAZ, ChevronRight, Database, Layers, Table2 } from 'lucide-react'
import { useMemo, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import {
  useDataCatalog,
  useDataCoverage,
  type CoveragePatient,
  type DataCatalog,
  type DataCoverage,
} from '../../api/data'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import PriorityBadge from '../../components/PriorityBadge'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import Tile from '../../components/Tile'
import { PRIORITY } from '../../lib/risk'
import { SettingsHero } from '../settings/Switch'
import { DaysMeter, ViewState } from './DataBits'
import DataNav from './DataNav'
import { FAMILY_GLYPH, FAMILY_VIEW, TIERS, dayAge, sourceName } from './dataFormat'

/** `/data` — the Clinic version's Data tab, roster first: what is collected
 *  for every chart this console lists, family by family, with the five tiers
 *  the data moves through named once at the top. A row opens the chart's own
 *  data; a cell opens it at that family. The roster is whatever the console
 *  lists: one clinic's when the workspace menu has picked one. */

type Window = '7' | '30' | '90'
type Sort = 'name' | 'tier' | 'coverage'

const WINDOWS: { key: Window; label: string }[] = [
  { key: '7', label: '7 days' },
  { key: '30', label: '30 days' },
  { key: '90', label: '90 days' },
]

const SORTS: { key: Sort; label: string }[] = [
  { key: 'tier', label: 'By tier' },
  { key: 'coverage', label: 'By coverage' },
  { key: 'name', label: 'By name' },
]

function coverageOf(p: CoveragePatient): number {
  return Object.values(p.cells).reduce((sum, cell) => sum + cell.days, 0)
}

function sorted(patients: CoveragePatient[], sort: Sort): CoveragePatient[] {
  const rows = [...patients]
  if (sort === 'name') return rows.sort((a, b) => a.name.localeCompare(b.name))
  if (sort === 'coverage') return rows.sort((a, b) => coverageOf(b) - coverageOf(a))
  const order = (p: CoveragePatient) => (p.risk_level ? PRIORITY[p.risk_level].order : 9)
  return rows.sort((a, b) => order(a) - order(b) || a.name.localeCompare(b.name))
}

/** The five tiers as a pipeline, each with what this roster holds of it. */
function TierStrip({ coverage, catalog }: { coverage: DataCoverage; catalog: DataCatalog | undefined }) {
  const sources = new Set<string>()
  let readings = 0
  for (const p of coverage.patients) {
    for (const cell of Object.values(p.cells)) {
      readings += cell.rows
      cell.sources.forEach((s) => sources.add(s))
    }
  }
  const signals = catalog?.metrics.filter((m) => m.tier === 'scored' || m.tier === 'display').length
  const inHouse = catalog?.metrics.filter((m) => m.in_house || m.computed).length
  const counts: Record<string, string> = {
    sources: `${sources.size} ${sources.size === 1 ? 'source' : 'sources'}`,
    raw: `${readings.toLocaleString()} readings`,
    signals: signals == null ? 'Daily signals' : `${signals} signals`,
    medpull: inHouse == null ? 'MedPull metrics' : `${inHouse} metrics`,
    care: catalog ? `${catalog.care_metrics.length} care metrics` : 'Care metrics',
  }
  return (
    <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" aria-label="How the data is organised">
      {TIERS.map((tier, i) => (
        <li
          key={tier.key}
          className="rise panel relative flex flex-col px-4 py-4"
          style={{ '--rise-delay': `${60 + i * 45}ms` } as CSSProperties}
        >
          <span className="micro">Tier {tier.step}</span>
          <span className="mt-1 text-copy-lg font-medium text-ink">{tier.name}</span>
          <span className="mt-1 text-copy tabular-nums text-ink">{counts[tier.key]}</span>
          <span className="mt-2 text-label text-secondary">{tier.line}</span>
          {i < TIERS.length - 1 && (
            <ChevronRight
              aria-hidden
              size={16}
              className="absolute -right-[13px] top-1/2 z-10 hidden -translate-y-1/2 text-secondary lg:block"
            />
          )}
        </li>
      ))}
    </ol>
  )
}

function Cell({
  patient,
  family,
  coverage,
}: {
  patient: CoveragePatient
  family: string
  coverage: DataCoverage
}) {
  const cell = patient.cells[family]
  if (!cell || cell.days === 0) {
    return <span className="text-copy text-secondary">—</span>
  }
  const names = cell.sources.map(sourceName).join(', ')
  return (
    <Link
      to={`/data/patients/${encodeURIComponent(patient.id)}?view=${FAMILY_VIEW[family] ?? 'raw'}`}
      className="group -mx-1.5 inline-flex flex-col rounded-control-sm px-1.5 py-1 hover:bg-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"
      title={`${cell.days} of ${coverage.days} days · ${cell.rows.toLocaleString()} readings · ${names}`}
    >
      <DaysMeter days={cell.days} of={coverage.days} />
      <span className="meta mt-0.5 whitespace-nowrap">{dayAge(cell.last, coverage.as_of)}</span>
    </Link>
  )
}

function PatientCell({ patient }: { patient: CoveragePatient }) {
  return (
    <Link
      to={`/data/patients/${encodeURIComponent(patient.id)}`}
      className="group flex min-w-0 items-center gap-3 rounded-control-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
    >
      <Avatar name={patient.name} tier={patient.risk_level ?? undefined} />
      <span className="min-w-0">
        <span className="block truncate text-copy font-medium text-ink group-hover:underline">
          {patient.name}
        </span>
        <span className="meta block truncate">
          {patient.device
            ? `${sourceName(patient.device.provider)}${patient.device.model ? ` · ${patient.device.model}` : ''}`
            : 'Followed by check-in, no device'}
        </span>
      </span>
    </Link>
  )
}

function CoverageTable({ coverage, patients }: { coverage: DataCoverage; patients: CoveragePatient[] }) {
  return (
    <div className="hidden overflow-x-auto lg:block">
      <table className="w-full min-w-[980px] border-separate border-spacing-0 text-left">
        <caption className="sr-only">
          Days with data in the last {coverage.days} days, by chart and by kind of data
        </caption>
        <thead>
          <tr>
            <th scope="col" className="px-4 pb-2 pt-3 text-label font-medium text-secondary">
              Chart
            </th>
            {coverage.families.map((f) => {
              const glyph = FAMILY_GLYPH[f.key]
              const Icon = glyph?.icon
              return (
                <th key={f.key} scope="col" className="px-3 pb-2 pt-3 text-label font-medium text-secondary">
                  <span className="inline-flex items-center gap-1.5" title={f.name}>
                    {Icon && <Icon aria-hidden size={14} />}
                    {glyph?.short ?? f.name}
                  </span>
                </th>
              )
            })}
            <th scope="col" className="px-3 pb-2 pt-3 text-label font-medium text-secondary">
              Check-ins
            </th>
            <th scope="col" className="px-4 pb-2 pt-3 text-label font-medium text-secondary">
              Read
            </th>
          </tr>
        </thead>
        <tbody>
          {patients.map((p) => (
            <tr key={p.id} className="align-middle">
              <th scope="row" className="max-w-[260px] border-t border-hairline px-4 py-3 font-normal">
                <PatientCell patient={p} />
              </th>
              {coverage.families.map((f) => (
                <td key={f.key} className="border-t border-hairline px-3 py-2">
                  <Cell patient={p} family={f.key} coverage={coverage} />
                </td>
              ))}
              <td className="border-t border-hairline px-3 py-2">
                {p.checkins.count > 0 ? (
                  <span className="text-copy tabular-nums text-ink">{p.checkins.count}</span>
                ) : (
                  <span className="text-copy text-secondary">—</span>
                )}
              </td>
              <td className="border-t border-hairline px-4 py-2">
                {p.risk_level ? <PriorityBadge priority={p.risk_level} /> : <span className="meta">Not read yet</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Under 1024px the table becomes one card per chart. */
function CoverageCards({ coverage, patients }: { coverage: DataCoverage; patients: CoveragePatient[] }) {
  return (
    <ul className="divide-y divide-hairline lg:hidden">
      {patients.map((p) => {
        const filled = coverage.families.filter((f) => (p.cells[f.key]?.days ?? 0) > 0)
        return (
          <li key={p.id} className="px-4 py-4">
            <div className="flex items-start justify-between gap-3">
              <PatientCell patient={p} />
              {p.risk_level && <PriorityBadge priority={p.risk_level} className="shrink-0" />}
            </div>
            {filled.length === 0 ? (
              <p className="meta mt-3">Nothing collected in this window.</p>
            ) : (
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-4">
                {filled.map((f) => (
                  <div key={f.key} className="min-w-0">
                    <dt className="meta truncate">{FAMILY_GLYPH[f.key]?.short ?? f.name}</dt>
                    <dd>
                      <Cell patient={p} family={f.key} coverage={coverage} />
                    </dd>
                  </div>
                ))}
              </dl>
            )}
          </li>
        )
      })}
    </ul>
  )
}

export default function DataRosterPage() {
  const [window, setWindow] = useState<Window>('30')
  const [sort, setSort] = useState<Sort>('tier')
  const coverage = useDataCoverage(Number(window))
  const catalog = useDataCatalog()
  const patients = useMemo(
    () => (coverage.data ? sorted(coverage.data.patients, sort) : []),
    [coverage.data, sort],
  )

  return (
    <div className="pb-10">
      <SettingsHero
        nav={<DataNav />}
        icon={<Database />}
        title="Data"
        decor={[<Database key="d" />, <Layers key="l" />, <Table2 key="t" />]}
      >
        Everything collected for this roster, from the raw reading to what was computed from it,
        and where each number came from.
      </SettingsHero>

      <div className="mt-10 space-y-stack">
        <ViewState
          loading={coverage.isLoading}
          error={coverage.isError}
          onRetry={() => void coverage.refetch()}
          what="The roster’s data"
        >
          {coverage.data && coverage.data.patients.length === 0 && (
            <EmptyState icon={<Table2 />} family="teal" title="No charts on this roster yet">
              Once a clinic has charts, what each one collects appears here by kind of data.
            </EmptyState>
          )}
          {coverage.data && coverage.data.patients.length > 0 && (
            <>
              <TierStrip coverage={coverage.data} catalog={catalog.data} />
              <SectionCard
                flush
                title="Coverage by chart"
                icon={<Tile size="sm" family="teal" icon={<Table2 />} />}
                aside={`${patients.length} ${patients.length === 1 ? 'chart' : 'charts'} · days with data out of ${coverage.data.days}`}
                className="rise"
                style={{ '--rise-delay': '320ms' } as CSSProperties}
              >
                <div className="flex flex-wrap items-center justify-between gap-3 px-4 pb-3 pt-1">
                  <SegmentedControl<Window>
                    options={WINDOWS}
                    value={window}
                    onChange={setWindow}
                    size="sm"
                    role="radiogroup"
                    aria-label="Window"
                  />
                  <span className="inline-flex items-center gap-2">
                    <ArrowDownAZ aria-hidden size={16} className="text-secondary" />
                    <SegmentedControl<Sort>
                      options={SORTS}
                      value={sort}
                      onChange={setSort}
                      size="sm"
                      role="radiogroup"
                      aria-label="Order"
                    />
                  </span>
                </div>
                <CoverageTable coverage={coverage.data} patients={patients} />
                <CoverageCards coverage={coverage.data} patients={patients} />
              </SectionCard>
              <p className="meta px-1">
                A bar is the number of days in the window with at least one reading of that kind.
                Open a chart for its sources, every raw reading, the daily signals against the
                person’s own baseline, what MedPull computes itself, and the care metrics.
              </p>
            </>
          )}
        </ViewState>
      </div>
    </div>
  )
}
