import { useLocation } from 'react-router-dom'
import SegmentedControl from '../../components/SegmentedControl'

type Page = 'notifications' | 'library'

const OPTIONS: { key: Page; label: string; to: string }[] = [
  { key: 'notifications', label: 'Notifications', to: '/settings/notifications' },
  { key: 'library', label: 'Library', to: '/settings/library' },
]

/** Settings sub-nav — route-driven, shared by every settings page. */
export default function SettingsNav({ className = '' }: { className?: string }) {
  const { pathname } = useLocation()
  const value: Page = pathname.startsWith('/settings/library') ? 'library' : 'notifications'
  return <SegmentedControl<Page> options={OPTIONS} value={value} aria-label="Settings" className={className} />
}
