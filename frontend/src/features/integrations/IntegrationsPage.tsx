import { CircleCheck, Footprints, Plug, Smartphone, TriangleAlert, Webhook } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'
import { useIntegrations, useJunctionStatus } from '../../api/queries'
import type {
  AggregatorStatus,
  IntegrationProvider,
  JunctionEvent,
  ProviderStatus,
} from '../../api/types'
import Disclosure from '../../components/Disclosure'
import EmptyState from '../../components/EmptyState'
import SectionCard from '../../components/SectionCard'
import { SkeletonCard } from '../../components/Skeleton'
import { relativeTime } from '../../lib/format'

const CAPABILITY_LABELS: [string, string[]][] = [
  ['Steps', ['steps']],
  ['Heart rate', ['resting_hr', 'hr_sample']],
  ['HRV', ['hrv_rmssd', 'hrv_sdnn']],
  ['Sleep', ['sleep_duration', 'sleep_stages']],
  ['SpO₂', ['spo2']],
  ['Respiration', ['respiratory_rate']],
  ['Temperature', ['skin_temp', 'skin_temp_delta']],
  ['Workouts', ['exercise_session']],
]

const STATUS_CHIP: Record<ProviderStatus, { label: string; className: string; icon?: ReactNode }> = {
  mock_connected: {
    label: 'Connected',
    className: 'bg-risk-low-bg text-risk-low',
    icon: <CircleCheck size={11} />,
  },
  live: { label: 'Live', className: 'bg-risk-low-bg text-risk-low', icon: <CircleCheck size={11} /> },
  needs_setup: { label: 'Needs setup', className: 'bg-risk-med-bg text-risk-med' },
  via_junction: { label: 'Via Junction', className: 'bg-brand-tint text-brand' },
  needs_app: {
    label: 'Needs patient app',
    className: 'bg-risk-missing-bg text-risk-missing',
    icon: <Smartphone size={11} />,
  },
  coming_soon: { label: 'Coming soon', className: 'bg-risk-missing-bg text-risk-missing' },
}

const STATUS_ORDER: Record<ProviderStatus, number> = {
  mock_connected: 0,
  live: 0,
  via_junction: 1,
  needs_setup: 2,
  needs_app: 3,
  coming_soon: 4,
}

function capabilityChips(p: IntegrationProvider): string[] {
  return CAPABILITY_LABELS.filter(([, keys]) =>
    keys.some((k) => p.capabilities.includes(k)),
  ).map(([label]) => label)
}

function buttonFor(p: IntegrationProvider, aggregatorConfigured: boolean) {
  switch (p.status) {
    case 'mock_connected':
      return {
        label: 'Manage connection',
        title: 'This is the demo data source — there is no live connection to manage.',
      }
    case 'via_junction':
      return {
        label: 'Link per patient',
        title: aggregatorConfigured
          ? `Open a patient record and use Connect wearable — the patient signs in to ${p.name} on Junction's page.`
          : `Set JUNCTION_API_KEY to link ${p.name} devices from a patient record.`,
      }
    case 'needs_app':
      return {
        label: 'Connect',
        title: `${p.name} lives on the phone. It reaches Junction through its mobile SDK inside a patient app, which is not built yet.`,
      }
    default:
      return { label: 'Connect', title: 'No integration path yet.' }
  }
}

