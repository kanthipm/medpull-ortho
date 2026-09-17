import {
  Activity,
  CircleCheck,
  Clock,
  HeartPulse,
  Plug,
  Smartphone,
  TriangleAlert,
  Watch,
  Waypoints,
  Webhook,
  Wrench,
} from 'lucide-react'
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
import ListRow, { ListGroup } from '../../components/ListRow'
import { SkeletonCard } from '../../components/Skeleton'
import Tile, { type TileFamily } from '../../components/Tile'
import { relativeTime } from '../../lib/format'
import { GroupFooter, GroupHeader, SettingsHero } from '../settings/Switch'

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

/** Providers are grouped by status, iOS-settings style. The group header
 *  names the state, so the rows carry no status chip (R7). */
type GroupKey = 'connected' | 'junction' | 'setup' | 'app' | 'soon'
const GROUP_OF: Record<ProviderStatus, GroupKey> = {
  mock_connected: 'connected',
  live: 'connected',
  via_junction: 'junction',
  needs_setup: 'setup',
  needs_app: 'app',
  coming_soon: 'soon',
}
const GROUPS: {
  key: GroupKey
  title: string
  family: TileFamily
  icon: ReactNode
  footer?: string
}[] = [
  { key: 'connected', title: 'Connected', family: 'teal', icon: <Activity /> },
  {
    key: 'junction',
    title: 'Through Junction',
    family: 'blue',
    icon: <Waypoints />,
    footer: 'Link these from a patient record with Connect wearable. The patient signs in on Junction’s page.',
  },
  { key: 'setup', title: 'Needs setup', family: 'blue', icon: <Wrench /> },
  {
    key: 'app',
    title: 'Needs the patient app',
    family: 'violet',
    icon: <Smartphone />,
    footer:
      'These stores live on the phone and reach Junction through its mobile SDK inside a patient app.',
  },
  { key: 'soon', title: 'Coming soon', family: 'indigo', icon: <Clock /> },
]

/** Rows with a 40px tile: 16 + 40 + 12. */
const TILE_LG_INSET = 68

function capabilities(p: IntegrationProvider): string {
  const labels = CAPABILITY_LABELS.filter(([, keys]) =>
    keys.some((k) => p.capabilities.includes(k)),
  ).map(([label]) => label)
  if (p.gait_capable) labels.push('Gait and mobility')
  return labels.join(' · ')
}

function guidance(p: IntegrationProvider, aggregatorConfigured: boolean): string {
  switch (p.status) {
    case 'mock_connected':
      return 'The demo data source. There is no live connection to manage.'
    case 'live':
      return 'Delivering data now.'
    case 'via_junction':
      return aggregatorConfigured
        ? `Open a patient record and use Connect wearable to link ${p.name}.`
        : `Set JUNCTION_API_KEY to link ${p.name} devices from a patient record.`
    case 'needs_app':
      return `${p.name} lives on the phone, so it waits on the patient app.`
    case 'needs_setup':
      return 'The connector needs credentials before it can deliver.'
    default:
      return 'No integration path yet.'
  }
}

function ProviderRow({ p, family, icon, aggregatorConfigured }: {
  p: IntegrationProvider
  family: TileFamily
  icon: ReactNode
  aggregatorConfigured: boolean
}) {
  const caps = capabilities(p)
  return (
    <ListRow
      leading={<Tile size="lg" family={family} icon={icon} />}
      title={p.name}
      subtitle={guidance(p, aggregatorConfigured)}
      meta={caps || undefined}
      aside={
        p.connected_patients > 0 ? (
          <span className="meta whitespace-nowrap tabular-nums">
            {p.connected_patients} patient{p.connected_patients === 1 ? '' : 's'}
          </span>
        ) : undefined
      }
    />
  )
}

// --- Junction ------------------------------------------------------------------

/** A readout on an OPAQUE panel tile inside the tinted card, so the state
 *  inks sit on --panel (risk-low 5.369 / 9.035, risk-med 5.815 / 9.641) and
 *  the label reads --body (the card's on-tint scope). State is also in words
 *  and in the glyph, never colour alone. */
