import { Gauge } from 'lucide-react'
import type { ReadinessPanel } from '../../api/sports'
import Sparkline from '../../components/charts/Sparkline'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import DotLine from '../patient/DotLine'
import { SignedBar, StatusChip } from './SportsBits'
import { BAND_WORD, TONE_TEXT, bandTone, fmt, sd, zTone } from './sportsFormat'

/** Readiness: the score in light type with its band in words, the 28-day
 *  line against the "normal" of 50, and each component as a signed bar. */
export default function ReadinessCard({ readiness }: { readiness: ReadinessPanel | null }) {
  if (!readiness) {
    return (
      <SectionCard title="Readiness">
        <EmptyState variant="inline" icon={<Gauge />} family="teal" title="No readiness yet">
          Overnight HRV, resting heart rate and sleep from a connected wearable build the score.
        </EmptyState>
      </SectionCard>
    )
  }
  const x = readiness.extra
  const tone = bandTone(x.band)
  return (
    <SectionCard title="Readiness" aside={<StatusChip status={readiness.status} text={readiness.status_text} />}>
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span className={`big-num text-[2.75rem] ${tone ? TONE_TEXT[tone] : 'text-ink'}`}>{fmt(x.score)}</span>
        <span className="text-copy text-secondary">
          / 100{x.band ? ` · ${BAND_WORD[x.band]}` : ''}
        </span>
      </p>
      {readiness.sub && <p className="mt-1 text-copy text-body">{readiness.sub}</p>}
      {readiness.series.length > 0 && (
        <div className="mt-3 rounded-control-sm bg-panel p-2">
          <Sparkline series={readiness.series} baseline={50} unit="" label="Readiness, 28 days" />
        </div>
      )}
      {x.components.length > 0 && (
        <ul className="mt-4 space-y-2.5" aria-label="What moved the score">
          {x.components.map((c) => {
            const t = zTone(c.z)
            return (
              <li key={c.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3">
                <div className="min-w-0">
                  <span className="block truncate text-copy text-ink">{c.label}</span>
                  <span className="meta block truncate">
                    <span className="text-ink">{c.value}</span> · {c.text}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <SignedBar z={c.z} className="!w-20" />
                  <span className={`w-14 text-right text-label tabular-nums ${t ? TONE_TEXT[t] : 'text-secondary'}`}>
                    {sd(c.z)}
                  </span>
                </div>
              </li>
            )
          })}
        </ul>
      )}
      <DotLine
        as="p"
        className="meta mt-4"
        parts={[
          ...readiness.stats.map((s) => `${s.label} ${s.value}${s.unit ? ` ${s.unit}` : ''}`),
          readiness.coverage,
        ]}
      />
    </SectionCard>
  )
}
