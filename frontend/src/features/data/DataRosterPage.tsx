import { BookOpenText, Database, Layers, Table2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import EmptyState from '../../components/EmptyState'
import { SettingsHero } from '../settings/Switch'

/** `/data` — the Clinic version's Data tab: the roster's data in tiers,
 *  from the sources and their coverage down to the care metrics. The page
 *  head is in place; the roster view itself arrives with the Data stream
 *  (docs/dev/showcase.md, "Data"). Until then it points at where the same
 *  readings live today. */
export default function DataRosterPage() {
  return (
    <div className="pb-10">
      <SettingsHero
        icon={<Database />}
        title="Data"
        decor={[<Database key="d" />, <Layers key="l" />, <Table2 key="t" />]}
      >
        Every reading behind the roster will be here in tiers: sources and coverage, raw
        readings, daily signals against each person’s baseline, what MedPull computes itself, and
        the care metrics.
      </SettingsHero>

      <EmptyState
        className="rise mt-8"
        icon={<Table2 />}
        family="teal"
        title="For now, the data is on each chart"
        action={
          <>
            <Link to="/" className="btn-tinted">
              Open the worklist
            </Link>
            <Link to="/data/dictionary" className="btn-plain">
              <BookOpenText size={16} aria-hidden /> Metric dictionary
            </Link>
          </>
        }
      >
        Open a chart from the worklist and expand Full stats for its metrics, signals and raw
        readings.
      </EmptyState>
    </div>
  )
}
