import { Copy, Table2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { RawDataRow } from '../../../api/care'
import { useRawData } from '../../../api/care'
import SectionCard from '../../../components/SectionCard'
import SegmentedControl from '../../../components/SegmentedControl'
import { RefreshOverlay, SkeletonCard } from '../../../components/Skeleton'
import Tile from '../../../components/Tile'
import { useToast } from '../../../components/Toast'
import { shortDate } from '../../../lib/format'
import { fmtNum as fmtRaw, metricTypeLabel } from './labels'

/** Raw data tab: every observation in the window, grouped by metric type,
 *  newest first — the audit trail behind the metrics above.
 *
 *  The window (7d / 30d / 90d) and the metric type are both the app's
 *  segmented control; the type strip scrolls sideways when a patient has many
 *  types. The table sits in a 12px rounded container that CLIPS (overflow
 *  auto), with an opaque --soft sticky header and opaque --panel rows, so
 *  every number is on a solid fill. Figures use the UI face with tabular
 *  digits (R19). Contrast, light / dark: ink on panel 18.377 / 16.8+, muted on
 *  panel 5.393 / 4.906, muted on the --soft header 4.755 / 4.582. */

/** fmtNum with a true minus (U+2212, R19). */
const fmtNum = (v: number) => fmtRaw(v).replace('-', '\u2212')

type Days = '7' | '30' | '90'
const DAY_OPTIONS = [
  { key: '7' as const, label: '7d' },
  { key: '30' as const, label: '30d' },
  { key: '90' as const, label: '90d' },
]

const ROW_CAP = 400

function jsonSummary(json: Record<string, unknown> | null): string {
  if (!json) return ''
  const entries = Object.entries(json)
  const parts = entries.slice(0, 3).map(([k, v]) => {
    if (typeof v === 'number') return `${k}=${fmtNum(v)}`
    if (Array.isArray(v)) return `${k}[${v.length}]`
    if (v && typeof v === 'object') return `${k}{…}`
    return `${k}=${String(v)}`
  })
  return parts.join(' · ') + (entries.length > 3 ? ' …' : '')
}

function csvCell(v: unknown): string {
  const s = v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function toCsv(metricType: string, rows: RawDataRow[]): string {
  const head = ['metric_type', 'date', 'start_time', 'value', 'unit', 'source', 'granularity', 'patient_reported', 'json']
  const lines = rows.map((r) =>
    [metricType, r.date, r.start_time, r.value, r.unit, r.source, r.granularity, r.patient_reported, r.json]
      .map(csvCell)
      .join(','),
  )
  return [head.join(','), ...lines].join('\n')
}

function timeOf(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

export default function RawDataTable({
  patientId,
  enabled,
  refreshing,
}: {
  patientId: string
  enabled: boolean
  refreshing: boolean
}) {
  const [days, setDays] = useState<Days>('30')
  const [selected, setSelected] = useState<string | null>(null)
  const { data, isLoading, isError } = useRawData(patientId, Number(days), enabled)
  const toast = useToast()

  const types = data?.metric_types ?? []
  const current =
    selected && types.some((t) => t.metric_type === selected)
      ? selected
      : (types[0]?.metric_type ?? null)
  const rows: RawDataRow[] = current ? (data?.rows[current] ?? []) : []
  const currentType = types.find((t) => t.metric_type === current)
  const truncated =
    data?.truncated === true ||
    currentType?.truncated === true ||
    (currentType != null && currentType.count > rows.length && rows.length >= ROW_CAP)
  const totalRows = types.reduce((n, t) => n + t.count, 0)

  // Keep the selected type visible in the sideways strip (keyboard arrows can
  // move it off-screen). Only the strip scrolls, never the page.
  const stripRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const strip = stripRef.current
    const item = strip?.querySelector<HTMLElement>('[data-segment-active="true"]')
    if (!strip || !item) return
    const pad = 24
    const left = item.offsetLeft - pad
    const right = item.offsetLeft + item.offsetWidth + pad - strip.clientWidth
    if (strip.scrollLeft > left) strip.scrollLeft = left
    else if (strip.scrollLeft < right) strip.scrollLeft = right
  }, [current, data])

  const copyCsv = async () => {
    if (!current) return
    try {
      await navigator.clipboard.writeText(toCsv(current, rows))
      toast(`Copied ${rows.length} ${metricTypeLabel(current).toLowerCase()} rows as CSV`)
    } catch {
      toast('Copy failed — the clipboard is not available here', 'warning')
    }
  }

  const typeOptions = types.map((t) => ({
    key: t.metric_type,
    text: `${metricTypeLabel(t.metric_type)} ${t.count}`,
    label: (
      <span className="inline-flex items-baseline gap-1.5 whitespace-nowrap">
        {metricTypeLabel(t.metric_type)}
        <span className="tabular-nums">{t.count.toLocaleString()}</span>
      </span>
    ),
  }))

  const TD = 'whitespace-nowrap px-3 py-2'

  return (
    <SectionCard
      title="Raw data"
      icon={<Tile size="sm" family="blue" icon={<Table2 />} />}
      action={
        <SegmentedControl<Days>
          options={DAY_OPTIONS}
          value={days}
          onChange={setDays}
          size="sm"
          aria-label="Window"
        />
      }
    >
      <RefreshOverlay show={refreshing} />
      {isLoading && <SkeletonCard lines={4} />}
      {isError && <p className="text-copy text-secondary">Raw data could not be loaded.</p>}
      {data && types.length === 0 && (
        <p className="text-copy text-secondary">No observations in the last {days} days.</p>
      )}
      {data && types.length > 0 && (
        <div>
          <p className="meta tabular-nums">
            {types.length} metric types · {totalRows.toLocaleString()} observations ·{' '}
            {data.checkins_count} check-ins · {data.tasks_count} tasks
          </p>

          {/* p-1.5 leaves room for the R9 focus ring, which sits outside the
              item and would otherwise be cut by the scroll container. */}
          <div ref={stripRef} className="relative -mx-1.5 mt-2 overflow-x-auto p-1.5">
            <SegmentedControl<string>
              options={typeOptions}
              value={current ?? undefined}
              onChange={setSelected}
              size="sm"
              aria-label="Metric type"
            />
          </div>

          {currentType && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <p className="meta">
                <span className="font-medium text-ink">{metricTypeLabel(currentType.metric_type)}</span>
                {currentType.unit && <> · {currentType.unit}</>}
                {currentType.source_providers.length > 0 && (
                  <> · {currentType.source_providers.join(', ')}</>
                )}
                {currentType.first && currentType.last && (
                  <>
                    {' '}
                    · {shortDate(currentType.first)} – {shortDate(currentType.last)}
                  </>
                )}
              </p>
              <button
                type="button"
                onClick={copyCsv}
                className="btn-tinted btn-sm"
                disabled={rows.length === 0}
              >
                <Copy aria-hidden /> Copy CSV
              </button>
            </div>
          )}

          <div
            className="mt-3 max-h-80 overflow-auto rounded-control border border-line bg-panel"
            tabIndex={0}
            role="region"
            aria-label={`${current ? metricTypeLabel(current) : 'Raw'} observations`}
          >
            <table className="w-full min-w-[640px] border-collapse text-left text-label tabular-nums">
              <thead className="sticky top-0 z-[1] bg-soft">
                <tr className="text-secondary">
                  <th scope="col" className="px-3 py-2 font-medium">Date</th>
                  <th scope="col" className="px-3 py-2 font-medium">Time</th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">Value</th>
                  <th scope="col" className="px-3 py-2 font-medium">Unit</th>
                  <th scope="col" className="px-3 py-2 font-medium">Source</th>
                  <th scope="col" className="px-3 py-2 font-medium">Granularity</th>
                  <th scope="col" className="px-3 py-2 font-medium">Reported</th>
                  <th scope="col" className="px-3 py-2 font-medium">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {rows.map((r, i) => (
                  <tr
                    key={`${r.date}-${r.start_time ?? ''}-${i}`}
                    className="bg-panel transition-colors duration-state ease-apple hover:bg-soft"
                  >
                    <td className={`${TD} text-ink`}>{r.date}</td>
                    <td className={`${TD} text-secondary`}>{timeOf(r.start_time)}</td>
                    <td className={`${TD} text-right font-medium text-ink`}>
                      {r.value == null ? '—' : fmtNum(r.value)}
                    </td>
                    <td className={`${TD} text-secondary`}>{r.unit}</td>
                    <td className={`${TD} text-secondary`}>{r.source}</td>
                    <td className={`${TD} text-secondary`}>{r.granularity}</td>
                    <td className={TD}>
                      {r.patient_reported ? (
                        <span className="text-ink">Patient</span>
                      ) : (
                        <span className="text-secondary">Device</span>
                      )}
                    </td>
                    <td
                      className="max-w-[16rem] truncate px-3 py-2 text-secondary"
                      title={r.json ? JSON.stringify(r.json) : undefined}
                    >
                      {jsonSummary(r.json)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {truncated && currentType && (
            <p className="meta mt-2 tabular-nums">
              Showing the newest {rows.length.toLocaleString()} of {currentType.count.toLocaleString()}{' '}
              rows. Narrow the window to see the rest.
            </p>
          )}
        </div>
      )}
    </SectionCard>
  )
}
