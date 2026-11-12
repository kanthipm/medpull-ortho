import { LineChart } from 'lucide-react'
import { useState } from 'react'
import { useDailySeries, type DataSummary } from '../../../api/data'
import { usePatientMetrics } from '../../../api/queries'
import SectionCard from '../../../components/SectionCard'
import SegmentedControl from '../../../components/SegmentedControl'
import Tile from '../../../components/Tile'
import SignalsBody from '../../patient/metrics/SignalsBody'
import { Fact, Facts, ViewState } from '../DataBits'
import { num } from '../dataFormat'
import SeriesChart from '../SeriesChart'

/** Tier 3 — one value a day per signal, against the person's own baseline.
 *  The cards are the chart's signal panel (status, finding, the last two
 *  weeks); under them, any one signal over a longer window with its
 *  baseline, the expected curve where the engine uses one, and which source
 *  supplied each day. */

type Window = '30' | '60' | '90'

const SELECT =
  'h-9 min-w-0 rounded-control-sm border border-line bg-panel px-2.5 text-copy text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus'

function Closer({ patientId, summary }: { patientId: string; summary: DataSummary }) {
  const judged = summary.metrics.filter((m) => m.count > 0 && (m.tier === 'scored' || m.tier === 'display'))
  const [metric, setMetric] = useState(judged[0]?.metric_type ?? '')
  const [window, setWindow] = useState<Window>('90')
  const series = useDailySeries(patientId, metric ? [metric] : [], Number(window))
  const one = series.data?.series[0]
  if (judged.length === 0) return null
  const latest = one?.points[one.points.length - 1]
  return (
    <SectionCard
      title="A closer look"
      icon={<Tile size="sm" family="indigo" icon={<LineChart />} />}
      aside="The series the engine reads, one value a day"
    >
      <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
        <label className="flex min-w-0 flex-col gap-1">
          <span className="meta">Signal</span>
          <select className={SELECT} value={metric} onChange={(e) => setMetric(e.target.value)}>
            {judged.map((m) => (
              <option key={m.metric_type} value={m.metric_type}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <SegmentedControl<Window>
          options={[
            { key: '30', label: '30 days' },
            { key: '60', label: '60 days' },
            { key: '90', label: '90 days' },
          ]}
          value={window}
          onChange={setWindow}
          size="sm"
          role="radiogroup"
          aria-label="Window"
        />
      </div>
      <ViewState
        loading={series.isLoading}
        error={series.isError}
        onRetry={() => void series.refetch()}
        what="The series"
      >
        {one && (
          <>
            <Facts>
              <Fact
                label="Latest"
                value={latest ? num(latest.value) : '—'}
                hint={one.unit}
              />
              {one.baseline && (
                <Fact
                  label={one.baseline.is_preop ? 'Own baseline (before surgery)' : 'Own baseline'}
                  value={num(one.baseline.mean)}
                  hint={`± ${num(one.baseline.sd)} over ${one.baseline.n_days} days`}
                />
              )}
              {one.latest_z != null && (
                <Fact
                  label="Latest against the reference"
                  value={`${one.latest_z > 0 ? '+' : '−'}${Math.abs(one.latest_z).toFixed(1)}`}
                  hint="SD"
                />
              )}
            </Facts>
            <div className="mt-5">
              <SeriesChart series={one} />
            </div>
            <p className="meta mt-3">
              {one.aggregation === 'additive'
                ? 'A day’s value is the source’s daily total.'
                : 'A day’s value is the mean of that day’s readings from the source that ranks first.'}{' '}
              {one.reference === 'baseline'
                ? 'Judged against the person’s own baseline.'
                : one.reference
                  ? 'Judged against the recovery curve expected for this procedure, scaled to the person’s own baseline.'
                  : 'Shown as recorded; not judged.'}
              {one.stale ? ' The latest reading is too old to judge.' : ''}
            </p>
          </>
        )}
      </ViewState>
    </SectionCard>
  )
}

export default function SignalsView({ patientId, summary }: { patientId: string; summary: DataSummary }) {
  const signals = usePatientMetrics(patientId)
  return (
    <div className="space-y-stack">
      <ViewState
        loading={signals.isLoading}
        error={signals.isError}
        onRetry={() => void signals.refetch()}
        what="The signals"
      >
        {signals.data && <SignalsBody data={signals.data} refreshing={false} />}
      </ViewState>
      <Closer patientId={patientId} summary={summary} />
    </div>
  )
}
