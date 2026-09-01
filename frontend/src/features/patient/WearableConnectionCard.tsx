import {
  CircleCheck,
  Copy,
  ExternalLink,
  Link2,
  RefreshCw,
  TriangleAlert,
  Unplug,
  Watch,
} from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import {
  useCreateJunctionLink,
  useDisconnectJunction,
  useJunctionBackfill,
  usePatientWearables,
  useRefreshWearables,
} from '../../api/queries'
import type { JunctionLink, PatientWearables, WearableDevice } from '../../api/types'
import Modal from '../../components/Modal'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay, SkeletonCard } from '../../components/Skeleton'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'

function StatusChip({ data }: { data: PatientWearables }) {
  const c = data.connection
  if (!data.aggregator.configured && (!c || c.status === 'disconnected')) {
    return <span className="chip bg-risk-missing-bg text-risk-missing">Demo source</span>
  }
  if (!c || c.status === 'disconnected') {
    return <span className="chip bg-soft text-muted">Not linked</span>
  }
  if (c.status === 'linked') {
    return (
      <span className="chip bg-risk-low-bg text-risk-low">
        <CircleCheck size={11} /> Linked
      </span>
    )
  }
  if (c.status === 'error') {
    return (
      <span className="chip bg-risk-high-bg text-risk-high">
        <TriangleAlert size={11} /> Needs attention
      </span>
    )
  }
  return <span className="chip bg-risk-med-bg text-risk-med">Awaiting patient</span>
}

function DeviceRow({ d }: { d: WearableDevice }) {
  const tone =
    d.status === 'connected' ? 'text-risk-low' : d.status === 'error' ? 'text-risk-high' : 'text-faint'
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-1.5 text-[12.5px] font-medium">
      <Watch size={13} className="relative top-[2px] shrink-0 text-faint" />
      <span className="text-ink">{d.model}</span>
      <span className={`font-mono text-[11px] uppercase tracking-[.04em] ${tone}`}>{d.status}</span>
      <span className="text-faint">
        {d.last_sync_at ? `synced ${relativeTime(d.last_sync_at)}` : 'no sync yet'}
      </span>
    </li>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="micro">{label}</p>
      <p className="mt-0.5 truncate text-[13px] font-semibold text-ink">{children}</p>
    </div>
  )
}

function LinkModal({
  link,
  firstName,
  onClose,
}: {
  link: JunctionLink
  firstName: string
  onClose: () => void
}) {
  const toast = useToast()
  const [copied, setCopied] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link.link_url)
      setCopied(true)
      toast('Link copied', 'success')
    } catch {
      toast('Copy failed — select the link and copy it by hand', 'warning')
    }
  }
  const expiry = link.expires_at
    ? new Date(link.expires_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    : null
  return (
    <Modal title={`Connect ${firstName}'s wearable`} onClose={onClose}>
      <p className="text-[13px] font-medium leading-[1.55] text-body">
        Share this link with {firstName}. They sign in to their device's account (Oura, Fitbit,
        Garmin, WHOOP, Withings, Polar or Dexcom) on Junction's page — nothing is typed into this
        console. Data starts flowing within minutes and the pre-op history back-fills on its own.
      </p>
      <label className="mt-4 block">
        <span className="micro">One-time link{expiry ? ` · expires ${expiry}` : ''}</span>
        <input
          readOnly
          value={link.link_url}
          onFocus={(e) => e.currentTarget.select()}
          className="mt-1 w-full rounded-btn border border-line bg-soft px-3 py-2 font-mono text-[12px] text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
        />
      </label>
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={copy} className="btn-primary w-auto">
          <Copy size={14} /> {copied ? 'Copied' : 'Copy link'}
        </button>
        <a
          href={link.link_url}
          target="_blank"
          rel="noreferrer"
          className="qa-btn"
          title="Opens Junction's page in a new tab — hand the device to the patient to sign in"
        >
          <ExternalLink size={14} /> Open here
        </a>
      </div>
      <p className="mt-3 text-[11.5px] font-medium leading-[1.5] text-faint">
        The link is single-use. Issue a new one if it expires before {firstName} gets to it.
      </p>
    </Modal>
  )
}

