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
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'

/** Connection state, in words, on its own opaque tint (pairs measured in
 *  lib/risk.ts: low 4.731 / 6.484, med 5.165 / 6.890, high 4.835 / 5.701,
 *  missing 6.367 / 5.093; "Not linked" is body on soft 6.367 / 6.211). */
function StatusChip({ data }: { data: PatientWearables }) {
  const c = data.connection
  if (!data.aggregator.configured && (!c || c.status === 'disconnected')) {
    return <span className="chip bg-risk-missing-tint text-risk-missing-ink">Demo source</span>
  }
  if (!c || c.status === 'disconnected') {
    return <span className="chip bg-soft text-body">Not linked</span>
  }
  if (c.status === 'linked') {
    return (
      <span className="chip gap-1 bg-risk-low-tint text-risk-low-ink">
        <CircleCheck size={12} aria-hidden /> Linked
      </span>
    )
  }
  if (c.status === 'error') {
    return (
      <span className="chip gap-1 bg-risk-high-tint text-risk-high-ink">
        <TriangleAlert size={12} aria-hidden /> Needs attention
      </span>
    )
  }
  return <span className="chip bg-risk-med-tint text-risk-med-ink">Awaiting patient</span>
}

const DEVICE_STATUS: Record<string, { word: string; dot: string; ink: string }> = {
  connected: { word: 'Connected', dot: 'bg-risk-low-ink', ink: 'text-risk-low-ink' },
  error: { word: 'Error', dot: 'bg-risk-high-ink', ink: 'text-risk-high-ink' },
}

/** One device: model over "status · synced …". The status is a dot AND a
 *  word, so it never rests on colour (low ink on panel 5.4 / 9.4, high 5.6 /
 *  7.6). */
function DeviceRow({ d }: { d: WearableDevice }) {
  const st = DEVICE_STATUS[d.status] ?? {
    word: d.status.replace(/_/g, ' ').replace(/^./, (x) => x.toUpperCase()),
    dot: 'bg-line-strong',
    ink: 'text-secondary',
  }
  return (
    <li className="flex items-center gap-3 py-2.5">
      <Tile size="sm" family="teal" icon={<Watch />} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-copy font-medium text-ink">{d.model}</p>
        <p className="meta flex flex-wrap items-center gap-x-1.5">
          <span className={`inline-flex items-center gap-1 font-medium ${st.ink}`}>
            <span aria-hidden className={`h-1.5 w-1.5 rounded-pill ${st.dot}`} />
            {st.word}
          </span>
          <span aria-hidden>·</span>
          <span className="tabular-nums">
            {d.last_sync_at ? `synced ${relativeTime(d.last_sync_at)}` : 'no sync yet'}
          </span>
        </p>
      </div>
    </li>
  )
}

/** Label over value, like the app's portfolio tiles, on an opaque soft fill
 *  (ink 16.202 / 16.060, body 6.367 / 6.211). */
function Field({
  label,
  children,
  className = '',
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`min-w-0 rounded-control bg-soft px-3 py-2.5 ${className}`}>
      <dt className="text-label text-body">{label}</dt>
      <dd className="mt-0.5 truncate text-copy font-medium tabular-nums text-ink">{children}</dd>
    </div>
  )
}

/** An inline notice on its own opaque tint, icon + words (never colour
 *  alone). med 5.165 / 6.890, high 4.835 / 5.701. */
