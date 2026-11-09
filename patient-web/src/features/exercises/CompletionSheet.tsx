/* The sheet that closes an exercise, behind a session's Finish and behind
   "Just mark it done": how much it hurts now, how hard it was, what was
   done (filled in from the dose), a note, and the clip of the attempt the
   way the therapist asked for it — required, optional, or not at all.
   Send carries the session's clock when there was one
   (docs/dev/hep-schedule.md, "Second pass", "Start the exercise"). */

import { useRef, useState, type ChangeEvent } from 'react'
import { messageFor, useApp } from '../../core/appModel'
import { AttachmentPrep } from '../../core/attachments'
import {
  Dates, DOT, durationLabel, effortWord, holdIsUnit, sizeLabel, therapistShortName, videoRequirement,
  wearableRequirement, type AnswerValue, type ExerciseAssignment, type StagedUpload,
} from '../../core/models'
import { CloseButton, ErrorBanner, MPButton, NavBar, PrimaryButton, Screen, SecondaryButton, Toggle } from '../../ui/components'
import { Sym } from '../../ui/icons'
import { ScaleAnswer } from '../checkin/CheckinView'

/** The session the sheet closes, when there was one: the phone's own clock
 *  and what was asked before it began. Null for an exercise done away from
 *  the phone. */
export type SessionFacts = {
  startedAt: Date
  endedAt: Date
  painBefore: number | null
  wearableWorn: boolean | null
}

type ClipState =
  | { kind: 'none' }
  | { kind: 'uploading'; name: string; size: number; fraction: number }
  | { kind: 'ready'; name: string; size: number; staged: StagedUpload }
  | { kind: 'failed'; name: string; message: string }

