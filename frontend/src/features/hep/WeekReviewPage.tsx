import { CalendarCheck, CalendarRange } from 'lucide-react'
import { Link } from 'react-router-dom'
import EmptyState from '../../components/EmptyState'
import { SettingsHero } from '../settings/Switch'
import ExercisesNav from './ExercisesNav'
import { CALENDAR } from './paths'

/** `/calendar/week` — one lifter's week in review, and next week's draft.
 *  The page head and its place in the sub-nav are set; the review itself
 *  arrives with the Calendar stream (docs/dev/showcase.md, "Calendar").
 *  Until then it points at the two pages that hold the same week today. */
export default function WeekReviewPage() {
  return (
    <div className="pb-10">
      <SettingsHero nav={<ExercisesNav />} icon={<CalendarRange />} title="Week">
        One lifter’s week in review will be here: what was done against what was prescribed, pain
        and effort by day, and next week’s draft for you to approve.
      </SettingsHero>

      <EmptyState
        className="rise mt-8"
        icon={<CalendarCheck />}
        family="teal"
        title="For now, the week is on the schedule"
        action={
          <>
            <Link to={CALENDAR.schedule} className="btn-tinted">
              Open the schedule
            </Link>
            <Link to={CALENDAR.review} className="btn-plain">
              Clips to review
            </Link>
          </>
        }
      >
        The schedule shows each lifter’s week by day, and Review holds the clips waiting on you.
      </EmptyState>
    </div>
  )
}
