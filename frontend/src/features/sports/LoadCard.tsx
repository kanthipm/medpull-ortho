import { Activity } from 'lucide-react'
import type { LoadSummary } from '../../api/sports'
import EmptyState from '../../components/EmptyState'
import InlineReadout from '../../components/InlineReadout'
import SectionCard from '../../components/SectionCard'
import DotLine from '../patient/DotLine'
import LoadBars from './LoadBars'
import { StatusChip } from './SportsBits'
import { fmt, loadTone, meanPerDay, pct } from './sportsFormat'

/** Session load: the week's total against the recent weeks, monotony and
 *  the acute:chronic ratio for context, the 28 daily bars, and the finding.
 *  Tones follow the engine's own steps (15% weekly rise, ACWR 1.3 / 1.5,
 *  monotony over 2). */
export default function LoadCard({ load, asOf }: { load: LoadSummary | null; asOf: string }) {
  if (!load) {
    return (
      <SectionCard title="Training load">
        <EmptyState variant="inline" icon={<Activity />} family="teal" title="No sessions logged yet">
          Session RPE and minutes, or a Catapult feed, build the load picture.
        </EmptyState>
      </SectionCard>
    )
  }
  const acwrTone = load.acwr == null ? undefined : load.acwr >= 1.5 ? 'high' : load.acwr >= 1.3 ? 'med' : undefined
  const monotonyTone = load.monotony != null && load.monotony > 2 ? 'high' : undefined
  return (
    <SectionCard title="Training load" aside={<StatusChip status={load.status} text={load.status_text} />}>
      <InlineReadout
        items={[
          { key: 'week', label: 'AU this week', value: fmt(load.week_load) },
          {
            key: 'change',
            label: 'vs recent weeks',
            value: pct(load.change_pct),
            tone: loadTone(load.change_pct),
          },
          { key: 'monotony', label: 'monotony', value: fmt(load.monotony, 2), tone: monotonyTone },
          { key: 'acwr', label: 'acute:chronic', value: fmt(load.acwr, 2), tone: acwrTone },
        ]}
      />
      <div className="mt-3 rounded-control-sm bg-panel p-2">
        <LoadBars data={load.series} asOf={asOf} unit="AU" label="Daily session load" className="h-36" />
      </div>
      <p className="meta mt-1.5">Dashed line: the 28-day mean, {fmt(meanPerDay(load.series, asOf))} AU per day.</p>
      {load.finding && <p className="mt-3 text-copy text-body">{load.finding}</p>}
      <DotLine
        as="p"
        className="meta mt-2"
        parts={[
          load.sessions_week != null && `${load.sessions_week} sessions`,
          load.minutes_week != null && `${fmt(load.minutes_week)} min`,
          load.games_week ? `${load.games_week} ${load.games_week === 1 ? 'game' : 'games'}` : null,
          load.source,
        ]}
      />
    </SectionCard>
  )
}
