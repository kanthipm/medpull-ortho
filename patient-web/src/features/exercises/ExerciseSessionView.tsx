/* The guided task behind Start (route `/today/exercises/:id/session`): one
   step at a time, each a full screen with one primary button, the way a
   workout app walks you through a set. Start (pain right now, one tap) →
   your watch, when the therapist asked for it → set up your phone → do the
   exercise (her clip looping, the steps, the dose, a clock and the set
   counter) → record your attempt, when she asked for it → checking the
   recording while it uploads → how it feels now and how hard it was →
   done. Stages the requirements turn off are simply absent from the strip
   (docs/dev/hep-schedule.md, "Second pass", "Start the exercise"). */

import { useEffect, useRef, useState, type ChangeEvent, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { messageFor, useApp } from '../../core/appModel'
import { AttachmentPrep } from '../../core/attachments'
import {
  Dates, DOT, effortLabel, effortWord, holdIsUnit, isOpenAssignment, loadLabel, painLabel, therapistShortName, typeset,
  videoRequirement, wearableRequirement,
  type AnswerValue, type ExerciseAssignment, type StagedUpload,
} from '../../core/models'
import { Card, ErrorBanner, MPButton, NavBar, NavTextButton, PrimaryButton, Screen, SecondaryButton, Spinner } from '../../ui/components'
import { Sym } from '../../ui/icons'
import { useBack } from '../../ui/useBack'
import { ScaleAnswer } from '../checkin/CheckinView'
import { EffortScale } from './CompletionSheet'
import { ClipPlayer, MissingExercise, OutcomeCard, useAssignment } from './ExerciseDetailView'

/** The rest between sets of a counted exercise. The dose carries no rest
 *  of its own; a minute is what a loading programme usually asks. */
const REST_SECONDS = 60
/** A clip of the attempt stops itself here: long enough for a set, short
 *  enough to send on a phone. */
const RECORD_SECONDS = 20

// MARK: - The demo stand-ins

/** Reading the wearable. A browser cannot see a watch, so this is the
 *  demo's stand-in: after about two seconds it says one was found. The
 *  phone apps replace this one function with the real check. */
function detectWearable(): Promise<{ detected: boolean; name: string }> {
  return new Promise((resolve) => setTimeout(() => resolve({ detected: true, name: 'Apple Watch' }), 2000))
}

/** Checking a recording. Nothing is analysed: the demo's stand-in waits
 *  about two seconds — which also covers the upload running beside it —
 *  and says the clip looks good. */
function checkRecording(): Promise<{ ok: boolean }> {
  return new Promise((resolve) => setTimeout(() => resolve({ ok: true }), 2000))
}

// MARK: - Where the task opens

export function ExerciseSessionDestination() {
  const { id } = useParams()
  const back = useBack(`/today/exercises/${id ?? ''}`)
  const { a, waited } = useAssignment(id)
  if (!a) return <MissingExercise back={{ label: 'Exercise', onClick: back }} waited={waited} title="Session" />
  return <GuidedTask a={a} onLeave={back} />
}

type StageKey = 'start' | 'wearable' | 'setup' | 'exercise' | 'record' | 'check' | 'pain' | 'done'

/** The stages this exercise needs, in order. */
function stagesFor(a: ExerciseAssignment): StageKey[] {
  const s: StageKey[] = ['start']
  if (wearableRequirement(a) !== 'off') s.push('wearable')
  s.push('setup', 'exercise')
  if (videoRequirement(a) !== 'off') s.push('record', 'check')
  s.push('pain', 'done')
  return s
}

const stageTitles: Record<StageKey, string> = {
  start: 'Start', wearable: 'Your watch', setup: 'Set up your phone', exercise: 'Do the exercise',
  record: 'Record your attempt', check: 'Checking your recording', pain: 'How did it go?', done: 'Done',
}

/** A recorded attempt, ready to upload. */
type Take = { data: Blob; contentType: string; filename: string }

export function GuidedTask({ a, onLeave }: { a: ExerciseAssignment; onLeave: () => void }) {
  const app = useApp()
  const navigate = useNavigate()
  const stages = stagesFor(a)
  const [index, setIndex] = useState(0)
  const stage = stages[index]
  const steps = stages.length - 1 // "done" is not a step
  const [startedAt, setStartedAt] = useState<Date | null>(null)
  const [endedAt, setEndedAt] = useState<Date | null>(null)
  const [painBefore, setPainBefore] = useState<AnswerValue | null>(null)
  const [worn, setWorn] = useState<boolean | null>(null)
  const [setsDone, setSetsDone] = useState(0)
  const [take, setTake] = useState<Take | null>(null)
  const [clip, setClip] = useState<StagedUpload | null>(null)
  const [updated, setUpdated] = useState<ExerciseAssignment | null>(null)
  const therapist = therapistShortName(a.assignedByName)
  const watchAsk = wearableRequirement(a)
  const clipAsk = videoRequirement(a)

  const next = () => setIndex((i) => Math.min(stages.length - 1, i + 1))
  const jumpTo = (key: StageKey) => setIndex(Math.max(index, stages.indexOf(key)))

  // The therapist logged it from the room while this was open.
  if (!isOpenAssignment(a) && stage !== 'done') {
    return (
      <TaskScreen title="Session" onLeave={onLeave} leaveLabel="Back"
        bottom={<PrimaryButton title="Back to the exercise" onClick={onLeave} />}>
        <Heading pill={a.title} title="This one’s already done." />
        <OutcomeCard a={a} fresh={false} />
      </TaskScreen>
    )
  }

  const strip = stage === 'done' ? null : <TaskStrip step={index + 1} of={steps} />

  switch (stage) {
    case 'start':
      return (
        <StartStage a={a} strip={strip} painBefore={painBefore} onPain={setPainBefore} onLeave={onLeave}
          onStarted={(began) => { setStartedAt(began); next() }} />
      )
    case 'wearable':
      return (
        <WearableStage a={a} strip={strip} onLeave={onLeave}
          onContinue={(detected) => { setWorn(detected); next() }} />
      )
    case 'setup':
      return <SetupStage strip={strip} onLeave={onLeave} onReady={next} />
    case 'exercise':
      return (
        <ExerciseStage a={a} strip={strip} startedAt={startedAt ?? new Date()} onLeave={onLeave}
          onDone={(done) => { setSetsDone(done); setEndedAt(new Date()); next() }} />
      )
    case 'record':
      return (
        <RecordStage a={a} strip={strip} onLeave={onLeave}
          onUse={(t) => { setTake(t); next() }}
          onSkip={clipAsk === 'optional' ? () => jumpTo('pain') : undefined} />
      )
    case 'check':
      return (
        <CheckStage take={take} strip={strip} therapist={therapist} onLeave={onLeave}
          onContinue={(staged) => { setClip(staged); next() }} />
      )
    case 'pain':
      return (
        <PainStage a={a} strip={strip} onLeave={onLeave} onSent={(u) => { setUpdated(u); next() }}
          send={(painAfter, effort, note) => app.completeExercise(a, {
            painAfter, note, video: clip, effort,
            setsDone: setsDone > 0 ? setsDone : null, repsDone: a.reps ?? null, loadDoneKg: a.loadKg ?? null,
            wearableWorn: watchAsk === 'off' ? null : worn === true,
            startedAt: startedAt ? Dates.iso(startedAt) : null,
            endedAt: endedAt ? Dates.iso(endedAt) : null,
          })} />
      )
    case 'done':
      return <DoneStage a={updated ?? a} startedAt={startedAt} endedAt={endedAt} onHome={() => navigate('/today')} />
  }
}

// MARK: - The frame every stage shares

/** A stage: the nav with its title and a quiet Leave, the strip, the
 *  body, and the one primary button pinned at the bottom. */
function TaskScreen({ title, onLeave, leaveLabel = 'Leave', strip, children, bottom, gap = 18 }: {
  title: string; onLeave: () => void; leaveLabel?: string; strip?: ReactNode; children: ReactNode; bottom?: ReactNode; gap?: number
}) {
  return (
    <Screen
      nav={(s) => <NavBar title={title} scrolled={s} leading={<NavTextButton onClick={onLeave}>{leaveLabel}</NavTextButton>} />}
      bottom={bottom ? <div className="sheet-controls above-tabbar">{bottom}</div> : undefined}
    >
      <div className="content" style={{ gap, padding: '6px 20px 28px' }}>
        {strip}
        {children}
      </div>
    </Screen>
  )
}

/** "Step 3 of 7" and its dots. */
function TaskStrip({ step, of }: { step: number; of: number }) {
  return (
    <div className="task-strip" aria-label={`Step ${step} of ${of}`}>
      <div className="task-dots" aria-hidden="true">
        {Array.from({ length: of }, (_, i) => <i key={i} className={i + 1 < step ? 'done' : i + 1 === step ? 'now' : undefined} />)}
      </div>
      <span className="t-label c-muted figures">Step {step} of {of}</span>
    </div>
  )
}

function Heading({ pill, title, sub }: { pill?: string; title: string; sub?: ReactNode }) {
  return (
    <div className="stack-8">
      {pill && <span className="schedule-pill" style={{ alignSelf: 'flex-start' }}>{pill}</span>}
      <h1 className="t-display-s c-ink" style={{ margin: 0 }}>{title}</h1>
      {sub && <span className="t-copy-lg c-body">{sub}</span>}
    </div>
  )
}

/** The green check that closes a checking stage. */
function CheckSeal({ label }: { label: string }) {
  return (
    <div className="stack-12 center fade-in" style={{ alignItems: 'center', padding: '12px 0' }} role="status">
      <div className="seal" aria-hidden="true"><Sym name="checkmark" size={34} weight="semibold" /></div>
      <span className="t-copy-lg-m c-ink">{label}</span>
    </div>
  )
}

// MARK: - 1. Start

/** "You have this to do": the title, the dose, her note, the pain right
 *  now in one tap, and Start. */
function StartStage({ a, strip, painBefore, onPain, onLeave, onStarted }: {
  a: ExerciseAssignment; strip: ReactNode; painBefore: AnswerValue | null; onPain: (v: AnswerValue | null) => void
  onLeave: () => void; onStarted: (began: Date) => void
}) {
  const app = useApp()
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const therapist = therapistShortName(a.assignedByName)

  const start = async () => {
    const began = new Date()
    setStarting(true)
    setError(null)
    try {
      // The watch is asked on its own stage; the start carries the pain.
      await app.startExercise(a, { painBefore: typeof painBefore === 'number' ? painBefore : null, wearableWorn: null })
      onStarted(began)
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setStarting(false)
    }
  }

  return (
    <TaskScreen title={stageTitles.start} onLeave={onLeave} strip={strip}
      bottom={<>{error && <ErrorBanner text={error} />}<PrimaryButton title="Start" icon="play.fill" loading={starting} onClick={() => void start()} /></>}>
      <Heading pill="You have this to do" title={typeset(a.title)} sub={a.dose} />
      {a.rpeTarget != null && (
        <span className="t-copy c-muted">Aim for effort {a.rpeTarget}/10{DOT}{effortWord(a.rpeTarget).toLowerCase()}</span>
      )}
      {a.clinicianInstructions && (
        <Card tint>
          <div className="stack-3">
            <span className="t-label-m secondary">{therapist} says</span>
            <span className="t-copy-lg c-ink lh-2">{typeset(a.clinicianInstructions)}</span>
          </div>
        </Card>
      )}
      <Card>
        <div className="stack-10">
          <span className="t-copy-lg-m c-ink">Pain right now?</span>
          <ScaleAnswer value={painBefore} painting onChange={onPain} />
          <span className="t-label c-muted">One tap. Skip it if you’d rather.</span>
        </div>
      </Card>
    </TaskScreen>
  )
}

// MARK: - 2. Your watch

/** Looks for the watch, then Continue. When the therapist requires it and
 *  none is found, the task cannot go on until a retry finds one. */
function WearableStage({ a, strip, onLeave, onContinue }: {
  a: ExerciseAssignment; strip: ReactNode; onLeave: () => void; onContinue: (detected: boolean) => void
}) {
  const required = wearableRequirement(a) === 'required'
  const therapist = therapistShortName(a.assignedByName)
  const [attempt, setAttempt] = useState(0)
  const [result, setResult] = useState<{ detected: boolean; name: string } | null>(null)

  useEffect(() => {
    let cancelled = false
    void detectWearable().then((r) => { if (!cancelled) setResult(r) })
    return () => { cancelled = true }
  }, [attempt])

  const checking = result == null
  const found = result?.detected === true
  let bottom: ReactNode
  if (checking) bottom = <PrimaryButton title="Checking…" disabled />
  else if (found) bottom = <PrimaryButton title="Continue" onClick={() => onContinue(true)} />
  else if (required) bottom = <PrimaryButton title="Try again" icon="arrow.counterclockwise" onClick={() => { setResult(null); setAttempt((n) => n + 1) }} />
  else bottom = <PrimaryButton title="Continue without it" onClick={() => onContinue(false)} />

  return (
    <TaskScreen title={stageTitles.wearable} onLeave={onLeave} strip={strip} bottom={bottom}>
      <Heading title={required ? 'Wear your watch for this one.' : 'Wearing your watch?'}
        sub={required ? `${therapist} wants your heart rate with it.` : 'Your heart rate comes along with the exercise when you are.'} />
      <Card tint={found}>
        <div className="stack-12 center" style={{ alignItems: 'center', padding: '18px 0' }}>
          {checking && (
            <>
              <span style={{ color: 'rgb(var(--brand))' }}><Spinner size={34} /></span>
              <span className="t-copy-lg-m c-ink" role="status">Checking for your watch…</span>
              <span className="t-copy secondary">Keep it on your wrist and close to the phone.</span>
            </>
          )}
          {!checking && found && <CheckSeal label={`Detected${DOT}${result.name}`} />}
          {!checking && !found && (
            <>
              <span className="c-risk-med"><Sym name="applewatch" size={34} weight="regular" /></span>
              <span className="t-copy-lg-m c-ink" role="status">No watch found</span>
              <span className="t-copy secondary">{required ? 'Put your watch on and try again.' : 'You can carry on without it.'}</span>
            </>
          )}
        </div>
      </Card>
      {!checking && !found && required && (
        <span className="t-label c-muted center">{therapist} asked for this one with your watch on, so the exercise waits for it.</span>
      )}
    </TaskScreen>
  )
}

// MARK: - 3. Set up your phone

function SetupStage({ strip, onLeave, onReady }: { strip: ReactNode; onLeave: () => void; onReady: () => void }) {
  return (
    <TaskScreen title={stageTitles.setup} onLeave={onLeave} strip={strip} bottom={<PrimaryButton title="Ready" onClick={onReady} />}>
      <Heading title="Prop your phone up." sub="Against something about knee height, two metres away, so it can see your whole body." />
      <Card>
        <SetupArt />
      </Card>
      <span className="t-label c-muted center">A chair leg or a bag works. Turn the sound up if you want to hear the timer.</span>
    </TaskScreen>
  )
}

/** The illustration: the phone propped at knee height, the person two
 *  metres away, drawn in the app's ink and sage. */
function SetupArt() {
  return (
    <svg className="setup-art" viewBox="0 0 320 180" role="img" aria-label="A phone propped at knee height, two metres from where you stand">
      <line x1="12" y1="150" x2="308" y2="150" className="floor" />
      <g transform="translate(40 118) rotate(-14)">
        <rect x="0" y="0" width="22" height="40" rx="4" className="phone" />
        <rect x="3" y="4" width="16" height="30" rx="2" className="phone-screen" />
      </g>
      <path d="M62 150 l10 -28" className="prop" />
      <g className="person">
        <circle cx="250" cy="52" r="12" />
        <path d="M250 64 v38" />
        <path d="M250 74 l-22 18 M250 74 l22 18" />
        <path d="M250 102 l-16 44 M250 102 l16 44" />
      </g>
      <path d="M78 164 H228" className="measure" />
      <path d="M78 158 v12 M228 158 v12" className="measure" />
      <text x="153" y="178" textAnchor="middle" className="label">about 2 m</text>
      <path d="M30 118 h-14" className="measure" />
      <text x="14" y="112" textAnchor="start" className="label">knee height</text>
    </svg>
  )
}

// MARK: - 4. Do the exercise

type Phase =
  | { kind: 'work'; set: number }
  | { kind: 'rest'; set: number; endsAt: number }
  | { kind: 'hold'; set: number; endsAt: number }
  | { kind: 'all' }

/** Her clip looping, the steps, the dose, a clock and the set counter —
 *  rest between sets, or a timed hold when the set is one. The primary
 *  moves the set on; "I'm done" is there at any point. */
function ExerciseStage({ a, strip, startedAt, onLeave, onDone }: {
  a: ExerciseAssignment; strip: ReactNode; startedAt: Date; onLeave: () => void; onDone: (setsDone: number) => void
}) {
  const [phase, setPhase] = useState<Phase>({ kind: 'work', set: 1 })
  const now = useNow(true)
  const sets = Math.max(1, a.sets ?? 1)
  const timedHold = holdIsUnit(a)
  const hold = a.holdSeconds ?? 0

  // A rest or a hold that runs out moves the session on by itself.
  useEffect(() => {
    if (phase.kind !== 'rest' && phase.kind !== 'hold') return
    const after: Phase = phase.kind === 'rest'
      ? { kind: 'work', set: phase.set }
      : phase.set < sets ? { kind: 'work', set: phase.set + 1 } : { kind: 'all' }
    const t = window.setTimeout(() => setPhase(after), Math.max(0, phase.endsAt - Date.now()))
    return () => window.clearTimeout(t)
  }, [phase, sets])

  const elapsed = Math.max(0, Math.floor((now - startedAt.getTime()) / 1000))
  const left = phase.kind === 'rest' || phase.kind === 'hold' ? Math.max(0, Math.ceil((phase.endsAt - now) / 1000)) : null
  const doseBits: string[] = []
  if (!timedHold && a.reps != null) doseBits.push(`${a.reps} reps`)
  if (!timedHold && hold > 0) doseBits.push(`hold ${hold} s each`)
  const kg = loadLabel(a.loadKg)
  if (kg) doseBits.push(kg)
  if (a.sideLabel && a.side !== 'not_applicable') doseBits.push(a.sideLabel)

  const doneSets = phase.kind === 'all' ? sets : phase.set - 1
  const nowSet = phase.kind === 'work' || phase.kind === 'hold' ? phase.set : null
  let eyebrow: string
  let line: string
  let primary: ReactNode
  switch (phase.kind) {
    case 'work':
      eyebrow = `Set ${phase.set} of ${sets}`
      if (timedHold) {
        line = [`Hold for ${hold} s`, ...doseBits].join(DOT)
        primary = <PrimaryButton title="Start the hold" icon="play.fill" onClick={() => setPhase({ kind: 'hold', set: phase.set, endsAt: Date.now() + hold * 1000 })} />
      } else {
        line = doseBits.join(DOT) || a.dose
        primary = phase.set < sets
          ? <PrimaryButton title="Next set" icon="arrow.right" onClick={() => setPhase({ kind: 'rest', set: phase.set + 1, endsAt: Date.now() + REST_SECONDS * 1000 })} />
          : <PrimaryButton title="I’m done" icon="checkmark" onClick={() => onDone(sets)} />
      }
      break
    case 'rest':
      eyebrow = 'Rest'
      line = `Next up: set ${phase.set} of ${sets}`
      primary = <PrimaryButton title="Skip the rest" icon="forward.end.fill" onClick={() => setPhase({ kind: 'work', set: phase.set })} />
      break
    case 'hold':
      eyebrow = `Set ${phase.set} of ${sets}${DOT}Holding`
      line = 'Keep it steady. The next set comes up on its own.'
      primary = <PrimaryButton title="Stop early" icon="stop.fill" onClick={() => setPhase(phase.set < sets ? { kind: 'work', set: phase.set + 1 } : { kind: 'all' })} />
      break
    case 'all':
      eyebrow = 'All done'
      line = `All ${sets} ${sets === 1 ? 'set' : 'sets'} done.`
      primary = <PrimaryButton title="I’m done" icon="checkmark" onClick={() => onDone(sets)} />
      break
  }
  const finishEarly = phase.kind !== 'all' && !(phase.kind === 'work' && phase.set === sets && !timedHold)

  return (
    <TaskScreen title={stageTitles.exercise} onLeave={onLeave} strip={strip} gap={14}
      bottom={
        <>
          {primary}
          {finishEarly && (
            <MPButton kind="plain" bare className="center" onClick={() => onDone(doneSets)}>
              <span className="t-copy-m">I’m done — stop here</span>
            </MPButton>
          )}
        </>
      }>
      {a.video && <ClipPlayer url={a.video.url} poster={a.video.posterUrl} label={`${a.title}, demonstration`} loop />}
      <Card tint>
        <div className="stack-12">
          <div className="hstack">
            <span className="t-label-m secondary">{eyebrow}</span>
            <span className="spacer" />
            <span className="hstack-6 t-label secondary figures" aria-label={`${clock(elapsed)} on the clock`}>
              <Sym name="timer" size={13} weight="medium" />{clock(elapsed)}
            </span>
          </div>
          <span className={left != null ? 'session-clock rest' : 'session-clock'}
            aria-label={left != null ? `${left} seconds left` : `${clock(elapsed)} on the clock`}>
            {left != null ? clock(left) : clock(elapsed)}
          </span>
          <div className="set-pips" aria-hidden="true">
            {Array.from({ length: sets }, (_, i) => (
              <i key={i} className={i < doneSets ? 'done' : i + 1 === nowSet ? 'now' : undefined} />
            ))}
          </div>
          <span className="t-copy-lg c-ink">{line}</span>
          {a.clinicianInstructions && <span className="t-copy secondary">“{typeset(a.clinicianInstructions)}”</span>}
        </div>
      </Card>
      {a.steps.length > 0 && (
        <Card padding={0}>
          <ol className="steps" style={{ paddingTop: 8 }}>
            {a.steps.map((s, i) => <li key={i}>{typeset(s)}</li>)}
          </ol>
        </Card>
      )}
    </TaskScreen>
  )
}

// MARK: - 5. Record your attempt

type RecordMode = 'asking' | 'live' | 'countdown' | 'recording' | 'review' | 'fallback'

/** A live camera preview and a big record button: three, two, one, then
 *  up to twenty seconds, then "Use this" or "Again". Where the browser
 *  cannot record MP4 — the only clip format the server takes besides
 *  QuickTime — or the camera is refused, the camera-roll picker stands in. */
function RecordStage({ a, strip, onLeave, onUse, onSkip }: {
  a: ExerciseAssignment; strip: ReactNode; onLeave: () => void; onUse: (take: Take) => void; onSkip?: () => void
}) {
  const canRecord = typeof MediaRecorder !== 'undefined' && typeof MediaRecorder.isTypeSupported === 'function'
    && MediaRecorder.isTypeSupported('video/mp4') && !!navigator.mediaDevices?.getUserMedia
  const [mode, setMode] = useState<RecordMode>(() => (canRecord ? 'asking' : 'fallback'))
  const [count, setCount] = useState(3)
  const [elapsed, setElapsed] = useState(0)
  const [taken, setTaken] = useState<{ blob: Blob; url: string } | null>(null)
  const [fallback, setFallback] = useState<{ name: string; message: string } | null>(null)
  const video = useRef<HTMLVideoElement | null>(null)
  const stream = useRef<MediaStream | null>(null)
  const recorder = useRef<MediaRecorder | null>(null)
  const chunks = useRef<Blob[]>([])
  const input = useRef<HTMLInputElement | null>(null)
  const therapist = therapistShortName(a.assignedByName)
  const required = videoRequirement(a) === 'required'
  const app = useApp()
  const [demo, setDemo] = useState(false)
  const [sampling, setSampling] = useState(false)
  useEffect(() => { void app.api.isDemo().then(setDemo) }, [app])

  /** Demo stacks only: the therapist's own demonstration stands in for the
   *  patient's attempt, so the task runs end to end in front of a room
   *  whatever the browser's camera support. Never offered on the real app. */
  const takeSample = async () => {
    const url = a.video?.url
    if (!url) return
    setSampling(true)
    try {
      const blob = app.api.needsSession(url) ? await app.api.mediaBlob(url) : await (await fetch(url)).blob()
      stopRecording()
      onUse({ data: blob, contentType: 'video/mp4', filename: 'attempt.mp4' })
    } catch {
      setFallback({ name: 'sample', message: 'The sample clip could not be loaded. Try recording instead.' })
      setSampling(false)
    }
  }

  // The camera, for as long as this stage is showing.
  useEffect(() => {
    if (!canRecord) return
    let cancelled = false
    navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
      .then((s) => {
        if (cancelled) { s.getTracks().forEach((t) => t.stop()); return }
        stream.current = s
        setMode('live')
      })
      .catch(() => { if (!cancelled) setMode('fallback') })
    return () => {
      cancelled = true
      if (recorder.current?.state === 'recording') recorder.current.stop()
      stream.current?.getTracks().forEach((t) => t.stop())
      stream.current = null
    }
  }, [canRecord])

  // The preview element shows the stream whenever both exist.
  useEffect(() => {
    if (video.current && stream.current && (mode === 'live' || mode === 'countdown' || mode === 'recording')) {
      video.current.srcObject = stream.current
    }
  })

  // Three, two, one — then the recorder starts.
  useEffect(() => {
    if (mode !== 'countdown') return
    const t = window.setTimeout(() => {
      if (count > 1) { setCount((c) => c - 1); return }
      const s = stream.current
      if (!s) { setMode('fallback'); return }
      chunks.current = []
      const r = new MediaRecorder(s, { mimeType: 'video/mp4' })
      r.ondataavailable = (e) => { if (e.data.size) chunks.current.push(e.data) }
      r.onstop = () => {
        const blob = new Blob(chunks.current, { type: 'video/mp4' })
        setTaken({ blob, url: URL.createObjectURL(blob) })
        setMode('review')
      }
      r.start(250)
      recorder.current = r
      setElapsed(0)
      setMode('recording')
    }, 1000)
    return () => window.clearTimeout(t)
  }, [mode, count])

  // The clock while recording; it stops itself at the limit.
  useEffect(() => {
    if (mode !== 'recording') return
    const began = Date.now()
    const t = window.setInterval(() => {
      const s = (Date.now() - began) / 1000
      setElapsed(s)
      if (s >= RECORD_SECONDS) {
        const r = recorder.current
        if (r && r.state === 'recording') r.stop()
        recorder.current = null
      }
    }, 200)
    return () => window.clearInterval(t)
  }, [mode])

  // A take that is not used is let go of.
  useEffect(() => () => { if (taken) URL.revokeObjectURL(taken.url) }, [taken])

  const stopRecording = () => {
    const r = recorder.current
    if (r && r.state === 'recording') r.stop()
    recorder.current = null
  }

  const again = () => {
    setTaken(null)
    setCount(3)
    setMode(stream.current ? 'live' : 'fallback')
  }

  const pick = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const ready = await AttachmentPrep.video(file)
    if (!ready) {
      const over = file.size > AttachmentPrep.maxMediaBytes
      setFallback({
        name: file.name,
        message: over
          ? `That clip is over ${Math.floor(AttachmentPrep.maxMediaBytes / 1_048_576)} MB. Try a shorter one.`
          : 'Use a video from your camera (MP4 or QuickTime).',
      })
      return
    }
    onUse({ data: ready.data, contentType: ready.contentType, filename: ready.filename ?? 'attempt.mp4' })
  }

  let bottom: ReactNode
  switch (mode) {
    case 'asking':
      bottom = <PrimaryButton title="Waiting for the camera…" disabled />
      break
    case 'live':
      bottom = <PrimaryButton title="Record" icon="video.fill" onClick={() => { setCount(3); setMode('countdown') }} />
      break
    case 'countdown':
      bottom = <PrimaryButton title="Get ready…" disabled />
      break
    case 'recording':
      bottom = <PrimaryButton title="Stop" icon="stop.fill" onClick={stopRecording} />
      break
    case 'review':
      bottom = (
        <>
          <PrimaryButton title="Use this" icon="checkmark" onClick={() => taken && onUse({ data: taken.blob, contentType: 'video/mp4', filename: 'attempt.mp4' })} />
          <SecondaryButton title="Again" icon="arrow.counterclockwise" onClick={again} />
        </>
      )
      break
    case 'fallback':
      bottom = <PrimaryButton title="Record a clip of you doing it" icon="video.fill" onClick={() => input.current?.click()} />
      break
  }

  return (
    <TaskScreen title={stageTitles.record} onLeave={onLeave} strip={strip} gap={14}
      bottom={
        <>
          {bottom}
          {demo && a.video?.url && mode !== 'recording' && mode !== 'countdown' && mode !== 'review' && (
            <SecondaryButton title={sampling ? 'Loading the sample…' : 'Use a sample clip (demo)'} icon="film"
              disabled={sampling} onClick={() => void takeSample()} />
          )}
          {onSkip && mode !== 'recording' && mode !== 'countdown' && (
            <MPButton kind="plain" bare className="center" onClick={onSkip}><span className="t-copy-m">Skip recording</span></MPButton>
          )}
        </>
      }>
      <Heading title={required ? `${therapist} asked for a clip of this one.` : `Show ${therapist} your form.`}
        sub={mode === 'fallback'
          ? 'Film a few seconds of you doing it with your camera and pick the clip here.'
          : `A few seconds is plenty. It stops on its own at ${RECORD_SECONDS} seconds and goes to your care team only.`} />
      {mode !== 'fallback' && (
        <div className="clip-box">
          {mode === 'review' && taken
            ? <video src={taken.url} controls playsInline aria-label="Your attempt" />
            : <video ref={video} autoPlay muted playsInline aria-label="Camera preview" />}
          {mode === 'asking' && <div className="clip-state"><Spinner /></div>}
          {mode === 'countdown' && (
            <div className="clip-state"><span className="rec-count figures" aria-live="assertive">{count}</span></div>
          )}
          {mode === 'recording' && (
            <span className="rec-badge figures" role="status"><i /> {clock(elapsed)}{DOT}{RECORD_SECONDS - Math.floor(elapsed)} s left</span>
          )}
        </div>
      )}
      {mode === 'fallback' && (
        <>
          <input ref={input} type="file" className="attach-input" accept="video/mp4,video/quicktime" capture="environment"
            aria-hidden="true" tabIndex={-1} onChange={(e) => void pick(e)} />
          <Card>
            <div className="hstack-top">
              <span className="c-brand-ink"><Sym name="camera" size={22} weight="regular" /></span>
              <div className="stack-3 grow">
                <span className="t-copy-lg-m c-ink">Your camera app does this part</span>
                <span className="t-copy secondary">
                  This browser can’t record straight into the app, so the button below opens your camera and brings the clip back here.
                </span>
                {fallback && <span className="t-label c-risk-med">{fallback.message}</span>}
              </div>
            </div>
          </Card>
        </>
      )}
    </TaskScreen>
  )
}

