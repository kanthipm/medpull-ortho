import { CircleCheck, CircleDashed, FileCheck2, RefreshCw, Sparkles } from 'lucide-react'
import { useState } from 'react'
import {
  useApproveDocument,
  useRegenerateDocument,
  useRtmDocuments,
  useRtmStatus,
} from '../../api/queries'
import AIAttribution from '../../components/AIAttribution'
import Disclosure from '../../components/Disclosure'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay, SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'

function ChecklistRow({ done, label, detail }: { done: boolean; label: string; detail?: string }) {
  return (
    <li className="flex items-center gap-2.5 py-2 first:pt-0 last:pb-0">
      {done ? (
        <CircleCheck size={15} className="shrink-0 text-risk-low" />
      ) : (
        <CircleDashed size={15} className="shrink-0 text-faint" />
      )}
      <span className="text-[13px] font-medium text-ink">{label}</span>
      {detail && <span className="text-[12px] font-medium text-faint">· {detail}</span>}
    </li>
  )
}

function DocumentationList({ patientId }: { patientId: string }) {
  const { data, isLoading } = useRtmDocuments(patientId)
  const approve = useApproveDocument(patientId)
  const regenerate = useRegenerateDocument(patientId)
  const toast = useToast()
  const [busyId, setBusyId] = useState<number | null>(null)

  if (isLoading) return <SkeletonCard lines={3} />
  const documents = data?.documents ?? []
  if (documents.length === 0) return null

  return (
    <div className="space-y-3">
      {documents.map((doc) => (
        <div key={doc.id} className="rounded-row border border-line bg-soft/50 p-3.5">
          <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
            <AIAttribution
              kind={doc.kind === 'encounter_note' ? 'encounter note' : 'monthly summary'}
              generatedAt={doc.created_at}
              provider={doc.provider}
            />
            {doc.status === 'approved' ? (
              <span className="chip bg-risk-low-bg text-risk-low">Approved</span>
            ) : (
              <span className="chip bg-risk-med-bg text-risk-med">Awaiting review</span>
            )}
          </div>
          <p className="text-[13px] font-semibold tracking-[-.01em] text-ink">{doc.title}</p>
          <p className="mt-1 text-[12.5px] font-medium leading-[1.55] text-body">{doc.body}</p>
          {doc.status !== 'approved' && (
            <div className="mt-2.5 flex gap-2">
              <button
                type="button"
                disabled={approve.isPending}
                onClick={() =>
                  approve.mutate(doc.id, {
                    onSuccess: () => toast('Documentation approved'),
                    onError: () => toast('Approval failed — try again', 'warning'),
                  })
                }
                className="btn-primary !w-auto px-3 py-1.5 text-[12px]"
              >
                <FileCheck2 size={13} /> Approve
              </button>
              <button
                type="button"
                disabled={regenerate.isPending && busyId === doc.id}
                onClick={() => {
                  setBusyId(doc.id)
                  regenerate.mutate(doc.id, {
                    onSuccess: () => toast('Draft regenerated', 'info'),
                    onError: () => toast('Regeneration failed — try again', 'warning'),
                    onSettled: () => setBusyId(null),
                  })
                }}
                className="qa-btn"
              >
                <RefreshCw
                  size={13}
                  className={regenerate.isPending && busyId === doc.id ? 'animate-spin' : ''}
                />
                Regenerate
              </button>
            </div>
          )}
        </div>
      ))}
      <p className="border-t border-line pt-2 text-[11px] font-medium leading-[1.5] text-faint">
        AI drafts are editable records for provider review — nothing is filed without approval.
      </p>
    </div>
  )
}