function Notice({ tone, children }: { tone: 'med' | 'high'; children: ReactNode }) {
  const cls =
    tone === 'high' ? 'bg-risk-high-tint text-risk-high-ink' : 'bg-risk-med-tint text-risk-med-ink'
  return (
    <p className={`mt-3 flex items-start gap-2 rounded-control px-3.5 py-2.5 text-copy font-medium ${cls}`}>
      <TriangleAlert size={16} aria-hidden className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </p>
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
    <Modal
      title={`Connect ${firstName}'s wearable`}
      onClose={onClose}
      footer={
        <>
          <a
            href={link.link_url}
            target="_blank"
            rel="noreferrer"
            className="btn-tinted"
            title="Opens Junction's page in a new tab — hand the device to the patient to sign in"
          >
            <ExternalLink size={16} aria-hidden /> Open here
          </a>
          <button type="button" onClick={copy} className="btn-filled">
            <Copy size={16} aria-hidden /> {copied ? 'Copied' : 'Copy link'}
          </button>
        </>
      }
    >
      <p className="text-copy text-body">
        Share this link with {firstName}. They sign in to their device's account (Oura, Fitbit,
        Garmin, WHOOP, Withings, Polar or Dexcom) on Junction's page — nothing is typed into this
        console. Data starts flowing within minutes and the pre-op history back-fills on its own.
      </p>
      <label className="mt-4 block">
        <span className="text-copy font-medium text-ink">One-time link</span>
        {expiry && <span className="meta ml-1.5">expires {expiry}</span>}
        <input
          readOnly
          value={link.link_url}
          onFocus={(e) => e.currentTarget.select()}
          className="field mt-1.5 font-mono"
        />
      </label>
      <p className="meta mt-3">
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
      <SectionCard title="Wearables" icon={<Tile size="sm" family="teal" icon={<Watch />} />}>
        <p className="text-copy text-secondary">The connection state couldn't be loaded.</p>
      </SectionCard>
    )
  }

  const c = data.connection
  const configured = data.aggregator.configured
  const active = c !== null && c.status !== 'disconnected'
  // An account made under the other Junction environment cannot be reached
  // from this deployment: every route but Disconnect answers 409 for it.
  const wrongEnvironment = active && c.environment !== data.aggregator.environment
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
      onSuccess: (result) => {
        setConfirmDisconnect(false)
        // The local mapping is always retired; whether Junction actually
        // deleted the account is a separate fact the provider must see.
        if (result.remote === 'deleted' || result.remote === 'already_disconnected') {
          toast(`${firstName}'s Junction account was deleted — history stays on the chart`, 'info')
        } else {
          toast(
            `Retired here, but Junction did not confirm deleting the account (${result.remote}) — remove it in the Junction dashboard`,
            'warning',
          )
        }
      },
      onError: (err) => toast(`Disconnect failed — ${err.message}`, 'warning'),
    })

  const runRefresh = () =>
    refresh.mutate(undefined, {
      onSuccess: (r) =>
        r.refresh_error
          ? toast(`Refresh failed — ${r.refresh_error}`, 'warning')
          : toast('Connection state refreshed', 'info'),
      onError: (err) => toast(`Refresh failed — ${err.message}`, 'warning'),
    })

  return (
    <SectionCard
      title="Wearables"
      icon={<Tile size="sm" family="teal" icon={<Watch />} />}
      aside={
        wrongEnvironment ? (
          <span className="chip gap-1 bg-risk-med-tint text-risk-med-ink">
            <TriangleAlert size={12} aria-hidden /> Other environment
          </span>
        ) : (
          <StatusChip data={data} />
        )
      }
    >
      <RefreshOverlay show={refreshing} />

      {!configured && !active && (
        <p className="text-copy text-body">
          {firstName}'s chart runs on the demo data source. Live device linking arrives the moment
          Junction is configured on the Integrations page — the button below lights up and nothing
          else on this chart changes.
        </p>
      )}

      {configured && !active && (
        <p className="text-copy text-body">
          No live wearable is linked. Issue a one-time Junction link for {firstName} to sign in to
          their device's account; readings then flow into this chart automatically.
        </p>
      )}

      {c && active && (
        <dl className="grid grid-cols-2 gap-2">
          <Field label="Devices via Junction" className="col-span-2">
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
        </dl>
      )}

      {c && active && c.status === 'pending_link' && (
        <p className="mt-3 text-copy text-body">
          Waiting for {firstName} to open the link and sign in. Links are single-use and expire
          within the hour — issue a fresh one if needed.
        </p>
      )}

      {c && wrongEnvironment && (
        <Notice tone="med">
          This account lives on Junction's {c.environment} host and this deployment is configured
          for {data.aggregator.environment}. Disconnect it and issue a new link.
        </Notice>
      )}

      {/* The provider-error copy is tied to the error *state*, not to the
          presence of a message: a retired connection can carry a note about
          what Junction did not delete, which is shown as-is. */}
      {c && c.last_error && (c.status === 'error' || c.status === 'disconnected') && (
        <Notice tone="high">
          {c.status === 'error'
            ? `Junction reports a provider error: ${c.last_error}. A new link lets ${firstName} sign in again.`
            : c.last_error}
        </Notice>
      )}

      {data.devices.length > 0 && (
        <ul className="mt-3 divide-y divide-hairline" aria-label="Devices">
          {data.devices.map((d) => (
            <DeviceRow key={d.id} d={d} />
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        {/* A disabled button takes no pointer events, so the reason lives on
            the wrapping span (the Integrations page does the same). */}
        <span
          className="inline-flex"
          title={
            !configured
              ? 'Configure Junction on the Integrations page first'
              : wrongEnvironment
                ? 'Disconnect this account before linking under the current environment'
                : undefined
          }
        >
          <button
            type="button"
            onClick={issueLink}
            disabled={!configured || busy || wrongEnvironment}
            className={active ? 'btn-tinted btn-sm' : 'btn-filled'}
          >
            <Link2 size={16} aria-hidden /> {active ? 'New link' : 'Connect wearable'}
          </button>
        </span>
        {active && (
          <>
            <button
              type="button"
              onClick={runBackfill}
              disabled={busy || wrongEnvironment || c?.status === 'pending_link'}
              className="btn-gray btn-sm"
              title="Ask Junction to re-sync every linked device, then pull the whole ingestible window"
            >
              <RefreshCw
                size={14}
                aria-hidden
                className={backfill.isPending ? 'animate-spin' : ''}
              />{' '}
              Back-fill
            </button>
            <button
              type="button"
              onClick={runRefresh}
              disabled={busy || wrongEnvironment}
              className="btn-gray btn-sm"
            >
              Refresh status
            </button>
            <button
              type="button"
              onClick={() => setConfirmDisconnect(true)}
              disabled={busy}
              className="btn-danger btn-sm"
            >
              <Unplug size={14} aria-hidden /> Disconnect
            </button>
          </>
        )}
      </div>

      {link && <LinkModal link={link} firstName={firstName} onClose={() => setLink(null)} />}

      {confirmDisconnect && (
        <Modal
          title="Disconnect wearable?"
          size="sm"
          onClose={() => setConfirmDisconnect(false)}
          footer={
            <>
              <button type="button" onClick={() => setConfirmDisconnect(false)} className="btn-gray">
                Keep connected
              </button>
              <button type="button" onClick={runDisconnect} disabled={busy} className="btn-danger">
                <Unplug size={16} aria-hidden /> Disconnect
              </button>
            </>
          }
        >
          <p className="text-copy text-body">
            This retires {firstName}'s Junction account and stops new readings. Everything already
            on the chart stays. Reconnecting later means issuing a new link.
          </p>
        </Modal>
      )}
    </SectionCard>
  )
}
