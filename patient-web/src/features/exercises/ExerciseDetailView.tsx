/* One exercise on the schedule (route `/today/exercises/:id`): the
   therapist's clip to follow, the steps, what to take care of, the dose and
   her note, then **Start** — the session screen — with "Just mark it done"
   under it for an exercise done away from the phone, and "Can't do it
   today" with a reason. Done, it shows what went back — pain, effort, how
   long — and what the therapist said about it (docs/dev/hep-schedule.md,
   "Patient web UI" and "Second pass"). */

import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { messageFor, useApp, type AppModel } from '../../core/appModel'
import {
  awaitingReview, Dates, doneLine, DOT, durationLabel, effortWord, isOpenAssignment, loadLabel, sessionSeconds,
  therapistShortName, typeset, videoRequirement, wearableRequirement,
  type ExerciseAssignment, type ExerciseReview, type Requirement,
} from '../../core/models'
import {
  Card, Chip, CloseButton, EmptyRow, ErrorBanner, Initials, InsetDivider, MPButton, NavBar, PrimaryButton, Screen,
  Sheet, Spinner,
} from '../../ui/components'
import { Sym } from '../../ui/icons'
import { CardTitleRow, Glyph } from '../../ui/rows'
import { useBack } from '../../ui/useBack'
import { teamInitials } from '../today/TodayView'
import { CompletionSheet } from './CompletionSheet'

/** Where an exercise opens. The row comes from today's feed; a link to one
 *  that is not on it asks the server once, then says so. */
export function ExerciseDestination() {
  const { id } = useParams()
  const location = useLocation()
  const back = useBack('/today')
  const from = (location.state as { from?: string } | null)?.from ?? 'Today'
  const { a, waited } = useAssignment(id)
  const backItem = { label: from, onClick: back }
  if (!a) return <MissingExercise back={backItem} waited={waited} />
  return <ExerciseDetailView a={a} back={backItem} />
}

/** The row behind an id, from wherever this app holds it: today's list,
 *  the still-to-do group, the program's days. The schedule keeps polling
 *  on the screen too — the therapist may log it done from the room while
 *  the person reads it. A row in none of them is asked for once; `waited`
 *  says the asking is over. */
export function useAssignment(id: string | undefined): { a: ExerciseAssignment | null; waited: boolean } {
  const app = useApp()
  const a = findAssignment(app, id)
  const [waited, setWaited] = useState(false)
  useEffect(() => app.watchExercises(), [app])
  useEffect(() => {
    if (a) return
    let cancelled = false
    const asks = [app.refreshExercises(undefined, false)]
    if (!app.program) asks.push(app.refreshProgram(false))
    void Promise.all(asks).then(() => { if (!cancelled) setWaited(true) })
    return () => { cancelled = true }
  }, [app, a])
  return { a, waited }
}

function findAssignment(app: AppModel, id: string | undefined): ExerciseAssignment | null {
  if (!id) return null
  const n = Number(id)
  const feed = app.exercises
  const pools = [feed?.items ?? [], feed?.overdue ?? [], ...(app.program?.days.map((d) => d.items) ?? [])]
  for (const pool of pools) {
    const hit = pool.find((x) => x.id === n)
    if (hit) return hit
  }
  return null
}

/** The screen while a row is looked for, and once it was not found. */
export function MissingExercise({ back, waited, title = 'Exercise' }: {
  back: { label: string; onClick: () => void }; waited: boolean; title?: string
}) {
  return (
    <Screen withTabBar nav={(s) => <NavBar title={title} scrolled={s} back={back} />}>
      <div className="content">
        {waited
          ? <Card padding={0}><EmptyRow icon="figure.strengthtraining.traditional" title="That exercise isn’t on your list" detail="It may have been moved to another day or taken off by your therapist." /></Card>
          : <div className="hstack" style={{ justifyContent: 'center', color: 'rgb(var(--brand))', padding: 32 }}><Spinner /></div>}
      </div>
    </Screen>
  )
}

