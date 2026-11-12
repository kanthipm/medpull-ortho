import { ChevronLeft, Database, Layers } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import EmptyState from '../../components/EmptyState'
import { SettingsHero } from '../settings/Switch'

/** `/data/patients/:id` — one chart's data, tier by tier. The page head is
 *  in place; the tiers arrive with the Data stream (docs/dev/showcase.md,
 *  "Data"). Until then it sends the reader to the chart, whose Full stats
 *  section holds the same readings. */
export default function DataPatientPage() {
  const { id = '' } = useParams()
  return (
    <div className="pb-10">
      <SettingsHero icon={<Database />} title="Chart data">
        This chart’s data will be here tier by tier, from its sources and raw readings to the
        care metrics and the risk read.
      </SettingsHero>

      <EmptyState
        className="rise mt-8"
        icon={<Layers />}
        family="teal"
        title="For now, it is on the chart"
        action={
          <>
            <Link to={`/patients/${encodeURIComponent(id)}`} className="btn-tinted">
              Open the chart
            </Link>
            <Link to="/data" className="btn-plain">
              <ChevronLeft size={16} aria-hidden /> All data
            </Link>
          </>
        }
      >
        The chart’s Full stats section has its metrics, signals and raw readings.
      </EmptyState>
    </div>
  )
}