// MARK: - 6. Checking your recording

/** A progress ring for about two seconds, then the check. The staged
 *  upload runs underneath it, so the wait covers the upload; a failed
 *  upload says so and offers to try again. */
function CheckStage({ take, strip, therapist, onLeave, onContinue }: {
  take: Take | null; strip: ReactNode; therapist: string; onLeave: () => void; onContinue: (staged: StagedUpload | null) => void
}) {
  const app = useApp()
  const [attempt, setAttempt] = useState(0)
  const [state, setState] = useState<{ kind: 'working' } | { kind: 'ok'; staged: StagedUpload } | { kind: 'failed'; message: string }>({ kind: 'working' })

  useEffect(() => {
    if (!take) return
    let cancelled = false
    Promise.all([app.api.stageUpload(take.data, take.contentType, take.filename), checkRecording()])
      .then(([staged]) => { if (!cancelled) setState({ kind: 'ok', staged }) })
      .catch((e: unknown) => { if (!cancelled) setState({ kind: 'failed', message: messageFor(e) ?? 'The upload did not go through.' }) })
    return () => { cancelled = true }
  }, [app, take, attempt])

  if (!take) {
    // Nothing was recorded: the stage has nothing to check.
    return (
      <TaskScreen title={stageTitles.check} onLeave={onLeave} strip={strip} bottom={<PrimaryButton title="Continue" onClick={() => onContinue(null)} />}>
        <Heading title="No clip this time." />
      </TaskScreen>
    )
  }

  const bottom = state.kind === 'ok'
    ? <PrimaryButton title="Continue" onClick={() => onContinue(state.staged)} />
    : state.kind === 'failed'
      ? <PrimaryButton title="Try again" icon="arrow.counterclockwise" onClick={() => { setState({ kind: 'working' }); setAttempt((n) => n + 1) }} />
      : <PrimaryButton title="Checking…" disabled />

  return (
    <TaskScreen title={stageTitles.check} onLeave={onLeave} strip={strip} bottom={bottom}>
      <Heading title={state.kind === 'ok' ? 'Looks good.' : state.kind === 'failed' ? 'That didn’t go through.' : 'One moment.'}
        sub={state.kind === 'working' ? 'Checking your recording and saving it.' : undefined} />
      <Card tint={state.kind === 'ok'}>
        <div className="stack-12 center" style={{ alignItems: 'center', padding: '18px 0' }}>
          {state.kind === 'working' && (
            <>
              <span className="ring" aria-hidden="true" />
              <span className="t-copy-lg-m c-ink" role="status">Checking your recording…</span>
            </>
          )}
          {state.kind === 'ok' && <CheckSeal label={`Looks good — saved for ${therapist}`} />}
          {state.kind === 'failed' && (
            <>
              <span className="c-risk-med"><Sym name="video.slash" size={34} weight="regular" /></span>
              <span className="t-copy-lg-m c-ink" role="status">The clip didn’t upload</span>
              <span className="t-copy secondary">{state.message}</span>
            </>
          )}
        </div>
      </Card>
    </TaskScreen>
  )
}

