import { Archive, CalendarDays, ClipboardList, Dumbbell, Layers, Pencil, Plus, Repeat } from 'lucide-react'
import { useState, type CSSProperties } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/client'
import type { Template } from '../../api/hep'
import { useArchiveTemplate, useTemplates } from '../../api/hep'
import EmptyState from '../../components/EmptyState'
import ListRow, { ListGroup } from '../../components/ListRow'
import { Menu } from '../../components/Menu'
import Modal from '../../components/Modal'
import { SkeletonCard } from '../../components/Skeleton'
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'
import { relativeTime } from '../../lib/format'
import { GroupFooter, GroupHeader, SettingsHero } from '../settings/Switch'
import ApplyProgramDialog from './ApplyProgramDialog'
import ExercisesNav from './ExercisesNav'
import { weekdaysLabel } from './scheduleCopy'

/** `/exercise-programs` — the clinic's programs: a pattern of exercises by
 *  weekday, for a number of weeks, that "Apply to…" puts on a lifter's
 *  calendar from a start date. Open one to edit it; archiving takes it off
 *  the list and leaves every calendar built from it alone. */
export default function ProgramsPage() {
  const navigate = useNavigate()
  const toast = useToast()
  const templates = useTemplates()
  const archive = useArchiveTemplate()
  const [applying, setApplying] = useState<Template | null>(null)
  const [archiving, setArchiving] = useState<Template | null>(null)
  const rows = [...(templates.data?.templates ?? [])].sort((a, b) => a.name.localeCompare(b.name))

  const doArchive = () => {
    if (!archiving) return
    archive.mutate(archiving.id, {
      onSuccess: () => {
        toast(`${archiving.name} archived`, 'info')
        setArchiving(null)
      },
      onError: (e) => {
        toast(e instanceof ApiError && e.message ? e.message : 'Could not archive it', 'warning')
        setArchiving(null)
      },
    })
  }

  return (
    <div className="pb-10">
      <SettingsHero
        nav={<ExercisesNav />}
        icon={<Layers />}
        title="Programs"
        decor={[<Layers key="l" />, <Repeat key="r" />, <Dumbbell key="d" />]}
      >
        A program is a pattern of exercises by weekday — the dose, the load, what you ask for with
        each — that goes onto a lifter’s calendar from a start date, for as many weeks as it runs.
      </SettingsHero>

      <div
        className="rise mt-8 flex flex-wrap items-center gap-x-3 gap-y-3"
        style={{ '--rise-delay': '60ms' } as CSSProperties}
      >
        {templates.data && (
          <span className="meta tabular-nums">
            {rows.length} program{rows.length === 1 ? '' : 's'}
          </span>
        )}
        <Link to="/exercise-programs/new" className="btn-filled ml-auto">
          <Plus size={16} aria-hidden /> New program
        </Link>
      </div>

      <div className="rise mt-6" style={{ '--rise-delay': '100ms' } as CSSProperties}>
        {templates.isLoading ? (
          <SkeletonCard rows={3} />
        ) : templates.isError ? (
          <EmptyState
            title="Programs couldn’t be loaded."
            icon={<Layers />}
            action={
              <button type="button" className="btn-tinted" onClick={() => void templates.refetch()}>
                Try again
              </button>
            }
          >
            {templates.error instanceof Error && templates.error.message
              ? templates.error.message
              : 'Check that the API is running, then try again.'}
          </EmptyState>
        ) : rows.length === 0 ? (
          <EmptyState
            title="No programs yet"
            icon={<Layers />}
            family="teal"
            action={
              <Link to="/exercise-programs/new" className="btn-tinted">
                <Plus size={16} aria-hidden /> New program
              </Link>
            }
          >
            Build one from the library — a patellar-tendinopathy phase, a lumbar return to lifting —
            and put it on any lifter’s calendar in one step.
          </EmptyState>
        ) : (
          <section aria-labelledby="hep-programs">
            <GroupHeader id="hep-programs" onSky>
              Programs
              <span className="sr-only">, </span>
              <span className="badge-ring ml-2 align-[1px] tabular-nums">
                {rows.length}
                <span className="sr-only"> {rows.length === 1 ? 'program' : 'programs'}</span>
              </span>
            </GroupHeader>
            <ListGroup inset="tile" aria-labelledby="hep-programs">
              {rows.map((t) => (
                <ListRow
                  key={t.id}
                  leading={<Tile family="teal" icon={<ClipboardList />} />}
                  title={t.name}
                  to={`/exercise-programs/${t.id}`}
                  subtitle={t.description || summary(t)}
                  subtitleLines={2}
                  meta={`${t.weeks} week${t.weeks === 1 ? '' : 's'} · ${t.items.length} exercise${
                    t.items.length === 1 ? '' : 's'
                  } · updated ${relativeTime(t.updated_at)}`}
                  trailing={
                    <>
                      <button type="button" className="btn-tinted btn-sm" onClick={() => setApplying(t)}>
                        <CalendarDays size={14} aria-hidden /> Apply to…
                      </button>
                      <Menu
                        label={`More for ${t.name}`}
                        items={[
                          {
                            key: 'edit',
                            label: 'Edit',
                            icon: <Pencil />,
                            onSelect: () => navigate(`/exercise-programs/${t.id}`),
                          },
                          { key: 'sep', separator: true },
                          {
                            key: 'archive',
                            label: 'Archive',
                            description: 'Leaves every calendar built from it as it is',
                            icon: <Archive />,
                            danger: true,
                            onSelect: () => setArchiving(t),
                          },
                        ]}
                      />
                    </>
                  }
                  wrapTitle
                />
              ))}
            </ListGroup>
            <GroupFooter>
              Applying a program puts each exercise on its weekdays from the start date; days that
              already have the exercise are left alone. Editing a program later changes nothing already
              on a calendar.
            </GroupFooter>
          </section>
        )}
      </div>

      {applying && <ApplyProgramDialog key={applying.id} template={applying} onClose={() => setApplying(null)} />}

      {archiving && (
        <Modal
          title={`Archive ${archiving.name}?`}
          size="md"
          onClose={() => setArchiving(null)}
          description="It leaves this list. Every calendar built from it stays as it is."
          footer={
            <>
              <button type="button" className="btn-gray" onClick={() => setArchiving(null)}>
                Keep
              </button>
              <button type="button" className="btn-danger" disabled={archive.isPending} onClick={doArchive}>
                <Archive size={16} aria-hidden /> {archive.isPending ? 'Archiving…' : 'Archive'}
              </button>
            </>
          }
        >
          <p className="text-copy text-body">{summary(archiving)}</p>
        </Modal>
      )}
    </div>
  )
}

/** "Step-Ups (Mon · Wed · Fri), Heel Slides (Every day)" */
function summary(t: Template): string {
  if (t.items.length === 0) return 'No exercises yet'
  return t.items.map((i) => `${i.title} (${weekdaysLabel(i.weekdays)})`).join(', ')
}
