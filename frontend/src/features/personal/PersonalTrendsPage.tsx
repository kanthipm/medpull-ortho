import { CalendarRange, Dumbbell, Flame, Moon, Sparkle, TrendingUp } from 'lucide-react'
import type { CSSProperties } from 'react'
import { useParams } from 'react-router-dom'
import {
  usePersonalOverview,
  usePersonalWeek,
  type Panel,
  type PersonalOverview,
  type PersonalWeek,
  type Trend,
} from '../../api/personal'
import { NarrativeTile } from '../../components/AIAttribution'
import SectionCard from '../../components/SectionCard'
import Tile from '../../components/Tile'
import { relativeTime, shortDate } from '../../lib/format'
import { MemberHead, MiniLine, PersonalState, WritingBlock } from './PersonalBits'
import {
  PANEL_GLYPH,
  TREND_ORDER,
  changeTone,
  panelChip,
  short,
  signed,
  trendValue,
  trendWeeks,
  values,
} from './personalFormat'

/** `/personal/:memberId/trends` — the member's weeks: this week against the
 *  last, the week in the app's own words, thirteen weeks of each trend, then
 *  the two long reads the app is built around (sleep and recovery; training
 *  load and form). */
export default function PersonalTrendsPage() {
  const { memberId = '' } = useParams()
  const overview = usePersonalOverview(memberId)
  const week = usePersonalWeek(memberId)
  return (
    <div className="pb-10">
      <PersonalState
        loading={overview.isLoading || week.isLoading}
        error={overview.isError || week.isError || (!overview.isLoading && !overview.data)}
        onRetry={() => {
          void overview.refetch()
          void week.refetch()
        }}
      >
        {overview.data && week.data && <Trends o={overview.data} w={week.data} />}
      </PersonalState>
    </div>
  )
}

const TONE: Record<'good' | 'watch' | 'plain', string> = {
  good: 'bg-risk-low-tint text-risk-low-ink',
  watch: 'bg-risk-med-tint text-risk-med-ink',
  plain: 'bg-soft text-body',
}

function Trends({ o, w }: { o: PersonalOverview; w: PersonalWeek }) {
  const first = o.member.name.split(' ')[0]
  const week = w.week
  const panels = o.dashboard.panels
  return (
    <>
      <MemberHead overview={o} />

      {/* ── This week against last ──────────────────────────────────────── */}
      <SectionCard
        className="rise mt-8"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
        title="This week against last"
        icon={<Tile size="sm" family="teal" icon={<CalendarRange />} />}
        aside={`${shortDate(week.start)} to ${shortDate(week.end)}`}
      >
        <dl className="grid gap-x-6 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
          {TREND_ORDER.map((key) => {
            const m = week.metrics[key]
            const trend = w.trends[key]
            if (!m) return null
            const tone = changeTone(key, m.delta_pct)
            return (
              <div key={key} className="min-w-0">
                <dt className="text-label font-medium tracking-label text-secondary">
                  {trend?.label ?? key}
                  {/* The week's load is its total; the others are the week's average. */}
                  {key === 'load' ? ', week total' : ''}
                </dt>
                <dd className="mt-0.5">
                  <span className="big-num text-[1.5rem] text-ink">{trendValue(key, m.this, m.unit)}</span>
                  <span className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className={`chip normal-case tabular-nums ${TONE[tone]}`}>{signed(m.delta_pct)}</span>
                    <span className="meta">was {trendValue(key, m.last, m.unit)}</span>
                  </span>
                </dd>
              </div>
            )
          })}
        </dl>
        <ul className="mt-5 space-y-1 border-t border-hairline pt-4">
          {week.highlights.map((line) => (
            <li key={line} className="flex gap-2 text-copy text-ink">
              <Sparkle aria-hidden size={14} className="mt-1 shrink-0 text-secondary" />
              {line}
            </li>
          ))}
        </ul>
        <p className="meta mt-3">
          {week.sessions} session{week.sessions === 1 ? '' : 's'} · {Math.round(week.session_minutes)} min trained ·{' '}
          checked in {week.streaks.checkin_days} day{week.streaks.checkin_days === 1 ? '' : 's'} running
          {week.readiness_days.best?.value != null &&
            ` · best day ${shortDate(week.readiness_days.best.date)} (${Math.round(week.readiness_days.best.value)})`}
          {week.readiness_days.worst?.value != null &&
            ` · hardest ${shortDate(week.readiness_days.worst.date)} (${Math.round(week.readiness_days.worst.value)})`}
        </p>
      </SectionCard>

      {/* ── The week in the app's own words ─────────────────────────────── */}
      <SectionCard
        className="mt-stack"
        sum
        title={w.review.title || 'Your week'}
        icon={<NarrativeTile provider={w.review.provider} />}
        aside={`The weekly review · ${relativeTime(w.review.generated_at)}`}
      >
        <WritingBlock writing={w.review} text={w.review.body ?? ''} />
      </SectionCard>

      {/* ── Thirteen weeks ──────────────────────────────────────────────── */}
      <section className="mt-stack" aria-labelledby="thirteen-weeks">
        <h2 id="thirteen-weeks" className="mb-3 px-1 text-subhead font-medium text-ink">
          Thirteen weeks
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {TREND_ORDER.map((key) => {
            const trend = w.trends[key]
            return trend ? <TrendCard key={key} id={key} trend={trend} /> : null
          })}
        </div>
        <p className="meta mt-3 px-1">
          A bar is a week’s daily average (a week with too few days is left out). The change
          compares the last four weeks with the four before them.
        </p>
      </section>

      {/* ── The two long reads ──────────────────────────────────────────── */}
      <div className="mt-stack grid gap-stack lg:grid-cols-2 lg:items-start">
        <SectionCard title="Sleep and recovery" icon={<Tile size="sm" family="indigo" icon={<Moon />} />} aside="28 days">
          <div className="space-y-4">
            {(['sleep', 'hrv', 'resting_hr'] as const).map((key) =>
              panels[key] ? <LongRow key={key} panel={panels[key]} first={first} /> : null,
            )}
          </div>
        </SectionCard>

        <SectionCard title="Training load and form" icon={<Tile size="sm" family="teal" icon={<Dumbbell />} />} aside="28 days">
          <div className="space-y-4">
            {panels.load && <LongRow panel={panels.load} first={first} />}
            {panels.load && <Form panel={panels.load} />}
            {panels.overreach && <LongRow panel={panels.overreach} first={first} />}
          </div>
        </SectionCard>
      </div>

      <p className="meta mt-8 px-1">{w.review.guardrail}</p>
    </>
  )
}

