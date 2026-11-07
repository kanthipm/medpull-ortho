import { ClipboardList, Dumbbell, Plus, Stethoscope, Users } from 'lucide-react'
import { useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { Plan } from '../../api/hep'
import { usePlans } from '../../api/hep'
import EmptyState from '../../components/EmptyState'
import SegmentedControl from '../../components/SegmentedControl'
import { SkeletonCard } from '../../components/Skeleton'
import { relativeTime } from '../../lib/format'
import { GroupFooter, GroupHeader, SettingsHero } from '../settings/Switch'
import ExercisesNav from './ExercisesNav'
import { planStatus } from './planCopy'

type Filter = 'all' | 'draft' | 'active' | 'closed'
const FILTERS: { key: Filter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'draft', label: 'Drafts' },
  { key: 'active', label: 'Published' },
  { key: 'closed', label: 'Closed' },
]

/** `/exercise-plans` — every home exercise plan the clinic has written:
 *  drafts still being built, the plan each patient is on now, and the ones
 *  replaced or archived. */
export default function ExercisePlansPage() {
  const [filter, setFilter] = useState<Filter>('all')
  const plans = usePlans()
  const rows = (plans.data?.plans ?? []).filter((p) =>
    filter === 'all'
      ? true
      : filter === 'closed'
        ? p.status === 'superseded' || p.status === 'archived'
        : p.status === filter,
  )

  return (
    <div className="pb-10">
      <SettingsHero
        nav={<ExercisesNav />}
        icon={<ClipboardList />}
        title="Exercise plans"
        decor={[<ClipboardList key="c" />, <Dumbbell key="d" />, <Stethoscope key="s" />]}
      >
        Home exercise plans your clinic has assigned. Each patient is on one published plan at a
        time; publishing a new one replaces it.
      </SettingsHero>

      <div
        className="rise mt-8 flex flex-wrap items-center gap-x-3 gap-y-3"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        <SegmentedControl<Filter>
          options={FILTERS}
          value={filter}
          onChange={setFilter}
          tone="glass"
          role="radiogroup"
          aria-label="Plan status"
        />
        <Link to="/exercise-plans/new" className="btn-filled ml-auto">
          <Plus size={16} /> New plan
        </Link>
      </div>

      <div className="rise mt-6" style={{ '--rise-delay': '100ms' } as CSSProperties}>
        {plans.isLoading ? (
          <SkeletonCard rows={5} />
        ) : plans.isError ? (
          <EmptyState title="Plans couldn’t be loaded." icon={<ClipboardList />}>
            Refresh the page to try again.
          </EmptyState>
        ) : (
          <PlansTable rows={rows} filter={filter} />
        )}
      </div>
    </div>
  )
}

function PlansTable({ rows, filter }: { rows: Plan[]; filter: Filter }) {
  const id = 'hep-plans'
  return (
    <section aria-labelledby={id}>
      <GroupHeader id={id} onSky>
        {FILTERS.find((f) => f.key === filter)?.label === 'All' ? 'Plans' : `${FILTERS.find((f) => f.key === filter)?.label} plans`}
        <span className="sr-only">, </span>
        <span className="badge-ring ml-2 align-[1px] tabular-nums">
          {rows.length}
          <span className="sr-only"> {rows.length === 1 ? 'plan' : 'plans'}</span>
        </span>
      </GroupHeader>
      <div className="card-group">
        {rows.length === 0 ? (
          <div className="px-4 py-6">
            <EmptyState
              variant="inline"
              title={filter === 'all' ? 'No plans yet' : 'Nothing here'}
              icon={<Users />}
              family="teal"
              action={
                filter === 'all' ? (
                  <Link to="/exercise-plans/new" className="btn-tinted">
                    <Plus size={16} /> New plan
                  </Link>
                ) : undefined
              }
            >
              {filter === 'all'
                ? 'Build the first one from the library and publish it to a patient.'
                : 'Try another status.'}
            </EmptyState>
          </div>
        ) : (
          <div className="overflow-x-auto" tabIndex={0} role="region" aria-labelledby={id}>
            <table className="w-full min-w-[720px] text-left text-copy">
              <thead>
                <tr className="border-b border-hairline">
                  <Th>Patient</Th>
                  <Th>Plan</Th>
                  <Th className="text-right">Exercises</Th>
                  <Th>Assigned by</Th>
                  <Th>Updated</Th>
                  <Th className="text-right">Status</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {rows.map((p) => {
                  const chip = planStatus(p.status)
                  return (
                    <tr key={p.id}>
                      <Td>
                        <Link
                          to={`/exercise-plans/${p.id}`}
                          className="block font-medium text-ink hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus rounded-[6px]"
                        >
                          {p.patient?.name ?? <span className="text-secondary">No patient yet</span>}
                        </Link>
                      </Td>
                      <Td className="text-body">{p.title}</Td>
                      <Td className="text-right tabular-nums text-body">{p.exercise_count}</Td>
                      <Td className="text-body">{p.assigned_by_name ?? p.assigned_by}</Td>
                      <Td className="text-body">{relativeTime(p.updated_at)}</Td>
                      <Td className="text-right">
                        <span className={`chip ${chip.pill}`}>{chip.label}</span>
                      </Td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <GroupFooter>
        Published plans are frozen as written; editing the library later never changes what a
        patient was given. Open a plan to revise it, or publish a new one to replace it.
      </GroupFooter>
    </section>
  )
}

function Th({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <th scope="col" className={`px-2 py-2.5 text-label font-medium tracking-label text-secondary first:pl-4 last:pr-4 ${className}`}>
      {children}
    </th>
  )
}

function Td({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <td className={`px-2 py-3 align-top first:pl-4 last:pr-4 ${className}`}>{children}</td>
}
