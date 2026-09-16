import { useCallback, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import { uploadAttachment } from '../../api/attachments'
import type { MessageAttachment } from '../../api/types'
import { useToast } from '../../components/Toast'

/** What the backend accepts (app/storage/blobs.ALLOWED_TYPES). Kept in the
 *  picker too so a clinician is told before the upload rather than after. */
export const ACCEPT =
  'image/jpeg,image/png,image/webp,image/heic,image/heif,application/pdf,.heic,.heif'

/** More than a handful on one message is a folder, not a message. Matches
 *  the cap the message endpoint enforces. */
export const MAX_FILES = 8

/**
 * Pick files, upload them now, send their ids with the message later.
 *
 * Uploading on pick rather than on send is what makes a slow photo feel
 * like a slow photo instead of a slow Send button, and it means the
 * message endpoint only ever takes ids. An upload nobody claims is swept
 * server-side, so abandoning the composer leaves nothing behind.
 */
export function useAttachmentPicker(patientId: string) {
  const toast = useToast()
  const input = useRef<HTMLInputElement | null>(null)
  const [pending, setPending] = useState<MessageAttachment[]>([])
  const [busy, setBusy] = useState(false)

  const take = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) return
      const room = MAX_FILES - pending.length
      if (room <= 0) {
        toast(`Up to ${MAX_FILES} files on one message`, 'warning')
        return
      }
      const chosen = Array.from(files).slice(0, room)
      if (chosen.length < files.length) {
        toast(`Only the first ${chosen.length} were attached — ${MAX_FILES} per message`, 'warning')
      }
      setBusy(true)
      for (const file of chosen) {
        try {
          const a = await uploadAttachment(patientId, file)
          setPending((p) => [...p, a])
        } catch (e) {
          toast(
            e instanceof ApiError
              ? `${file.name}: ${e.message}`
              : `${file.name} could not be attached`,
            'warning',
          )
        }
      }
      setBusy(false)
    },
    [patientId, pending.length, toast],
  )

  const onChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      void take(e.target.files)
      // Same file twice in a row must fire change twice.
      e.target.value = ''
    },
    [take],
  )

  return {
    /** Props for a hidden <input type="file">. */
    inputProps: {
      ref: input,
      type: 'file' as const,
      accept: ACCEPT,
      multiple: true,
      className: 'hidden',
      onChange,
    },
    open: () => input.current?.click(),
    pending,
    busy,
    ids: pending.map((a) => a.id),
    remove: (id: number) => setPending((p) => p.filter((a) => a.id !== id)),
    reset: () => setPending([]),
    /** Files dropped onto the composer. */
    drop: (e: React.DragEvent) => {
      e.preventDefault()
      void take(e.dataTransfer.files)
    },
  }
}