function Readout({
  label,
  value,
  tone,
}: {
  label: string
  value: ReactNode
  tone?: 'ok' | 'warn'
}) {
  return (
    <div className="min-w-0 rounded-control bg-panel px-3.5 py-3">
      <p className="text-label font-medium tracking-label text-secondary">{label}</p>
      <p
        className={`mt-1 flex items-center gap-1.5 text-copy-lg font-medium ${
          tone === 'ok' ? 'text-risk-low-ink' : tone === 'warn' ? 'text-risk-med-ink' : 'text-ink'
        }`}
      >
        {tone === 'ok' && <CircleCheck size={16} aria-hidden className="shrink-0" />}
        {tone === 'warn' && <TriangleAlert size={16} aria-hidden className="shrink-0" />}
        <span className="min-w-0 truncate">{value}</span>
      </p>
    </div>
  )
}

function EventRow({ e }: { e: JunctionEvent }) {
  // On --panel: risk-low 5.369 / 9.035, risk-high 5.622 / 7.563; 'ignored'
  // is secondary (--body in this on-tint scope).
  const tone =
    e.status === 'processed'
      ? 'text-risk-low-ink'
      : e.status === 'ignored'
        ? 'text-secondary'
        : 'text-risk-high-ink'
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-4 py-2.5 text-copy">
      <span className="meta w-20 shrink-0 tabular-nums">
        {e.received_at ? relativeTime(e.received_at) : 'Unknown'}
      </span>
      <span className="min-w-0 flex-1 text-ink">{e.event_type ?? 'unknown event'}</span>
      <span className={`font-mono text-label ${tone}`}>{e.status}</span>
      {e.error && <span className="meta basis-full pl-[5.75rem]">{e.error}</span>}
    </li>
  )
}

function Code({ children }: { children: ReactNode }) {
  return (
    <code className="rounded-[6px] bg-panel px-1.5 py-0.5 font-mono text-copy text-ink">
      {children}
    </code>
  )
}

function AggregatorCard({ a, events }: { a: AggregatorStatus; events: JunctionEvent[] | undefined }) {
  const endpoint = `${window.location.origin}${a.webhook_path}`
  return (
    <section
      aria-labelledby="junction-title"
      className="card-tint rise mt-8 p-5 sm:p-6"
      style={{ '--rise-delay': '60ms' } as CSSProperties}
    >
      <div className="flex flex-wrap items-start gap-x-4 gap-y-3">
        {/* R1: on the brand-tint card the tile is panel-filled (a brand-tint
            tile would be 1:1 against it). brand-ink glyph on panel 5.746 / 6.783. */}
        <Tile size="lg" family="blue" icon={<Waypoints />} className="!bg-panel" />
        <div className="min-w-0 flex-1">
          <p className="meta">Wearable aggregator</p>
          <h2 id="junction-title" className="text-title font-semibold text-ink">
            Junction
          </h2>
        </div>
        {a.configured ? (
          <span className="chip bg-risk-low-tint text-risk-low-ink">
            <CircleCheck size={12} aria-hidden /> Live · {a.environment}
          </span>
        ) : (
          <span className="chip bg-risk-med-tint text-risk-med-ink">
            <TriangleAlert size={12} aria-hidden /> Needs setup
          </span>
        )}
      </div>

      <p className="mt-4 max-w-3xl text-copy-lg text-body">
        {a.configured ? (
          <>
            Each patient gets one Junction account, issued from their record. Every device they
            link on Junction’s page delivers through <Code>{a.webhook_path}</Code> into the same
            observation store the demo source uses, so the worklist never learns which brand the
            data came from.
          </>
        ) : (
          <>
            The connector is built and idle. Set <Code>JUNCTION_API_KEY</Code> and{' '}
            <Code>JUNCTION_WEBHOOK_SECRET</Code> (in <Code>.env</Code>, or Parameter Store on
            AWS), then register the endpoint below in Junction’s webhook dashboard. Until then
            this workspace runs on the demo data source.
          </>
        )}
      </p>

      <div className="mt-5 grid gap-2 sm:grid-cols-2">
        <Readout label="Environment" value={`${a.environment} · ${a.region.toUpperCase()}`} />
        <Readout
          label="Webhook secret"
          value={a.webhook_secret_configured ? 'Configured' : 'Missing, so deliveries are rejected'}
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

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-control bg-panel px-3.5 py-3">
        <Webhook size={16} aria-hidden className="shrink-0 text-cat-blue-ink" />
        <span className="text-copy font-medium text-secondary">Webhook endpoint</span>
        <code className="min-w-0 flex-1 truncate font-mono text-copy text-ink">{endpoint}</code>
      </div>

      {a.configured && (
        <div className="mt-3">
          <Disclosure label="Recent deliveries" hint={events ? `${events.length} shown` : undefined}>
            {events && events.length > 0 ? (
              <ul className="card-group" style={{ ['--row-inset' as string]: '16px' }}>
                {events.map((e) => (
                  <EventRow key={e.id} e={e} />
                ))}
              </ul>
            ) : (
              <p className="text-copy text-secondary">
                Nothing received yet. Junction sends a delivery as soon as a patient links a
                device.
              </p>
            )}
          </Disclosure>
        </div>
      )}
    </section>
  )
}

