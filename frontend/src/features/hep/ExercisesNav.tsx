import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useReviewCount } from '../../api/calendar'
import { useQuestions } from '../../api/pt'
import SegmentedControl from '../../components/SegmentedControl'
import { CALENDAR, calendarSection, type CalendarSection } from './paths'

/** The Calendar tab's sub-nav, like SettingsNav: the glass segmented control
 *  on the sky, sized as a sub-nav under the app bar. The schedule (the week
 *  grid) comes first; Week is each lifter's week in review; Review carries the
 *  count of done days waiting on the therapist; Questions the count of
 *  lifters' questions sorted to today; Programs are the clinic's templates;
 *  then the library they are built from, the plans, and the clinic's own
 *  rules. The paths are in `paths.ts`. */
export default function ExercisesNav({ className = '' }: { className?: string }) {
  const { pathname } = useLocation()
  const waiting = useReviewCount().data?.count ?? 0
  const asked = useQuestions().data?.today.length ?? 0
  const options: { key: CalendarSection; label: ReactNode; text: string; to: string }[] = [
    { key: 'schedule', label: 'Schedule', text: 'Schedule', to: CALENDAR.schedule },
    { key: 'week', label: 'Week', text: 'Week', to: CALENDAR.week },
    {
      key: 'review',
      label: (
        <>
          Review
          {waiting > 0 && (
            <span className="ml-1.5 inline-grid min-h-[18px] min-w-[18px] place-items-center rounded-pill bg-risk-med-tint px-1 text-micro font-medium leading-none tabular-nums text-risk-med-ink">
              {waiting}
              <span className="sr-only"> awaiting</span>
            </span>
          )}
        </>
      ),
      text: waiting > 0 ? `Review, ${waiting} awaiting` : 'Review',
      to: CALENDAR.review,
    },
    {
      key: 'questions',
      label: (
        <>
          Questions
          {asked > 0 && (
            <span className="ml-1.5 inline-grid min-h-[18px] min-w-[18px] place-items-center rounded-pill bg-risk-med-tint px-1 text-micro font-medium leading-none tabular-nums text-risk-med-ink">
              {asked}
              <span className="sr-only"> for today</span>
            </span>
          )}
        </>
      ),
      text: asked > 0 ? `Questions, ${asked} for today` : 'Questions',
      to: CALENDAR.questions,
    },
    { key: 'programs', label: 'Programs', text: 'Programs', to: CALENDAR.programs },
    { key: 'library', label: 'Library', text: 'Library', to: CALENDAR.library },
    { key: 'plans', label: 'Plans', text: 'Plans', to: CALENDAR.plans },
    { key: 'rules', label: 'Rules', text: 'Rules', to: CALENDAR.rules },
  ]
  return (
    <SegmentedControl<CalendarSection>
      options={options}
      value={calendarSection(pathname)}
      size="sm"
      tone="glass"
      aria-label="Calendar sections"
      className={className}
    />
  )
}
