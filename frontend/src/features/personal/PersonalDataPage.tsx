import { Download, FileJson, ListChecks, Radio, StickyNote, Watch } from 'lucide-react'
import { useState, type CSSProperties } from 'react'
import { useParams } from 'react-router-dom'
import {
  downloadMemberExport,
  usePersonalOverview,
  usePersonalSignals,
  type PersonalOverview,
} from '../../api/personal'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'
import { relativeTime, shortDate } from '../../lib/format'
import { MemberHead, MiniLine, PanelCard, PersonalState } from './PersonalBits'
import { panelsInOrder, providerName, short, values } from './personalFormat'

/** `/personal/:memberId/data` — what is under the member's readouts: where
 *  the data comes from, every readout with how it is worked out and what it
 *  was worked out from, the raw daily signals, what they logged themselves,
 *  the notes the coach keeps, and the export their own "Export my data"
 *  produces. */
export default function PersonalDataPage() {
  const { memberId = '' } = useParams()
  const overview = usePersonalOverview(memberId)
  return (
    <div className="pb-10">
      <PersonalState
        loading={overview.isLoading}
        error={overview.isError || (!overview.isLoading && !overview.data)}
        onRetry={() => void overview.refetch()}
      >
        {overview.data && <Data memberId={memberId} o={overview.data} />}
      </PersonalState>
    </div>
  )
}

type Window = '14' | '30' | '90'

