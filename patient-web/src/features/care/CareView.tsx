/* One thread with everyone on the other end. What the patient types goes
   to their care team. The mic, and the quick-log chips, go to MedPull's
   assistant, which logs pain or a task, answers at once, and passes
   anything serious to the team. Both land in the same thread
   (Features/Care/CareView.swift). */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { messageFor, useApp } from '../../core/appModel'
import { AttachmentPrep, VoiceNoteRecorder, useObservable, type Ready } from '../../core/attachments'
import { isTouchDevice } from '../../core/config'
import { attachmentDisplayName, attachmentSymbol, sizeLabel, type ChatAttachment } from '../../core/models'
import { SpeechController, useSpeech } from '../../core/speech'
import { Card, ErrorBanner, Initials, Menu, MPButton, NavBar, Screen, Spinner } from '../../ui/components'
import { Sym } from '../../ui/icons'
import { teamInitials } from '../today/TodayView'
import { Bubble, ComposerField, ComposerRoundButton } from './Conversation'

/** Quick logs. They FILL the field, never send it: a tapped "my pain is a
 *  4" that went straight to the chart would be a score nobody gave. */
const quickLogs = ['My pain is a ', 'I did my exercises', 'I walked today', 'A note for my nurse: ']

export function CareView() {
  const app = useApp()
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const speech = useSpeech(useMemo(() => new SpeechController(), []))
  const [thinking, setThinking] = useState(false)
  /** True while the draft began from a quick-log chip: it goes to the
   *  assistant, not the care team, and the composer says so. */
  const [draftToAssistant, setDraftToAssistant] = useState(false)
  const [pending, setPending] = useState<ChatAttachment[]>([])
  const [uploading, setUploading] = useState(false)
  const [preparing, setPreparing] = useState<string | null>(null)
  const recorder = useObservable(useMemo(() => new VoiceNoteRecorder(), []))
  const finishingNote = useRef(false)
  const wasRecording = useRef(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const plusRef = useRef<HTMLButtonElement | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const cameraInput = useRef<HTMLInputElement | null>(null)
  const photoInput = useRef<HTMLInputElement | null>(null)
  const fileInput = useRef<HTMLInputElement | null>(null)

  const team = app.me?.patient.careTeam ?? []

  useEffect(() => {
    void app.refreshMessages().then(() => app.markMessagesRead())
    const t = setInterval(() => { void app.refreshMessages(false) }, 20_000)
    return () => clearInterval(t)
  }, [app])

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [])
  useEffect(() => { scrollToBottom() }, [app.messages.length, thinking, speech.transcript, scrollToBottom])

  const finishVoiceNote = useCallback(async () => {
    finishingNote.current = true
    try {
      const note = await recorder.stop()
      if (!note) return
      setUploading(true)
      const ready = AttachmentPrep.voiceNote(note.blob, note.contentType)
      if (!ready) { setError('That recording could not be read.'); return }
      await upload(ready)
    } finally {
      finishingNote.current = false
      setUploading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recorder])

  // The time limit ran out: treat it as the person tapping stop.
  useEffect(() => {
    if (wasRecording.current && !recorder.isRecording && !finishingNote.current) void finishVoiceNote()
    wasRecording.current = recorder.isRecording
  }, [recorder.isRecording, finishVoiceNote])

  const canSend = !uploading && !speech.isListening && !thinking && !recorder.isRecording
    && (draft.trim() !== '' || pending.length > 0)

  /** To the assistant. The exchange lands on the thread server-side, so
   *  the refresh inside `ask` is what draws it. */
  const ask = async (text: string, channel: string, speak: boolean) => {
    setThinking(true)
    setError(null)
    try {
      const r = await app.ask(text, channel)
      if (speak) speech.speak(r.reply)
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setThinking(false)
    }
  }

  /** Typed: to the care team. From a chip: to the assistant. */
  const send = async () => {
    const text = draft.trim()
    const ids = pending.map((a) => a.id)
    if (!text && ids.length === 0) return
    if (draftToAssistant) {
      setDraft('')
      setDraftToAssistant(false)
      void ask(text, 'app', false)
      return
    }
    setSending(true)
    setError(null)
    try {
      await app.send(text, ids)
      setDraft('')
      setPending([])
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setSending(false)
    }
  }

  const toggleMic = async () => {
    if (speech.isListening) {
      const heard = speech.stopListening()
      if (heard) void ask(heard, 'voice', true)
    } else {
      inputRef.current?.blur()
      if (!speech.authorized && !(await speech.requestAuthorization())) return
      speech.startListening()
    }
  }

  /** Store one prepared file on the chart and add it to the composer. */
  const upload = async (ready: Ready) => {
    try {
      const stored = await app.api.upload(ready.data, ready.contentType, ready.filename)
      setPending((p) => [...p, stored])
    } catch (e) {
      setError(messageFor(e))
    }
  }

  const attachFiles = async (files: File[], fromPhotos: boolean) => {
    setUploading(true)
    setError(null)
    try {
      for (const file of files.slice(0, Math.max(0, 4 - pending.length))) {
        const isMovie = file.type.startsWith('video/')
        setPreparing(isMovie ? 'Uploading video…' : fromPhotos ? 'Adding…' : 'Preparing…')
        const ready = fromPhotos
          ? (isMovie ? await AttachmentPrep.video(file) : await AttachmentPrep.photo(file, file.name))
          : await AttachmentPrep.file(file)
        if (!ready) {
          setError(isMovie ? 'That video could not be read, or is too long to send.'
            : fromPhotos ? 'That photo could not be read.'
              : 'That file can’t be sent — photos, videos, recordings and PDFs only, under 48 MB.')
          continue
        }
        setPreparing(isMovie ? 'Uploading video…' : 'Uploading…')
        await upload(ready)
      }
    } finally {
      setUploading(false)
      setPreparing(null)
    }
  }

  const startVoiceNote = async () => {
    if (pending.length >= 4 || speech.isListening) return
    inputRef.current?.blur()
    setError(null)
    await recorder.start()
    if (recorder.errorText) setError(recorder.errorText)
  }

  const remove = (a: ChatAttachment) => {
    setPending((p) => p.filter((x) => x.id !== a.id))
    void app.api.withdrawAttachment(a.id).catch(() => undefined)
  }

  const menuItems = [
    ...(isTouchDevice() ? [{ label: 'Take a photo or video', icon: 'camera', onSelect: () => cameraInput.current?.click() }] : []),
    { label: 'Photo library', icon: 'photo.on.rectangle', onSelect: () => photoInput.current?.click() },
    { label: 'Record a voice note', icon: 'waveform', onSelect: () => void startVoiceNote() },
    { label: 'Choose a file', icon: 'doc', onSelect: () => fileInput.current?.click() },
  ]

  const composer = (
    <div className="composer-bar stack-8" style={{ paddingBottom: 'calc(8px + var(--tabbar-h) + var(--safe-bottom))' }}>
      {error && <ErrorBanner text={error} />}
      {(pending.length > 0 || uploading) && (
        <div className="quick-row">
          {pending.map((a) => (
            <span key={a.id} className="pending-chip">
              <span className="c-brand-ink"><Sym name={attachmentSymbol(a)} size={12} weight="medium" /></span>
              <span className="ellipsis" style={{ maxWidth: 140 }}>{attachmentDisplayName(a)}</span>
              <span className="c-muted" style={{ fontWeight: 400 }}>{sizeLabel(a.byteSize)}</span>
              <button type="button" className="c-muted touch-target" style={{ minHeight: 0 }} onClick={() => remove(a)} aria-label={`Remove ${attachmentDisplayName(a)}`}>
                <Sym name="xmark" size={12} weight="medium" />
              </button>
            </span>
          ))}
          {uploading && <span className="pending-chip c-muted"><Spinner size={12} /><span>{preparing ?? 'Adding…'}</span></span>}
        </div>
      )}
      {draft === '' && !speech.isListening && (
        <div className="quick-row">
          <span className="t-label-m c-muted" style={{ paddingRight: 2, flexShrink: 0 }}>Quick log</span>
          {quickLogs.map((phrase) => (
            <MPButton key={phrase} kind="gray" size="small" disabled={thinking} className="press"
              onClick={() => { setDraft(phrase); setDraftToAssistant(true); inputRef.current?.focus() }} title="Puts this in the message field">
              {phrase.trim() + (phrase.endsWith(' ') ? '…' : '')}
            </MPButton>
          ))}
        </div>
      )}
      {draftToAssistant && draft !== '' && (
        <div className="hstack-6 t-label c-brand-ink" style={{ padding: '0 6px' }}>
          <Sym name="sparkles" size={12} weight="medium" />
          <span>To MedPull, which logs it for you</span>
          <span className="spacer" />
          <MPButton kind="plain" bare size="small" onClick={() => { setDraft(''); setDraftToAssistant(false) }}>Clear</MPButton>
        </div>
      )}
      {recorder.isRecording ? (
        <div className="hstack" style={{ gap: 10 }}>
          <ComposerRoundButton name="xmark" label="Cancel the voice note" onClick={() => void recorder.cancel()} />
          <div className="recording-box" aria-label={`Recording, ${recorder.elapsedText}`}>
            <i className="tone-dot" style={{ background: 'rgb(var(--risk-high))', width: 8, height: 8 }} aria-hidden="true" />
            <span className="t-copy-lg-m c-ink figures">{recorder.elapsedText}</span>
            <span className="meter"><i style={{ width: `${Math.max(4, recorder.level * 100)}%` }} /></span>
            <span className="t-label c-muted">Recording</span>
          </div>
          <ComposerRoundButton name="stop.fill" active label="Stop and attach the voice note" onClick={() => void finishVoiceNote()} />
        </div>
      ) : (
        <div className="hstack" style={{ gap: 8, alignItems: 'flex-end' }}>
          <ComposerRoundButton name="plus" label="Attach a photo, video, voice note or file" buttonRef={plusRef}
            disabled={uploading || pending.length >= 4 || speech.isListening || draftToAssistant}
            onClick={() => setMenuOpen(true)} />
          <ComposerField
            placeholder={speech.isListening ? 'Listening…' : draftToAssistant ? 'Tell MedPull' : 'Message your care team'}
            text={draft} onChange={(t) => { setDraft(t); if (t === '') setDraftToAssistant(false) }} canSend={canSend} busy={sending} disabled={speech.isListening}
            onSend={() => void send()} inputRef={inputRef} />
          <ComposerRoundButton name={speech.isListening ? 'stop.fill' : 'mic.fill'} active={speech.isListening}
            disabled={thinking || sending} label={speech.isListening ? 'Stop and send' : 'Talk'}
            onClick={() => void toggleMic()} />
        </div>
      )}
      {speech.isListening && <span className="t-label c-risk-high" aria-live="polite">Listening. Tap stop to send.</span>}
      <Menu open={menuOpen} onClose={() => setMenuOpen(false)} anchor={plusRef} items={menuItems} />
      <input ref={cameraInput} className="attach-input" type="file" accept="image/*,video/*" capture="environment"
        onChange={(e) => { const f = Array.from(e.target.files ?? []); e.target.value = ''; if (f.length) void attachFiles(f, true) }} />
      <input ref={photoInput} className="attach-input" type="file" accept="image/*,video/*" multiple
        onChange={(e) => { const f = Array.from(e.target.files ?? []); e.target.value = ''; if (f.length) void attachFiles(f, true) }} />
      <input ref={fileInput} className="attach-input" type="file" accept={AttachmentPrep.accept} multiple
        onChange={(e) => { const f = Array.from(e.target.files ?? []); e.target.value = ''; if (f.length) void attachFiles(f, false) }} />
    </div>
  )

  return (
    <Screen scrollRef={scrollRef} fogHeight={300} nav={(s) => <NavBar title="Care team" scrolled={s} />} bottom={composer}>
      <div className="stack-10" style={{ padding: '0 16px 12px' }}>
        {team.length > 0 && (
          <div className="stack-8" style={{ alignItems: 'center', padding: '12px 0 10px' }}>
            <span className="team-avatars on-canvas" aria-hidden="true">
              {team.slice(0, 3).map((m, i) => <Initials key={i} text={teamInitials(m.name)} size={40} tone="low" style="soft" />)}
            </span>
            <div className="stack-2 center">
              <span className="t-copy-m c-ink">Your care team</span>
              <span className="t-label c-muted">{team.map((m) => m.name).join(', ')}</span>
            </div>
          </div>
        )}
        {app.messages.length === 0 && (
          <Card>
            <div className="stack-8">
              <span className="t-copy-lg-m c-ink">How this works</span>
              <span className="t-copy c-body lh-2">
                Anything you type goes to your care team, and the plus button sends them a photo, a short video, a voice note or a file. Tap the mic, or one of the quick logs, to tell MedPull how you feel: it logs it for you, answers straight away, and passes anything serious to the team.
              </span>
            </div>
          </Card>
        )}
        {app.messages.map((m) => <Bubble key={m.id} message={m} />)}
        {speech.isListening && speech.transcript && (
          <span className="t-copy-lg c-muted" style={{ textAlign: 'right', paddingLeft: 48 }}>{speech.transcript}</span>
        )}
        {thinking && (
          <div className="hstack-8 c-brand-ink"><Spinner size={16} /><span className="t-label c-muted">MedPull is thinking</span></div>
        )}
        {speech.errorText && <ErrorBanner text={speech.errorText} />}
      </div>
    </Screen>
  )
}
