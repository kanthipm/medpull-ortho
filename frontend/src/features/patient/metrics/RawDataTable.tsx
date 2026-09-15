import { Copy } from 'lucide-react'
import { useState } from 'react'
import type { RawDataRow } from '../../../api/care'
import { useRawData } from '../../../api/care'
import SectionCard from '../../../components/SectionCard'
import SegmentedControl from '../../../components/SegmentedControl'
import { RefreshOverlay, SkeletonCard } from '../../../components/Skeleton'
import { useToast } from '../../../components/Toast'
import { shortDate } from '../../../lib/format'
import { fmtNum, metricTypeLabel } from './labels'

/** Raw data tab: every observation in the window, grouped by metric type,
 *  newest first — the audit trail behind the metrics above. */

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

  const copyCsv = async () => {
    if (!current) return
    try {
      await navigator.clipboard.writeText(toCsv(current, rows))
      toast(`Copied ${rows.length} ${metricTypeLabel(current).toLowerCase()} rows as CSV`)
    } catch {
      toast('Copy failed — the clipboard is not available here', 'warning')
    }
  }

  return (
    <SectionCard
      title="Raw data"
      aside={
        <SegmentedControl<Days>
          options={DAY_OPTIONS}
          value={days}
          onChange={setDays}
          aria-label="Window"
        />
      }
    >
      <RefreshOverlay show={refreshing} />
      {isLoading && <SkeletonCard lines={4} />}
      {isError && (
        <p className="text-[12.5px] font-medium text-muted">Raw data could not be loaded.</p>
      )}
      {data && types.length === 0 && (
        <p className="text-[12.5px] font-medium text-muted">
          No observations in the last {days} days.
        </p>
      )}
      {data && types.length > 0 && (
        <div>
          <p className="micro">
            {types.length} metric types · {totalRows.toLocaleString()} observations ·{' '}
            {data.checkins_count} check-ins · {data.tasks_count} tasks
          </p>

          <div className="mt-2.5 flex flex-wrap gap-1.5" role="tablist" aria-label="Metric type">
            {types.map((t) => {
              const active = t.metric_type === current
              return (
                <button
                  key={t.metric_type}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setSelected(t.metric_type)}
                  className={`chip cursor-pointer transition-colors duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand ${
                    active ? 'bg-brand-tint text-brand' : 'bg-soft text-muted hover:text-ink'
                  }`}
                >
                  {metricTypeLabel(t.metric_type)}
                  <span className="font-mono tabular-nums opacity-70">{t.count}</span>
                </button>
              )
            })}
          </div>

          {currentType && (
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <p className="text-[11.5px] font-medium text-faint">
                <span className="text-body">{metricTypeLabel(currentType.metric_type)}</span>
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
              <button type="button" onClick={copyCsv} className="qa-btn" disabled={rows.length === 0}>
                <Copy size={13} /> Copy CSV
              </button>
            </div>
          )}

          <div className="mt-2 max-h-80 overflow-auto rounded-[10px] border border-line">
            <table className="w-full min-w-[640px] border-collapse text-left text-[12px]">
              <thead className="sticky top-0 bg-soft">
                <tr className="text-[10.5px] font-medium uppercase tracking-[.06em] text-faint">
                  <th className="px-2.5 py-1.5 font-medium">Date</th>
                  <th className="px-2.5 py-1.5 font-medium">Time</th>
                  <th className="px-2.5 py-1.5 text-right font-medium">Value</th>
                  <th className="px-2.5 py-1.5 font-medium">Unit</th>
                  <th className="px-2.5 py-1.5 font-medium">Source</th>
                  <th className="px-2.5 py-1.5 font-medium">Granularity</th>
                  <th className="px-2.5 py-1.5 font-medium">Reported</th>
                  <th className="px-2.5 py-1.5 font-medium">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {rows.map((r, i) => (
                  <tr key={`${r.date}-${r.start_time ?? ''}-${i}`} className="bg-panel">
                    <td className="whitespace-nowrap px-2.5 py-1.5 font-mono tabular-nums text-ink">
                      {r.date}
                    </td>
                    <td className="whitespace-nowrap px-2.5 py-1.5 font-mono tabular-nums text-muted">
                      {timeOf(r.start_time)}
                    </td>
                    <td className="whitespace-nowrap px-2.5 py-1.5 text-right font-mono font-medium tabular-nums text-ink">
                      {r.value == null ? '—' : fmtNum(r.value)}
                    </td>
                    <td className="whitespace-nowrap px-2.5 py-1.5 text-muted">{r.unit}</td>
                    <td className="whitespace-nowrap px-2.5 py-1.5 text-muted">{r.source}</td>
                    <td className="whitespace-nowrap px-2.5 py-1.5 text-muted">{r.granularity}</td>
                    <td className="whitespace-nowrap px-2.5 py-1.5">
                      {r.patient_reported ? (
                        <span className="chip bg-brand-tint text-brand">patient</span>
                      ) : (
                        <span className="text-faint">device</span>
                      )}
                    </td>
                    <td className="max-w-[16rem] truncate px-2.5 py-1.5 text-faint" title={r.json ? JSON.stringify(r.json) : undefined}>
                      {jsonSummary(r.json)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {truncated && currentType && (
            <p className="mt-2 text-[11px] font-medium leading-[1.5] text-faint">
              Showing the newest {rows.length.toLocaleString()} of {currentType.count.toLocaleString()}{' '}
              rows — narrow the window to see the rest.
            </p>
          )}
        </div>
      )}
    </SectionCard>
  )
}