function Data({ memberId, o }: { memberId: string; o: PersonalOverview }) {
  const toast = useToast()
  const first = o.member.name.split(' ')[0]
  const d = o.dashboard
  const [exporting, setExporting] = useState(false)
  const panels = panelsInOrder(d.sections, d.panels)

  const onExport = async () => {
    setExporting(true)
    try {
      await downloadMemberExport(memberId)
    } catch {
      toast('The export could not be made. Try again.', 'warning')
    } finally {
      setExporting(false)
    }
  }

  return (
    <>
      <MemberHead overview={o} />

      {/* ── Where it comes from ─────────────────────────────────────────── */}
      <SectionCard
        className="rise mt-8"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
        title="Where it comes from"
        icon={<Tile size="sm" family="teal" icon={<Watch />} />}
        aside={`${d.days_with_data} days on file`}
        action={
          <button type="button" className="btn-plain btn-sm" onClick={onExport} disabled={exporting}>
            <Download aria-hidden size={16} /> {exporting ? 'Preparing…' : 'Export'}
          </button>
        }
      >
        {o.member.devices.length === 0 ? (
          <p className="text-copy text-secondary">No device is connected.</p>
        ) : (
          <ul className="divide-y divide-hairline">
            {o.member.devices.map((dev) => (
              <li key={`${dev.provider}-${dev.model}`} className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5 py-2.5 first:pt-0 last:pb-0">
                <span className="text-copy text-ink">
                  <span className="font-medium">{dev.model ?? providerName(dev.provider)}</span>{' '}
                  <span className="text-secondary">· {providerName(dev.provider)}</span>
                </span>
                <span className="meta">
                  {dev.connected_at ? `connected ${shortDate(dev.connected_at)}` : ''}
                  {dev.last_sync_at ? ` · last sync ${relativeTime(dev.last_sync_at).toLowerCase()}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="meta mt-4 inline-flex items-center gap-1.5">
          <FileJson aria-hidden size={12} /> Export is the one document {first}’s own “Export my data” produces:
          the profile, the readings, the logs and the thread.
        </p>
      </SectionCard>

      {/* ── Every readout, with its method ──────────────────────────────── */}
      <section className="mt-stack" aria-labelledby="personal-methods">
        <h2 id="personal-methods" className="mb-3 px-1 text-subhead font-medium text-ink">
          Every readout, and how it is worked out
        </h2>
        <div className="grid gap-3 lg:grid-cols-2">
          {panels.map((panel) => (
            <PanelCard key={panel.key} panel={panel} detail />
          ))}
        </div>
      </section>

      <Signals memberId={memberId} />

      <div className="mt-stack grid gap-stack lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:items-start">
        {/* ── What they logged themselves ─────────────────────────────── */}
        <SectionCard
          title="What they logged"
          icon={<Tile size="sm" family="blue" icon={<ListChecks />} />}
          aside={`${o.logs.length} day${o.logs.length === 1 ? '' : 's'}, 0 to 10`}
          flush
        >
          {o.logs.length === 0 ? (
            <p className="px-5 pb-5 text-copy text-secondary">Nothing logged in the last month.</p>
          ) : (
            <div className="max-h-[26rem] overflow-auto">
              <table className="w-full min-w-[420px] border-separate border-spacing-0 text-left">
                <caption className="sr-only">The member’s own daily check-ins, newest first, each scored 0 to 10</caption>
                <thead className="sticky top-0 bg-panel">
                  <tr>
                    {['Day', 'Mood', 'Sleep quality', 'Soreness', 'Energy'].map((h) => (
                      <th key={h} scope="col" className="px-4 pb-2 pt-2 text-label font-medium text-secondary">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {o.logs.map((log) => (
                    <tr key={log.date}>
                      <th scope="row" className="whitespace-nowrap border-t border-hairline px-4 py-2 text-left text-copy font-normal tabular-nums text-ink">
                        {shortDate(log.date)}
                      </th>
                      {[log.mood, log.sleep_quality, log.soreness, log.energy].map((v, i) => (
                        <td key={i} className="border-t border-hairline px-4 py-2 text-copy tabular-nums text-ink">
                          {v == null ? <span className="text-secondary">—</span> : short(v, 0)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>

        {/* ── What the coach keeps in mind ────────────────────────────── */}
        <SectionCard
          title="What the coach keeps in mind"
          icon={<Tile size="sm" family="indigo" icon={<StickyNote />} />}
          aside={`${o.notes.length} note${o.notes.length === 1 ? '' : 's'}`}
        >
          {o.notes.length === 0 ? (
            <p className="text-copy text-secondary">Nothing noted yet.</p>
          ) : (
            <ul className="divide-y divide-hairline">
              {o.notes.map((n) => (
                <li key={`${n.date}-${n.text}`} className="py-2.5 first:pt-0 last:pb-0">
                  <p className="text-copy text-ink">{n.text}</p>
                  <p className="meta mt-0.5">
                    {shortDate(n.date)} ·{' '}
                    {n.source === 'coach' ? 'said to the coach' : n.source === 'checkin' ? 'from a check-in' : n.source}
                  </p>
                </li>
              ))}
            </ul>
          )}
          <p className="meta mt-4">
            Things {first} told the coach that it carries from one conversation to the next. {first} can
            read and clear them in the app.
          </p>
        </SectionCard>
      </div>

      <p className="meta mt-8 px-1">{o.brief.guardrail}</p>
    </>
  )
}

/** The raw daily signals behind the readouts, as the member's own "all
 *  metrics" screen lists them: the latest value, how many days carry one,
 *  and the shape of the window. */
function Signals({ memberId }: { memberId: string }) {
  const [window, setWindow] = useState<Window>('30')
  const signals = usePersonalSignals(memberId, Number(window))
  const rows = signals.data?.metrics ?? []
  return (
    <SectionCard
      className="mt-stack"
      title="Raw daily signals"
      icon={<Tile size="sm" family="violet" icon={<Radio />} />}
      aside={signals.data ? `since ${shortDate(signals.data.since)}` : undefined}
      action={
        <SegmentedControl<Window>
          options={[
            { key: '14', label: '14 days' },
            { key: '30', label: '30 days' },
            { key: '90', label: '90 days' },
          ]}
          value={window}
          onChange={setWindow}
          size="sm"
          role="radiogroup"
          aria-label="Window"
        />
      }
      flush
    >
      {signals.isLoading ? (
        <p className="meta px-5 pb-5">Loading the signals…</p>
      ) : signals.isError ? (
        <p className="px-5 pb-5 text-copy text-secondary">The signals could not be loaded.</p>
      ) : rows.length === 0 ? (
        <p className="px-5 pb-5 text-copy text-secondary">No signals in this window.</p>
      ) : (
        <div className={`overflow-x-auto transition-opacity duration-state ease-apple ${signals.isPlaceholderData ? 'opacity-60' : ''}`}>
          <table className="w-full min-w-[640px] border-separate border-spacing-0 text-left">
            <caption className="sr-only">Each raw signal: its latest value, the days that carry one, and its shape over the window</caption>
            <thead>
              <tr>
                {['Signal', 'Latest', 'Days with a reading', 'Over the window'].map((h) => (
                  <th key={h} scope="col" className="px-5 pb-2 pt-1 text-label font-medium text-secondary">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const points = values(row.series)
                return (
                  <tr key={row.key}>
                    <th scope="row" className="border-t border-hairline px-5 py-2.5 text-left font-normal">
                      <span className="text-copy font-medium text-ink">{row.label}</span>
                      <span className="meta block">{row.unit}</span>
                    </th>
                    <td className="whitespace-nowrap border-t border-hairline px-5 py-2.5 text-copy tabular-nums text-ink">
                      {row.latest?.value != null ? short(row.latest.value, 1) : '—'}
                      {row.latest && <span className="meta block">{shortDate(row.latest.date)}</span>}
                    </td>
                    <td className="border-t border-hairline px-5 py-2.5 text-copy tabular-nums text-ink">
                      {row.days_with_data ?? points.length}
                      <span className="text-secondary"> of {signals.data?.days}</span>
                    </td>
                    <td className="w-[36%] border-t border-hairline px-5 py-2.5">
                      <MiniLine points={points} height={32} label={`${row.label} over the window`} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </SectionCard>
  )
}
