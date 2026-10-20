import { Moon } from 'lucide-react'
import type { Panel } from '../../api/sports'
import Sparkline from '../../components/charts/Sparkline'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { StatusChip } from './SportsBits'
import { numberOf } from './sportsFormat'

/** Sleep, HRV and resting heart rate as compact blocks in one card: the
 *  engine's headline figure, its status in words, the 28-day sparkline on an
 *  opaque well with the athlete's own baseline dashed, the finding, and the
 *  panel's stats. */
export default function SignalPanels({ panels }: { panels: Record<string, Panel | null | undefined> }) {
  const items: { p: Panel; baseline: number | null; unit: string }[] = []
  const sleep = panels.sleep
  if (sleep) items.push({ p: sleep, baseline: numberOf(sleep.extra.need_hours), unit: 'h' })
  const hrv = panels.hrv
  if (hrv) items.push({ p: hrv, baseline: numberOf(hrv.extra.baseline_mean), unit: hrv.unit || 'ms' })
  const rhr = panels.resting_hr
  if (rhr) items.push({ p: rhr, baseline: numberOf(rhr.extra.baseline_mean), unit: rhr.unit || 'bpm' })

  return (
    <SectionCard title="Overnight signals">
      {items.length === 0 ? (
        <EmptyState variant="inline" icon={<Moon />} family="indigo" title="No overnight signals yet">
          Sleep, HRV and resting heart rate arrive from a connected wearable.
        </EmptyState>
      ) : (
        <div className="divide-y divide-hairline">
          {items.map(({ p, baseline, unit }) => (
            <SignalBlock key={p.key} p={p} baseline={baseline} unit={unit} />
          ))}
        </div>
      )}
    </SectionCard>
  )
}

function SignalBlock({ p, baseline, unit }: { p: Panel; baseline: number | null; unit: string }) {
  const nodata = p.status === 'nodata'
  return (
    <section className="py-4 first:pt-0 last:pb-0" aria-label={p.title}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-copy-lg font-medium text-ink">{p.title}</h3>
        <StatusChip status={p.status} text={p.status_text} />
      </div>
      <p className="mt-1.5 flex flex-wrap items-baseline gap-x-1.5">
        <span className="big-num text-[1.75rem] text-ink">{p.headline}</span>
        {p.unit && <span className="text-copy text-secondary">{p.unit}</span>}
        {p.sub && <span className="text-copy text-secondary">· {p.sub}</span>}
      </p>
      {!nodata && p.series.length > 0 && (
        <div className="mt-2.5 rounded-control-sm bg-panel p-2">
          <Sparkline series={p.series} baseline={baseline} unit={unit} label={p.title} />
        </div>
      )}
      {p.finding && <p className="mt-2.5 text-copy text-body">{p.finding}</p>}
      {p.stats.length > 0 && (
        <dl className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-4 min-[1200px]:grid-cols-2">
          {p.stats.map((s) => (
            <div key={s.label} className="min-w-0">
              <dt className="meta truncate">{s.label}</dt>
              <dd className="text-copy tabular-nums text-ink">
                {s.value}
                {s.unit && <span className="text-secondary"> {s.unit}</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}
