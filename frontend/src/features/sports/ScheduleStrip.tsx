import { Dumbbell, Target, Trophy, Users } from 'lucide-react'
import type { ReactNode } from 'react'
import type { TeamEvent } from '../../api/sports'
import SectionCard from '../../components/SectionCard'
import Tile, { type TileFamily } from '../../components/Tile'
import { shortDate } from '../../lib/format'
import { addDays, daysBetween, nextGame, opponentLine, timeLabel, weekday } from './sportsFormat'

/** Event kinds on the console's tile families (hue by category, never by
 *  state): games clay, practice sage, lifts amber, shootarounds lilac. */
const KIND: Record<string, { family: TileFamily; icon: ReactNode }> = {
  game: { family: 'violet', icon: <Trophy /> },
  match: { family: 'violet', icon: <Trophy /> },
  practice: { family: 'teal', icon: <Users /> },
  lift: { family: 'blue', icon: <Dumbbell /> },
  shootaround: { family: 'indigo', icon: <Target /> },
}

/** The next seven days as a strip of day cells, today first and on the
 *  brand tint with the lime "now" dot. Each event is a small tile, its
 *  title, the opponent and the start time. */
export default function ScheduleStrip({ events, asOf }: { events: TeamEvent[]; asOf: string }) {
  const days = Array.from({ length: 7 }, (_, i) => addDays(asOf, i))
  const game = nextGame(events, asOf)
  const aside = game
    ? game.date === asOf
      ? `Game day · ${opponentLine(game)}`
      : `Next game in ${daysBetween(asOf, game.date)} ${daysBetween(asOf, game.date) === 1 ? 'day' : 'days'} · ${opponentLine(game)}`
    : 'No game on the schedule'

  return (
    <SectionCard title="This week" aside={aside}>
      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7" aria-label="The next seven days">
        {days.map((day, i) => {
          const today = i === 0
          const evs = events
            .filter((e) => e.date === day)
            .sort((a, b) => (a.start_time ?? '').localeCompare(b.start_time ?? ''))
          return (
            <li
              key={day}
              aria-current={today ? 'date' : undefined}
              className={`min-w-0 rounded-control p-3 ${today ? 'on-tint bg-brand-tint' : 'bg-soft'}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-2 text-copy font-medium text-ink">
                  {today && <span aria-hidden className="dot-lime" />}
                  {today ? 'Today' : weekday(day)}
                </span>
                <span className="meta tabular-nums">{shortDate(day)}</span>
              </div>
              {evs.length === 0 ? (
                <p className="meta mt-2.5">Rest day</p>
              ) : (
                <ul className="mt-2.5 space-y-2">
                  {evs.map((e) => {
                    const k = KIND[e.kind] ?? { family: 'teal' as const, icon: <Users /> }
                    const when = timeLabel(e.start_time)
                    return (
                      <li key={e.id} className="flex items-start gap-2">
                        <Tile size="sm" family={k.family} icon={k.icon} className="mt-0.5" />
                        <span className="min-w-0">
                          <span className="line-clamp-2 block text-copy text-ink">
                            {e.title}
                            {e.opponent && <span className="text-secondary"> · {opponentLine(e)}</span>}
                          </span>
                          <span className="meta block truncate tabular-nums">
                            {[when, e.home == null ? null : e.home ? 'Home' : 'Away'].filter(Boolean).join(' · ')}
                          </span>
                        </span>
                      </li>
                    )
                  })}
                </ul>
              )}
            </li>
          )
        })}
      </ol>
    </SectionCard>
  )
}
