import { CalendarDays, Smartphone, Watch } from 'lucide-react'
import type { CSSProperties } from 'react'
import type { DataSummary, SummaryMetric } from '../../../api/data'
import Disclosure from '../../../components/Disclosure'
import SectionCard from '../../../components/SectionCard'
import Tile from '../../../components/Tile'
import { relativeTime, shortDate } from '../../../lib/format'
import { TierChip } from '../DataBits'
import { FAMILY_GLYPH, sourceName } from '../dataFormat'

/** Tier 1 — where this person's data comes from: their devices and the app,
 *  a calendar of which kinds of data arrived on which days, and every metric
 *  with its sources (the one the daily series uses first). */

function Devices({ summary }: { summary: DataSummary }) {
  const none = summary.devices.length === 0
  return (
    <SectionCard title="Devices and the app" icon={<Tile size="sm" family="teal" icon={<Watch />} />}>
      {none && (
        <p className="text-copy text-secondary">
          No device is connected. This person is followed by check-in: what they report is under
          Reported.
        </p>
      )}
      <ul className="divide-y divide-hairline">
        {summary.devices.map((d) => (
          <li key={d.id} className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-2.5 first:pt-0">
            <span className="min-w-0">
              <span className="block text-copy font-medium text-ink">{d.model ?? d.provider_name}</span>
              <span className="meta block">
                {d.provider_name}
                {d.via_junction ? ' through Junction' : ''}
                {d.connected_at ? ` · connected ${shortDate(d.connected_at)}` : ''}
              </span>
            </span>
            <span className="meta whitespace-nowrap">
              {d.last_sync_at ? `Last sync ${relativeTime(d.last_sync_at)}` : 'Never synced'}
            </span>
          </li>
        ))}
        <li className="flex flex-wrap items-center justify-between gap-x-6 gap-y-1 py-2.5 last:pb-0">
          <span className="flex min-w-0 items-center gap-2">
            <Smartphone aria-hidden size={16} className="shrink-0 text-secondary" />
            <span className="text-copy text-ink">
              {summary.app.signed_in ? 'Signed in to the app' : 'Not signed in to the app'}
              {summary.app.texts ? ' · reachable by text' : ''}
            </span>
          </span>
          {summary.app.last_seen_at && (
            <span className="meta whitespace-nowrap">Last seen {relativeTime(summary.app.last_seen_at)}</span>
          )}
        </li>
      </ul>
    </SectionCard>
  )
}

/** Sixty days as one strip per family: a filled cell is a day with at least
 *  one reading of that kind. */
function CoverageCalendar({ summary }: { summary: DataSummary }) {
  const { calendar } = summary
  const families = calendar.families.filter((f) =>
    calendar.by_day.some((d) => d.families.includes(f.key)),
  )
  if (families.length === 0) return null
  return (
    <SectionCard
      title="What arrived, day by day"
      icon={<Tile size="sm" family="indigo" icon={<CalendarDays />} />}
      aside={`${shortDate(calendar.since)} to ${shortDate(calendar.until)}`}
    >
      <div className="space-y-2">
        {families.map((f) => {
          const days = calendar.by_day.filter((d) => d.families.includes(f.key)).length
          return (
            <div key={f.key} className="flex items-center gap-3">
              <span className="w-24 shrink-0 truncate text-label text-secondary sm:w-32">
                {FAMILY_GLYPH[f.key]?.short ?? f.name}
              </span>
              <span
                className="grid min-w-0 flex-1 gap-px"
                style={{ gridTemplateColumns: `repeat(${calendar.by_day.length}, minmax(0, 1fr))` }}
                role="img"
                aria-label={`${f.name}: data on ${days} of ${calendar.by_day.length} days`}
              >
                {calendar.by_day.map((d) => (
                  <span
                    key={d.date}
                    title={`${shortDate(d.date)}${d.families.includes(f.key) ? '' : ': nothing'}`}
                    className={`h-4 rounded-[2px] ${
                      d.families.includes(f.key) ? 'bg-chart-s1' : 'bg-[rgb(var(--fill))]'
                    }`}
                  />
                ))}
              </span>
              <span className="w-10 shrink-0 text-right text-label tabular-nums text-secondary">{days} d</span>
            </div>
          )
        })}
      </div>
    </SectionCard>
  )
}

