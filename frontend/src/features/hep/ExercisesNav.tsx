import { useLocation } from 'react-router-dom'
import SegmentedControl from '../../components/SegmentedControl'

type Page = 'plans' | 'library'

const OPTIONS: { key: Page; label: string; text: string; to: string }[] = [
  { key: 'plans', label: 'Plans', text: 'Plans', to: '/exercise-plans' },
  { key: 'library', label: 'Library', text: 'Library', to: '/exercise-library' },
]

/** Sub-nav for the exercise pages, like SettingsNav: the glass segmented
 *  control on the sky, sized as a sub-nav under the app bar. */
export default function ExercisesNav({ className = '' }: { className?: string }) {
  const { pathname } = useLocation()
  const value: Page = pathname.startsWith('/exercise-library') ? 'library' : 'plans'
  return (
    <SegmentedControl<Page>
      options={OPTIONS}
      value={value}
      size="sm"
      tone="glass"
      aria-label="Exercise sections"
      className={className}
    />
  )
}
