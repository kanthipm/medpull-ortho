import { Cpu, Info } from 'lucide-react'
import { useDailySeries, useDataCatalog, type DailySeries, type DataSummary } from '../../../api/data'
import SectionCard from '../../../components/SectionCard'
import Tile from '../../../components/Tile'
import { shortDate } from '../../../lib/format'
import { Fact, Facts, ViewState } from '../DataBits'
import { num, sourceName } from '../dataFormat'
import SeriesChart from '../SeriesChart'

/** Tier 4 — what MedPull computes itself: gait, stairs, the walk tests and
 *  range of motion from the phone's motion sensors, a stress index from the
 *  overnight signals, and training load and program from check-ins. The same
 *  algorithm for everyone, whatever watch they wear. Shown for context; none
 *  of it moves the risk tier. */

function MetricPanel({ series, method, sessions }: { series: DailySeries; method: string | null; sessions: number }) {
  const latest = series.points[series.points.length - 1]
  const sources = [...new Set(series.points.map((p) => p.source).filter(Boolean))] as string[]
  return (
    <div className="rounded-control bg-soft p-4">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-copy-lg font-medium text-ink">{series.label}</h3>
        <span className="meta whitespace-nowrap">
          {series.computed ? 'Computed nightly' : `${sessions} ${sessions === 1 ? 'reading' : 'readings'}`}
        </span>
      </div>
      <p className="mt-1 flex items-baseline gap-1.5">
        <span className="big-num text-[1.75rem] text-ink">{latest ? num(latest.value) : '—'}</span>
        <span className="text-copy text-secondary">
          {series.unit}
          {latest ? ` · ${shortDate(latest.date)}` : ''}
        </span>
      </p>
      <div className="mt-3 rounded-control-sm bg-panel p-3">
        <SeriesChart series={series} height={140} />
      </div>
      {method && <p className="meta mt-3">{method}</p>}
      {sources.length > 1 && (
        <p className="meta mt-1">
          Days in this series came from {sources.map(sourceName).join(' and ')}: where both measured a
          day, MedPull’s own reading is the one used.
        </p>
      )}
    </div>
  )
}

function ReportedBlock({ summary }: { summary: DataSummary }) {
  const r = summary.reported
  if (!r) return null
  return (
    <SectionCard title="From check-ins" aside="What the person reported, as numbers">
      <Facts>
        {r.load_week_mean != null && (
          <Fact label="Training load, this week" value={num(r.load_week_mean)} hint="AU a day" />
        )}
        {r.load_prior_mean != null && (
          <Fact label="Their weeks before" value={num(r.load_prior_mean)} hint="AU a day" />
        )}
        {r.pain_latest != null && (
          <Fact
            label="Pain, latest"
            value={num(r.pain_latest)}
            hint={r.pain_prior_mean != null ? `of 10 · ${num(r.pain_prior_mean)} the week before` : 'of 10'}
          />
        )}
        {(r.program_days ?? 0) > 0 && r.program_done_7d != null && r.program_week_days != null && (
          <Fact label="Program, last 7 days" value={num(r.program_done_7d)} hint={`of ${r.program_week_days} days`} />
        )}
        <Fact label="Check-ins, 14 days" value={r.checkins_14d} />
      </Facts>
      {(r.load_days ?? 0) > 0 && (
        <p className="meta mt-4">
          Training load is effort (0 to 10) times minutes, as the person reported them. It is shown
          against their own earlier weeks; it is a description of what they did, not a prediction.
        </p>
      )}
    </SectionCard>
  )
}

export default function MedPullView({ patientId, summary }: { patientId: string; summary: DataSummary }) {
  const catalog = useDataCatalog()
  const inHouse = summary.metrics.filter((m) => m.in_house && m.count > 0)
  const hasVitals = summary.metrics.some((m) => m.metric_type === 'resting_hr' && m.count > 0)
  const keys = [...inHouse.map((m) => m.metric_type), ...(hasVitals ? ['stress_index'] : [])].slice(0, 12)
  const series = useDailySeries(patientId, keys, 90)
  const methods = new Map((catalog.data?.metrics ?? []).map((m) => [m.key, m.method ?? m.what]))
  const counts = new Map(summary.metrics.map((m) => [m.metric_type, m.count]))
  const shown = (series.data?.series ?? []).filter((s) => s.points.length > 0)

  return (
    <div className="space-y-stack">
      <div className="card-tint flex items-start gap-3 px-5 py-4">
        <Info aria-hidden size={18} className="mt-0.5 shrink-0 text-body" />
        <p className="text-copy text-ink">
          These are computed by MedPull itself, from the phone’s motion sensors, the overnight
          signals and check-ins, so they read the same whatever watch someone wears. They are shown
          for context and are not part of the risk read.
        </p>
      </div>

      {keys.length > 0 && (
        <SectionCard
          title="Movement and recovery"
          icon={<Tile size="sm" family="blue" icon={<Cpu />} />}
          aside={catalog.data ? `Algorithm ${catalog.data.versions.mobility}` : undefined}
        >
          <ViewState
            loading={series.isLoading}
            error={series.isError}
            onRetry={() => void series.refetch()}
            what="The computed metrics"
          >
            {shown.length === 0 ? (
              <p className="text-copy text-secondary">Nothing computed in the last 90 days.</p>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                {shown.map((s) => (
                  <MetricPanel
                    key={s.metric}
                    series={s}
                    method={methods.get(s.metric) ?? null}
                    sessions={counts.get(s.metric) ?? s.points.length}
                  />
                ))}
              </div>
            )}
          </ViewState>
        </SectionCard>
      )}

      <ReportedBlock summary={summary} />

      {keys.length === 0 && !summary.reported && (
        <SectionCard title="Nothing computed yet">
          <p className="text-copy text-secondary">
            Gait, stairs, the six-minute walk and range of motion are recorded when the person does a
            guided test in the app’s Measure tab; the stress index needs a few nights from a watch.
          </p>
        </SectionCard>
      )}
    </div>
  )
}