export default function WearableConnectionCard({
  patientId,
  patientName,
  refreshing,
}: {
  patientId: string
  patientName: string
  refreshing: boolean
}) {
  const toast = useToast()
  const { data, isLoading, isError } = usePatientWearables(patientId)
  const createLink = useCreateJunctionLink(patientId)
  const backfill = useJunctionBackfill(patientId)
  const disconnect = useDisconnectJunction(patientId)
  const refresh = useRefreshWearables(patientId)
  const [link, setLink] = useState<JunctionLink | null>(null)
  const [confirmDisconnect, setConfirmDisconnect] = useState(false)
  const firstName = patientName.split(' ')[0]

  if (isLoading) return <SkeletonCard lines={2} />
  if (isError || !data) {
    return (
      <SectionCard title="Wearable connection">
        <p className="text-[13px] font-medium text-muted">The connection state couldn't be loaded.</p>
      </SectionCard>
    )
  }

  const c = data.connection
  const configured = data.aggregator.configured
  const active = c !== null && c.status !== 'disconnected'
  const busy = createLink.isPending || backfill.isPending || disconnect.isPending || refresh.isPending

  const issueLink = () =>
    createLink.mutate(undefined, {
      onSuccess: (result) => setLink(result),
      onError: (err) => toast(`Couldn't issue a link — ${err.message}`, 'warning'),
    })

  const runBackfill = () =>
    backfill.mutate(
      { refresh: true },
      {
        onSuccess: (r) => {
          const landed = r.ingested + r.updated
          toast(
            landed
              ? `Back-fill landed ${landed} reading${landed === 1 ? '' : 's'} (${r.start} → ${r.end})${
                  r.complete ? '' : ' — partial, run again to finish'
                }`
              : `Nothing new from Junction (${r.duplicates} already on file)`,
            landed ? 'success' : 'info',
          )
        },
        onError: (err) => toast(`Back-fill failed — ${err.message}`, 'warning'),
      },
    )

  const runDisconnect = () =>
    disconnect.mutate(undefined, {
      onSuccess: () => {
        setConfirmDisconnect(false)
        toast(`${firstName}'s Junction account was retired — history stays on the chart`, 'info')
      },
      onError: (err) => toast(`Disconnect failed — ${err.message}`, 'warning'),
    })

  const runRefresh = () =>
    refresh.mutate(undefined, {
      onSuccess: (r) =>
        r.refresh_error
          ? toast(`Junction didn't answer — ${r.refresh_error}`, 'warning')
          : toast('Connection state refreshed', 'info'),
      onError: (err) => toast(`Refresh failed — ${err.message}`, 'warning'),
    })

  return (
    <SectionCard
      title="Wearable connection"
      spine={active && c?.status === 'linked' ? 'bg-risk-low' : undefined}
      aside={<StatusChip data={data} />}
    >
      <RefreshOverlay show={refreshing} />

      {!configured && !active && (
        <p className="text-[13px] font-medium leading-[1.55] text-body">
          {firstName}'s chart runs on the demo data source. Live device linking arrives the moment
          Junction is configured on the Integrations page — the button below lights up and nothing
          else on this chart changes.
        </p>
      )}

      {configured && !active && (
        <p className="text-[13px] font-medium leading-[1.55] text-body">
          No live wearable is linked. Issue a one-time Junction link for {firstName} to sign in to
          their device's account; readings then flow into this chart automatically.
        </p>
      )}

      {c && active && (
        <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Devices via Junction">
            {c.providers.length === 0
              ? c.status === 'pending_link'
                ? 'None yet'
                : '—'
              : c.providers.map((p) => `${p.name}${p.status === 'error' ? ' (error)' : ''}`).join(', ')}
          </Field>
          <Field label="Last reading">{c.last_data_at ? relativeTime(c.last_data_at) : 'None yet'}</Field>
          <Field label="Last back-fill">
            {c.last_backfill_at ? relativeTime(c.last_backfill_at) : 'Not run'}
          </Field>
          <Field label="Link issued">
            {c.last_link_issued_at ? relativeTime(c.last_link_issued_at) : '—'}
          </Field>
        </div>
      )}

      {c && active && c.status === 'pending_link' && (
        <p className="mt-3 text-[12.5px] font-medium leading-[1.5] text-muted">
          Waiting for {firstName} to open the link and sign in. Links are single-use and expire
          within the hour — issue a fresh one if needed.
        </p>
      )}

      {c && active && c.last_error && (
        <p className="mt-3 flex items-start gap-2 rounded-btn border border-risk-high/30 bg-risk-high-bg px-3 py-2 text-[12.5px] font-medium leading-[1.5] text-risk-high">
          <TriangleAlert size={14} className="mt-0.5 shrink-0" />
          <span>
            Junction reports a provider error: {c.last_error}. A new link lets {firstName} sign in
            again.
          </span>
        </p>
      )}

      {data.devices.length > 0 && (
        <ul className="mt-3 divide-y divide-line border-t border-line">
          {data.devices.map((d) => (
            <DeviceRow key={d.id} d={d} />
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={issueLink}
          disabled={!configured || busy}
          className={active ? 'qa-btn' : 'btn-primary w-auto'}
          title={configured ? undefined : 'Configure Junction on the Integrations page first'}
        >
          <Link2 size={14} /> {active ? 'New link' : 'Connect wearable'}
        </button>
        {active && (
          <>
            <button
              type="button"
              onClick={runBackfill}
              disabled={busy || c?.status === 'pending_link'}
              className="qa-btn"
              title="Ask Junction to re-sync every linked device, then pull the whole ingestible window"
            >
              <RefreshCw size={14} className={backfill.isPending ? 'animate-spin' : ''} /> Back-fill
            </button>
            <button type="button" onClick={runRefresh} disabled={busy} className="qa-btn">
              Refresh status
            </button>
            <button
              type="button"
              onClick={() => setConfirmDisconnect(true)}
              disabled={busy}
              className="qa-btn text-risk-high hover:border-risk-high/40"
            >
              <Unplug size={14} /> Disconnect
            </button>
          </>
        )}
      </div>

      {link && <LinkModal link={link} firstName={firstName} onClose={() => setLink(null)} />}

      {confirmDisconnect && (
        <Modal title="Disconnect wearable" onClose={() => setConfirmDisconnect(false)}>
          <p className="text-[13px] font-medium leading-[1.55] text-body">
            This retires {firstName}'s Junction account and stops new readings. Everything already
            on the chart stays. Reconnecting later means issuing a new link.
          </p>
          <div className="mt-4 flex gap-2">
            <button type="button" onClick={runDisconnect} disabled={busy} className="btn-primary w-auto">
              Disconnect
            </button>
            <button type="button" onClick={() => setConfirmDisconnect(false)} className="qa-btn">
              Keep connected
            </button>
          </div>
        </Modal>
      )}
    </SectionCard>
  )
}
