import { Moon } from 'lucide-react'
import { useState } from 'react'
import { useSleep } from '../../../api/data'
import SectionCard from '../../../components/SectionCard'
import SegmentedControl from '../../../components/SegmentedControl'
import Tile from '../../../components/Tile'
import { METRIC_STATUS, type MetricStatus } from '../../../lib/risk'
import { shortDate } from '../../../lib/format'
import { Fact, Facts, ViewState } from '../DataBits'
import { clock, hoursText, num, sourceName } from '../dataFormat'
import NightsChart from '../NightsChart'

/** The nights: how long, in which stages, when, and what the engine makes of
 *  them. A chart with no device has no nights here; what the person says
 *  about their sleep in a check-in is under Reported. */

type Window = '14' | '30' | '60'

function pct(value: number | null): string {
  return value == null ? '—' : `${Math.round(value)}%`
}

export default function SleepView({ patientId }: { patientId: string }) {
  const [window, setWindow] = useState<Window>('30')
  const sleep = useSleep(patientId, Number(window))
  const data = sleep.data
  const derived = data?.derived.nocturnal_disruption
  const status = (derived?.status ?? 'nodata') as MetricStatus
  // Only a source that times the night has an "In bed" column worth a column.
  const timed = (data?.nights ?? []).some((n) => n.bedtime && n.wake)
  return (
    <ViewState
      loading={sleep.isLoading}
      error={sleep.isError}
      onRetry={() => void sleep.refetch()}
      what="The nights"
    >
      {data && data.nights.length === 0 && (
        <SectionCard title="Sleep" icon={<Tile size="sm" family="indigo" icon={<Moon />} />}>
          <p className="text-copy text-secondary">
            No nights from a device. Where the check-in asks about sleep, the answers are under
            Reported.
          </p>
        </SectionCard>
      )}
      {data && data.nights.length > 0 && (
        <div className="space-y-stack">
          <SectionCard
            title="The nights"
            icon={<Tile size="sm" family="indigo" icon={<Moon />} />}
            aside={`${data.averages.nights} nights`}
            action={
              <SegmentedControl<Window>
                options={[
                  { key: '14', label: '14' },
                  { key: '30', label: '30' },
                  { key: '60', label: '60' },
                ]}
                value={window}
                onChange={setWindow}
                size="sm"
                role="radiogroup"
                aria-label="Nights shown"
              />
            }
          >
            <Facts>
              <Fact label="Average night" value={hoursText(data.averages.duration_h)} />
              <Fact label="Last 7 nights" value={hoursText(data.last_7.duration_h)} />
              {data.baseline && (
                <Fact
                  label={data.baseline.is_preop ? 'Own norm, before surgery' : 'Own norm'}
                  value={hoursText(data.baseline.mean)}
                />
              )}
              {data.averages.efficiency != null && (
                <Fact label="Efficiency" value={pct(data.averages.efficiency * 100)} hint="of the night asleep" />
              )}
            </Facts>
            <div className="mt-6">
              <NightsChart nights={data.nights} />
            </div>
          </SectionCard>

          <div className="grid gap-stack lg:grid-cols-2">
            <SectionCard title="Stages" aside={`${data.averages.nights_with_stages} nights with stages`}>
              {data.averages.nights_with_stages === 0 ? (
                <p className="text-copy text-secondary">This source reports a duration, not stages.</p>
              ) : (
                <dl className="divide-y divide-hairline">
                  {(
                    [
                      ['Deep', data.averages.deep_h, data.averages.deep_pct],
                      ['REM', data.averages.rem_h, data.averages.rem_pct],
                      ['Light', data.averages.light_h, data.averages.light_pct],
                      ['Awake', data.averages.awake_h, data.averages.awake_pct],
                    ] as const
                  ).map(([name, hours, share]) => (
                    <div key={name} className="flex items-baseline justify-between gap-4 py-2 first:pt-0 last:pb-0">
                      <dt className="text-copy text-ink">{name}</dt>
                      <dd className="text-copy tabular-nums text-ink">
                        {hoursText(hours)} <span className="meta">· {pct(share)}</span>
                      </dd>
                    </div>
                  ))}
                </dl>
              )}
            </SectionCard>

            <SectionCard title="What the engine reads from them">
              <dl className="divide-y divide-hairline">
                <div className="py-2.5 first:pt-0">
                  <dt className="flex flex-wrap items-center gap-2">
                    <span className="text-copy font-medium text-ink">Nocturnal disruption</span>
                    {derived && (
                      <span className={`chip ${METRIC_STATUS[status]?.pill ?? ''}`}>{derived.status_text}</span>
                    )}
                  </dt>
                  <dd className="mt-1 text-copy text-ink">
                    {derived
                      ? derived.finding
                      : 'Not enough nights with stages to read disruption yet.'}
                  </dd>
                </div>
                {data.derived.sleep_duration && (
                  <div className="py-2.5">
                    <dt className="text-copy font-medium text-ink">Sleep duration, against the own norm</dt>
                    <dd className="mt-1 text-copy text-ink">{data.derived.sleep_duration.finding}</dd>
                  </div>
                )}
                {data.consistency.nights > 0 && (
                  <div className="py-2.5 last:pb-0">
                    <dt className="text-copy font-medium text-ink">Timing</dt>
                    <dd className="mt-1 text-copy text-ink">
                      Usually in bed around {data.consistency.mean_bedtime} and up around{' '}
                      {data.consistency.mean_wake}; bedtime varies by about{' '}
                      {num(data.consistency.bedtime_sd_min, 0)} minutes.
                    </dd>
                  </div>
                )}
              </dl>
            </SectionCard>
          </div>

          <SectionCard title="Night by night" flush>
            <div className="max-h-[28rem] overflow-auto">
              <table className="w-full min-w-[560px] border-separate border-spacing-0 text-left">
                <caption className="sr-only">Each night: its length, its stages and where it came from</caption>
                <thead className="sticky top-0 bg-panel">
                  <tr>
                    {['Night', 'Length', 'Deep', 'REM', 'Light', 'Awake', ...(timed ? ['In bed'] : []), 'Source'].map((h) => (
                      <th key={h} scope="col" className="px-4 pb-2 pt-3 text-label font-medium text-secondary">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.nights.map((n) => (
                    <tr key={n.date}>
                      <th scope="row" className="whitespace-nowrap border-t border-hairline px-4 py-2 text-left text-copy font-normal tabular-nums text-ink">
                        {shortDate(n.date)}
                      </th>
                      <td className="whitespace-nowrap border-t border-hairline px-4 py-2 text-copy tabular-nums text-ink">
                        {hoursText(n.duration_h)}
                      </td>
                      {(['deep', 'rem', 'light', 'awake'] as const).map((s) => (
                        <td key={s} className="whitespace-nowrap border-t border-hairline px-4 py-2 text-copy tabular-nums text-ink">
                          {n.stages?.[s] != null ? hoursText(n.stages[s]) : '—'}
                        </td>
                      ))}
                      {timed && (
                        <td className="whitespace-nowrap border-t border-hairline px-4 py-2 text-copy tabular-nums text-ink">
                          {n.bedtime && n.wake ? `${clock(n.bedtime)} – ${clock(n.wake)}` : '—'}
                        </td>
                      )}
                      <td className="border-t border-hairline px-4 py-2 text-copy text-ink">{sourceName(n.source)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </SectionCard>
        </div>
      )}
    </ViewState>
  )
}
