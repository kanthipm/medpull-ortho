import { Trash2, Video } from 'lucide-react'
import { useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import type { ClipUploadProgress, Exercise } from '../../api/hep'
import { CLIP_ACCEPT, clipContentType, useDeleteClinicClip, useUploadClinicClip } from '../../api/hep'
import { useToast } from '../../components/Toast'

/** The therapist's own demonstration of an exercise.
 *
 *  A file input that opens the camera on a phone (`capture="user"`) and the
 *  picker on a laptop, then ticket → S3 POST (or the API's direct path when
 *  the ticket says so) → confirm, with a progress bar and a plain error.
 *  Once up, the clip plays wherever the exercise is assigned; with a clip
 *  of the clinic's own in place the button says Replace and Remove takes
 *  it down (the library's clip, if any, shows again). */
export default function ClinicClipUpload({
  exerciseId,
  exerciseTitle,
  actor,
  own = null,
  onUploaded,
  className = '',
}: {
  exerciseId: number
  exerciseTitle: string
  /** The care-team id the clip is filed under (uploaded and reviewed by). */
  actor: string
  /** The clinic's current clip for this exercise, when it has one. */
  own?: { id: number } | null
  onUploaded?: (exercise: Exercise) => void
  className?: string
}) {
  const toast = useToast()
  const upload = useUploadClinicClip()
  const remove = useDeleteClinicClip()
  const input = useRef<HTMLInputElement>(null)
  const [progress, setProgress] = useState<ClipUploadProgress | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)

  const take = (file: File | undefined) => {
    if (!file) return
    if (!CLIP_ACCEPT.split(',').includes(clipContentType(file))) {
      setError('Choose an MP4 or QuickTime (.mov) clip.')
      return
    }
    setError(null)
    setProgress({ phase: 'ticket', fraction: 0 })
    upload.mutate(
      { exerciseId, file, actor, onProgress: setProgress },
      {
        onSuccess: (e) => {
          setProgress(null)
          toast(`Your demonstration of ${exerciseTitle} is up`, 'success')
          onUploaded?.(e)
        },
        onError: (e) => {
          setProgress(null)
          setError(e instanceof ApiError && e.message ? e.message : 'The upload failed')
        },
      },
    )
  }

  const takeDown = () => {
    if (!own) return
    remove.mutate(
      { exerciseId, mediaId: own.id },
      {
        onSuccess: () => {
          setConfirming(false)
          toast('Your demonstration was removed', 'info')
        },
        onError: (e) => {
          setConfirming(false)
          setError(e instanceof ApiError && e.message ? e.message : 'The clip could not be removed')
        },
      },
    )
  }

  const pct = progress ? Math.round((progress.phase === 'upload' ? progress.fraction : progress.phase === 'confirm' ? 1 : 0) * 100) : 0
  const phaseText =
    progress?.phase === 'ticket'
      ? 'Asking for a slot…'
      : progress?.phase === 'upload'
        ? 'Uploading…'
        : 'Checking the clip…'

  return (
    <div className={className}>
      <input
        ref={input}
        type="file"
        accept={CLIP_ACCEPT}
        capture="user"
        tabIndex={-1}
        aria-hidden
        className="sr-only"
        onChange={(e) => {
          take(e.target.files?.[0])
          // the same file twice in a row must fire change twice
          e.target.value = ''
        }}
      />
      {progress ? (
        <div role="status" className="min-w-[220px] rounded-control bg-soft px-3 py-2.5">
          <div className="flex items-center justify-between gap-3 text-copy text-ink">
            <span>{phaseText}</span>
            <span className="meta tabular-nums">{pct}%</span>
          </div>
          <div
            role="progressbar"
            aria-label="Upload progress"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={pct}
            className="mt-2 h-1.5 overflow-hidden rounded-pill bg-panel"
          >
            <div
              className="h-full rounded-pill bg-brand transition-[width] duration-state ease-apple"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" className="btn-tinted btn-sm" onClick={() => input.current?.click()}>
            <Video size={14} aria-hidden />
            {own ? 'Replace your demonstration' : 'Upload your demonstration'}
          </button>
          {own &&
            (confirming ? (
              <span className="flex items-center gap-1.5 text-copy text-body">
                Take it down?
                <button type="button" className="btn-danger btn-sm" disabled={remove.isPending} onClick={takeDown}>
                  {remove.isPending ? 'Removing…' : 'Remove'}
                </button>
                <button type="button" className="btn-plain-muted btn-sm" onClick={() => setConfirming(false)}>
                  Keep
                </button>
              </span>
            ) : (
              <button type="button" className="btn-plain-muted btn-sm" onClick={() => setConfirming(true)}>
                <Trash2 size={14} aria-hidden /> Remove
              </button>
            ))}
        </div>
      )}
      {error && (
        <p role="alert" className="mt-2 text-copy text-risk-high-ink">
          {error}
        </p>
      )}
    </div>
  )
}
