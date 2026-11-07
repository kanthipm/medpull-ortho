import { Archive, ArchiveRestore, Film, Pencil } from 'lucide-react'
import { useState } from 'react'
import type { Exercise, Vocab } from '../../api/hep'
import { useUpdateExercise } from '../../api/hep'
import Modal from '../../components/Modal'
import { useToast } from '../../components/Toast'
import ExerciseForm from './ExerciseForm'
import { statusChip, toBody, type ExerciseDraft } from './hepCopy'

/** One exercise as the patient will read it: the demonstration (or its
 *  placeholder until a clip is reviewed), the steps, equipment and
 *  precautions. A custom exercise can be edited or archived from here. */
export default function ExercisePreviewModal({
  exercise,
  regions,
  categories,
  onClose,
}: {
  exercise: Exercise
  regions: Vocab[]
  categories: Vocab[]
  onClose: () => void
}) {
  const toast = useToast()
  const update = useUpdateExercise()
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<ExerciseDraft>(() => ({
    title: exercise.title,
    body_region: exercise.body_region,
    category: exercise.category,
    steps: exercise.steps.join('\n'),
    synonyms: exercise.synonyms.join(', '),
    equipment: exercise.equipment,
    precautions: exercise.precautions,
  }))
  const custom = exercise.origin === 'custom'
  const archived = exercise.status === 'archived'
  const chip = statusChip(exercise.status)

  const save = () =>
    update.mutate(
      { id: exercise.id, ...toBody(draft) },
      {
        onSuccess: () => {
          toast('Exercise updated', 'success')
          setEditing(false)
        },
        onError: (e) => toast(`Could not save — ${e.message}`, 'warning'),
      },
    )

  const toggleArchive = () =>
    update.mutate(
      { id: exercise.id, status: archived ? 'draft' : 'archived' },
      {
        onSuccess: () => {
          toast(archived ? 'Restored to your exercises' : 'Archived', 'success')
          onClose()
        },
        onError: (e) => toast(`Could not update — ${e.message}`, 'warning'),
      },
    )

  const footer = editing ? (
    <>
      <button type="button" className="btn-gray" onClick={() => setEditing(false)}>
        Cancel
      </button>
      <button
        type="button"
        className="btn-filled"
        disabled={!draft.title.trim() || update.isPending}
        onClick={save}
      >
        {update.isPending ? 'Saving…' : 'Save changes'}
      </button>
    </>
  ) : custom ? (
    <>
      <button type="button" className="btn-gray" onClick={toggleArchive} disabled={update.isPending}>
        {archived ? <ArchiveRestore size={16} /> : <Archive size={16} />}
        {archived ? 'Restore' : 'Archive'}
      </button>
      <button type="button" className="btn-tinted" onClick={() => setEditing(true)}>
        <Pencil size={16} /> Edit
      </button>
      <button type="button" className="btn-filled" onClick={onClose}>
        Done
      </button>
    </>
  ) : (
    <button type="button" className="btn-filled" onClick={onClose}>
      Done
    </button>
  )

  return (
    <Modal
      title={editing ? `Edit ${exercise.title}` : exercise.title}
      size="lg"
      onClose={onClose}
      footer={footer}
      eyebrow={
        <p className="mb-1 flex flex-wrap items-center gap-2 text-label text-secondary">
          <span>{exercise.body_region_label}</span>
          <span aria-hidden>·</span>
          <span>{exercise.category_label}</span>
          <span aria-hidden>·</span>
          <span>{custom ? 'Your exercise' : 'Standard'}</span>
          <span className={`chip ${chip.pill}`}>{chip.label}</span>
        </p>
      }
    >
      {editing ? (
        <ExerciseForm value={draft} onChange={setDraft} regions={regions} categories={categories} idPrefix={`edit-${exercise.id}`} />
      ) : (
        <div className="space-y-5">
          <DemoPlaceholder exercise={exercise} />
          <section aria-labelledby={`steps-${exercise.id}`}>
            <h3 id={`steps-${exercise.id}`} className="mb-2 text-copy font-medium text-body">
              Steps
            </h3>
            {exercise.steps.length > 0 ? (
              <ol className="list-decimal space-y-1.5 pl-5 text-copy-lg text-ink">
                {exercise.steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            ) : (
              <p className="text-copy text-secondary">No steps written yet.</p>
            )}
          </section>
          <dl className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-surface bg-soft p-4">
              <dt className="text-label font-medium tracking-label text-secondary">Equipment</dt>
              <dd className="mt-1 text-copy text-ink">{exercise.equipment || 'None'}</dd>
            </div>
            <div className="rounded-surface bg-soft p-4">
              <dt className="text-label font-medium tracking-label text-secondary">Precautions</dt>
              <dd className="mt-1 text-copy text-ink">{exercise.precautions || 'None noted'}</dd>
            </div>
          </dl>
          {exercise.synonyms.length > 0 && (
            <p className="meta">Also called {exercise.synonyms.join(', ')}</p>
          )}
        </div>
      )}
    </Modal>
  )
}

/** The demonstration slot. A reviewed clip plays muted on loop; until one is
 *  approved, a labelled still so the layout the patient will see is already
 *  the one the clinician previews. */
function DemoPlaceholder({ exercise }: { exercise: Exercise }) {
  const media = exercise.media
  if (media?.playable && media.url) {
    return (
      <video
        className="aspect-video w-full rounded-surface bg-soft object-cover"
        src={media.url}
        poster={media.poster_url ?? undefined}
        muted
        loop
        playsInline
        autoPlay
        controls
        preload="metadata"
        aria-label={`${exercise.title} demonstration`}
      />
    )
  }
  const label = media
    ? media.approval_status === 'rejected'
      ? 'Demonstration needs a new clip'
      : 'Demonstration awaiting review'
    : 'Demonstration coming soon'
  return (
    <div
      role="img"
      aria-label={`${label}. The steps below describe the movement.`}
      className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-surface bg-soft text-secondary"
    >
      <Film aria-hidden size={28} />
      <span className="text-copy font-medium">{label}</span>
      <span className="text-label">Patients see the written steps until a clip is approved</span>
    </div>
  )
}
