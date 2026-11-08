/* One exercise on today's schedule (route `/today/exercises/:id`): the
   therapist's clip to follow, the steps, what to take care of, the dose and
   her note, then "Mark done" — a sheet asking how much it hurt after, a
   note, and a clip of the attempt — or "Can't do it today" with a reason
   (docs/dev/hep-schedule.md, "Patient web UI"). */

import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { useLocation, useParams } from 'react-router-dom'
import { messageFor, useApp } from '../../core/appModel'
import { AttachmentPrep } from '../../core/attachments'
import {
  Dates, DOT, isOpenAssignment, painLabel, sizeLabel, therapistShortName, typeset,
  type AnswerValue, type ExerciseAssignment, type StagedUpload,
} from '../../core/models'
import {
  Card, Chip, CloseButton, EmptyRow, ErrorBanner, Initials, InsetDivider, MPButton, NavBar, PrimaryButton, Screen,
  SecondaryButton, Sheet, Spinner,
} from '../../ui/components'
import { Sym } from '../../ui/icons'
import { CardTitleRow, Glyph } from '../../ui/rows'
import { useBack } from '../../ui/useBack'
import { ScaleAnswer } from '../checkin/CheckinView'
import { teamInitials } from '../today/TodayView'

/** Where an exercise opens. The row comes from today's feed; a link to one
 *  that is not on it asks the server once, then says so. */
export function ExerciseDestination() {
  const app = useApp()
  const { id } = useParams()
  const location = useLocation()
  const back = useBack('/today')
  const from = (location.state as { from?: string } | null)?.from ?? 'Today'
  const a = app.exercises?.items.find((x) => String(x.id) === id) ?? null
  const [waited, setWaited] = useState(false)

  // The schedule keeps polling on this screen too: the therapist may log
  // it done from the room while the person reads it.
  useEffect(() => app.watchExercises(), [app])
  useEffect(() => {
    if (a) return
    void app.refreshExercises(undefined, false).then(() => setWaited(true))
  }, [app, a])

  const backItem = { label: from, onClick: back }
  if (!a) {
    return (
      <Screen withTabBar nav={(s) => <NavBar title="Exercise" scrolled={s} back={backItem} />}>
        <div className="content">
          {waited
            ? <Card padding={0}><EmptyRow icon="figure.strengthtraining.traditional" title="That exercise isn’t on today’s list" detail="It may have been moved to another day or taken off by your therapist." /></Card>
            : <div className="hstack" style={{ justifyContent: 'center', color: 'rgb(var(--brand))', padding: 32 }}><Spinner /></div>}
        </div>
      </Screen>
    )
  }
  return <ExerciseDetailView a={a} back={backItem} />
}

