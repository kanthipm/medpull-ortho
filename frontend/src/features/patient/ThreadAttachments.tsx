import { FileText, ImageOff, Paperclip, Trash2, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { attachmentSrc, fileSize } from '../../api/attachments'
import { useWithdrawAttachment } from '../../api/queries'
import type { MessageAttachment } from '../../api/types'
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
          <p key={a.id} className="text-[11.5px] font-medium italic text-faint">
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
      className="mb-1 cursor-pointer rounded-btn p-1 text-faint transition-colors duration-150 hover:bg-risk-high-bg hover:text-risk-high"
      onClick={() => {
        if (!window.confirm('Take this file back? The patient will see that it was removed.')) return
        withdraw.mutate(a.id, {
          onSuccess: () => toast('File taken back', 'info'),
          onError: () => toast('That file could not be removed', 'warning'),
        })
      }}
    >
      <Trash2 size={12} />
    </button>
  )
}

function Thumb({ patientId, a }: { patientId: string; a: MessageAttachment }) {
  const { src, failed } = useImage(patientId, a)
  const [open, setOpen] = useState(false)

  if (failed) {
    return (
      <span className="flex items-center gap-1.5 rounded-row border border-line bg-soft px-2 py-1.5 text-[11.5px] font-medium text-muted">
        <ImageOff size={12} /> That photo could not be loaded
      </span>
    )
  }
  return (
    <>
      <button
        type="button"
        onClick={() => src && setOpen(true)}
        title="Open full size"
        className="block cursor-pointer overflow-hidden rounded-row border border-line bg-soft transition-opacity duration-150 hover:opacity-90"
      >
        {src ? (
          <img
            src={src}
            alt={a.filename ?? 'Photo from the thread'}
            className="max-h-44 max-w-[220px] object-cover"
          />
        ) : (
          <span className="block h-24 w-36 animate-pulse bg-soft" />
        )}
      </button>
      {open && src && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Photo"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
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
            className="pointer-events-none relative max-h-full max-w-full rounded-card"
          />
          <button
            type="button"
            aria-label="Close"
            className="absolute right-4 top-4 cursor-pointer rounded-btn bg-white/90 p-1.5 text-ink"
            onClick={() => setOpen(false)}
          >
            <X size={16} />
          </button>
        </div>
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
    'flex max-w-[260px] items-center gap-2 rounded-row border border-line bg-panel px-2.5 py-1.5 text-left transition-colors duration-150 hover:border-brand/35 hover:bg-brand-tint'
  const inner = (
    <>
      <FileText size={14} className="shrink-0 text-brand" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-semibold text-ink">{name}</span>
        <span className="block text-[11px] font-medium text-muted">
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
          className="flex items-center gap-1.5 rounded-btn border border-line bg-soft px-2 py-1 text-[11.5px] font-medium text-body"
        >
          <Paperclip size={11} className="text-brand" />
          <span className="max-w-[140px] truncate">
            {a.filename ?? (a.kind === 'image' ? 'Photo' : 'File')}
          </span>
          <span className="text-faint">{fileSize(a.byte_size)}</span>
          <button
            type="button"
            aria-label="Remove"
            className="cursor-pointer text-faint transition-colors hover:text-risk-high"
            onClick={() => onRemove(a.id)}
          >
            <X size={11} />
          </button>
        </span>
      ))}
      {busy && <span className="text-[11.5px] font-medium text-muted">Uploading…</span>}
    </div>
  )
}