/** One trend over thirteen weeks as bars, with where it stands now and how
 *  the last four weeks compare with the four before. */
function TrendCard({ id, trend }: { id: string; trend: Trend }) {
  const weeks = trendWeeks(trend)
  const glyph = PANEL_GLYPH[id === 'steps' ? 'activity' : id]
  const Icon = glyph?.icon ?? TrendingUp
  const latest = weeks[weeks.length - 1]
  const lo = Math.min(...weeks.map((w) => w.value))
  const hi = Math.max(...weeks.map((w) => w.value))
  // Bars start a little under the lowest week, so a narrow range (resting
  // heart rate) still shows its shape; the numbers are printed either side.
  const floor = lo - (hi - lo || 1) * 0.35
  const tone = changeTone(id, trend.change_pct)
  return (
    <article className="rounded-control bg-soft p-4" aria-label={`${trend.label}, thirteen weeks`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <Tile size="sm" family={glyph?.family ?? 'teal'} icon={<Icon />} />
          <h3 className="truncate text-copy-lg font-medium text-ink">{trend.label}</h3>
        </div>
        {trend.change_pct != null && (
          <span className={`chip shrink-0 normal-case tabular-nums ${TONE[tone]}`}>{signed(trend.change_pct)}</span>
        )}
      </div>
      <p className="mt-3">
        <span className="big-num text-[1.75rem] text-ink">{latest ? trendValue(id, latest.value, trend.unit) : '—'}</span>
        <span className="meta ml-2">{id === 'load' || id === 'steps' ? 'a day, this week' : 'average this week'}</span>
      </p>
      {weeks.length < 2 ? (
        <p className="meta mt-3">
          {trend.weeks_with_data} week{trend.weeks_with_data === 1 ? '' : 's'} so far; the trend starts with the second.
        </p>
      ) : (
        <>
          <ol
            className="mt-3 flex h-20 items-end gap-1 rounded-control-sm bg-panel px-2 pb-1.5 pt-2"
            aria-label={`${trend.label} by week, oldest first`}
          >
            {trend.weeks.map((wk) => {
              const share = wk.value == null ? 0 : (wk.value - floor) / (hi - floor || 1)
              return (
                <li key={wk.week} className="flex h-full flex-1 items-end" title={`Week of ${shortDate(wk.week)}: ${trendValue(id, wk.value, trend.unit)}`}>
                  <span
                    className={`block w-full rounded-[3px] ${wk.value == null ? 'bg-[rgb(var(--fill))]' : 'bg-chart-s1'}`}
                    style={{ height: wk.value == null ? '3px' : `${Math.max(6, share * 100)}%` }}
                  />
                  <span className="sr-only">
                    Week of {shortDate(wk.week)}: {wk.value == null ? 'not enough days' : trendValue(id, wk.value, trend.unit)}.
                  </span>
                </li>
              )
            })}
          </ol>
          <p className="meta mt-1.5 flex justify-between tabular-nums">
            <span>{shortDate(trend.weeks[0].week)}</span>
            <span>
              low {trendValue(id, lo, trend.unit)} · high {trendValue(id, hi, trend.unit)}
            </span>
          </p>
        </>
      )}
    </article>
  )
}

/** One readout across four weeks: its state in words, the number, the line
 *  of days, and its small figures. */
function LongRow({ panel, first }: { panel: Panel; first: string }) {
  const series = values(panel.series)
  const need = panel.key === 'sleep' ? (panel.extra?.need_hours as number | undefined) : undefined
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="text-copy font-medium text-ink">
          {panel.title}{' '}
          <span className="font-normal tabular-nums text-secondary">
            {panel.headline}
            {panel.unit ? ` ${panel.unit}` : ''}
          </span>
        </h3>
        <span className={`chip ${panelChip(panel.status)}`}>{panel.status_text}</span>
      </div>
      {series.length > 1 && (
        <div className="mt-2 rounded-control-sm bg-soft px-2 py-1.5">
          <MiniLine
            points={series}
            height={56}
            reference={need ?? null}
            label={`${panel.title} over ${series.length} days${need != null ? `; the dashed rule is ${first}’s sleep need` : ''}`}
          />
        </div>
      )}
      {panel.stats && panel.stats.length > 0 && (
        <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
          {panel.stats.map((s) => (
            <div key={s.label} className="flex items-baseline gap-1.5">
              <dt className="text-label text-secondary">{s.label}</dt>
              <dd className="text-copy tabular-nums text-ink">
                {s.value}
                {s.unit && <span className="text-secondary"> {s.unit}</span>}
              </dd>
            </div>
          ))}
        </dl>
      )}
      <p className="mt-1.5 text-copy text-body">{panel.finding}</p>
    </div>
  )
}