export default function RtmReadinessCard({
  patientId,
  refreshing,
}: {
  patientId: string
  refreshing: boolean
}) {
  const { data: rtm, isLoading } = useRtmStatus(patientId)

  if (isLoading) return <SkeletonCard lines={4} />
  if (!rtm) return null

  const monitoringPct = Math.min(100, Math.round((rtm.monitoring.days / rtm.monitoring.target) * 100))

  return (
    <SectionCard
      title="RTM readiness"
      spine={rtm.ready_to_bill ? 'bg-risk-low' : undefined}
      aside={
        rtm.ready_to_bill ? (
          <span className="chip bg-risk-low-bg text-risk-low">Ready to bill</span>
        ) : (
          <span className="chip bg-risk-med-bg text-risk-med">In progress</span>
        )
      }
    >
      <RefreshOverlay show={refreshing} />

      <div className="mb-4">
        <div className="flex items-baseline justify-between">
          <span className="micro">Monitoring progress</span>
          <span className="font-mono text-[13px] font-medium tabular-nums text-ink">
            {!rtm.monitoring.enrolled
              ? `— / ${rtm.monitoring.target} days`
              : rtm.monitoring.eligible
                ? 'Complete'
                : `${Math.min(rtm.monitoring.days, rtm.monitoring.target)} / ${rtm.monitoring.target} days`}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line">
          <div
            className={`h-full rounded-full transition-[width] duration-500 ${
              rtm.monitoring.eligible ? 'bg-risk-low' : 'bg-brand'
            }`}
            style={{ width: `${rtm.monitoring.enrolled ? monitoringPct : 0}%` }}
          />
        </div>
        <p className="mt-1.5 text-[11.5px] font-medium text-faint">
          {!rtm.monitoring.enrolled
            ? 'Monitoring days begin accruing once enrollment is complete'
            : rtm.monitoring.eligible
              ? `Monitoring eligible — ${rtm.monitoring.days} monitoring days this window (16 required)`
              : `${rtm.monitoring.target - rtm.monitoring.days} more monitoring days accrue in this 30-day window`}
        </p>
      </div>

      <ul className="divide-y divide-line">
        <ChecklistRow done={rtm.enrollment.education_complete} label="Education complete" />
        <ChecklistRow done={rtm.enrollment.consent_complete} label="Consent complete" />
        <ChecklistRow
          done={rtm.enrollment.baseline_complete}
          label="Baseline complete"
          detail={rtm.enrollment.pathway ?? undefined}
        />
        <ChecklistRow
          done={rtm.treatment_management.minutes >= 20}
          label={`Provider review: ${rtm.treatment_management.minutes} minutes`}
          detail="20 min target"
        />
        <ChecklistRow
          done={rtm.treatment_management.interactive_communication}
          label="Interactive communication"
          detail={rtm.treatment_management.interactive_communication ? 'logged' : 'required'}
        />
        <ChecklistRow
          done={rtm.documentation_ready}
          label={`Documentation: ${rtm.documentation_ready ? 'ready' : 'awaiting approval'}`}
        />
      </ul>

      <div className="mt-4">
        <span className="micro">Billing eligibility</span>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {rtm.billing.map((code) => (
            <span
              key={code.cpt}
              title={code.note}
              className={`chip font-mono ${
                code.eligible ? 'bg-risk-low-bg text-risk-low' : 'bg-risk-missing-bg text-risk-missing'
              }`}
            >
              CPT {code.cpt}
              {code.units > 1 ? ` ×${code.units}` : ''}
              {!code.eligible && code.note ? ` — ${code.note}` : ''}
            </span>
          ))}
        </div>
      </div>

      <div className="mt-4 flex items-start gap-3 rounded-row border border-line bg-soft/60 p-3">
        <Sparkles size={14} className="mt-0.5 shrink-0 text-brand" />
        <span>
          <span className="micro block">Suggested next action</span>
          <span className="mt-0.5 block text-[13px] font-medium text-ink">{rtm.suggested_action}</span>
        </span>
      </div>

      <div className="mt-3">
        <Disclosure label="Documentation" hint="AI-drafted, provider-approved">
          <DocumentationList patientId={patientId} />
        </Disclosure>
      </div>
    </SectionCard>
  )
}
