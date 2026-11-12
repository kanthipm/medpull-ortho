import { Download, ListFilter } from 'lucide-react'
import { Fragment, useState } from 'react'
import { downloadExport, useReadings, type Reading, type ReadingFilters } from '../../../api/data'
import SectionCard from '../../../components/SectionCard'
import Tile from '../../../components/Tile'
import { useToast } from '../../../components/Toast'
import { shortDate } from '../../../lib/format'
import { Busy, ViewState } from '../DataBits'
import { clock, num, sourceName } from '../dataFormat'

/** Tier 2 — every stored reading for this chart, newest first, with its
 *  provenance: when, from which source and device, at what grain, and
 *  whether it is the reading the daily series uses for that day. Filter by
 *  metric, source or date; export what the filter shows. */

const SELECT =
  'h-9 min-w-0 rounded-control-sm border border-line bg-panel px-2.5 text-copy text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus'

function Details({ json }: { json: Record<string, unknown> }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-label">
      {Object.entries(json).map(([key, value]) => (
        <Fragment key={key}>
          <dt className="text-secondary">{key.replace(/_/g, ' ')}</dt>
          <dd className="min-w-0 break-words tabular-nums text-ink">
            {typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value)}
          </dd>
        </Fragment>
      ))}
    </dl>
  )
}