function ProviderCard({
  p,
  index,
  aggregatorConfigured,
}: {
  p: IntegrationProvider
  index: number
  aggregatorConfigured: boolean
}) {
  const active = p.status === 'mock_connected' || p.status === 'live'
  const chip = STATUS_CHIP[p.status]
  const button = buttonFor(p, aggregatorConfigured)
  return (
    <div
      style={{ '--rise-delay': `${160 + index * 45}ms` } as CSSProperties}
      className={`rise relative flex flex-col overflow-hidden rounded-card border border-line bg-panel p-4 ${
        active ? 'pl-[18px]' : ''
      }`}
    >
      {active && <span aria-hidden className="absolute inset-y-0 left-0 w-[2px] bg-risk-low" />}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span
            aria-hidden
            className={`grid h-8 w-8 shrink-0 place-items-center rounded-btn ${
              active ? 'bg-brand text-white' : 'bg-soft text-faint'
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
        <span className={`chip ${chip.className}`}>
          {chip.icon}
          {chip.label}
        </span>
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

      {/* No card button has a click target: the demo source has nothing to
          manage, brands are linked from a patient record, and the on-device
          stores wait on the patient app. The span carries the tooltip because
          a disabled button takes no pointer events. */}
      <div className="mt-auto pt-4">
        <span className="block" title={button.title}>
          <button type="button" disabled className="qa-btn w-full">
            {button.label}
          </button>
        </span>
      </div>
    </div>
  )
}

function Readout({ label, value, tone }: { label: string; value: ReactNode; tone?: 'ok' | 'warn' }) {
  return (
    <div className="min-w-0">
      <p className="micro">{label}</p>
      <p
        className={`mt-0.5 truncate text-[13px] font-semibold ${
          tone === 'ok' ? 'text-risk-low' : tone === 'warn' ? 'text-risk-med' : 'text-ink'
        }`}
      >
        {value}
      </p>
    </div>
  )
}

function EventRow({ e }: { e: JunctionEvent }) {
  const tone =
    e.status === 'processed'
      ? 'text-risk-low'
      : e.status === 'ignored'
        ? 'text-faint'
        : 'text-risk-high'
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-1.5 text-[12px] font-medium">
      <span className="font-mono text-[11px] text-faint">{e.received_at ? relativeTime(e.received_at) : '—'}</span>
      <span className="text-body">{e.event_type ?? 'unknown event'}</span>
      <span className={`font-mono text-[11px] uppercase tracking-[.04em] ${tone}`}>{e.status}</span>
      {e.error && <span className="basis-full text-[11.5px] text-muted">{e.error}</span>}
    </li>
  )
}

function AggregatorCard({ a, events }: { a: AggregatorStatus; events: JunctionEvent[] | undefined }) {
  const endpoint = `${window.location.origin}${a.webhook_path}`
  return (
    <SectionCard
      sum
      spine={a.configured ? 'bg-risk-low' : 'bg-risk-med'}
      className="rise mt-6"
      style={{ '--rise-delay': '60ms' } as CSSProperties}
      eyebrow={<p className="micro mb-1.5">Wearable aggregator</p>}
      title="Junction"
      aside={
        a.configured ? (
          <span className="chip bg-risk-low-bg text-risk-low">
            <CircleCheck size={11} /> Live · {a.environment}
          </span>
        ) : (
          <span className="chip bg-risk-med-bg text-risk-med">
            <TriangleAlert size={11} /> Needs setup
          </span>
        )
      }
    >
      <p className="text-[13.5px] font-medium leading-[1.55] text-body">
        {a.configured ? (
          <>
            One Junction account per patient, issued from the patient record. Every device a
            patient links on Junction's page delivers through{' '}
            <span className="font-mono text-[12.5px] text-ink">{a.webhook_path}</span> into the same
            normalized observation store the demo source uses — the worklist never learns which
            brand it came from.
          </>
        ) : (
          <>
            The connector is built and idle. Set{' '}
            <span className="font-mono text-[12.5px] text-ink">JUNCTION_API_KEY</span> and{' '}
            <span className="font-mono text-[12.5px] text-ink">JUNCTION_WEBHOOK_SECRET</span>{' '}
            (in <span className="font-mono text-[12.5px] text-ink">.env</span>, or Parameter Store
            on AWS), then register the endpoint below in Junction's webhook dashboard. Until then
            this workspace runs on the demo data source.
          </>
        )}
      </p>

      <div className="mt-4 grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
        <Readout label="Environment" value={`${a.environment} · ${a.region.toUpperCase()}`} />
        <Readout
          label="Webhook secret"
          value={a.webhook_secret_configured ? 'Configured' : 'Missing — deliveries rejected'}
          tone={a.webhook_secret_configured ? 'ok' : 'warn'}
        />
        <Readout
          label="Patients linked"
          value={
            a.connections.total === 0
              ? 'None yet'
              : `${a.connections.linked} linked · ${a.connections.pending} pending${
                  a.connections.error ? ` · ${a.connections.error} error` : ''
                }`
          }
        />
        <Readout
          label="Last delivery"
          value={a.last_delivery_at ? relativeTime(a.last_delivery_at) : 'Never'}
        />
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 rounded-btn border border-line bg-panel px-3 py-2">
        <Webhook size={14} className="shrink-0 text-faint" />
        <span className="micro">Webhook endpoint</span>
        <code className="min-w-0 truncate font-mono text-[12px] text-ink">{endpoint}</code>
      </div>

      {a.configured && (
        <div className="mt-2">
          <Disclosure label="Recent deliveries" hint={events ? `${events.length} shown` : undefined}>
            {events && events.length > 0 ? (
              <ul className="divide-y divide-line">
                {events.map((e) => (
                  <EventRow key={e.id} e={e} />
                ))}
              </ul>
            ) : (
              <p className="text-[12.5px] font-medium text-muted">
                Nothing received yet. Junction sends a delivery the moment a patient links a device.
              </p>
            )}
          </Disclosure>
        </div>
      )}
    </SectionCard>
  )
}

export default function IntegrationsPage() {
  const { data, isLoading, isError } = useIntegrations()
  const configured = data?.aggregator.configured ?? false
  const status = useJunctionStatus(configured)

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

  const providers = data.providers
    .filter((p) => p.key !== 'junction')
    .sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status])

  return (
    <div>
      {header}

      <AggregatorCard a={data.aggregator} events={status.data?.recent_events} />

      <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {providers.map((p, i) => (
          <ProviderCard key={p.key} p={p} index={i} aggregatorConfigured={configured} />
        ))}
      </div>

      <p className="mt-6 border-t border-line pt-2 text-[11px] font-medium leading-[1.5] text-faint">
        Gait &amp; mobility metrics (walking speed, asymmetry, steadiness) are measured only by
        Apple devices, and Apple Health reaches Junction only through its mobile SDK inside a
        patient app. A patient chart carries a card for each signal their own device reported,
        so those cards are simply absent for everyone else.
      </p>
    </div>
  )
}
