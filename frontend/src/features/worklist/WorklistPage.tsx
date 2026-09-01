import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { usePracticeOverview, useWorklist, type AskResult } from '../../api/queries'
import type { WorklistPatient } from '../../api/types'
import AskBar from './AskBar'
import AIAttribution from '../../components/AIAttribution'
import ConfidenceChip from '../../components/ConfidenceChip'
import InlineReadout from '../../components/InlineReadout'
import PriorityBadge from '../../components/PriorityBadge'
import GuardrailFootnote from '../../components/GuardrailFootnote'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard, SkeletonLine } from '../../components/Skeleton'
import EmptyState from '../../components/EmptyState'
import { longDate, relativeTime } from '../../lib/format'
import { PRIORITY, type Priority } from '../../lib/risk'
import { practiceReadout } from './practiceStrip'

type Filter = 'all' | 'high' | 'missing_data'

const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'high', label: 'High risk' },
  { key: 'missing_data', label: 'Missing data' },
]

const TIER_ORDER: Priority[] = ['high', 'medium', 'missing_data', 'low']

function headline(stats: { high: number; missing: number }): string {
  if (stats.high === 1) return '1 patient needs your attention today'
  if (stats.high > 1) return `${stats.high} patients need your attention today`
  if (stats.missing > 0) return 'No urgent reviews — some data gaps to check'
  return 'All patients are recovering as expected'
}

