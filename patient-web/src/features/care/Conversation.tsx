/* The pieces of a conversation: the bubble, the composer field with the
   send button inside it, the round buttons beside it, and the files on a
   line (Features/Care/Conversation.swift, Core/Attachments.swift). */

import { useEffect, useRef, useState, type RefObject } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../../core/appModel'
import { attachmentCache, audioClips, AudioClipPlayer, useObservable } from '../../core/attachments'
import {
  attachmentDisplayName, attachmentNoun, Dates, DOT, DOT_LEAD, filesOf, fromClinician, isAudio, isImage, isVideo, isWithdrawn,
  opensTask, sizeLabel, type ChatAttachment, type ChatMessage,
} from '../../core/models'
import { cx, MPButton, Spinner } from '../../ui/components'
import { Sym } from '../../ui/icons'

export function Bubble({ message }: { message: ChatMessage }) {
  const app = useApp()
  const navigate = useNavigate()
  const mine = message.sender === 'patient'
  // A clinician's message is signed with their name; the app's own words
  // are not, because that is the patient's default assumption.
  let who: string
  if (fromClinician(message)) who = message.authorName ?? 'Care team'
  else if (message.sender === 'care_team') who = 'Care team'
  else if (message.sender === 'copilot') who = message.channel === 'sms' ? `MedPull${DOT}text` : 'MedPull'
  else who = message.channel === 'sms' ? `You${DOT}by text` : message.channel === 'voice' ? `You${DOT}by voice` : 'You'
  const taskId = opensTask(message.action)
  return (
    <div className={cx('bubble-line', mine ? 'mine' : 'theirs')}>
      {message.text.trim() && (
        <div className={cx('bubble', mine && 'mine', (message.sender === 'care_team' || fromClinician(message)) && 'team')}>{message.text}</div>
      )}
      <AttachmentStrip attachments={filesOf(message)} mine={mine} />
      {taskId != null && message.action?.label && (
        <div style={{ paddingTop: 2 }}>
          <MPButton kind="filled" onClick={() => { app.setPendingTaskId(taskId); navigate('/today'); void app.refreshTasks() }}>
            <Sym name="arrow.right.circle.fill" size={16} weight="semibold" />
            <span>{message.action.label}</span>
          </MPButton>
        </div>
      )}
      <div className="bubble-meta">
        <span>{who}</span>
        {fromClinician(message) && <span className="approved">Care team approved</span>}
        <span>·</span>
        <span>{Dates.relative(message.createdAt)}</span>
        {message.deliveryStatus === 'failed' && <span className="c-risk-med">{DOT_LEAD}not delivered by text</span>}
      </div>
    </div>
  )
}

/** The 44pt round button beside a composer field. */
export function ComposerRoundButton({ name, active = false, disabled, onClick, label, buttonRef }: {
  name: string; active?: boolean; disabled?: boolean; onClick?: () => void; label: string; buttonRef?: RefObject<HTMLButtonElement | null>
}) {
  return (
    <button ref={buttonRef} type="button" className={cx('round-btn', active && 'active')} disabled={disabled} onClick={onClick} aria-label={label}>
      <Sym name={name} size={17} weight="semibold" />
    </button>
  )
}