export function ExerciseDetailView({ a, back }: { a: ExerciseAssignment; back: { label: string; onClick: () => void } }) {
  const [marking, setMarking] = useState(false)
  const [skipping, setSkipping] = useState(false)
  const [justSent, setJustSent] = useState(false)
  const open = isOpenAssignment(a)
  const therapist = therapistShortName(a.assignedByName)
  const isToday = a.scheduledFor === Dates.dayString(new Date())

  return (
    <>
      <Screen
        withTabBar
        nav={(s) => <NavBar title="Exercise" scrolled={s} back={back} />}
        bottom={open ? (
          <div className="action-bar" role="toolbar">
            <button type="button" className="btn-text" onClick={() => setSkipping(true)}>Can’t do it today</button>
            <span className="spacer" />
            <MPButton kind="filled" size="large" onClick={() => setMarking(true)} ariaLabel="Mark done">
              <Sym name="checkmark" size={16} weight="semibold" />
              <span>Mark done</span>
            </MPButton>
          </div>
        ) : undefined}
      >
        <div className="content" style={{ gap: 20, padding: '12px 20px 120px' }}>
          <div className="stack-8">
            <span className="schedule-pill" style={{ alignSelf: 'flex-start' }}>{isToday ? 'Today' : Dates.monthDay(a.scheduledFor)}</span>
            <h1 className="t-display-s c-ink" style={{ margin: 0 }}>{typeset(a.title)}</h1>
            <span className="t-copy-lg c-body">{a.dose}</span>
            {a.assignedByName && <span className="t-copy c-muted">From {a.assignedByName}</span>}
          </div>

          {!open && <OutcomeCard a={a} fresh={justSent} />}

          {a.video ? (
            <div className="stack-8">
              <ClipPlayer url={a.video.url} poster={a.video.posterUrl} label={`${a.title}, demonstration`} />
              <span className="t-label c-muted px-4">
                {a.video.uploadedByName ? `${a.video.uploadedByName}’s demonstration` : 'From the exercise library'}
                {a.video.source === 'clinic' && a.video.uploadedByName ? '' : `${DOT}Follow the steps below`}
              </span>
            </div>
          ) : (
            <span className="t-copy c-muted px-4">No clip for this one yet — the steps below are what to follow.</span>
          )}

          {a.clinicianInstructions && (
            <Card tint>
              <div className="hstack-top">
                <Initials text={teamInitials(a.assignedByName)} size={34} tone="low" style="soft" />
                <div className="stack-3 grow">
                  <span className="t-label-m secondary">{therapist} says</span>
                  <span className="t-copy-lg c-ink lh-2">{typeset(a.clinicianInstructions)}</span>
                </div>
              </div>
            </Card>
          )}

          {a.steps.length > 0 && (
            <Card padding={0}>
              <CardTitleRow title="How to do it" note={a.equipment ? `Needs ${a.equipment.toLowerCase()}` : null} />
              <ol className="steps">
                {a.steps.map((s, i) => <li key={i}>{typeset(s)}</li>)}
              </ol>
            </Card>
          )}

          {a.precautions && (
            <Card>
              <div className="hstack-top">
                <Glyph name="exclamationmark.triangle.fill" family="blue" />
                <div className="stack-3 grow">
                  <span className="t-copy-lg-m c-ink">Take care</span>
                  <span className="t-copy c-body lh-2">{typeset(a.precautions)}</span>
                </div>
              </div>
            </Card>
          )}

          <Card padding={0}>
            <Fact label="Dose" value={a.dose} />
            {a.sideLabel && a.side !== 'not_applicable' && <><InsetDivider leading={16} /><Fact label="Side" value={a.sideLabel} /></>}
            {a.holdSeconds != null && <><InsetDivider leading={16} /><Fact label="Hold" value={`${a.holdSeconds} s`} /></>}
            <InsetDivider leading={16} />
            <Fact label="Equipment" value={a.equipment || 'None needed'} />
          </Card>
        </div>
      </Screen>

      <Sheet open={marking} onClose={() => setMarking(false)}>
        <MarkDoneSheet a={a} onClose={() => setMarking(false)} onSent={() => { setMarking(false); setJustSent(true) }} />
      </Sheet>
      <Sheet open={skipping} onClose={() => setSkipping(false)}>
        <SkipSheet a={a} onClose={() => setSkipping(false)} onSkipped={() => setSkipping(false)} />
      </Sheet>
    </>
  )
}

/** A label and its value on one row of a card. */
function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="hstack" style={{ padding: '0 16px', minHeight: 48 }}>
      <span className="t-copy-lg c-ink">{label}</span>
      <span className="spacer" />
      <span className="t-copy-lg c-muted" style={{ textAlign: 'right' }}>{value}</span>
    </div>
  )
}

// MARK: - What came back

/** Done: "Sent to Dr. Gregg · pain 4/10", when, the note, the clip that
 *  went with it. Skipped: the reason. */