export default function WorklistPage() {
  const { data, isLoading, isError } = useWorklist()
  const { data: practice } = usePracticeOverview()
  const [filter, setFilter] = useState<Filter>('all')
  const [askResult, setAskResult] = useState<AskResult | null>(null)

  if (isLoading) {
    return (
      <div className="space-y-4">
        <SkeletonCard lines={2} />
        <SkeletonCard lines={5} />
        <SkeletonCard lines={5} />
      </div>
    )
  }
  if (isError || !data) {
    return (
      <EmptyState title="The worklist couldn't be loaded.">
        Check that the API is running, then reload this page.
      </EmptyState>
    )
  }

  const askIds = askResult && askResult.patient_ids.length > 0 ? new Set(askResult.patient_ids) : null
  const groups = TIER_ORDER.map((tier) => ({
    tier,
    patients: data.patients.filter((p) =>
      askIds
        ? askIds.has(p.id) && p.priority === tier
        : p.priority === tier && (filter === 'all' || p.priority === filter),
    ),
  })).filter((g) => g.patients.length > 0)

  let riseIndex = 0

  return (
    <div>
      <header className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
        <p className="font-mono text-[11px] uppercase tracking-[.22em] text-faint">{longDate()}</p>
        <h1 className="mt-2.5 text-[clamp(26px,3.6vw,34px)] font-semibold leading-[1.08] tracking-[-.03em] text-ink">
          {headline(data.stats)}
        </h1>
        <div className="mt-4">
          {practice ? (
            <InlineReadout items={practiceReadout(practice)} />
          ) : (
            <div className="flex gap-5">
              <SkeletonLine className="h-6 w-20" />
              <SkeletonLine className="h-6 w-24" />
              <SkeletonLine className="h-6 w-28" />
              <SkeletonLine className="h-6 w-24" />
              <SkeletonLine className="h-6 w-28" />
            </div>
          )}
        </div>
      </header>

      <div className="rise mt-6" style={{ '--rise-delay': '60ms' } as CSSProperties}>
        <SectionCard
          spine="bg-brand"
          eyebrow={
            <AIAttribution
              kind="daily briefing"
              generatedAt={data.briefing.generated_at}
              provider={data.briefing.provider}
            />
          }
        >
          <p className="text-[13.5px] leading-[1.6] text-body">{data.briefing.text}</p>
        </SectionCard>
      </div>

      <div className="rise mt-5" style={{ '--rise-delay': '100ms' } as CSSProperties}>
        <AskBar result={askResult} onResult={setAskResult} onClear={() => setAskResult(null)} />
      </div>

      <div
        className="rise mt-7 flex items-center justify-between gap-3"
        style={{ '--rise-delay': '140ms' } as CSSProperties}
      >
        <h2 className="text-[11px] font-semibold uppercase tracking-[.12em] text-faint">
          {askIds ? 'Matching patients' : 'Patient panel'}
        </h2>
        {!askIds && (
          <SegmentedControl
            options={FILTERS}
            value={filter}
            onChange={setFilter}
            aria-label="Filter patients"
            className="flex-none"
          />
        )}
      </div>

      {groups.length === 0 ? (
        <div className="mt-3">
          <EmptyState
            title={askIds ? 'No patients matched that question.' : 'No patients match this filter.'}
          >
            {askIds
              ? 'Clear the question to see the full roster.'
              : 'Switch back to All to see the full roster.'}
          </EmptyState>
        </div>
      ) : (
        <div
          className="rise mt-3 overflow-hidden rounded-card border border-line bg-panel"
          style={{ '--rise-delay': '160ms' } as CSSProperties}
        >
          {groups.map(({ tier, patients }) => (
            <div key={tier} className="border-b border-line last:border-0">
              <div className="flex items-center gap-2 bg-soft/70 px-4 py-2">
                <span className={`h-1.5 w-1.5 rounded-full ${PRIORITY[tier].dot}`} aria-hidden />
                <span className="text-[10.5px] font-semibold uppercase tracking-[.1em] text-muted">
                  {PRIORITY[tier].label}
                </span>
                <span className="font-mono text-[11px] font-medium tabular-nums text-faint">
                  {patients.length}
                </span>
              </div>
              <div className="divide-y divide-line">
                {patients.map((p) => (
                  <WorklistRow key={p.id} patient={p} index={riseIndex++} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <GuardrailFootnote className="mt-7" />
    </div>
  )
}

function WorklistRow({ patient: p, index }: { patient: WorklistPatient; index: number }) {
  const high = p.priority === 'high'
  return (
    <Link
      to={`/patients/${p.id}`}
      style={{ '--rise-delay': `${180 + index * 40}ms` } as CSSProperties}
      className={`rise group relative flex cursor-pointer items-center gap-3.5 px-4 py-3 transition-colors duration-150 focus-visible:outline focus-visible:-outline-offset-2 focus-visible:outline-2 focus-visible:outline-brand ${
        high ? 'bg-risk-high-bg/40 hover:bg-risk-high-bg/70' : 'hover:bg-soft/80'
      }`}
    >
      {high && <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-risk-high" />}
      <span
        aria-hidden
        className={`grid h-9 w-9 shrink-0 place-items-center rounded-full font-mono text-[11px] font-medium text-white ${
          high ? 'bg-risk-high' : 'bg-brand'
        }`}
      >
        {p.initials}
      </span>
      <span className="w-36 shrink-0 sm:w-52">
        <span className="block truncate text-[13.5px] font-semibold tracking-[-.01em] text-ink">
          {p.name}
        </span>
        <span className="mt-0.5 block truncate text-[11px] font-medium text-faint">
          {p.procedure_display.replace(/\s*\(.*\)$/, '')} ·{' '}
          <span className="font-mono">D{p.postop_day}</span>
        </span>
      </span>
      <PriorityBadge priority={p.priority} className="hidden shrink-0 lg:inline-flex" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] leading-snug text-body">{p.reason}</span>
        <ConfidenceChip level={p.data_confidence.level} className="mt-1" />
      </span>
      <span
        className="hidden w-[76px] shrink-0 text-right md:block"
        title={
          p.rtm.enrolled
            ? 'RTM monitoring days since enrollment (16-of-30 target)'
            : 'RTM enrollment in progress — monitoring days accrue after enrollment'
        }
      >
        {p.rtm.enrolled ? (
          p.rtm.eligible ? (
            <span className="text-[10.5px] font-semibold uppercase tracking-[.04em] text-risk-low">
              Complete
            </span>
          ) : (
            <span className="font-mono text-[12px] font-medium tabular-nums text-muted">
              {Math.min(p.rtm.days, p.rtm.target)}
              <span className="text-faint">/{p.rtm.target}d</span>
            </span>
          )
        ) : (
          <span className="text-[10.5px] font-medium uppercase tracking-[.04em] text-faint">
            Enrolling
          </span>
        )}
      </span>
      <span className="hidden w-32 shrink-0 text-right sm:block">
        <span className="block font-mono text-[11px] font-medium tabular-nums text-muted">
          {relativeTime(p.last_checkin_at)}
        </span>
        <span className="mt-0.5 block truncate text-[11px] font-medium text-faint">
          {p.assigned_provider.name}
        </span>
      </span>
      <ChevronRight
        size={16}
        aria-hidden
        className="hidden shrink-0 text-faint/60 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-muted sm:block"
      />
    </Link>
  )
}
