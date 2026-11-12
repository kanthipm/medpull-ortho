import { ArrowUpRight, Database } from 'lucide-react'
import { Link } from 'react-router-dom'
import Tile from '../../components/Tile'
import { VIEWS, dataPath } from './dataFormat'

/** The row on a chart that leads into its data: one link per view of the
 *  Data tab's explorer. It replaces the "Full stats" sheet the chart used to
 *  carry, so the readings, signals and metrics have one home. */
export default function DataLinks({ patientId, className = '' }: { patientId: string; className?: string }) {
  return (
    <nav
      aria-label="This chart’s data"
      className={`panel flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4 ${className}`}
    >
      <div className="flex min-w-0 flex-1 basis-[260px] items-center gap-3">
        <Tile size="sm" family="teal" icon={<Database />} />
        <div className="min-w-0">
          <h2 className="text-lede font-semibold text-ink">All data</h2>
          <p className="meta">Every reading, signal and metric behind this chart, tier by tier.</p>
        </div>
      </div>
      <ul className="flex flex-wrap gap-2">
        {VIEWS.map((v) => (
          <li key={v.key}>
            <Link to={dataPath(patientId, v.key)} className="btn-tinted btn-sm">
              {v.label}
            </Link>
          </li>
        ))}
        <li>
          <Link to={dataPath(patientId)} className="btn-plain btn-sm">
            Open <ArrowUpRight aria-hidden size={14} />
          </Link>
        </li>
      </ul>
    </nav>
  )
}