// MARK: - 7. How did it go?

function PainStage({ a, strip, onLeave, send, onSent }: {
  a: ExerciseAssignment; strip: ReactNode; onLeave: () => void
  send: (painAfter: number | null, effort: number | null, note: string) => Promise<ExerciseAssignment>
  onSent: (updated: ExerciseAssignment) => void
}) {
  const [pain, setPain] = useState<AnswerValue | null>(null)
  const [effort, setEffort] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const therapist = therapistShortName(a.assignedByName)

  const submit = async () => {
    setSending(true)
    setError(null)
    try {
      onSent(await send(typeof pain === 'number' ? pain : null, effort, note.trim()))
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setSending(false)
    }
  }

  return (
    <TaskScreen title={stageTitles.pain} onLeave={onLeave} strip={strip} gap={24}
      bottom={<>{error && <ErrorBanner text={error} />}<PrimaryButton title={`Send to ${therapist}`} loading={sending} onClick={() => void submit()} /></>}>
      <Heading pill={a.title} title="Nice work. How’s the pain now?" sub={`${therapist} sees your answers with the rest of your week.`} />
      <ScaleAnswer value={pain} painting onChange={setPain} />
      <div className="stack-10">
        <span className="t-copy-lg-m c-ink">How hard was it?</span>
        {a.rpeTarget != null && (
          <span className="t-label c-muted">{therapist} suggested around {a.rpeTarget}{DOT}{effortWord(a.rpeTarget).toLowerCase()}.</span>
        )}
        <EffortScale value={effort} onChange={setEffort} />
      </div>
      <div className="stack-10">
        <span className="t-copy-lg-m c-ink">Anything to add?</span>
        <textarea className="field" rows={3} placeholder="Optional — how it felt, what was hard" aria-label="A note for your therapist"
          value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
    </TaskScreen>
  )
}

