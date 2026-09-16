import { ApiError, REQUEST_TIMEOUT_MS, fetchJson } from './client'
import type { MessageAttachment } from './types'

/** Images and files on the thread, from the console's side.
 *
 * Two upload paths, because one deployment has an object store and the
 * other does not. With S3 the API presigns a POST and the bytes go straight
 * there, never through the Lambda's six-megabyte request ceiling; without
 * it, the API takes the body itself. The server decides which by answering
 * the ticket, so nothing here guesses.
 */

/** GET .../attachments/upload-ticket */
interface UploadTicket {
  storage_key: string
  direct: boolean
  max_bytes: number
  upload: { url: string; fields: Record<string, string>; expires_in: number } | null
}

/** Uploading is slower than reading: a photo over a hotel connection needs
 *  longer than the API's own deadline. */
const UPLOAD_TIMEOUT_MS = 90_000

async function post(url: string, body: BodyInit, headers: Record<string, string> = {}) {
  const controller = new AbortController()
  const deadline = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT_MS)
  try {
    return await fetch(url, { method: 'POST', body, headers, signal: controller.signal })
  } finally {
    clearTimeout(deadline)
  }
}

/**
 * Put one file on a patient's chart and return the stored attachment. The
 * caller sends the id with the message; an attachment nobody claims is
 * swept, so an abandoned composer leaves nothing on the thread.
 */
export async function uploadAttachment(
  patientId: string,
  file: File,
): Promise<MessageAttachment> {
  const base = `/api/patients/${patientId}/attachments`
  const type = file.type || 'application/octet-stream'
  const ticket = await fetchJson<UploadTicket>(
    `${base}/upload-ticket?content_type=${encodeURIComponent(type)}&byte_size=${file.size}`,
  )
  if (file.size > ticket.max_bytes) {
    throw new ApiError(413, `That file is over ${Math.floor(ticket.max_bytes / (1024 * 1024))} MB`)
  }

  if (ticket.direct || !ticket.upload) {
    const res = await post(
      `${base}/direct?filename=${encodeURIComponent(file.name)}`,
      file,
      { 'Content-Type': type },
    )
    if (!res.ok) throw new ApiError(res.status, await reason(res))
    return (await res.json()).attachment as MessageAttachment
  }

  // A presigned POST carries its own authorization in the signed fields, so
  // it must go out with no headers of ours attached — and the file part goes
  // last, which S3 requires.
  const form = new FormData()
  for (const [k, v] of Object.entries(ticket.upload.fields)) form.append(k, v)
  form.append('file', file)
  const put = await post(ticket.upload.url, form)
  if (!put.ok) {
    throw new ApiError(put.status, 'The upload was refused by storage')
  }
  return (
    await fetchJson<{ attachment: MessageAttachment }>(base, {
      method: 'POST',
      body: JSON.stringify({
        storage_key: ticket.storage_key,
        content_type: type,
        byte_size: file.size,
        filename: file.name,
      }),
      timeoutMs: REQUEST_TIMEOUT_MS,
    })
  ).attachment
}

async function reason(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
  } catch {
    /* non-JSON */
  }
  return res.statusText || 'The upload failed'
}

/**
 * A URL the browser can render for one attachment.
 *
 * Where there is an object store the server hands back a short-lived
 * presigned link and the browser fetches it directly. Where there is not,
 * the bytes come through the API and become an object URL — which the
 * caller must revoke, so these are cached by content hash rather than
 * fetched per render.
 */
export async function attachmentSrc(
  patientId: string,
  id: number,
): Promise<{ src: string; objectUrl: boolean }> {
  const base = `/api/patients/${patientId}/attachments/${id}`
  const { attachment } = await fetchJson<{ attachment: MessageAttachment & { url?: string } }>(base)
  if (attachment.url) return { src: attachment.url, objectUrl: false }
  const res = await fetch(`${base}/raw`)
  if (!res.ok) throw new ApiError(res.status, await reason(res))
  return { src: URL.createObjectURL(await res.blob()), objectUrl: true }
}

/** "2.4 MB", "812 KB" — a size is only worth printing when it decides
 *  whether someone taps it on a phone. */
export function fileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}
