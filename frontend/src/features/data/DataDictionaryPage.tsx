import { BookOpenText, ChevronLeft, Ruler } from 'lucide-react'
import { Link } from 'react-router-dom'
import EmptyState from '../../components/EmptyState'
import { SettingsHero } from '../settings/Switch'

/** `/data/dictionary` — every metric MedPull shows, with its unit, tier,
 *  source and method. The page head is in place; the table arrives with the
 *  Data stream (docs/dev/showcase.md, "Data"). Until then it says where a
 *  metric's method can already be read. */
export default function DataDictionaryPage() {
  return (
    <div className="pb-10">
      <SettingsHero icon={<BookOpenText />} title="Metric dictionary">
        Every metric MedPull shows will be listed here with its unit, its tier, where it comes
        from and how it is computed.
      </SettingsHero>

      <EmptyState
        className="rise mt-8"
        icon={<Ruler />}
        family="teal"
        title="For now, each metric explains itself"
        action={
          <Link to="/data" className="btn-plain">
            <ChevronLeft size={16} aria-hidden /> All data
          </Link>
        }
      >
        On a chart, the i beside any metric says what it measures and how it is worked out.
      </EmptyState>
    </div>
  )
}
