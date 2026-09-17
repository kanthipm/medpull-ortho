import { FileText, ImageOff, Paperclip, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { attachmentSrc, fileSize } from '../../api/attachments'
import { useWithdrawAttachment } from '../../api/queries'
import type { MessageAttachment } from '../../api/types'
import Tile from '../../components/Tile'
import { useToast } from '../../components/Toast'

/**
 * Images and files under a thread line.
 *
 * A photograph of an incision is the point of the message, so an image is
 * shown rather than listed. A document is a filename and a size, because
 * that is what decides whether a clinician opens it now.
 *
 * Links are short-lived and minted per request, so the bytes are cached by
 * content hash: a thread that re-renders every twenty seconds must not
 * re-download every photo on it.
 */

// Keyed by content hash, not by attachment id: the same photo sent twice
// is one download, and a thread that refetches every few seconds must not
// re-download every image on it.
const CACHE = new Map<string, string>()

function useImage(patientId: string, a: MessageAttachment) {
  const key = a.sha256 ?? `id:${a.id}`
  const [src, setSrc] = useState<string | null>(() => CACHE.get(key) ?? null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (src || failed) return
    let live = true
    attachmentSrc(patientId, a.id)
      .then(({ src: url }) => {
        if (!live) return
        CACHE.set(key, url)
        setSrc(url)
      })
      .catch(() => live && setFailed(true))
    return () => {
      live = false
    }
  }, [patientId, a.id, key, src, failed])

  return { src, failed }
}

export default function ThreadAttachments({
  patientId,
  items,
  align = 'start',
}: {
  patientId: string
  items: MessageAttachment[]
  align?: 'start' | 'end'
}) {
  if (items.length === 0) return null
  return (
    <div className={`mt-1.5 flex flex-col gap-1.5 ${align === 'end' ? 'items-end' : 'items-start'}`}>
      {items.map((a) =>
        a.withdrawn ? (
          <p key={a.id} className="text-label font-medium text-secondary">
            {a.kind === 'image' ? 'Photo' : 'File'} taken back
          </p>
        ) : (
          <div key={a.id} className="flex items-end gap-1.5">
            {a.kind === 'image' ? (
              <Thumb patientId={patientId} a={a} />
            ) : (
              <FileRow patientId={patientId} a={a} />
            )}
            {a.uploaded_by !== 'patient' && <Withdraw patientId={patientId} a={a} />}
          </div>
        ),
      )}
    </div>
  )
}

/** The clinic's own file, taken back. Never offered for a patient's photo:
 *  removing what somebody sent you is not the clinic's call. */
function Withdraw({ patientId, a }: { patientId: string; a: MessageAttachment }) {
  const toast = useToast()
  const withdraw = useWithdrawAttachment(patientId)
  return (
    <button
      type="button"
      title="Take this file back"
      aria-label="Take this file back"
      disabled={withdraw.isPending}
      className="btn-icon btn-sm hover:bg-risk-high-tint hover:text-risk-high-ink"
      onClick={() => {
        if (!window.confirm('Take this file back? The patient will see that it was removed.')) return
        withdraw.mutate(a.id, {
          onSuccess: () => toast('File taken back', 'info'),
          onError: () => toast('That file could not be removed', 'warning'),
        })
      }}
    >
      <Trash2 size={14} aria-hidden />
    </button>
  )
}

