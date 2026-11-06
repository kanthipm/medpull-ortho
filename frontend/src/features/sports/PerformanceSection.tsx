import { TrendingDown, TrendingUp } from 'lucide-react'
import { useState } from 'react'
import type { Asymmetry, AthletePerformance, Neuromuscular, PerfHeadline } from '../../api/sports'
import SectionCard from '../../components/SectionCard'
import { shortDate } from '../../lib/format'
import DotLine from '../patient/DotLine'
import { Meter, StatusChip } from './SportsBits'
import { DASH, TONE_TEXT, fmt, ordinal, pct, words } from './sportsFormat'

const SHOW = 9

/** The headline tests as soft tiles with a percentile meter against the
 *  level's reference, then the side-to-side asymmetries and the weekly
 *  neuromuscular read. */
export default function PerformanceSection({ performance }: { performance: AthletePerformance }) {
  const [all, setAll] = useState(false)
  const tests = performance.headline
  const visible = all ? tests : tests.slice(0, SHOW)
  const counts = `${performance.logged} of ${performance.available} tests logged`
  const aside =
    performance.overall_percentile != null
      ? `${ordinal(performance.overall_percentile)} percentile overall · ${counts}`
      : counts
  return (
    <SectionCard title="Performance" aside={aside}>
      {tests.length === 0 ? (
        <p className="text-copy text-secondary">No tests on file yet.</p>
      ) : (
        <>
          <ul className="grid grid-cols-2 gap-2 min-[900px]:grid-cols-3" aria-label="Headline tests">
            {visible.map((t) => (
              <TestTile key={t.key} t={t} />
            ))}
          </ul>
          {tests.length > SHOW && (
            <div className="mt-3 flex justify-center">
              <button type="button" className="btn-plain btn-sm" onClick={() => setAll((a) => !a)}>
                {all ? 'Show fewer' : `Show all ${tests.length} tests`}
              </button>
            </div>
          )}
        </>
      )}
      <Asymmetries items={performance.asymmetries} />
      <Neuro n={performance.neuromuscular} />
    </SectionCard>
  )
}

function TestTile({ t }: { t: PerfHeadline }) {
  const trend = t.trend
  const trendClass = trend ? (trend.better ? TONE_TEXT.low : TONE_TEXT.high) : ''
  const logged = t.logged && t.latest_text
  return (
    <li className="flex min-w-0 flex-col rounded-control bg-soft px-3.5 py-3">
      <span className="block truncate text-copy text-secondary" title={t.label}>
        {t.label}
      </span>
      <span className="mt-1 flex flex-wrap items-baseline gap-x-1.5 text-title font-medium tabular-nums text-ink">
        {logged ? t.latest_text : DASH}
        {logged && t.unit && <span className="text-label font-normal text-secondary">{t.unit}</span>}
      </span>
      {t.band ? (
        <>
          <Meter pct={t.band.percentile} className="mt-2 !h-1.5" />
          <span className="meta mt-1 block tabular-nums">
            {ordinal(t.band.percentile)} percentile · {t.band.word}
          </span>
        </>
      ) : (
        <span className="meta mt-1 block">{logged ? 'No reference band' : 'Not logged'}</span>
      )}
      <DotLine
        as="span"
        className="meta mt-0.5 block"
        parts={[
          trend && (
            <span className={`inline-flex items-center gap-1 tabular-nums ${trendClass}`}>
              {trend.better ? <TrendingUp aria-hidden size={12} /> : <TrendingDown aria-hidden size={12} />}
              {pct(trend.pct)} {trend.better ? 'better' : 'worse'}
            </span>
          ),
          t.days_ago != null &&
            (t.days_ago === 0 ? 'today' : t.days_ago === 1 ? 'yesterday' : `${t.days_ago} days ago`),
        ]}
      />
    </li>
  )
}

function Asymmetries({ items }: { items: Asymmetry[] }) {
  return (
    <section className="mt-5 border-t border-hairline pt-4" aria-label="Asymmetries">
      <h3 className="text-copy-lg font-medium text-ink">Asymmetries</h3>
      {items.length === 0 ? (
        <p className="mt-1 text-copy text-secondary">No side-to-side difference flagged.</p>
      ) : (
        <ul className="mt-1 divide-y divide-hairline">
          {items.map((a) => (
            <li key={a.key} className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2">
              <span className="min-w-0 flex-1 text-copy text-ink">{a.label}</span>
              <span className="meta tabular-nums">
                {fmt(a.asymmetry.pct)}% · weaker {a.asymmetry.weaker} · LSI {fmt(a.asymmetry.lsi)}%
              </span>
              <StatusChip status={a.status} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Neuro({ n }: { n: Neuromuscular }) {
  return (
    <section className="mt-5 border-t border-hairline pt-4" aria-label="Neuromuscular">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-copy-lg font-medium text-ink">Neuromuscular</h3>
        <StatusChip status={n.status} text={n.status_text} />
      </div>
      {n.finding && <p className="mt-1.5 text-copy text-body">{n.finding}</p>}
      {n.signals.length > 0 && (
        <dl className="mt-2.5 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {n.signals.map((s) => {
            // A tenth off baseline is the published step for jump strategy.
            const off = Math.abs(s.pct) >= 10
            return (
              <div key={s.label} className="min-w-0 rounded-control bg-soft px-3 py-2.5">
                <dt className="meta truncate">{s.label}</dt>
                <dd className="text-copy tabular-nums text-ink">{s.value}</dd>
                <dd className={`meta tabular-nums ${off ? TONE_TEXT.high : ''}`}>
                  {pct(s.pct)} vs {s.baseline}
                </dd>
              </div>
            )
          })}
        </dl>
      )}
      <DotLine
        as="p"
        className="meta mt-2"
        parts={[n.source && words(n.source), n.latest_date && shortDate(n.latest_date)]}
      />
    </section>
  )
}