/** Fitness, fatigue and form: the slow average of load, the fast one, and
 *  the gap between them, as three lines with their latest values printed. */
function Form({ panel }: { panel: Panel }) {
  const rows = (panel.extra?.form_series as { date: string; fitness: number; fatigue: number; form: number }[] | undefined) ?? []
  if (rows.length < 2) return null
  const unit = (panel.extra?.unit as string | undefined) ?? ''
  const last = rows[rows.length - 1]
  const lines = [
    { key: 'fitness', label: 'Fitness', hint: 'the slow average (42 days)', points: rows.map((r) => r.fitness), value: last.fitness },
    { key: 'fatigue', label: 'Fatigue', hint: 'the fast average (7 days)', points: rows.map((r) => r.fatigue), value: last.fatigue },
    { key: 'form', label: 'Form', hint: 'fitness minus fatigue', points: rows.map((r) => r.form), value: last.form },
  ]
  return (
    <div>
      <h3 className="flex items-center gap-2 text-copy font-medium text-ink">
        <Flame aria-hidden size={14} className="text-secondary" /> Fitness, fatigue and form
      </h3>
      <div className="mt-2 grid gap-2 sm:grid-cols-3">
        {lines.map((l) => (
          <div key={l.key} className="rounded-control-sm bg-soft px-2.5 py-2">
            <p className="flex items-baseline justify-between gap-2">
              <span className="text-label text-secondary">{l.label}</span>
              <span className="text-copy font-medium tabular-nums text-ink">
                {short(l.value, 0)}
                {unit && <span className="font-normal text-secondary"> {unit}</span>}
              </span>
            </p>
            <MiniLine points={l.points} height={40} reference={l.key === 'form' ? 0 : null} label={`${l.label} over ${rows.length} days`} />
            <p className="text-micro text-secondary">{l.hint}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
