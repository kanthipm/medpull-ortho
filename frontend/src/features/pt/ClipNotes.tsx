import { History, Mic, Square, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState, type RefObject } from 'react'
import { attachmentSrc, uploadAttachment } from '../../api/attachments'
import { dayText, useClipCommentAction, useClipDetail, type PtClipComment, type PtEarlierClip } from '../../api/pt'
import { useToast } from '../../components/Toast'
import { errorText } from './ptWords'

/** Under a lifter's clip, in the day dialog: what makes looking at it quick.
 *
 *  A comment is pinned to the moment the clip is paused on ("0:12 knees
 *  drifting in"); pressing its time takes the clip back there. Typed
 *  comments wait and go out as lines of the reply, so the person gets one
 *  message, in order. A voice note is the therapist saying it instead: it
 *  goes onto their thread at once, as the audio, under her name.
 *
 *  "Earlier clips" lists the same exercise on earlier days of this chart,
 *  and plays the picked one under today's, with what was said then. */
export default function ClipNotes({
  assignmentId,
  patientId,
  patientName,
  by,
  clipRef,
  reviewed,
}: {
  assignmentId: number
  patientId: string
  patientName: string
  /** The care-team id the comments are filed under. */
  by: string
  /** Today's clip, for the moment it is on and for going back to one. */
  clipRef: RefObject<HTMLVideoElement | null>
  /** The reply has gone: comments can be read, and no more are taken. */
  reviewed: boolean
}) {
  const toast = useToast()
  const detail = useClipDetail(assignmentId)
  const act = useClipCommentAction(assignmentId)
  const [text, setText] = useState('')
  const [pin, setPin] = useState(true)
  const [now, setNow] = useState(0)
  const [earlier, setEarlier] = useState<number | null>(null)
  const recorder = useVoiceNote()
  const first = patientName.split(' ')[0]
  const comments = detail.data?.comments ?? []
  const before = detail.data?.earlier ?? []
  const fail = (e: unknown) => toast(errorText(e), 'warning')

  // The moment the clip is on, read while this is on screen. The element
  // mounts after its source resolves, so it is looked for on a slow tick
  // rather than once.
  useEffect(() => {
    const id = window.setInterval(() => {
      const t = clipRef.current?.currentTime
      if (t != null && Number.isFinite(t)) setNow(t)
    }, 400)
    return () => window.clearInterval(id)
  }, [clipRef])

  const atMs = pin ? Math.round(now * 1000) : null
  const seek = (ms: number) => {
    const v = clipRef.current
    if (!v) return
    v.currentTime = ms / 1000
    v.pause()
  }

  const add = () =>
    act.mutate(
      { by, at_ms: atMs, text: text.trim() },
      { onSuccess: () => setText(''), onError: fail },
    )

  const sendVoice = async (file: File) => {
    try {
      const attachment = await uploadAttachment(patientId, file)
      act.mutate(
        { by, at_ms: atMs, text: text.trim() || undefined, voice_attachment_id: attachment.id },
        {
          onSuccess: () => {
            setText('')
            toast(`${first} has your voice note on their thread`, 'success')
          },
          onError: fail,
        },
      )
    } catch (e) {
      fail(e)
    }
  }

  const stop = async () => {
    const file = await recorder.stop()
    if (file) await sendVoice(file)
  }

  const shown = before.find((c) => c.assignment_id === earlier)

  return (
    <div className="mt-3 space-y-3">
      {comments.length > 0 && (
        <ul className="space-y-1.5" aria-label="Comments on this clip">
          {comments.map((c) => (
            <CommentRow
              key={c.id}
              comment={c}
              patientId={patientId}
              onSeek={seek}
              onRemove={reviewed ? undefined : () => act.mutate({ remove: c.id }, { onError: fail })}
            />
          ))}
        </ul>
      )}

      {!reviewed && (
        <div className="rounded-control bg-panel/70 p-3 ring-1 ring-inset ring-hairline">
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex cursor-pointer select-none items-center gap-1.5 text-label text-secondary">
              <input
                type="checkbox"
                className="h-4 w-4 accent-brand"
                checked={pin}
                onChange={(e) => setPin(e.target.checked)}
              />
              At <span className="tabular-nums text-ink">{mmss(now * 1000)}</span>
            </label>
            <input
              className="field !min-h-9 min-w-[12rem] flex-1 !py-1"
              value={text}
              maxLength={400}
              placeholder={pin ? 'What you see at this moment' : 'A remark on the whole clip'}
              aria-label="Comment on the clip"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && text.trim() && !act.isPending) add()
              }}
            />
            <button type="button" className="btn-gray btn-sm" disabled={!text.trim() || act.isPending} onClick={add}>
              Add
            </button>
            {recorder.supported ? (
              recorder.recording ? (
                <button type="button" className="btn-danger btn-sm" onClick={() => void stop()}>
                  <Square aria-hidden size={13} /> Stop and send · {mmss(recorder.elapsedMs)}
                </button>
              ) : (
                <button
                  type="button"
                  className="btn-plain btn-sm"
                  disabled={act.isPending}
                  onClick={() => void recorder.start().catch(() => toast('The microphone is not available here', 'warning'))}
                >
                  <Mic aria-hidden size={14} /> Say it instead
                </button>
              )
            ) : (
              <label className="btn-plain btn-sm cursor-pointer">
                <Mic aria-hidden size={14} /> Attach a voice note
                <input
                  type="file"
                  className="sr-only"
                  accept="audio/mp4,audio/mpeg,audio/wav,.m4a,.mp3,.wav"
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    e.target.value = ''
                    if (file) void sendVoice(file)
                  }}
                />
              </label>
            )}
          </div>
          <p className="meta mt-1.5">
            Typed comments go out as lines of your reply, in order. A voice note goes to {first}’s thread as soon as
            you stop.
          </p>
        </div>
      )}

      {before.length > 0 && (
        <div>
          <h4 className="flex items-center gap-1.5 text-label font-medium tracking-label text-secondary">
            <History aria-hidden size={13} /> Earlier clips of this exercise
          </h4>
          <ul className="mt-1.5 flex flex-wrap gap-1.5">
            {before.map((c) => (
              <li key={c.assignment_id}>
                <button
                  type="button"
                  aria-pressed={earlier === c.assignment_id}
                  onClick={() => setEarlier(earlier === c.assignment_id ? null : c.assignment_id)}
                  className={`inline-flex min-h-8 items-center gap-1.5 rounded-pill px-3 text-label font-medium ring-1 ring-inset transition-colors duration-state ease-apple ${
                    earlier === c.assignment_id
                      ? 'bg-brand-tint text-brand-ink ring-brand-tint-strong'
                      : 'bg-panel/70 text-ink ring-line-strong/60 hover:bg-panel'
                  }`}
                >
                  {dayText(c.day)}
                  {c.load && <span className="font-normal text-secondary">{c.load}</span>}
                </button>
              </li>
            ))}
          </ul>
          {shown && <EarlierClip clip={shown} patientId={patientId} />}
        </div>
      )}
    </div>
  )
}