// --- page ----------------------------------------------------------------------

export default function IntegrationsPage() {
  const { data, isLoading, isError } = useIntegrations()
  const configured = data?.aggregator.configured ?? false
  const status = useJunctionStatus(configured)

  const header = (
    <SettingsHero
      icon={<Plug />}
      badge={<span className="badge-ring">One data store for every source</span>}
      title="Integrations"
      decor={[<Watch key="watch" />, <Waypoints key="junction" />, <HeartPulse key="vitals" />]}
    >
      Every source feeds the same Recovery Intelligence Engine, so connecting a new provider
      never changes what you see on the worklist.
    </SettingsHero>
  )

  if (isLoading) {
    return (
      <div className="pb-10">
        {header}
        <div className="mt-8 space-y-8">
          <SkeletonCard lines={4} />
          <SkeletonCard rows={4} />
        </div>
      </div>
    )
  }
  if (isError || !data) {
    return (
      <div className="pb-10">
        {header}
        <EmptyState title="Integrations couldn't be loaded." icon={<Plug />} className="mt-8">
          Refresh the page to try again.
        </EmptyState>
      </div>
    )
  }

  const providers = data.providers.filter((p) => p.key !== 'junction')

  return (
    <div className="pb-10">
      {header}

      <AggregatorCard a={data.aggregator} events={status.data?.recent_events} />

      {GROUPS.map((g, i) => {
        const rows = providers.filter((p) => GROUP_OF[p.status] === g.key)
        if (rows.length === 0) return null
        const id = `providers-${g.key}`
        return (
          <section
            key={g.key}
            aria-labelledby={id}
            className="rise mt-8"
            style={{ '--rise-delay': `${120 + i * 40}ms` } as CSSProperties}
          >
            <GroupHeader id={id}>{g.title}</GroupHeader>
            <ListGroup inset={TILE_LG_INSET} aria-labelledby={id}>
              {rows.map((p) => (
                <ProviderRow
                  key={p.key}
                  p={p}
                  family={g.family}
                  icon={g.icon}
                  aggregatorConfigured={configured}
                />
              ))}
            </ListGroup>
            {g.footer && <GroupFooter>{g.footer}</GroupFooter>}
          </section>
        )
      })}

      <p className="meta mt-10 max-w-3xl px-4">
        Gait and mobility metrics (walking speed, asymmetry, steadiness) come only from Apple
        devices, and Apple Health reaches Junction only through its mobile SDK inside a patient
        app. A patient’s chart shows a card for each signal their own device reported, so those
        cards are absent for everyone else.
      </p>
    </div>
  )
}