/** The composer: a capsule field with the send button inside it. */
export function ComposerField({ placeholder, text, onChange, canSend, busy = false, disabled, onSend, inputRef }: {
  placeholder: string; text: string; onChange: (t: string) => void; canSend: boolean; busy?: boolean
  disabled?: boolean; onSend: () => void; inputRef?: RefObject<HTMLTextAreaElement | null>
}) {
  const localRef = useRef<HTMLTextAreaElement | null>(null)
  const ref = inputRef ?? localRef
  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(120, el.scrollHeight)}px`
  }, [text, ref])
  return (
    <div className="composer-field">
      <textarea ref={ref} rows={1} placeholder={placeholder} value={text} disabled={disabled} aria-label={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey && canSend && !busy) { e.preventDefault(); onSend() } }} />
      <button type="button" className="composer-send" disabled={!canSend || busy} onClick={onSend} aria-label={busy ? 'Sending' : 'Send'}>
        <i>{busy ? <Spinner size={16} /> : <Sym name="arrow.up" size={15} weight="semibold" />}</i>
      </button>
    </div>
  )
}

// MARK: - Files on a line

/** Everything attached to one line, in the bubble's own alignment. */
export function AttachmentStrip({ attachments, mine }: { attachments: ChatAttachment[]; mine: boolean }) {
  if (attachments.length === 0) return null
  return (
    <div className="stack-6" style={{ alignItems: mine ? 'flex-end' : 'flex-start' }}>
      {attachments.map((a) => {
        if (isWithdrawn(a)) {
          const n = attachmentNoun(a)
          return <span key={a.id} className="t-label c-muted">{n.charAt(0).toUpperCase() + n.slice(1)} taken back</span>
        }
        if (isImage(a)) return <AttachmentImageView key={a.id} attachment={a} />
        if (isVideo(a)) return <AttachmentVideoView key={a.id} attachment={a} />
        if (isAudio(a)) return <AttachmentAudioView key={a.id} attachment={a} />
        return <AttachmentFileView key={a.id} attachment={a} />
      })}
    </div>
  )
}

function useLoaded(a: ChatAttachment) {
  const app = useApp()
  const cache = useObservable(attachmentCache)
  useEffect(() => { void cache.load(a, app.api) }, [a, app, cache])
  return { url: cache.url(a), failed: cache.didFail(a) }
}

/** One photo on a thread line: the image once it is here, a placeholder
 *  while it is coming, and a plain line of words if it cannot be shown. */
export function AttachmentImageView({ attachment }: { attachment: ChatAttachment }) {
  const { url, failed } = useLoaded(attachment)
  if (url) return <img className="attachment-image" src={url} alt={attachmentDisplayName(attachment)} />
  if (failed) {
    return (
      <span className="hstack-6 t-label-m c-muted" style={{ padding: '10px 12px' }}>
        <Sym name="photo.badge.exclamationmark" size={16} />This photo could not be loaded
      </span>
    )
  }
  return <span className="attachment-placeholder" style={{ color: 'rgb(var(--muted))' }}><Spinner /></span>
}

/** A clip on a thread line: the player once the file is here. */
export function AttachmentVideoView({ attachment }: { attachment: ChatAttachment }) {
  const { url, failed } = useLoaded(attachment)
  if (url) return <video className="attachment-video" src={url} controls playsInline preload="metadata" aria-label={attachmentDisplayName(attachment)} />
  if (failed) {
    return (
      <span className="hstack-6 t-label-m c-muted" style={{ padding: '10px 12px' }}>
        <Sym name="video.slash" size={16} />This video could not be loaded
      </span>
    )
  }
  return <span className="attachment-placeholder" style={{ width: 240, height: 180, color: 'rgb(var(--muted))' }}><Spinner /></span>
}

/** A voice note on a thread line: play, the clock, a thin progress line. */
export function AttachmentAudioView({ attachment }: { attachment: ChatAttachment }) {
  const { url, failed } = useLoaded(attachment)
  const clips = useObservable(audioClips)
  const [duration, setDuration] = useState<number | null>(null)
  const key = attachment.sha256 ?? `id:${attachment.id}`
  const playing = clips.isPlaying(key)
  useEffect(() => {
    if (!url || duration != null) return
    void AudioClipPlayer.duration(url).then(setDuration)
  }, [url, duration])
  let clock = sizeLabel(attachment.byteSize)
  if (duration != null) {
    const shown = playing ? duration * clips.progress : duration
    const s = Math.round(shown)
    clock = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  }
  return (
    <div className="attachment-audio">
      <button type="button" className="play-btn press-88" disabled={!url} onClick={() => { if (url) clips.toggle(key, url) }}
        aria-label={playing ? 'Pause' : `Play ${attachmentDisplayName(attachment)}`}>
        <Sym name={playing ? 'pause.fill' : 'play.fill'} size={15} weight="semibold" />
      </button>
      <div className="stack-6 grow">
        <div className="hstack-6">
          <span className="c-brand-ink"><Sym name="waveform" size={13} weight="medium" /></span>
          <span className="t-copy-m c-ink ellipsis">{attachment.filename == null ? 'Voice note' : attachmentDisplayName(attachment)}</span>
          <span className="spacer" />
          {failed ? <span className="t-label-m c-risk-med">Could not load</span>
            : !url ? <Spinner size={12} className="c-muted" />
              : <span className="t-label c-muted figures">{clock}</span>}
        </div>
        <div className="progress-line"><i style={{ width: `${(playing ? clips.progress : 0) * 100}%` }} /></div>
      </div>
    </div>
  )
}

/** A document on a thread line: a name and a size. */
export function AttachmentFileView({ attachment }: { attachment: ChatAttachment }) {
  const app = useApp()
  const cache = useObservable(attachmentCache)
  const open = async () => {
    if (!cache.url(attachment)) await cache.load(attachment, app.api)
    const u = cache.url(attachment)
    if (u) window.open(u, '_blank', 'noopener')
  }
  return (
    <button type="button" className="attachment-file" onClick={() => void open()} aria-label={`Open ${attachmentDisplayName(attachment)}`}>
      <span className="c-brand-ink"><Sym name={attachment.contentType === 'application/pdf' ? 'doc.richtext' : 'doc'} size={18} weight="regular" /></span>
      <span className="stack" style={{ gap: 1, textAlign: 'left' }}>
        <span className="t-copy-m c-ink ellipsis">{attachmentDisplayName(attachment)}</span>
        <span className="t-label-m c-muted">{sizeLabel(attachment.byteSize)}</span>
      </span>
    </button>
  )
}