export function ExerciseDetailView({ a, back }: { a: ExerciseAssignment; back: { label: string; onClick: () => void } }) {
  const navigate = useNavigate()
  const [marking, setMarking] = useState(false)
  const [skipping, setSkipping] = useState(false)
  const [justSent, setJustSent] = useState(false)
  const open = isOpenAssignment(a)
  const therapist = therapistShortName(a.assignedByName)
  const isToday = a.scheduledFor === Dates.dayString(new Date())
  const clipAsk = videoRequirement(a)
  const watchAsk = wearableRequirement(a)
  const start = () => navigate(`/today/exercises/${a.id}/session`, { state: { from: 'Exercise' } })

  return (
    <>
      <Screen
        withTabBar
        nav={(s) => <NavBar title="Exercise" scrolled={s} back={back} />}
        bottom={open ? (
          <div className="action-bar stacked" role="toolbar">
            <div className="action-row">
              <button type="button" className="btn-text" onClick={() => setSkipping(true)}>Can’t do it today</button>
              <span className="spacer" />
              <MPButton kind="filled" size="large" onClick={start} ariaLabel="Start">
                <Sym name="play.fill" size={16} weight="semibold" />
                <span>Start</span>
              </MPButton>
            </div>
            <div className="action-sub">
              <button type="button" className="btn-text" onClick={() => setMarking(true)}>Just mark it done</button>
            </div>
          </div>
        ) : undefined}
      >
        <div className="content" style={{ gap: 20, padding: `12px 20px ${open ? 160 : 40}px` }}>
          <div className="stack-8">
            <div className="ask-pills">
              <span className="schedule-pill">{isToday ? 'Today' : Dates.monthDay(a.scheduledFor)}</span>
              {clipAsk === 'required' && (
                <span className="schedule-pill"><Sym name="video.fill" size={11} weight="medium" />Clip asked for</span>
              )}
              {watchAsk === 'required' && (
                <span className="schedule-pill"><Sym name="applewatch" size={11} weight="medium" />Watch on</span>
              )}
            </div>
            <h1 className="t-display-s c-ink" style={{ margin: 0 }}>{typeset(a.title)}</h1>
            <span className="t-copy-lg c-body">{a.dose}</span>
            {a.rpeTarget != null && (
              <span className="t-copy c-muted">Aim for effort {a.rpeTarget}/10{DOT}{effortWord(a.rpeTarget).toLowerCase()}</span>
            )}
            {a.assignedByName && <span className="t-copy c-muted">From {a.assignedByName}</span>}
          </div>

          {!open && <OutcomeCard a={a} fresh={justSent} />}
          {open && a.session?.startedAt && (
            <span className="t-label c-muted px-4">
              You started this {Dates.relative(a.session.startedAt)}. Start again and the clock begins afresh.
            </span>
          )}

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
            {a.loadKg != null && <><InsetDivider leading={16} /><Fact label="Load" value={loadLabel(a.loadKg) ?? ''} /></>}
            {a.rpeTarget != null && <><InsetDivider leading={16} /><Fact label="Effort to aim for" value={`${a.rpeTarget}/10${DOT}${effortWord(a.rpeTarget).toLowerCase()}`} /></>}
            <InsetDivider leading={16} />
            <Fact label="Equipment" value={a.equipment || 'None needed'} />
            {clipAsk !== 'off' && <><InsetDivider leading={16} /><Fact label="A clip of you doing it" value={askWords(clipAsk)} /></>}
            {watchAsk !== 'off' && <><InsetDivider leading={16} /><Fact label="Your watch on" value={askWords(watchAsk)} /></>}
          </Card>
        </div>
      </Screen>

      <Sheet open={marking} onClose={() => setMarking(false)}>
        <CompletionSheet a={a} session={null} onClose={() => setMarking(false)} onSent={() => { setMarking(false); setJustSent(true) }} />
      </Sheet>
      <Sheet open={skipping} onClose={() => setSkipping(false)}>
        <SkipSheet a={a} onClose={() => setSkipping(false)} onSkipped={() => setSkipping(false)} />
      </Sheet>
    </>
  )
}