function Thumb({ patientId, a }: { patientId: string; a: MessageAttachment }) {
  const { src, failed } = useImage(patientId, a)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        setOpen(false)
      }
    }
    document.addEventListener('keydown', onKey, true)
    return () => document.removeEventListener('keydown', onKey, true)
  }, [open])

  if (failed) {
    // An Apple photo that reached us untranscoded is the one case with a
    // real answer, and "could not be loaded" sent people looking for a
    // network fault instead.
    const heic = a.content_type === 'image/heic' || a.content_type === 'image/heif'
    return (
      <span className="flex max-w-[260px] items-center gap-2 rounded-control bg-soft px-3 py-2 text-label font-medium text-body">
        <ImageOff size={14} aria-hidden className="shrink-0" />
        {heic
          ? 'This photo is in Apple’s HEIC format, which this browser cannot show'
          : 'That photo could not be loaded'}
      </span>
    )
  }
  return (
    <>
      <button
        type="button"
        onClick={() => src && setOpen(true)}
        title="Open full size"
        aria-label={`Open ${a.filename ?? 'photo'} full size`}
        className="block cursor-zoom-in overflow-hidden rounded-[18px] border border-line bg-soft transition-[opacity,transform] duration-state ease-apple hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus active:scale-press motion-reduce:active:scale-100"
      >
        {src ? (
          <img
            src={src}
            alt={a.filename ?? 'Photo from the thread'}
            className="max-h-44 max-w-[220px] object-cover"
          />
        ) : (
          <span className="block h-24 w-36 animate-pulse bg-soft motion-reduce:animate-none" />
        )}
      </button>
      {/* Portalled to the top layer (R5): the thread lives inside a clipped
          card, and a fixed layer under a transformed ancestor is contained. */}
      {open && src && createPortal(
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Photo"
          className="scrim fixed inset-0 z-50 flex items-center justify-center p-6"
        >
          {/* The backdrop is a real button, so clicking away and tabbing to
              it both close — a div with an onClick does neither. */}
          <button
            type="button"
            aria-label="Close photo"
            className="absolute inset-0 cursor-zoom-out"
            onClick={() => setOpen(false)}
          />
          <img
            src={src}
            alt={a.filename ?? 'Photo from the thread'}
            className="pointer-events-none relative max-h-full max-w-full rounded-surface shadow-overlay"
          />
          <button
            type="button"
            aria-label="Close"
            className="btn-icon absolute right-4 top-4 bg-panel text-ink shadow-float hover:bg-soft"
            onClick={() => setOpen(false)}
          >
            <X size={18} aria-hidden />
          </button>
        </div>,
        document.body,
      )}
    </>
  )
}

function FileRow({ patientId, a }: { patientId: string; a: MessageAttachment }) {
  const [state, setState] = useState<'idle' | 'opening' | 'blocked' | 'failed'>('idle')
  const [href, setHref] = useState<string | null>(null)
  const name = a.filename ?? 'Document'

  // The link is minted by the click that opens it: one handed out on render
  // would have expired by the time anybody used it.
  const open = async () => {
    setState('opening')
    try {
      const { src } = await attachmentSrc(patientId, a.id)
      setHref(src)
      // A window opened after an await can still be blocked. If it was,
      // offer the link to click rather than doing nothing.
      setState(window.open(src, '_blank', 'noopener,noreferrer') ? 'idle' : 'blocked')
    } catch {
      setState('failed')
    }
  }

  const label =
    state === 'opening'
      ? 'Opening…'
      : state === 'failed'
        ? 'Could not be opened'
        : fileSize(a.byte_size)

  const shell =
    'flex max-w-[260px] items-center gap-2.5 rounded-control border border-line bg-panel py-2 pl-2 pr-3 text-left transition-colors duration-state ease-apple hover:bg-soft focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus'
  const inner = (
    <>
      <Tile family="blue" icon={<FileText />} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-copy font-medium text-ink">{name}</span>
        <span className="block text-label tabular-nums text-secondary">
          {state === 'blocked' ? 'Click to open' : label}
        </span>
      </span>
    </>
  )

  if (state === 'blocked' && href) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className={`${shell} cursor-pointer`}>
        {inner}
      </a>
    )
  }
  return (
    <button type="button" onClick={open} className={`${shell} cursor-pointer`}>
      {inner}
    </button>
  )
}

/** The composer's side: files picked but not yet sent. */
export function PendingAttachments({
  items,
  onRemove,
  busy,
}: {
  items: MessageAttachment[]
  onRemove: (id: number) => void
  busy: boolean
}) {
  if (items.length === 0 && !busy) return null
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      {items.map((a) => (
        <span
          key={a.id}
          className="flex min-h-7 items-center gap-1.5 rounded-pill bg-soft py-0.5 pl-2.5 pr-1 text-label font-medium text-ink"
        >
          <Paperclip size={12} aria-hidden className="shrink-0 text-body" />
          <span className="max-w-[140px] truncate">
            {a.filename ?? (a.kind === 'image' ? 'Photo' : 'File')}
          </span>
          <span className="font-normal tabular-nums text-body">{fileSize(a.byte_size)}</span>
          <button
            type="button"
            aria-label={`Remove ${a.filename ?? (a.kind === 'image' ? 'photo' : 'file')}`}
            className="grid h-6 w-6 cursor-pointer place-items-center rounded-pill text-body transition-colors duration-state ease-apple hover:bg-panel hover:text-risk-high-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"
            onClick={() => onRemove(a.id)}
          >
            <X size={12} aria-hidden />
          </button>
        </span>
      ))}
      {busy && (
        <span role="status" className="text-label font-medium text-secondary">
          Uploading…
        </span>
      )}
    </div>
  )
}
