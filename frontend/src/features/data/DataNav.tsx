import { useLocation } from 'react-router-dom'
import SegmentedControl from '../../components/SegmentedControl'

type Section = 'roster' | 'dictionary'

/** The Data tab's sub-nav, like the Calendar's: the roster by data family,
 *  and the dictionary of every metric. A chart's own data sits under the
 *  roster. */
export default function DataNav({ className = '' }: { className?: string }) {
  const { pathname } = useLocation()
  const value: Section = pathname.startsWith('/data/dictionary') ? 'dictionary' : 'roster'
  return (
    <SegmentedControl<Section>
      options={[
        { key: 'roster', label: 'Roster', to: '/data' },
        { key: 'dictionary', label: 'Dictionary', to: '/data/dictionary' },
      ]}
      value={value}
      size="sm"
      tone="glass"
      aria-label="Data sections"
      className={className}
    />
  )
}
