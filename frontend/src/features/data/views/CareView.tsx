import { ShieldAlert } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import type { DataSummary, StoredAssessment } from '../../../api/data'
import { useCareMetrics } from '../../../api/care'
import TrajectoryChart from '../../../components/charts/TrajectoryChart'
import PriorityBadge from '../../../components/PriorityBadge'
import SectionCard from '../../../components/SectionCard'
import Tile from '../../../components/Tile'
import { relativeTime } from '../../../lib/format'
import MetricsTab from '../../patient/metrics/MetricsTab'
import { Fact, Facts, ViewState } from '../DataBits'
import { num } from '../dataFormat'

/** Tier 5 — what everything above adds up to: the stored risk read with the
 *  reasons behind it, and every care metric by family. A flag here is a
 *  reason to look, not a finding. */

const SEVERITY = ['', 'Minor', 'Worth a look', 'Needs a look'] as const

function RiskRead({ a }: { a: StoredAssessment }) {
  const composite = a.composite
  const biggest = Math.max(0.0001, ...(composite?.drivers ?? []).map((d) => d.contribution))
  return (
    <SectionCard
      title="The risk read"
      icon={<Tile size="sm" family="risk-high" icon={<ShieldAlert />} />}
      aside={`Computed ${relativeTime(a.computed_at)} · engine ${a.engine_version}`}
    >
      <div className="flex flex-wrap items-center gap-3">
        <PriorityBadge priority={a.risk.level} />
        <span className="text-copy text-secondary">
          {a.basis === 'reported'
            ? 'Read from check-ins alone: no device on this chart.'
            : 'Read from the wearable’s signals against the person’s own baseline.'}
        </span>
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="text-copy font-medium text-secondary">Why this tier</h3>
          {a.risk.reasons.length === 0 ? (
            <p className="mt-2 text-copy text-ink">Nothing is out of range.</p>
          ) : (
            <ul className="mt-2 divide-y divide-hairline">
              {a.risk.reasons.map((r) => (
                <li key={r.code} className="flex items-start justify-between gap-4 py-2 first:pt-0">
                  <span className="text-copy text-ink">{r.text}</span>
                  <span className="meta shrink-0 whitespace-nowrap">{SEVERITY[r.severity] ?? ''}</span>
                </li>
              ))}
            </ul>
          )}
          <Facts>
            <div className="mt-5 flex flex-wrap gap-x-10 gap-y-4">
              <Fact label="Score" value={num(a.risk.score, 0)} hint="of 100" />
              {a.confidence && (
                <Fact
                  label="Data in hand"
                  value={`${a.confidence.days_with_data} of ${a.confidence.window_days}`}
                  hint="days"
                />
              )}
              {composite?.index != null && <Fact label="Signals moving together" value={num(composite.index, 1)} hint="index" />}
            </div>
          </Facts>
          {a.confidence && a.confidence.dark_metrics.length > 0 && (
            <p className="meta mt-3">
              Not arriving: {a.confidence.dark_metrics.map((m) => m.replace(/_/g, ' ')).join(', ')}.
            </p>
          )}
        </div>

        <div>
          {composite && composite.drivers.length > 0 && (
            <>
              <h3 className="text-copy font-medium text-secondary">What is moving the index</h3>
              <ul className="mt-2 space-y-2">
                {composite.drivers.map((d) => (
                  <li key={d.metric_type} className="flex items-center gap-3">
                    <span className="w-40 shrink-0 truncate text-copy text-ink">
                      {d.label} {d.direction === 'up' ? '↑' : '↓'}
                    </span>
                    <span aria-hidden className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-pill bg-[rgb(var(--fill))]">
                      <span
                        className="block h-full rounded-pill bg-chart-s1"
                        style={{ width: `${Math.max(4, (d.contribution / biggest) * 100)}%` }}
                      />
                    </span>
                    <span className="w-10 shrink-0 text-right text-label tabular-nums text-secondary">
                      {Math.round(d.contribution * 100)}%
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {a.trajectory && a.trajectory.actual.length > 1 && (
            <div className={composite && composite.drivers.length > 0 ? 'mt-6' : ''}>
              <h3 className="mb-2 text-copy font-medium text-secondary">Recovery against the expected range</h3>
              <TrajectoryChart
                actual={a.trajectory.actual}
                expected={a.trajectory.expected}
                changePointDay={a.trajectory.change_point_day}
              />
            </div>
          )}
        </div>
      </div>
      <p className="meta mt-5">
        Computed from the tiers before it. A flag is a reason for a clinician to look; it is not a
        diagnosis and it does not predict an outcome.
      </p>
    </SectionCard>
  )
}

export default function CareView({ patientId, summary }: { patientId: string; summary: DataSummary }) {
  const care = useCareMetrics(patientId)
  // `?metric=M12` (a headline tile on the chart, or a next step) lands on
  // that metric's card: scrolled to and ringed once, when the cards exist.
  // The ring is a direct DOM touch that clears itself, not React state.
  const [params] = useSearchParams()
  const focus = params.get('metric')
  const landed = useRef<string | null>(null)
  const ready = care.data != null
  useEffect(() => {
    if (!focus || !ready || landed.current === focus) return
    const el = document.getElementById(`metric-${focus}`)
    if (!el) return
    landed.current = focus
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.style.boxShadow = '0 0 0 3px rgb(var(--focus))'
    const timer = window.setTimeout(() => {
      el.style.boxShadow = ''
    }, 1800)
    return () => {
      window.clearTimeout(timer)
      el.style.boxShadow = ''
    }
  }, [focus, ready])
  return (
    <div className="space-y-stack">
      {summary.assessment ? (
        <RiskRead a={summary.assessment} />
      ) : (
        <SectionCard title="The risk read">
          <p className="text-copy text-secondary">This chart has not been read by the engine yet.</p>
        </SectionCard>
      )}
      <ViewState
        loading={care.isLoading}
        error={care.isError}
        onRetry={() => void care.refetch()}
        what="The care metrics"
      >
        {care.data && <MetricsTab data={care.data} refreshing={false} />}
      </ViewState>
    </div>
  )
}
