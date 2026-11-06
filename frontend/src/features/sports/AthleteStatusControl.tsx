import { Pencil } from 'lucide-react'
import { useId, useRef, useState } from 'react'
import { STATUS_OPTIONS, useSetAthleteStatus, type Availability } from '../../api/sports'
import { Popover } from '../../components/Menu'
import SegmentedControl from '../../components/SegmentedControl'
import { useToast } from '../../components/Toast'

/** The staff's availability control: a capsule that opens a small top-layer
 *  dialog with the three states on a segmented control and the note the
 *  board shows under the name. Saves with `PATCH …/status {status, note}`
 *  and refetches the athlete and the team board. The draft is seeded when
 *  the dialog opens, from the record as it stands then. */
export default function AthleteStatusControl({
  teamId,
  athleteId,
  status,
  note,
  className = '',
}: {
  teamId: string
  athleteId: string
  status: Availability
  note: string | null
  className?: string
}) {
  const [open, setOpen] = useState(false)
  const [draftStatus, setDraftStatus] = useState<Availability>(status)
  const [draftNote, setDraftNote] = useState(note ?? '')
  const anchorRef = useRef<HTMLButtonElement>(null)
  const id = useId()
  const mutation = useSetAthleteStatus(teamId, athleteId)
  const toast = useToast()

  const show = () => {
    setDraftStatus(status)
    setDraftNote(note ?? '')
    setOpen(true)
  }
  const close = () => setOpen(false)
  const save = () => {
    mutation.mutate(
      { status: draftStatus, note: draftNote.trim() || null },
      {
        onSuccess: (r) => {
          toast(`Availability set to ${r.status_label}`, 'success')
          setOpen(false)
        },
        onError: (err) => toast(`Could not update availability — ${err.message}`, 'warning'),
      },
    )
  }

  return (
    <div className={className}>
      <button
        ref={anchorRef}
        type="button"
        className="btn-tinted"
        onClick={show}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
      >
        <Pencil aria-hidden /> Set availability
      </button>
      <Popover
        open={open}
        onClose={close}
        anchorRef={anchorRef}
        id={id}
        aria-label="Set availability"
        placement="bottom-end"
        className="w-[min(380px,calc(100vw-16px))] p-4"
      >
        <p className="text-copy font-medium text-ink">Availability</p>
        <SegmentedControl
          className="mt-2"
          fullWidth
          role="radiogroup"
          aria-label="Availability"
          options={STATUS_OPTIONS}
          value={draftStatus}
          onChange={setDraftStatus}
        />
        <label htmlFor={`${id}-note`} className="mt-3 block text-copy text-ink">
          Note for the board
        </label>
        <textarea
          id={`${id}-note`}
          className="field mt-1 resize-none"
          rows={3}
          maxLength={300}
          value={draftNote}
          onChange={(e) => setDraftNote(e.target.value)}
          placeholder="Right ankle, day 9: bike and balance, no practice until hops are symmetric."
        />
        <p className="meta mt-1">Shown on the team board and in the athlete’s app.</p>
        <div className="mt-3 flex justify-end gap-2">
          <button type="button" className="btn-plain-muted btn-sm" onClick={close}>
            Cancel
          </button>
          <button type="button" className="btn-filled btn-sm" onClick={save} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Save'}
          </button>
        </div>
      </Popover>
    </div>
  )
}
