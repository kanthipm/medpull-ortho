import { ArrowUpRight, ChevronLeft, ChevronRight, Database } from 'lucide-react'
import type { CSSProperties } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useDataCoverage, useDataSummary } from '../../api/data'
import Avatar from '../../components/Avatar'
import EmptyState from '../../components/EmptyState'
import PriorityBadge from '../../components/PriorityBadge'
import SegmentedControl from '../../components/SegmentedControl'
import { PRIORITY } from '../../lib/risk'
import { ViewState } from './DataBits'
import { VIEWS, isDataView, sourceName, type DataView } from './dataFormat'
import CareView from './views/CareView'
import MedPullView from './views/MedPullView'
import RawView from './views/RawView'
import ReportedView from './views/ReportedView'
import SignalsView from './views/SignalsView'
import SleepView from './views/SleepView'
import SourcesView from './views/SourcesView'

/** `/data/patients/:id` — one chart's data, tier by tier. The view is in the
 *  address (`?view=`), so any of them can be linked to; the roster's cells
 *  land on the view their family belongs to. Previous and next walk the
 *  roster in the order the Data tab lists it. */
export default function DataPatientPage() {
  const { id = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const requested = params.get('view')
  const view: DataView = isDataView(requested) ? requested : 'sources'
  const summary = useDataSummary(id)
  const roster = useDataCoverage(30)

  const order = [...(roster.data?.patients ?? [])].sort((a, b) => {
    const rank = (level: typeof a.risk_level) => (level ? PRIORITY[level].order : 9)
    return rank(a.risk_level) - rank(b.risk_level) || a.name.localeCompare(b.name)
  })
  const at = order.findIndex((p) => p.id === id)
  const previous = at > 0 ? order[at - 1] : null
  const next = at >= 0 && at < order.length - 1 ? order[at + 1] : null
  const to = (pid: string) => `/data/patients/${encodeURIComponent(pid)}?view=${view}`

  const patient = summary.data?.patient
  const assessment = summary.data?.assessment
  const devices = summary.data?.devices ?? []

  return (
    <div className="pb-10">
      <header data-hero className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link to="/data" className="btn-plain btn-sm -ml-3">
            <ChevronLeft aria-hidden size={16} /> Roster
          </Link>
          <div className="flex items-center gap-1">
            {previous ? (
              <Link to={to(previous.id)} className="btn-plain btn-sm" aria-label={`Previous: ${previous.name}`}>
                <ChevronLeft aria-hidden size={16} /> <span className="hidden sm:inline">{previous.name}</span>
              </Link>
            ) : null}
            {next ? (
              <Link to={to(next.id)} className="btn-plain btn-sm" aria-label={`Next: ${next.name}`}>
                <span className="hidden sm:inline">{next.name}</span> <ChevronRight aria-hidden size={16} />
              </Link>
            ) : null}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-4">
          {patient && <Avatar name={patient.name} tier={assessment?.risk.level} size="lg" />}
          <div className="min-w-0">
            <p className="micro inline-flex items-center gap-1.5">
              <Database aria-hidden size={12} /> Data
            </p>
            <h1 className="display-title mt-1 text-section text-ink">{patient?.name ?? 'Chart data'}</h1>
          </div>
        </div>
        {patient && (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
            {assessment && <PriorityBadge priority={assessment.risk.level} />}
            <span className="text-copy-lg text-body">
              {patient.pathway}
              {patient.mode === 'recovery' ? ` · day ${patient.postop_day}` : ''}
              {patient.hospital ? ` · ${patient.hospital.name}` : ''}
            </span>
          </div>
        )}
        {patient && (
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1">
            <span className="meta">
              {devices.length > 0
                ? devices.map((d) => d.model ?? sourceName(d.provider)).join(' · ')
                : 'No device: followed by check-in'}
            </span>
            <Link to={`/patients/${encodeURIComponent(patient.id)}`} className="btn-plain btn-sm">
              Open chart <ArrowUpRight aria-hidden size={14} />
            </Link>
          </div>
        )}

        <div className="mt-6 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <SegmentedControl<DataView>
            options={VIEWS}
            value={view}
            onChange={(key) => setParams(key === 'sources' ? {} : { view: key }, { replace: true })}
            tone="glass"
            size="sm"
            aria-label="What to show"
          />
        </div>
      </header>

      <div className="mt-8">
        <ViewState
          loading={summary.isLoading}
          error={summary.isError && !summary.data}
          onRetry={() => void summary.refetch()}
          what="This chart’s data"
        >
          {!summary.data ? (
            <EmptyState
              title="No chart with that id on this roster"
              action={
                <Link to="/data" className="btn-tinted">
                  Back to the roster
                </Link>
              }
            >
              It may belong to another clinic, or the link may be old.
            </EmptyState>
          ) : (
            <>
              {view === 'sources' && <SourcesView summary={summary.data} />}
              {view === 'raw' && <RawView patientId={id} />}
              {view === 'signals' && <SignalsView patientId={id} summary={summary.data} />}
              {view === 'medpull' && <MedPullView patientId={id} summary={summary.data} />}
              {view === 'care' && <CareView patientId={id} summary={summary.data} />}
              {view === 'sleep' && <SleepView patientId={id} />}
              {view === 'reported' && <ReportedView patientId={id} />}
            </>
          )}
        </ViewState>
      </div>
    </div>
  )
}
