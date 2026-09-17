import { useLocation } from 'react-router-dom'
import SegmentedControl from '../../components/SegmentedControl'

type Page = 'general' | 'library'

// The General page still lives at /settings/notifications (App.tsx owns the
// route table); it now carries alert channels AND appearance.
const OPTIONS: { key: Page; label: string; text: string; to: string }[] = [
  { key: 'general', label: 'General', text: 'General', to: '/settings/notifications' },
  { key: 'library', label: 'Library', text: 'Library', to: '/settings/library' },
]

/** Settings sub-nav — route-driven, shared by every settings page. The
 *  brand-thumb segmented control, sized down so it reads as a sub-nav under
 *  the app bar rather than a second bar. */
export default function SettingsNav({ className = '' }: { className?: string }) {
  const { pathname } = useLocation()
  const value: Page = pathname.startsWith('/settings/library') ? 'library' : 'general'
  return (
    <SegmentedControl<Page>
      options={OPTIONS}
      value={value}
      size="sm"
      aria-label="Settings sections"
      className={className}
    />
  )
}
