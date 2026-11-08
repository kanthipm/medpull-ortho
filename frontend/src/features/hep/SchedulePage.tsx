import { CalendarDays, Dumbbell, Film, MonitorSmartphone } from 'lucide-react'
import type { CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { useConsoleSession, useIsDemo } from '../../api/queries'
import { SettingsHero } from '../settings/Switch'
import ExercisesNav from './ExercisesNav'
import ScheduleBoard from './ScheduleBoard'

/** `/exercise-schedule` — the clinic's week: every patient's exercises by
 *  day, what they did and how it felt, and the therapist's own clip behind
 *  each one. The first tab of Exercises; the demo-screen link shows on the
 *  demo stack only. */
export default function SchedulePage() {
  const demo = useIsDemo()
  const { data: session } = useConsoleSession()
  const clinic = session?.scope.kind === 'hospital' ? session.scope.name : null

  return (
    <div className="pb-10">
      <SettingsHero
        nav={<ExercisesNav />}
        icon={<CalendarDays />}
        title="Exercise schedule"
        decor={[<CalendarDays key="c" />, <Dumbbell key="d" />, <Film key="f" />]}
      >
        {clinic ? `${clinic}’s week` : 'The week'} on one grid: each patient’s exercises by day,
        what they did and how it felt, and your own demonstration playing on their phone.
      </SettingsHero>

      <div className="rise mt-8" style={{ '--rise-delay': '80ms' } as CSSProperties}>
        <ScheduleBoard
          aside={
            demo ? (
              <Link to="/demo/hirt" className="btn-plain btn-sm">
                <MonitorSmartphone size={14} aria-hidden /> Open the demo screen
              </Link>
            ) : undefined
          }
        />
      </div>
    </div>
  )
}