function mmss(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function CommentRow({
  comment: c,
  patientId,
  onSeek,
  onRemove,
}: {
  comment: PtClipComment
  patientId: string
  onSeek: (ms: number) => void
  onRemove?: () => void
}) {
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 text-copy text-ink">
      {c.at_ms != null ? (
        <button
          type="button"
          onClick={() => onSeek(c.at_ms ?? 0)}
          aria-label={`Go to ${mmss(c.at_ms)} in the clip`}
          className="rounded-pill bg-soft px-2 text-label font-medium tabular-nums text-ink hover:bg-brand-tint focus-visible:outline focus-visible:outline-2 focus-visible:outline-focus"
        >
          {mmss(c.at_ms)}
        </button>
      ) : (
        <span className="rounded-pill bg-soft px-2 text-label text-secondary">Whole clip</span>
      )}
      {c.text && <span className="min-w-0">{c.text}</span>}
      {c.voice && <Media patientId={patientId} file={c.voice} kind="audio" label="Voice note" />}
      <span className="meta">
        {c.by_name ?? c.by}
        {c.voice ? ' · sent to their thread' : ''}
      </span>
      {onRemove && (
        <button type="button" className="btn-icon btn-sm ml-auto" aria-label="Delete this comment" onClick={onRemove}>
          <Trash2 aria-hidden />
        </button>
      )}
    </li>
  )
}