function MetricRow({ m }: { m: SummaryMetric }) {
  return (
    <tr className="align-top">
      <th scope="row" className="border-t border-hairline py-2.5 pr-3 text-left font-normal">
        <span className="text-copy font-medium text-ink">{m.label}</span>
        <span className="meta block">{m.unit}</span>
      </th>
      <td className="border-t border-hairline px-3 py-2.5">
        <TierChip tier={m.tier} />
      </td>
      <td className="border-t border-hairline px-3 py-2.5 text-copy tabular-nums text-ink">
        {m.count.toLocaleString()}
        <span className="meta block">{m.days} days</span>
      </td>
      <td className="border-t border-hairline px-3 py-2.5 text-copy text-ink">
        {m.first && m.last ? (
          <span className="whitespace-nowrap tabular-nums">
            {shortDate(m.first)} – {shortDate(m.last)}
          </span>
        ) : (
          '—'
        )}
      </td>
      <td className="border-t border-hairline py-2.5 pl-3 text-copy text-ink">
        {m.sources.length === 0
          ? '—'
          : m.sources.map((s, i) => (
              <span key={s.key} className="block">
                {sourceName(s.key)}
                <span className="meta">
                  {' '}
                  {s.count.toLocaleString()}
                  {i === 0 && m.sources.length > 1 ? ' · used first' : ''}
                </span>
              </span>
            ))}
      </td>
    </tr>
  )
}

function Metrics({ summary }: { summary: DataSummary }) {
  const collected = summary.metrics.filter((m) => m.count > 0)
  const absent = summary.metrics.filter((m) => m.count === 0 && m.tier !== 'declared')
  const byFamily = new Map<string, SummaryMetric[]>()
  for (const m of collected) byFamily.set(m.family, [...(byFamily.get(m.family) ?? []), m])
  if (collected.length === 0) {
    return (
      <SectionCard title="Every metric and its sources">
        <p className="text-copy text-secondary">No readings are stored for this chart yet.</p>
      </SectionCard>
    )
  }
  return (
    <SectionCard title="Every metric and its sources" aside={`${collected.length} collected`}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] border-separate border-spacing-0 text-left">
          <thead>
            <tr>
              {['Metric', 'Tier', 'Readings', 'From – to', 'Sources'].map((h, i) => (
                <th
                  key={h}
                  scope="col"
                  className={`pb-2 text-label font-medium text-secondary ${i === 0 ? 'pr-3' : i === 4 ? 'pl-3' : 'px-3'}`}
                >
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          {[...byFamily.entries()].map(([family, rows]) => (
            <tbody key={family}>
              <tr>
                <th colSpan={5} scope="colgroup" className="pb-1 pt-4 text-left">
                  <span className="micro">{FAMILY_GLYPH[family]?.short ?? family}</span>
                </th>
              </tr>
              {rows.map((m) => (
                <MetricRow key={m.metric_type} m={m} />
              ))}
            </tbody>
          ))}
        </table>
      </div>
      {absent.length > 0 && (
        <Disclosure
          className="mt-4"
          label="Not collected for this person"
          hint={`${absent.length} metric${absent.length === 1 ? '' : 's'}`}
        >
          <ul className="card-group mt-1 bg-soft" style={{ '--row-inset': '16px' } as CSSProperties}>
            {absent.map((m) => (
              <li key={m.metric_type} className="px-4 py-2.5">
                <p className="text-copy font-medium text-ink">{m.label}</p>
                <p className="meta">
                  {m.availability_note ??
                    (m.availability === 'active'
                      ? 'Recorded when the person does a guided test in the app.'
                      : m.availability === 'unavailable'
                        ? 'Their device does not measure this.'
                        : 'Nothing received yet.')}
                </p>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </SectionCard>
  )
}

export default function SourcesView({ summary }: { summary: DataSummary }) {
  return (
    <div className="space-y-stack">
      <Devices summary={summary} />
      <CoverageCalendar summary={summary} />
      <Metrics summary={summary} />
    </div>
  )
}
