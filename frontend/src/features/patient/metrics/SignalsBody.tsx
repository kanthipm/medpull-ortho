import { Activity, CalendarCheck, Radar, TrendingUp } from 'lucide-react'
import type { CSSProperties } from 'react'
import type { MetricInsight, PatientMetrics } from '../../../api/types'
import AdherenceDots from '../../../components/AdherenceDots'
import ConfidenceChip from '../../../components/ConfidenceChip'
import Sparkline from '../../../components/charts/Sparkline'
import TrajectoryChart from '../../../components/charts/TrajectoryChart'
import SectionCard from '../../../components/SectionCard'
import { RefreshOverlay } from '../../../components/Skeleton'
import Tile from '../../../components/Tile'
import { shortDate } from '../../../lib/format'
import { METRIC_STATUS } from '../../../lib/risk'
import DotLine from '../DotLine'
import { GUARDED_NOTE, tileChipClass } from './labels'
import { signalTile } from './metricTiles'

/** The Signals tab of Full stats: trajectory, multi-signal deviation, the
 *  wearable trends and adherence. Its data comes from the lazy
 *  `usePatientMetrics` query the tab owns.
 *
 *  The wearable trends are drawn like the app's "Your portfolio" card: ONE
 *  white card holding soft filled tiles (category Tile + name, state chip,
 *  large tabular latest value with unit, date, then the sparkline in an opaque
 *  --panel well). The 4px status spine is gone — a 20px corner turns it into a
 *  crescent, and the chip already carries the state as a word. Contrast on
 *  --soft is documented in MetricCard.tsx. */

/** Latest reading, one decimal, true minus (R19). */
function latest(m: MetricInsight): { value: string; date: string } | null {
  const last = m.series[m.series.length - 1]
  if (!last) return null
  // Counts (steps) read as whole numbers with separators; small readings
  // keep one decimal.
  const v = last.value
  const text = Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : String(Math.round(v * 10) / 10)
  return {
    value: text.replace('-', '−'),
    date: shortDate(last.date),
  }
}

function SignalTile({ m, index }: { m: MetricInsight; index: number }) {
  const tile = signalTile(m.metric_key)
  const chip =
    m.status === 'flag' || m.status === 'watch'
      ? m.status_text || METRIC_STATUS[m.status].label
      : m.status === 'nodata'
        ? 'Needs data'
        : METRIC_STATUS[m.status].label
  const now = latest(m)
  const nameId = `signal-${m.metric_key}-name`
  return (
    <article
      aria-labelledby={nameId}
      style={{ '--rise-delay': `${index * 40}ms` } as CSSProperties}
      className="rise flex flex-col rounded-control bg-soft p-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <Tile family={tile.family} icon={tile.icon} />
          <h4 id={nameId} className="min-w-0 text-copy-lg font-medium text-ink">
            {m.name}
          </h4>
        </div>
        <span className={`chip shrink-0 ${tileChipClass(m.status)}`}>{chip}</span>
      </div>

      <p className="mt-3 flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
        <span className="big-num text-[2.25rem] text-ink">{now?.value ?? '—'}</span>
        {m.unit && <span className="text-copy text-secondary">{m.unit}</span>}
      </p>
      {now && <p className="meta mt-0.5">Latest · {now.date}</p>}

      <div className="mt-3 rounded-control-sm bg-panel px-2 py-1.5">
        <Sparkline series={m.series} baseline={m.baseline_mean} unit={m.unit} label={m.name} />
      </div>

      <p className="mt-3 text-copy text-body">{m.finding}</p>
      {m.next_step && (
        <p className="mt-2 flex items-start gap-1.5 text-copy font-medium text-brand-ink">
          <span aria-hidden>→</span> {m.next_step}
        </p>
      )}

      <DotLine
        as="p"
        className="meta mt-auto pt-3"
        parts={[
          m.coverage_text,
          m.confidence !== 'high' && <ConfidenceChip level={m.confidence} variant="meta" />,
          m.guarded && <span className="text-risk-med-ink">{GUARDED_NOTE}</span>,
        ]}
      />
    </article>
  )
}

const COMPOSITE = {
  high: { label: 'High', pill: 'bg-risk-high-tint text-risk-high-ink' },
  elevated: { label: 'Elevated', pill: 'bg-risk-med-tint text-risk-med-ink' },
  normal: { label: 'Normal', pill: 'bg-risk-low-tint text-risk-low-ink' },
} as const

export default function SignalsBody({
  data,
  refreshing,
}: {
  data: PatientMetrics
  refreshing: boolean
}) {
  const level =
    data.composite.level === 'high' || data.composite.level === 'elevated'
      ? COMPOSITE[data.composite.level]
      : COMPOSITE.normal

  return (
    <div className="space-y-stack">
      <SectionCard
        title="Recovery trajectory"
        icon={<Tile size="sm" family="indigo" icon={<TrendingUp />} />}
      >
        <RefreshOverlay show={refreshing} />
        <TrajectoryChart
          actual={data.trajectory.actual}
          expected={data.trajectory.expected}
          changePointDay={data.trajectory.change_point_day}
        />
      </SectionCard>

      {data.composite.drivers.length > 0 && (
        <SectionCard
          title="Multi-signal deviation"
          icon={<Tile size="sm" family="violet" icon={<Radar />} />}
          aside={<span className={`chip ${level.pill}`}>{level.label}</span>}
        >
          <RefreshOverlay show={refreshing} />
          <ul className="space-y-3">
            {data.composite.drivers.map((d) => {
              const pct = Math.round(d.contribution * 100)
              return (
                <li
                  key={d.metric_type}
                  className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3"
                >
                  <span className="truncate text-copy text-body" title={d.label}>
                    {d.label}
                  </span>
                  {/* --chart-s1 on the quiet --chart-grid track: 3.635 light /
                      5.054 dark (the brand fill on --line was 1.029 in dark).
                      The number beside it is the value; the bar is for the eye. */}
                  <span aria-hidden className="h-2 overflow-hidden rounded-pill bg-chart-grid">
                    <span
                      className="block h-full rounded-pill bg-chart-s1 transition-[width] duration-spring ease-spring motion-reduce:transition-none"
                      style={{ width: `${pct}%` }}
                    />
                  </span>
                  <span className="w-10 text-right text-copy font-medium tabular-nums text-ink">
                    {pct}%
                  </span>
                </li>
              )
            })}
          </ul>
          <p className="meta mt-4">
            Contribution of each signal to the deviation index · for review, not a diagnosis
          </p>
        </SectionCard>
      )}

      {data.metrics.length > 0 && (
        <SectionCard
          title="Wearable signals"
          icon={<Tile size="sm" family="teal" icon={<Activity />} />}
          aside={`${data.metrics.length} signal${data.metrics.length === 1 ? '' : 's'}`}
        >
          <RefreshOverlay show={refreshing} />
          <div className="grid gap-3 sm:grid-cols-2">
            {data.metrics.map((m, i) => (
              <SignalTile key={m.metric_key} m={m} index={i} />
            ))}
          </div>
        </SectionCard>
      )}

      <SectionCard
        title="Adherence and monitoring"
        icon={<Tile size="sm" family="blue" icon={<CalendarCheck />} />}
      >
        <RefreshOverlay show={refreshing} />
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-copy font-medium text-ink">Task adherence</p>
            <p className="meta mt-0.5">
              Last {data.adherence.days.length} days · {data.adherence.verified} verified ·{' '}
              {data.adherence.self_attested} self-attested
            </p>
          </div>
          <AdherenceDots days={data.adherence.days} rate={data.adherence.rate} />
        </div>
      </SectionCard>
    </div>
  )
}