function OutcomeCard({ a, fresh }: { a: ExerciseAssignment; fresh: boolean }) {
  const therapist = therapistShortName(a.assignedByName)
  if (a.status === 'skipped') {
    return (
      <Card tint className={fresh ? 'fade-in' : undefined}>
        <div className="hstack-top">
          <span className="c-muted" style={{ paddingTop: 2 }}><Sym name="minus.circle" size={24} weight="regular" /></span>
          <div className="stack-3 grow">
            <span className="t-copy-lg-m c-ink">Skipped today</span>
            {a.skipReason && <span className="t-copy c-ink lh-2">“{typeset(a.skipReason)}”</span>}
            <span className="t-copy secondary">{therapist} can see this with the rest of your week.</span>
          </div>
        </div>
      </Card>
    )
  }
  const c = a.completion
  const pain = painLabel(c?.painAfter)
  const byTherapist = c?.source === 'console'
  const headline = byTherapist
    ? `Logged by ${therapist}${pain ? `${DOT}${pain}` : ''}`
    : `Sent to ${therapist}${pain ? `${DOT}${pain}` : ''}`
  return (
    <Card tint className={fresh ? 'fade-in' : undefined}>
      <div className="stack-12">
        <div className="hstack-top">
          <span className="c-risk-low" style={{ paddingTop: 1 }}><Sym name="checkmark.seal.fill" size={24} weight="semibold" /></span>
          <div className="stack-3 grow">
            <span className="t-copy-lg-m c-ink">{headline}</span>
            {c?.note && <span className="t-copy c-ink lh-2">“{typeset(c.note)}”</span>}
            <span className="t-copy secondary">
              {c?.completedAt ? `${Dates.relative(c.completedAt)}${byTherapist ? '' : `${DOT}They’ll see it with their next review.`}` : 'They’ll see it with their next review.'}
            </span>
          </div>
        </div>
        {c?.video && !c.video.withdrawn && (
          <ClipPlayer url={c.video.url ?? null} attachmentId={c.video.id} poster={null} label="Your clip" />
        )}
      </div>
    </Card>
  )
}

// MARK: - The clip

/** A clip in the hero's frame. A presigned link plays as it is; a link
 *  into this API (no object store) is fetched under the session first. */
export function ClipPlayer({ url, poster, label, attachmentId }: {
  url: string | null; poster: string | null; label: string; attachmentId?: number
}) {
  const { src, loading, failed } = useClipURL(url, attachmentId)
  return (
    <div className="clip-box">
      {src && <video src={src} controls playsInline preload="metadata" poster={poster ?? undefined} aria-label={label} />}
      {!src && loading && <div className="clip-state"><Spinner /></div>}
      {!src && !loading && (
        <div className="clip-state">
          <span className="hstack-6 t-label-m" style={{ color: 'rgb(255 255 255 / 0.85)' }}>
            <Sym name="video.slash" size={16} />{failed ? 'This clip could not be loaded' : 'No clip'}
          </span>
        </div>
      )}
    </div>
  )
}

function useClipURL(url: string | null, attachmentId?: number): { src: string | null; loading: boolean; failed: boolean } {
  const app = useApp()
  const needsFetch = url ? app.api.needsSession(url) : attachmentId != null
  const key = url ?? (attachmentId != null ? `attachment:${attachmentId}` : null)
  const [state, setState] = useState<{ key: string | null; src: string | null; failed: boolean }>({ key: null, src: null, failed: false })
  useEffect(() => {
    if (!key || !needsFetch) return
    let cancelled = false
    let objectURL: string | null = null
    const bytes = url ? app.api.mediaBlob(url) : app.api.attachmentBlob(attachmentId!)
    bytes
      .then((b) => {
        if (cancelled) return
        objectURL = URL.createObjectURL(b)
        setState({ key, src: objectURL, failed: false })
      })
      .catch(() => { if (!cancelled) setState({ key, src: null, failed: true }) })
    return () => {
      cancelled = true
      if (objectURL) URL.revokeObjectURL(objectURL)
    }
  }, [app, key, url, attachmentId, needsFetch])
  if (!key) return { src: null, loading: false, failed: false }
  if (!needsFetch) return { src: url, loading: false, failed: false }
  if (state.key !== key) return { src: null, loading: true, failed: false }
  return { src: state.src, loading: false, failed: state.failed }
}

