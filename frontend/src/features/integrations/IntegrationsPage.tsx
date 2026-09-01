import { CircleCheck, Footprints, Plug } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useIntegrations } from '../../api/queries'
import type { IntegrationProvider } from '../../api/types'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard } from '../../components/Skeleton'

const CAPABILITY_LABELS: [string, string[]][] = [
  ['Steps', ['steps']],
  ['Heart rate', ['resting_hr', 'hr_sample']],
  ['HRV', ['hrv_rmssd']],
  ['Sleep', ['sleep_duration', 'sleep_stages']],
  ['SpO₂', ['spo2']],
  ['Respiration', ['respiratory_rate']],
  ['Temperature', ['skin_temp']],
  ['Workouts', ['exercise_session']],
]

function capabilityChips(p: IntegrationProvider): string[] {
  return CAPABILITY_LABELS.filter(([, keys]) =>
    keys.some((k) => p.capabilities.includes(k)),
  ).map(([label]) => label)
}

function ProviderCard({ p, index }: { p: IntegrationProvider; index: number }) {
  const connected = p.status === 'mock_connected'
  return (
    <div
      style={{ '--rise-delay': `${120 + index * 45}ms` } as CSSProperties}
      className={`rise relative flex flex-col overflow-hidden rounded-card border border-line bg-panel p-4 ${
        connected ? 'pl-[18px]' : ''
      }`}
    >
      {connected && <span aria-hidden className="absolute inset-y-0 left-0 w-[2px] bg-risk-low" />}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden
            className={`grid h-8 w-8 shrink-0 place-items-center rounded-btn ${
              connected ? 'bg-brand text-white' : 'bg-soft text-faint'
            }`}
          >
            <Plug size={14} />
          </span>
          <div>
            <h3 className="text-[14px] font-semibold tracking-[-.01em] text-ink">{p.name}</h3>
            {p.connected_patients > 0 && (
              <p className="mt-0.5 font-mono text-[11px] font-medium text-faint">
                {p.connected_patients} patient{p.connected_patients === 1 ? '' : 's'} on this
                device
              </p>
            )}
          </div>
        </div>
        {connected ? (
          <span className="chip bg-risk-low-bg text-risk-low">
            <CircleCheck size={11} /> Connected
          </span>
        ) : (
          <span className="chip bg-risk-missing-bg text-risk-missing">Coming soon</span>
        )}
      </div>

      <div className="mt-3.5 flex flex-wrap gap-1.5">
        {capabilityChips(p).map((label) => (
          <span key={label} className="chip bg-soft text-muted">
            {label}
          </span>
        ))}
        {p.gait_capable && (
          <span className="chip bg-brand-tint text-brand">
            <Footprints size={11} /> Gait & mobility
          </span>
        )}
      </div>

      {/* Neither button has anywhere to go yet: the demo source has no live
          connection behind it, and the provider connect flow arrives with the
          aggregator. The span carries the tooltip because a disabled button
          takes no pointer events. */}
      <div className="mt-auto pt-4">
        <span
          className="block"
          title={
            connected
              ? 'This workspace runs on the demo data source — there is no live connection to manage yet.'
              : 'Connecting a live provider arrives with the wearable aggregator integration.'
          }
        >
          <button type="button" disabled className="qa-btn w-full">
            {connected ? 'Manage connection' : 'Connect'}
          </button>
        </span>
      </div>
    </div>
  )
}

export default function IntegrationsPage() {
  const { data, isLoading, isError } = useIntegrations()

  const header = (
    <div className="rise" style={{ '--rise-delay': '0ms' } as CSSProperties}>
      <h1 className="text-[26px] font-semibold tracking-[-.03em] text-ink">Integrations</h1>
      <p className="mt-1 max-w-2xl text-[13px] font-medium text-muted">
        Every source feeds the same Recovery Intelligence Engine through one normalized data
        store — connecting a new provider never changes what you see on the worklist.
      </p>
    </div>
  )

  if (isLoading) {
    return (
      <div>
        {header}
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          <SkeletonCard lines={3} />
          <SkeletonCard lines={3} />
          <SkeletonCard lines={3} />
        </div>
      </div>
    )
  }
  if (isError || !data) {
    return <EmptyState title="Integrations couldn't be loaded." />
  }

  const providers = [...data.providers].sort(
    (a, b) => (a.status === 'mock_connected' ? -1 : 0) - (b.status === 'mock_connected' ? -1 : 0),
  )

  return (
    <div>
      {header}

      <SectionCard
        sum
        spine="bg-brand"
        className="rise mt-6"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        <p className="micro mb-1.5">Data pipeline</p>
        <p className="text-[13.5px] font-medium leading-[1.55] text-body">
          This workspace is running on the{' '}
          <span className="font-semibold text-ink">demo data source</span>. Production connections
          go live through a wearable aggregator (Terra or Junction) plus Apple Health for gait
          metrics — the connector scaffolding, webhook endpoint, and normalized observation
          store are already in place.
        </p>
      </SectionCard>

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {providers.map((p, i) => (
          <ProviderCard key={p.key} p={p} index={i} />
        ))}
      </div>

      <p className="mt-6 border-t border-line pt-2 text-[11px] font-medium leading-[1.5] text-faint">
        Gait &amp; mobility metrics (walking speed, asymmetry, steadiness) are measured only by
        Apple devices. A patient chart carries a card for each signal their own device
        reported, so those cards are simply absent for everyone else.
      </p>
    </div>
  )
}
