import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import type { CSSProperties } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { NextStep, WorklistRowWithStep } from '../../api/plan'
import { useCompleteNextStep } from '../../api/plan'
import { useWorklist, type AskResult } from '../../api/queries'
import MessageComposerModal from '../patient/plan/MessageComposerModal'
import { NextStepButton } from '../patient/plan/NextSteps'
import AskBar from './AskBar'
import AIAttribution from '../../components/AIAttribution'
import SentenceCase from './SentenceCase'
import ConfidenceChip from '../../components/ConfidenceChip'
import PriorityBadge from '../../components/PriorityBadge'
import GuardrailFootnote from '../../components/GuardrailFootnote'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard } from '../../components/Skeleton'
import EmptyState from '../../components/EmptyState'
import { longDate, relativeTime } from '../../lib/format'
import { PRIORITY, type Priority } from '../../lib/risk'

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
  const [filter, setFilter] = useState<Filter>('all')
  const [askResult, setAskResult] = useState<AskResult | null>(null)
  // A row's "Message" next step opens the composer for that patient; the
  // send is logged back as the step's completion.
  const [composer, setComposer] = useState<{ patient: WorklistRowWithStep; step: NextStep } | null>(
    null,
  )

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
        <p className="text-label font-medium text-muted">{longDate()}</p>
        <h1 className="mt-seam text-section font-normal text-ink">
          {headline(data.stats)}
        </h1>
      </header>

      <div className="rise mt-6" style={{ '--rise-delay': '60ms' } as CSSProperties}>
        <SectionCard
          spine="bg-brand"
          eyebrow={
            <SentenceCase>
              <AIAttribution
                kind="daily briefing"
                generatedAt={data.briefing.generated_at}
                provider={data.briefing.provider}
              />
            </SentenceCase>
          }
        >
          <p className="text-copy-lg text-body">{data.briefing.text}</p>
        </SectionCard>
      </div>

      <div className="rise mt-5" style={{ '--rise-delay': '100ms' } as CSSProperties}>
        <AskBar result={askResult} onResult={setAskResult} onClear={() => setAskResult(null)} />
      </div>

      <div
        className="rise mt-region flex items-center justify-between gap-tight"
        style={{ '--rise-delay': '140ms' } as CSSProperties}
      >
        <h2 className="micro">{askIds ? 'Matching patients' : 'Patient panel'}</h2>
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
        <div className="mt-tight">
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
          className="rise mt-tight overflow-hidden rounded-surface border border-line bg-panel"
          style={{ '--rise-delay': '160ms' } as CSSProperties}
        >
          {groups.map(({ tier, patients }) => (
            <div key={tier} className="border-b border-line last:border-0">
              <div className="flex items-center gap-seam bg-soft px-snug py-seam">
                <span className={`h-1.5 w-1.5 rounded-pill ${PRIORITY[tier].dot}`} aria-hidden />
                <span className="text-label font-medium text-muted">
                  {PRIORITY[tier].label}
                </span>
                <span className="text-label font-medium tabular-nums text-muted">
                  {patients.length}
                </span>
              </div>
              <div className="divide-y divide-line">
                {patients.map((p) => (
                  <WorklistRow
                    key={p.id}
                    patient={p}
                    index={riseIndex++}
                    onMessage={(step) => setComposer({ patient: p, step })}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <GuardrailFootnote className="mt-region" />

      {composer && (
        <WorklistComposer
          patient={composer.patient}
          step={composer.step}
          onClose={() => setComposer(null)}
        />
      )}
    </div>
  )
}

/** The composer for a row's message step. Its own component so the
 *  completion hook is bound to the row's patient id. */
function WorklistComposer({
  patient,
  step,
  onClose,
}: {
  patient: WorklistRowWithStep
  step: NextStep
  onClose: () => void
}) {
  const complete = useCompleteNextStep(patient.id)
  const phone = step.action.tel ?? null
  return (
    <MessageComposerModal
      patientId={patient.id}
      patientName={patient.name}
      phone={phone}
      prefill={step.action.prefill ?? ''}
      onClose={onClose}
      onSent={(r) =>
        complete.mutate({
          key: step.key,
          result: { message_id: r.message?.id ?? null, status: r.status },
        })
      }
    />
  )
}

function WorklistRow({
  patient: p,
  index,
  onMessage,
}: {
  patient: WorklistRowWithStep
  index: number
  onMessage: (step: NextStep) => void
}) {
  const high = p.priority === 'high'
  const navigate = useNavigate()
  const step = p.next_step ?? null
  // A high row carries a SOLID risk tint: the old bg-risk-high-bg/40 wash
  // composited differently over panel and over the zebra header, so its real
  // ratio was not the published one. On the solid tint --muted is 4.638:1
  // light but only 3.698:1 dark, so the row's secondary lines step up to
  // --body (6.211 light / 5.013 dark). Hover is --soft for EVERY row, where
  // muted is 4.755 / 4.582 and body 6.367 / 6.211.
  const meta = high ? 'text-body' : 'text-muted'
  return (
    <Link
      to={`/patients/${p.id}`}
      style={{ '--rise-delay': `${180 + index * 40}ms` } as CSSProperties}
      className={`rise group relative flex cursor-pointer items-center gap-tight px-snug py-tight transition-colors duration-150 hover:bg-soft focus-visible:outline focus-visible:-outline-offset-2 focus-visible:outline-2 focus-visible:outline-brand ${
        high ? 'bg-risk-high-tint' : ''
      }`}
    >
      {high && <span aria-hidden className="absolute inset-y-0 left-0 w-el bg-risk-high-ink" />}
      {/* Identity, not risk: white on --risk-high-ink is 2.273:1 on the dark
          half and there is no --on-risk-high on the web surface, so the disc is
          the mode-invariant brand fill (--on-brand on --brand = 4.602:1 in both
          modes). Risk stays on the group header, the spine and PriorityBadge. */}
      <span
        aria-hidden
        className="grid h-10 w-10 shrink-0 place-items-center rounded-pill bg-brand tabular-nums text-label font-medium text-on-brand"
      >
        {p.initials}
      </span>
      <span className="w-36 shrink-0 sm:w-52">
        <span className="block truncate text-copy-lg font-medium text-ink">
          {p.name}
        </span>
        <span className={`mt-0.5 block truncate text-label ${meta}`}>
          {p.procedure_display.replace(/\s*\(.*\)$/, '')}
          {p.postop_day != null && (
            <>
              {' '}
              ·{' '}
              {/* "D6" means post-op day six, which says nothing true about a
                  patient who never had an operation. */}
              <span className="tabular-nums">
                {p.mode === 'general' ? `${p.postop_day}d` : `D${p.postop_day}`}
              </span>
            </>
          )}
        </span>
      </span>
      <PriorityBadge priority={p.priority} className="hidden shrink-0 lg:inline-flex" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-copy text-body">{p.reason}</span>
        {step && step.state.status === 'open' ? (
          <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="min-w-0 truncate text-copy font-medium text-brand-ink" title={step.detail}>
              → {step.title}
            </span>
            <NextStepButton
              patientId={p.id}
              step={step}
              phone={step.action.tel ?? null}
              canText={p.can_text}
              compact
              onMessage={onMessage}
              onOpen={() => navigate(`/patients/${p.id}`)}
            />
            <ConfidenceChip level={p.data_confidence.level} />
          </span>
        ) : (
          <ConfidenceChip level={p.data_confidence.level} className="mt-1" />
        )}
      </span>
      <span className="hidden w-32 shrink-0 text-right sm:block">
        <span className={`block text-label font-medium tabular-nums ${meta}`}>
          {relativeTime(p.last_checkin_at)}
        </span>
        <span className={`mt-0.5 block truncate text-label ${meta}`}>
          {p.assigned_provider.name}
        </span>
      </span>
      <ChevronRight
        size={18}
        aria-hidden
        className="hidden shrink-0 text-muted transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-ink sm:block"
      />
    </Link>
  )
}