// MARK: - Mark done

type ClipState =
  | { kind: 'none' }
  | { kind: 'uploading'; name: string; size: number; fraction: number }
  | { kind: 'ready'; name: string; size: number; staged: StagedUpload }
  | { kind: 'failed'; name: string; message: string }

/** The sheet behind "Mark done": how much it hurt after, a note, a clip of
 *  the attempt, Send. The clip uploads as soon as it is picked, so Send
 *  only has to name it. */
function MarkDoneSheet({ a, onClose, onSent }: { a: ExerciseAssignment; onClose: () => void; onSent: () => void }) {
  const app = useApp()
  const [pain, setPain] = useState<AnswerValue | null>(null)
  const [note, setNote] = useState('')
  const [clip, setClip] = useState<ClipState>({ kind: 'none' })
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement | null>(null)
  // A pick that was removed before it finished must not come back as ready.
  const generation = useRef(0)
  const therapist = therapistShortName(a.assignedByName)

  const pick = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const mine = ++generation.current
    const ready = await AttachmentPrep.video(file)
    if (!ready) {
      const over = file.size > AttachmentPrep.maxMediaBytes
      setClip({
        kind: 'failed', name: file.name,
        message: over
          ? `That clip is over ${Math.floor(AttachmentPrep.maxMediaBytes / 1_048_576)} MB. Try a shorter one.`
          : 'Use a video from your camera (MP4 or QuickTime).',
      })
      return
    }
    setClip({ kind: 'uploading', name: file.name, size: file.size, fraction: 0 })
    try {
      const staged = await app.api.stageUpload(ready.data, ready.contentType, ready.filename, (fraction) => {
        if (generation.current === mine) setClip({ kind: 'uploading', name: file.name, size: file.size, fraction })
      })
      if (generation.current === mine) setClip({ kind: 'ready', name: file.name, size: file.size, staged })
    } catch (err) {
      if (generation.current === mine) setClip({ kind: 'failed', name: file.name, message: messageFor(err) ?? 'The upload did not go through.' })
    }
  }

  const removeClip = () => {
    generation.current++
    setClip({ kind: 'none' })
  }

  const send = async () => {
    setSending(true)
    setError(null)
    try {
      await app.completeExercise(a, {
        painAfter: typeof pain === 'number' ? pain : null,
        note: note.trim(),
        video: clip.kind === 'ready' ? clip.staged : null,
      })
      onSent()
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setSending(false)
    }
  }

  const uploading = clip.kind === 'uploading'
  const sendTitle = uploading ? `Uploading your clip${DOT}${Math.round(clip.fraction * 100)}%` : `Send to ${therapist}`

  return (
    <Screen
      fogHeight={260}
      nav={(s) => <NavBar title="Mark done" scrolled={s} trailing={<CloseButton onClick={onClose} label="Cancel" />} />}
      bottom={
        <div className="sheet-controls">
          {error && <ErrorBanner text={error} />}
          <PrimaryButton title={sendTitle} loading={sending} disabled={uploading} onClick={() => void send()} />
        </div>
      }
    >
      <div className="content" style={{ gap: 24, padding: '8px 20px 28px' }}>
        <div className="stack-8">
          <span className="schedule-pill" style={{ alignSelf: 'flex-start' }}>{a.title}</span>
          <h1 className="t-display-s c-ink" style={{ margin: 0 }}>Nice work. How did it go?</h1>
          <span className="t-copy c-muted">{therapist} sees your answers with the rest of your week.</span>
        </div>

        <div className="stack-10">
          <span className="t-copy-lg-m c-ink">How’s the pain, now that you’ve done it?</span>
          <ScaleAnswer value={pain} painting onChange={setPain} />
        </div>

        <div className="stack-10">
          <span className="t-copy-lg-m c-ink">Anything to add?</span>
          <textarea className="field" rows={3} placeholder="Optional — how it felt, what was hard" aria-label="A note for your therapist"
            value={note} onChange={(e) => setNote(e.target.value)} />
        </div>

        <div className="stack-10">
          <span className="t-copy-lg-m c-ink">Show {therapist} your form</span>
          <input ref={input} type="file" className="attach-input" accept="video/mp4,video/quicktime" capture="environment"
            aria-hidden="true" tabIndex={-1} onChange={(e) => void pick(e)} />
          {clip.kind === 'none' && (
            <SecondaryButton title="Record a clip of you doing it" icon="video.fill" onClick={() => input.current?.click()} />
          )}
          {clip.kind !== 'none' && (
            <div className="upload-chip">
              <span className={clip.kind === 'failed' ? 'c-risk-med' : 'c-brand-ink'}>
                <Sym name={clip.kind === 'failed' ? 'video.slash' : 'film'} size={20} weight="regular" />
              </span>
              <div className="stack-6 grow">
                <div className="hstack-6">
                  <span className="t-copy-m c-ink ellipsis">{clip.name}</span>
                  <span className="spacer" />
                  {clip.kind === 'uploading' && <span className="t-label c-muted figures">{Math.round(clip.fraction * 100)}%</span>}
                  {clip.kind === 'ready' && <span className="t-label c-muted">{sizeLabel(clip.size)}</span>}
                </div>
                {clip.kind === 'uploading' && <div className="progress-line"><i style={{ width: `${clip.fraction * 100}%` }} /></div>}
                {clip.kind === 'ready' && <span className="t-label c-risk-low">Ready to send</span>}
                {clip.kind === 'failed' && <span className="t-label c-risk-med">{clip.message}</span>}
              </div>
              <button type="button" className="remove" onClick={removeClip} aria-label="Remove the clip">
                <Sym name="xmark.circle.fill" size={20} weight="regular" />
              </button>
            </div>
          )}
          {clip.kind === 'failed' && (
            <MPButton kind="plain" onClick={() => input.current?.click()}>Try another clip</MPButton>
          )}
          <span className="t-label c-muted">A few seconds is plenty. It goes to your care team only.</span>
        </div>
      </div>
    </Screen>
  )
}

