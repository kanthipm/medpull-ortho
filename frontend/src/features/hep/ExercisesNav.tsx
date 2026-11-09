import type { ReactNode } from 'react'
import { useLocation } from 'react-router-dom'
import { useReviewQueue } from '../../api/hep'
import SegmentedControl from '../../components/SegmentedControl'

type Page = 'schedule' | 'review' | 'programs' | 'plans' | 'library'

/** Sub-nav for the exercise pages, like SettingsNav: the glass segmented
 *  control on the sky, sized as a sub-nav under the app bar. The schedule
 *  (the week grid) comes first; Review carries the count of clips waiting
 *  on the therapist; Programs are the clinic's templates; plans and the
 *  library stay. */
export default function ExercisesNav({ className = '' }: { className?: string }) {
  const { pathname } = useLocation()
  const queue = useReviewQueue()
  const waiting = queue.data?.items.length ?? 0
  const value: Page = pathname.startsWith('/exercise-schedule')
    ? 'schedule'
    : pathname.startsWith('/exercise-review')
      ? 'review'
      : pathname.startsWith('/exercise-programs')
        ? 'programs'
        : pathname.startsWith('/exercise-library')
          ? 'library'
          : 'plans'
  const options: { key: Page; label: ReactNode; text: string; to: string }[] = [
    { key: 'schedule', label: 'Schedule', text: 'Schedule', to: '/exercise-schedule' },
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
      to: '/exercise-review',
    },
    { key: 'programs', label: 'Programs', text: 'Programs', to: '/exercise-programs' },
    { key: 'plans', label: 'Plans', text: 'Plans', to: '/exercise-plans' },
    { key: 'library', label: 'Library', text: 'Library', to: '/exercise-library' },
  ]
  return (
    <SegmentedControl<Page>
      options={options}
      value={value}
      size="sm"
      tone="glass"
      aria-label="Exercise sections"
      className={className}
    />
  )
}