function Row({ r, label }: { r: Reading; label: string }) {
  const [open, setOpen] = useState(false)
  const hasDetails = r.json != null && Object.keys(r.json).length > 0
  return (
    <>
      <tr className="align-top">
        <td className="whitespace-nowrap border-t border-hairline py-2 pr-3 text-copy tabular-nums text-ink">
          {shortDate(r.local_date)}
          <span className="meta block">{clock(r.start_time)}</span>
        </td>
        <td className="border-t border-hairline px-3 py-2 text-copy text-ink">{label}</td>
        <td className="whitespace-nowrap border-t border-hairline px-3 py-2 text-copy tabular-nums text-ink">
          {num(r.value)} <span className="meta">{r.unit ?? ''}</span>
        </td>
        <td className="border-t border-hairline px-3 py-2 text-copy text-ink">
          {sourceName(r.source)}
          {r.device && <span className="meta block max-w-[16ch] truncate" title={r.device}>{r.device}</span>}
        </td>
        <td className="border-t border-hairline px-3 py-2">
          <span className="meta">{r.granularity.replace(/_/g, ' ')}</span>
          {r.side && <span className="meta block">{r.side}</span>}
        </td>
        <td className="border-t border-hairline px-3 py-2">
          {r.used_in_series ? (
            <span className="chip bg-risk-low-tint normal-case tracking-label text-risk-low-ink">In the series</span>
          ) : (
            <span className="meta">Kept, not used</span>
          )}
        </td>
        <td className="border-t border-hairline py-2 pl-3 text-right">
          {hasDetails && (
            <button
              type="button"
              className="btn-plain btn-sm"
              aria-expanded={open}
              onClick={() => setOpen((o) => !o)}
            >
              {open ? 'Hide' : 'Details'}
            </button>
          )}
        </td>
      </tr>
      {open && hasDetails && r.json && (
        <tr>
          <td colSpan={7} className="pb-3">
            <div className="rounded-control bg-soft px-3 py-2.5">
              <Details json={r.json} />
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function RawView({
  patientId,
  initialFamily,
}: {
  patientId: string
  initialFamily?: string
}) {
  const [filters, setFilters] = useState<ReadingFilters>(initialFamily ? { family: initialFamily } : {})
  const [exporting, setExporting] = useState(false)
  const toast = useToast()
  const readings = useReadings(patientId, filters)
  const first = readings.data?.pages[0]
  const rows = readings.data?.pages.flatMap((p) => p.rows) ?? []
  const labels = new Map((first?.facets.metric_type ?? []).map((m) => [m.key, m.label]))
  const set = (patch: Partial<ReadingFilters>) => setFilters((f) => ({ ...f, ...patch }))

  const onExport = async () => {
    setExporting(true)
    try {
      await downloadExport(patientId, { kind: 'observations', ...filters }, `${patientId}-readings.csv`)
    } catch {
      toast('The export could not be made. Try again.', 'warning')
    } finally {
      setExporting(false)
    }
  }

  return (
    <SectionCard
      title="Raw readings"
      icon={<Tile size="sm" family="blue" icon={<ListFilter />} />}
      aside={first ? `${first.total.toLocaleString()} match` : undefined}
      action={
        <button type="button" className="btn-plain btn-sm" onClick={onExport} disabled={exporting || !first}>
          <Download aria-hidden size={16} /> {exporting ? 'Preparing…' : 'Export CSV'}
        </button>
      }
    >
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="flex min-w-0 flex-col gap-1">
          <span className="meta">Kind</span>
          <select
            className={SELECT}
            value={filters.family ?? ''}
            onChange={(e) => set({ family: e.target.value || undefined, metric_type: undefined })}
          >
            <option value="">Every kind</option>
            {(first?.facets.family ?? []).map((f) => (
              <option key={f.key} value={f.key}>
                {f.name} ({f.count.toLocaleString()})
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className="meta">Metric</span>
          <select
            className={SELECT}
            value={filters.metric_type ?? ''}
            onChange={(e) => set({ metric_type: e.target.value || undefined })}
          >
            <option value="">Every metric</option>
            {(first?.facets.metric_type ?? [])
              .filter((m) => !filters.family || m.family === filters.family)
              .map((m) => (
                <option key={m.key} value={m.key}>
                  {m.label} ({m.count.toLocaleString()})
                </option>
              ))}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className="meta">Source</span>
          <select
            className={SELECT}
            value={filters.source ?? ''}
            onChange={(e) => set({ source: e.target.value || undefined })}
          >
            <option value="">Every source</option>
            {(first?.facets.source ?? []).map((s) => (
              <option key={s.key} value={s.key}>
                {s.name} ({s.count.toLocaleString()})
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className="meta">From</span>
          <input
            type="date"
            className={SELECT}
            value={filters.from ?? ''}
            max={filters.to}
            onChange={(e) => set({ from: e.target.value || undefined })}
          />
        </label>
        <label className="flex min-w-0 flex-col gap-1">
          <span className="meta">To</span>
          <input
            type="date"
            className={SELECT}
            value={filters.to ?? ''}
            min={filters.from}
            onChange={(e) => set({ to: e.target.value || undefined })}
          />
        </label>
        {Object.values(filters).some(Boolean) && (
          <button type="button" className="btn-plain btn-sm" onClick={() => setFilters({})}>
            Clear
          </button>
        )}
      </div>

      <ViewState
        loading={readings.isLoading}
        error={readings.isError}
        onRetry={() => void readings.refetch()}
        what="The readings"
      >
        {rows.length === 0 ? (
          <p className="text-copy text-secondary">
            No readings match. A person followed by check-in alone has their answers under Reported.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-separate border-spacing-0 text-left">
                <thead>
                  <tr>
                    {['When', 'Metric', 'Value', 'Source', 'Grain', 'Daily series', ''].map((h, i) => (
                      <th
                        key={h || 'actions'}
                        scope="col"
                        className={`pb-2 text-label font-medium text-secondary ${i === 0 ? 'pr-3' : i === 6 ? 'pl-3' : 'px-3'}`}
                      >
                        {h || <span className="sr-only">Details</span>}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <Row key={r.id} r={r} label={labels.get(r.metric_type) ?? r.metric_type.replace(/_/g, ' ')} />
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="meta">
                Showing {rows.length.toLocaleString()} of {first?.total.toLocaleString()}
              </span>
              {readings.hasNextPage && (
                <button
                  type="button"
                  className="btn-tinted btn-sm"
                  onClick={() => void readings.fetchNextPage()}
                  disabled={readings.isFetchingNextPage}
                >
                  <Busy show={readings.isFetchingNextPage} /> Load more
                </button>
              )}
            </div>
          </>
        )}
      </ViewState>
    </SectionCard>
  )
}