export function CompletionSheet({ a, session, onClose, onSent }: {
  a: ExerciseAssignment
  session: SessionFacts | null
  onClose: () => void
  onSent: (updated: ExerciseAssignment) => void
}) {
  const app = useApp()
  const [pain, setPain] = useState<AnswerValue | null>(null)
  const [effort, setEffort] = useState<number | null>(null)
  const [sets, setSets] = useState(a.sets != null ? String(a.sets) : '')
  const [reps, setReps] = useState(a.reps != null ? String(a.reps) : '')
  const [load, setLoad] = useState(a.loadKg != null ? String(a.loadKg) : '')
  const [note, setNote] = useState('')
  const [clip, setClip] = useState<ClipState>({ kind: 'none' })
  const [worn, setWorn] = useState(session?.wearableWorn === true)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement | null>(null)
  // A pick that was removed before it finished must not come back as ready.
  const generation = useRef(0)

  const therapist = therapistShortName(a.assignedByName)
  const clipAsk = videoRequirement(a)
  const watchAsk = wearableRequirement(a)
  // The session screen asked about the watch before the start; the quick
  // path has to ask here.
  const askWatch = watchAsk !== 'off' && session == null
  const wornNow = session ? session.wearableWorn === true : worn
  const countsReps = !holdIsUnit(a)
  const hasLoad = a.loadKg != null
  const seconds = session ? Math.round((session.endedAt.getTime() - session.startedAt.getTime()) / 1000) : null

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

  const uploading = clip.kind === 'uploading'
  const clipMissing = clipAsk === 'required' && clip.kind !== 'ready'
  const watchMissing = watchAsk === 'required' && !wornNow
  const blocked = uploading || clipMissing || watchMissing
  let why: string | null = null
  if (clipMissing) why = `${therapist} asked for a clip of this one. Send is ready once it’s attached.`
  else if (watchMissing) why = `${therapist} asked for this one with your watch on.`

  const send = async () => {
    setSending(true)
    setError(null)
    try {
      const updated = await app.completeExercise(a, {
        painAfter: typeof pain === 'number' ? pain : null,
        note: note.trim(),
        video: clip.kind === 'ready' ? clip.staged : null,
        effort,
        setsDone: numberIn(sets),
        repsDone: countsReps ? numberIn(reps) : null,
        loadDoneKg: hasLoad ? numberIn(load) : null,
        wearableWorn: watchAsk === 'off' ? null : wornNow,
        startedAt: session ? Dates.iso(session.startedAt) : null,
        endedAt: session ? Dates.iso(session.endedAt) : null,
      })
      onSent(updated)
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setSending(false)
    }
  }

  const sendTitle = uploading ? `Uploading your clip${DOT}${Math.round(clip.fraction * 100)}%` : `Send to ${therapist}`
  const onTheClock = seconds != null ? durationLabel(seconds) : null

  return (
    <Screen
      fogHeight={260}
      nav={(s) => <NavBar title={session ? 'Finish' : 'Mark done'} scrolled={s} trailing={<CloseButton onClick={onClose} label="Cancel" />} />}
      bottom={
        <div className="sheet-controls">
          {error && <ErrorBanner text={error} />}
          {why && !uploading && <span className="t-label c-muted center">{why}</span>}
          <PrimaryButton title={sendTitle} loading={sending} disabled={blocked} onClick={() => void send()} />
        </div>
      }
    >
      <div className="content" style={{ gap: 24, padding: '8px 20px 28px' }}>
        <div className="stack-8">
          <span className="schedule-pill" style={{ alignSelf: 'flex-start' }}>{a.title}</span>
          <h1 className="t-display-s c-ink" style={{ margin: 0 }}>Nice work. How did it go?</h1>
          <span className="t-copy c-muted">
            {onTheClock ? `${onTheClock} on the clock${DOT}` : ''}{therapist} sees your answers with the rest of your week.
          </span>
        </div>

        <div className="stack-10">
          <span className="t-copy-lg-m c-ink">How’s the pain, now that you’ve done it?</span>
          <ScaleAnswer value={pain} painting onChange={setPain} />
        </div>

        <div className="stack-10">
          <span className="t-copy-lg-m c-ink">How hard was it?</span>
          {a.rpeTarget != null && (
            <span className="t-label c-muted">{therapist} suggested around {a.rpeTarget}{DOT}{effortWord(a.rpeTarget).toLowerCase()}.</span>
          )}
          <EffortScale value={effort} onChange={setEffort} />
        </div>

        <div className="stack-10">
          <span className="t-copy-lg-m c-ink">What you did</span>
          <div className="dose-grid">
            <label>
              <span>Sets</span>
              <input className="field" inputMode="numeric" pattern="[0-9]*" value={sets} aria-label="Sets done"
                onChange={(e) => setSets(e.target.value)} />
            </label>
            {countsReps && (
              <label>
                <span>Reps</span>
                <input className="field" inputMode="numeric" pattern="[0-9]*" value={reps} aria-label="Reps done"
                  onChange={(e) => setReps(e.target.value)} />
              </label>
            )}
            {hasLoad && (
              <label>
                <span>Load, kg</span>
                <input className="field" inputMode="decimal" value={load} aria-label="Load done, in kilograms"
                  onChange={(e) => setLoad(e.target.value)} />
              </label>
            )}
          </div>
          <span className="t-label c-muted">Filled in from {therapist}’s dose. Change it if you did more or less.</span>
        </div>

        <div className="stack-10">
          <span className="t-copy-lg-m c-ink">Anything to add?</span>
          <textarea className="field" rows={3} placeholder="Optional — how it felt, what was hard" aria-label="A note for your therapist"
            value={note} onChange={(e) => setNote(e.target.value)} />
        </div>

        {clipAsk !== 'off' && (
          <div className="stack-10">
            <span className="t-copy-lg-m c-ink">
              {clipAsk === 'required' ? `${therapist} asked for a clip of this one` : `Show ${therapist} your form`}
            </span>
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
            <span className="t-label c-muted">
              {clipAsk === 'required'
                ? 'A few seconds of you doing it is plenty. It goes to your care team only.'
                : 'A few seconds is plenty. It goes to your care team only.'}
            </span>
          </div>
        )}

        {askWatch && (
          <div className="stack-10">
            <span className="t-copy-lg-m c-ink">Your watch</span>
            <div className="upload-chip" style={{ gap: 14 }}>
              <span className="c-brand-ink"><Sym name="applewatch" size={22} weight="regular" /></span>
              <div className="stack-2 grow">
                <span className="t-copy-m c-ink">I had my watch on</span>
                <span className="t-label c-muted">
                  {watchAsk === 'required'
                    ? `${therapist} asked for your heart rate with this one.`
                    : 'Your heart rate comes along with it.'}
                </span>
              </div>
              <Toggle checked={worn} onChange={setWorn} label="I had my watch on" />
            </div>
          </div>
        )}
      </div>
    </Screen>
  )
}

/** 0 to 10 on the check-in's slider, with the lifter's words under the
 *  thumb: "Easy" at one end, "All out" at the other. */
export function EffortScale({ value, onChange }: { value: number | null; onChange: (n: number) => void }) {
  const n = value ?? 0
  return (
    <div className="stack-14">
      <div style={{ minHeight: 84, display: 'grid', placeItems: 'center' }}>
        {value == null ? (
          <span className="t-copy-lg-m c-muted">Drag to answer</span>
        ) : (
          <div className="stack center">
            <span className="t-display-xl figures c-brand-ink">{n}</span>
            <span className="t-copy-m c-muted">{effortWord(n)}</span>
          </div>
        )}
      </div>
      <input
        type="range" min={0} max={10} step={1} className="slider"
        value={n}
        style={{ ['--pct' as string]: `${n * 10}%`, ['--tint' as string]: value == null ? 'var(--track)' : 'var(--brand)' }}
        onChange={(e) => onChange(Number(e.target.value))}
        onPointerDown={() => { if (value == null) onChange(0) }}
        aria-label="How hard it was, 0 to 10"
        aria-valuetext={value == null ? 'Not answered' : `${n}, ${effortWord(n)}`}
      />
      <div className="hstack">
        <span className="t-label c-muted">Easy</span>
        <span className="spacer" />
        <span className="t-label c-muted">All out</span>
      </div>
    </div>
  )
}

/** A field's number, or null when it is empty or not one. */
function numberIn(text: string): number | null {
  const clean = text.trim().replace(',', '.')
  if (clean === '') return null
  const n = Number(clean)
  return Number.isFinite(n) && n >= 0 ? n : null
}