/** "Asked for" or "If you like", for a facts row. */
function askWords(r: Requirement): string {
  return r === 'required' ? 'Asked for' : 'If you like'
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

/** A figure and its word, for the done card's row of three. */
function Stat({ value, label }: { value: string; label: string }) {
  return <div className="stat"><b className="figures">{value}</b><span>{label}</span></div>
}

// MARK: - What came back

/** Done: "Sent to Dr. Gregg", the pain (before → after when both are
 *  known), the effort and how long it ran side by side, what was done, the
 *  note, the clip that went with it, and the therapist's reply once she
 *  has looked. Skipped: the reason. */
export function OutcomeCard({ a, fresh }: { a: ExerciseAssignment; fresh: boolean }) {
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
  const s = a.session ?? null
  const byTherapist = c?.source === 'console'
  const review = c?.review ?? null
  const seconds = sessionSeconds(a)
  const painBefore = s?.painBefore ?? null
  const painAfter = c?.painAfter ?? null
  const painValue = painAfter == null ? '—' : painBefore != null ? `${painBefore} → ${painAfter}` : String(painAfter)
  const effort = c?.effort ?? null
  const facts: string[] = []
  const did = doneLine(a)
  if (did) facts.push(did)
  if (s?.wearableWorn) facts.push('watch on')
  if (s?.hrAvg != null) facts.push(`heart rate ${s.hrAvg} avg${s.hrMax != null ? `, ${s.hrMax} max` : ''}`)
  const when = c?.completedAt ? Dates.relative(c.completedAt) : ''
  const sub = review || byTherapist ? when : `${when}${when ? DOT : ''}They’ll see it with their next review.`
  return (
    <Card tint className={fresh ? 'fade-in' : undefined}>
      <div className="stack-12">
        <div className="hstack-top">
          <span className="c-risk-low" style={{ paddingTop: 1 }}><Sym name="checkmark.seal.fill" size={24} weight="semibold" /></span>
          <div className="stack-3 grow">
            <span className="t-copy-lg-m c-ink">{byTherapist ? `Logged by ${therapist}` : `Sent to ${therapist}`}</span>
            {sub && <span className="t-copy secondary">{sub}</span>}
          </div>
        </div>
        <div className="outcome-stats">
          <Stat value={painValue} label={painBefore != null ? 'pain, before → after' : 'pain, out of 10'} />
          {effort != null && <Stat value={String(effort)} label={`effort${DOT}${effortWord(effort).toLowerCase()}`} />}
          {seconds != null && seconds > 0 && <Stat value={durationLabel(seconds) ?? ''} label="on the clock" />}
        </div>
        {facts.length > 0 && <span className="t-label secondary">{facts.join(DOT)}</span>}
        {c?.note && <span className="t-copy c-ink lh-2">“{typeset(c.note)}”</span>}
        {c?.video && !c.video.withdrawn && (
          <ClipPlayer url={c.video.url ?? null} attachmentId={c.video.id} poster={null} label="Your clip" />
        )}
        {review ? (
          <ReviewBox review={review} fallbackName={a.assignedByName} />
        ) : awaitingReview(a) ? (
          <span className="t-label secondary">{therapist} hasn’t looked at your clip yet.</span>
        ) : null}
      </div>
    </Card>
  )
}

/** What the therapist said about it, in her words, under her initials.
 *  The same note reaches the Care thread. */
function ReviewBox({ review, fallbackName }: { review: ExerciseReview; fallbackName: string }) {
  const name = review.byName || fallbackName
  return (
    <div className="review-box">
      <Initials text={teamInitials(name)} size={30} tone="low" style="soft" />
      <div className="stack-3 grow">
        <span className="t-label-m c-ink">
          {therapistShortName(name)}
          {review.at && <span className="c-muted">{DOT}{Dates.relative(review.at)}</span>}
        </span>
        {review.note
          ? <span className="t-copy c-ink lh-2">{typeset(review.note)}</span>
          : <span className="t-copy secondary">Has seen it. Nothing to change.</span>}
      </div>
    </div>
  )
}

// MARK: - The clip

/** A clip in the hero's frame. A presigned link plays as it is; a link
 *  into this API (no object store) is fetched under the session first.
 *  `loop` is the session's way: playing on its own, muted, round and
 *  round, with nothing to tap. */
export function ClipPlayer({ url, poster, label, attachmentId, loop = false }: {
  url: string | null; poster: string | null; label: string; attachmentId?: number; loop?: boolean
}) {
  const { src, loading, failed } = useClipURL(url, attachmentId)
  return (
    <div className="clip-box">
      {src && (loop
        ? <video src={src} autoPlay muted loop playsInline preload="auto" poster={poster ?? undefined} aria-label={label} />
        : <video src={src} controls playsInline preload="metadata" poster={poster ?? undefined} aria-label={label} />)}
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