// MARK: - Can't do it today

const skipReasons = ['Too sore', 'No time today', 'Not sure how', 'No equipment']

/** The sheet behind "Can't do it today": a reason, in a tap or in words. */
function SkipSheet({ a, onClose, onSkipped }: { a: ExerciseAssignment; onClose: () => void; onSkipped: () => void }) {
  const app = useApp()
  const [reason, setReason] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const therapist = therapistShortName(a.assignedByName)

  const skip = async () => {
    setSending(true)
    setError(null)
    try {
      await app.skipExercise(a, reason.trim())
      onSkipped()
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setSending(false)
    }
  }

  return (
    <Screen
      fogHeight={260}
      nav={(s) => <NavBar title="Can’t do it today" scrolled={s} trailing={<CloseButton onClick={onClose} label="Cancel" />} />}
      bottom={
        <div className="sheet-controls">
          {error && <ErrorBanner text={error} />}
          <PrimaryButton title="Skip today" loading={sending} onClick={() => void skip()} />
        </div>
      }
    >
      <div className="content" style={{ gap: 24, padding: '8px 20px 28px' }}>
        <div className="stack-8">
          <span className="schedule-pill" style={{ alignSelf: 'flex-start' }}>{a.title}</span>
          <h1 className="t-display-s c-ink" style={{ margin: 0 }}>That’s okay. What’s in the way?</h1>
          <span className="t-copy c-muted">{therapist} will see this and can change the plan.</span>
        </div>
        <div className="chip-row">
          {skipReasons.map((r) => (
            <Chip key={r} label={r} selected={reason === r} onClick={() => setReason(reason === r ? '' : r)} />
          ))}
        </div>
        <textarea className="field" rows={3} placeholder="Or say it in your own words — optional" aria-label="Why not today"
          value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
    </Screen>
  )
}
