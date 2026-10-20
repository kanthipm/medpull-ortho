import { useState } from 'react'
import type { TeamLoadPoint } from '../../api/sports'
import InlineReadout from '../../components/InlineReadout'
import SectionCard from '../../components/SectionCard'
import SegmentedControl from '../../components/SegmentedControl'
import LoadBars from './LoadBars'
import { addDays, fmt, loadTone, meanPerDay, pct } from './sportsFormat'

type Series = 'load' | 'jumps'

const OPTIONS: { key: Series; label: string }[] = [
  { key: 'load', label: 'Session load' },
  { key: 'jumps', label: 'Jumps' },
]

/** Per-athlete session load (or jump count) by day over four weeks, with
 *  this week against the week before. One series at a time, by the toggle. */
export default function TeamLoadChart({ load, asOf }: { load: TeamLoadPoint[]; asOf: string }) {
  const [series, setSeries] = useState<Series>('load')
  const unit = series === 'load' ? 'AU' : 'jumps'
  const data = load.map((p) => ({
    date: p.date,
    value: series === 'load' ? p.load_per_athlete : p.jumps_per_athlete,
  }))
  const weekStart = addDays(asOf, -6)
  const priorStart = addDays(asOf, -13)
  const sum = (from: string, to: string) =>
    data.filter((p) => p.date >= from && p.date <= to).reduce((a, p) => a + (p.value ?? 0), 0)
  const week = sum(weekStart, asOf)
  const prior = sum(priorStart, addDays(weekStart, -1))
  const change = prior > 0 ? ((week - prior) / prior) * 100 : null

  return (
    <SectionCard
      title="Team load"
      aside="per athlete · 28 days"
      action={
        <SegmentedControl
          size="sm"
          options={OPTIONS}
          value={series}
          onChange={setSeries}
          aria-label="Series"
        />
      }
    >
      <InlineReadout
        items={[
          { key: 'week', label: `${unit} this week`, value: fmt(week) },
          { key: 'prior', label: 'prior week', value: fmt(prior) },
          {
            key: 'change',
            label: 'week on week',
            value: pct(change),
            tone: loadTone(change),
            hint: change != null && change > 15 ? 'over the 15% step' : undefined,
          },
        ]}
      />
      <div className="mt-3 rounded-control-sm bg-panel p-2">
        <LoadBars
          data={data}
          asOf={asOf}
          unit={unit}
          label={series === 'load' ? 'Team session load per athlete' : 'Team jumps per athlete'}
        />
      </div>
      <p className="meta mt-1.5">
        Dashed line: the 28-day mean, {fmt(meanPerDay(data, asOf))} {unit} per athlete per day.
      </p>
    </SectionCard>
  )
}