// MARK: - 8. Done

function DoneStage({ a, startedAt, endedAt, onHome }: { a: ExerciseAssignment; startedAt: Date | null; endedAt: Date | null; onHome: () => void }) {
  const therapist = therapistShortName(a.assignedByName)
  const c = a.completion
  const seconds = startedAt && endedAt ? Math.max(0, Math.round((endedAt.getTime() - startedAt.getTime()) / 1000)) : null
  const line = [`Sent to ${therapist}`, painLabel(c?.painAfter), effortLabel(c?.effort), seconds != null ? clock(seconds) : null]
    .filter((s): s is string => !!s).join(DOT)
  return (
    <Screen nav={(s) => <NavBar title={stageTitles.done} scrolled={s} />}
      bottom={<div className="sheet-controls above-tabbar"><PrimaryButton title="Back to Today" onClick={onHome} /></div>}>
      <div className="content" style={{ gap: 18, padding: '6px 20px 28px' }}>
        <div className="stack-12 center fade-in" style={{ alignItems: 'center', padding: '28px 0 8px' }} role="status">
          <div className="seal" aria-hidden="true"><Sym name="checkmark" size={34} weight="semibold" /></div>
          <h1 className="t-display-s c-ink" style={{ margin: 0 }}>That’s one done.</h1>
          <span className="t-copy-lg c-body">{line}</span>
        </div>
        <OutcomeCard a={a} fresh />
      </div>
    </Screen>
  )
}

// MARK: - Clocks

/** "4:12" from seconds. */
function clock(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

/** The time, re-read twice a second while `active`, so a clock drawn from
 *  it moves. The first tick is half a second away; the clocks clamp at
 *  zero until then. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const t = window.setInterval(() => setNow(Date.now()), 500)
    return () => window.clearInterval(t)
  }, [active])
  return now
}