function EarlierClip({ clip: c, patientId }: { clip: PtEarlierClip; patientId: string }) {
  const facts = [
    c.load ?? '',
    c.pain_after != null ? `pain ${c.pain_after}/10 after` : '',
    c.effort != null ? `effort ${c.effort}/10` : '',
  ].filter(Boolean)
  return (
    <figure className="mt-2 max-w-sm">
      {c.video ? (
        <Media patientId={patientId} file={c.video} kind="video" label={`The clip from ${dayText(c.day)}`} />
      ) : (
        <p className="meta">That day’s clip is no longer stored.</p>
      )}
      <figcaption className="meta mt-1">
        {dayText(c.day)}
        {facts.length > 0 && ` · ${facts.join(' · ')}`}
        {c.review_note && <span className="block text-ink">You said: “{c.review_note}”</span>}
      </figcaption>
    </figure>
  )
}

/** One stored file, played: a presigned link where there is an object
 *  store, the bytes through the API where there is not. */
function Media({
  patientId,
  file,
  kind,
  label,
}: {
  patientId: string
  file: { id: number; url?: string | null }
  kind: 'audio' | 'video'
  label: string
}) {
  const [src, setSrc] = useState<string | null>(file.url ?? null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    if (file.url) return
    let revoke: string | null = null
    let cancelled = false
    attachmentSrc(patientId, file.id)
      .then(({ src: s, objectUrl }) => {
        if (cancelled) {
          if (objectUrl) URL.revokeObjectURL(s)
          return
        }
        if (objectUrl) revoke = s
        setSrc(s)
      })
      .catch(() => {
        if (!cancelled) setFailed(true)
      })
    return () => {
      cancelled = true
      if (revoke) URL.revokeObjectURL(revoke)
    }
  }, [patientId, file.id, file.url])
  if (failed) return <span className="meta">Could not be loaded.</span>
  if (!src) return <span className="meta">Loading…</span>
  return kind === 'audio' ? (
    <audio controls preload="metadata" src={src} aria-label={label} className="h-8 max-w-[240px]" />
  ) : (
    <video
      controls
      playsInline
      preload="metadata"
      src={src}
      aria-label={label}
      className="max-h-[360px] w-full rounded-control bg-ink object-contain"
    />
  )
}

/** The container the server keeps for a voice note. A browser that cannot
 *  record it (some record only WebM) is offered a file picker instead. */
const VOICE_TYPE = 'audio/mp4'

function useVoiceNote() {
  const supported =
    typeof window !== 'undefined' &&
    typeof window.MediaRecorder !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    window.MediaRecorder.isTypeSupported(VOICE_TYPE)
  const rec = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const [recording, setRecording] = useState(false)
  const [elapsedMs, setElapsedMs] = useState(0)

  useEffect(() => {
    if (!recording) return
    const began = Date.now()
    const id = window.setInterval(() => setElapsedMs(Date.now() - began), 250)
    return () => window.clearInterval(id)
  }, [recording])

  // Leaving the dialog mid-recording lets go of the microphone.
  useEffect(
    () => () => {
      rec.current?.stream.getTracks().forEach((t) => t.stop())
    },
    [],
  )

  const start = async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const r = new MediaRecorder(stream, { mimeType: VOICE_TYPE })
    chunks.current = []
    r.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.current.push(e.data)
    }
    r.start()
    rec.current = r
    setElapsedMs(0)
    setRecording(true)
  }

  const stop = () =>
    new Promise<File | null>((resolve) => {
      const r = rec.current
      if (!r) return resolve(null)
      r.onstop = () => {
        r.stream.getTracks().forEach((t) => t.stop())
        rec.current = null
        setRecording(false)
        const blob = new Blob(chunks.current, { type: VOICE_TYPE })
        resolve(blob.size > 0 ? new File([blob], 'voice-note.m4a', { type: VOICE_TYPE }) : null)
      }
      r.stop()
    })

  return { supported, recording, elapsedMs, start, stop }
}
