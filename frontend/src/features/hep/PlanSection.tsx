import { Dumbbell, Plus } from 'lucide-react'
import { Link } from 'react-router-dom'
import { usePatientPlans } from '../../api/hep'
import { useHealth } from '../../api/queries'
import EmptyState from '../../components/EmptyState'
import ListRow, { ListGroup } from '../../components/ListRow'
import SectionCard from '../../components/SectionCard'
import { RefreshOverlay, SkeletonCard } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { relativeTime } from '../../lib/format'
import { planStatus } from './planCopy'

/** The patient page's "Exercise plan" card: the published plan they are on
 *  (each exercise with its dose), any drafts waiting, and the way into the
 *  editor. Rendered only while the server's HEP flag is on. */
export default function PlanSection({ patientId, refreshing }: { patientId: string; refreshing: boolean }) {
  const hep = useHealth().data?.hep === true
  const plans = usePatientPlans(patientId)
  if (!hep) return null
  if (plans.isLoading) return <SkeletonCard rows={3} />
  const data = plans.data
  const active = data?.active ?? null
  const drafts = data?.drafts ?? []
  const newHref = `/exercise-plans/new?patient=${encodeURIComponent(patientId)}`

  return (
    <SectionCard
      title="Exercise plan"
      icon={<Tile size="sm" family="teal" icon={<Dumbbell />} />}
      aside={active?.published_at ? `Published ${relativeTime(active.published_at)}` : undefined}
      action={
        active ? (
          <Link to={`/exercise-plans/${active.id}`} className="btn-plain btn-sm">Edit plan</Link>
        ) : (
          <Link to={newHref} className="btn-plain btn-sm"><Plus size={14} /> Assign plan</Link>
        )
      }
      flush={Boolean(active)}
    >
      <RefreshOverlay show={refreshing} />
      {plans.isError ? (
        <EmptyState variant="inline" title="The exercise plan couldn’t be loaded." icon={<Dumbbell />}>
          Refresh the page to try again.
        </EmptyState>
      ) : active ? (
        <>
          {active.notes && <p className="px-5 pb-2 text-copy text-body">{active.notes}</p>}
          <ListGroup embedded inset="none" aria-label="Exercises on the published plan" as="ol">
            {(active.items ?? []).map((i) => (
              <ListRow key={i.id} compact title={i.title} subtitle={i.dose}
                meta={i.clinician_instructions || undefined}
                aside={i.media?.playable ? 'Clip' : undefined} />
            ))}
          </ListGroup>
          <p className="meta px-5 pb-4 pt-3">
            {active.exercise_count} exercise{active.exercise_count === 1 ? '' : 's'} · assigned by {active.assigned_by_name ?? active.assigned_by}
            {drafts.length > 0 && <> · <Link to={`/exercise-plans/${drafts[0].id}`} className="underline">A draft is waiting</Link></>}
          </p>
        </>
      ) : drafts.length > 0 ? (
        <ListGroup inset="none" aria-label="Draft plans" className="!rounded-[14px]">
          {drafts.map((d) => (
            <ListRow key={d.id} compact title={d.title} to={`/exercise-plans/${d.id}`}
              subtitle={`${d.exercise_count} exercise${d.exercise_count === 1 ? '' : 's'} · updated ${relativeTime(d.updated_at)}`}
              trailing={<span className={`chip ${planStatus(d.status).pill}`}>{planStatus(d.status).label}</span>} />
          ))}
        </ListGroup>
      ) : (
        <EmptyState variant="inline" title="No exercise plan yet" icon={<Dumbbell />} family="teal"
          action={<Link to={newHref} className="btn-tinted"><Plus size={16} /> Assign plan</Link>}>
          Build one from the library; it appears in their app the moment it is published.
        </EmptyState>
      )}
    </SectionCard>
  )
}
