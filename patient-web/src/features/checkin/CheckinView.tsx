/* The daily check-in, as its own flow rather than one long form: one thing
   at a time, says how much is left, and never blocks on an answer — every
   question can be passed over (Features/Checkin/CheckinView.swift).
   Answers are the same `{id: value}` the generic form sends. */

import { useEffect, useState } from 'react'
import { messageFor, useApp } from '../../core/appModel'
import { typeset, type AnswerValue, type Answers, type Question, type RecoveryTask } from '../../core/models'
import { Card, cx, ErrorBanner, InsetDivider, MPButton, NavBar, PrimaryButton, Screen } from '../../ui/components'
import { Sym } from '../../ui/icons'

export const choiceLabels: Record<string, string> = {
  yes: 'Yes', no: 'No', well: 'Well', rough: 'Rough night',
  all: 'All of them', some: 'Some', none: 'Not today',
}

export const Pain = {
  /** The words a patient would use, not a clinical scale's labels. */
  word(n: number): string {
    if (n === 0) return 'No pain'
    if (n <= 3) return 'Mild'
    if (n <= 6) return 'Moderate'
    if (n <= 8) return 'Bad'
    return 'Severe'
  },
}

export function CheckinView({ task, onDone, back }: {
  task: RecoveryTask
  onDone: () => void
  back: { label: string; onClick: () => void }
}) {
  const app = useApp()
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<Answers>({})
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  const questions = task.questions
  const isReview = step >= questions.length
  const current = isReview ? null : questions[step]
  const answered = Object.keys(answers).length

  const setAnswer = (id: string, value: AnswerValue | null) => {
    setAnswers((a) => {
      const next = { ...a }
      if (value == null) delete next[id]
      else next[id] = value
      return next
    })
  }

  const submit = async () => {
    setSending(true)
    setError(null)
    try {
      if (answered === 0) await app.skip(task)
      else await app.complete(task, answers)
      setDone(true)
      setTimeout(onDone, 1400)
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setSending(false)
    }
  }

  const sendTitle = answered === 0 ? 'Send nothing for now' : 'Send to my care team'

  if (done) {
    return (
      <Screen nav={(s) => <NavBar title="Daily check-in" scrolled={s} back={back} />} withTabBar>
        <CheckinDone />
      </Screen>
    )
  }

  return (
    <Screen
      nav={(s) => <NavBar title="Daily check-in" scrolled={s} back={back} />}
      withTabBar
      bottom={
        <div className="checkin-controls" style={{ paddingBottom: 'calc(8px + var(--tabbar-h) + var(--safe-bottom))' }}>
          {error && <ErrorBanner text={error} />}
          <PrimaryButton title={isReview ? sendTitle : 'Next'} loading={sending}
            onClick={() => { if (isReview) void submit(); else setStep((s) => s + 1) }} />
          <div className="hstack" style={{ minHeight: 44 }}>
            {step > 0 && (
              <MPButton kind="plain" onClick={() => setStep((s) => s - 1)}>
                <Sym name="chevron.left" size={14} weight="semibold" /> Back
              </MPButton>
            )}
            <span className="spacer" />
            {!isReview && current && (
              <MPButton kind="plain" onClick={() => { setAnswer(current.id, null); setStep((s) => s + 1) }}>
                {answers[current.id] == null ? 'Skip this one' : 'Clear'}
              </MPButton>
            )}
          </div>
        </div>
      }
    >
      <div className="stack-8" style={{ padding: '8px 20px 14px' }}>
        <span className="t-copy-m c-muted figures">{isReview ? 'Review' : `Question ${step + 1} of ${questions.length}`}</span>
        <div className="dots" aria-hidden="true">
          {questions.map((q, i) => <i key={q.id} className={i <= step || isReview ? 'on' : ''} />)}
        </div>
      </div>
      {current ? (
        <div key={current.id} className="fade-in stack-18" style={{ padding: '4px 20px 24px', minHeight: '46vh', justifyContent: 'center' }}>
          <h1 className="t-display-s c-ink" style={{ margin: 0 }}>{typeset(current.prompt)}</h1>
          <QuestionInput q={current} value={answers[current.id] ?? null} onChange={(v) => setAnswer(current.id, v)} />
        </div>
      ) : (
        <div className="fade-in stack-14" style={{ padding: '4px 20px 24px' }}>
          <h1 className="t-display-s c-ink" style={{ margin: 0 }}>
            {answered === 0 ? 'Nothing answered yet' : 'Here’s what goes to your care team'}
          </h1>
          {answered === 0 && <span className="t-copy c-muted">Tap any question to answer it, or send nothing and do it later.</span>}
          <Card padding={0}>
            {questions.map((q, i) => (
              <div key={q.id}>
                <button type="button" className="row-button" onClick={() => setStep(i)} aria-label={`Edit ${q.prompt}`}>
                  <div className="hstack-top" style={{ padding: '12px 16px' }}>
                    <div className="stack-3 grow">
                      <span className="t-copy c-muted">{typeset(q.prompt)}</span>
                      <span className={cx('t-copy-lg-m', answers[q.id] == null ? 'c-muted' : 'c-ink')}>{spoken(q, answers[q.id])}</span>
                    </div>
                    <span className="c-brand-ink"><Sym name="pencil" size={15} weight="medium" /></span>
                  </div>
                </button>
                {i < questions.length - 1 && <InsetDivider leading={16} />}
              </div>
            ))}
          </Card>
        </div>
      )}
    </Screen>
  )
}

/** The answer in the patient's own words, matching the transcript. */
function spoken(q: Question, value: AnswerValue | undefined): string {
  if (value == null) return 'Not answered'
  if (typeof value === 'number') return q.id === 'pain' ? `${value} out of 10 — ${Pain.word(value)}` : String(value)
  return choiceLabels[value] ?? value
}

function QuestionInput({ q, value, onChange }: { q: Question; value: AnswerValue | null; onChange: (v: AnswerValue | null) => void }) {
  switch (q.kind) {
    case 'scale':
      return <ScaleAnswer value={value} painting={q.id === 'pain'} onChange={onChange} />
    case 'yes_no':
    case 'choice':
      return <ChoiceAnswer options={q.options ?? ['yes', 'no']} value={value} onChange={onChange} />
    case 'number':
      return (
        <input className="field" inputMode="numeric" pattern="[0-9]*" placeholder={q.id === 'minutes' ? 'Minutes' : 'Number'}
          value={typeof value === 'number' ? String(value) : ''} aria-label={q.prompt}
          onChange={(e) => { const n = parseInt(e.target.value, 10); onChange(Number.isFinite(n) ? n : null) }} />
      )
    default:
      return (
        <textarea className="field" rows={4} placeholder="Optional — anything at all" aria-label={q.prompt}
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value.trim() ? e.target.value : null)} />
      )
  }
}

/** 0 to 10 on a slider rather than eleven chips: one gesture, and the
 *  number and the word under the thumb say what was chosen. */
export function ScaleAnswer({ value, painting, onChange }: {
  value: AnswerValue | null; painting: boolean; onChange: (v: AnswerValue | null) => void
}) {
  const number = typeof value === 'number' ? value : 0
  const riskInk = painting ? (number <= 3 ? 'risk-low' : number <= 6 ? 'risk-med' : 'risk-high') : null
  const tint = value == null ? 'track' : (riskInk ?? 'brand')
  const readoutInk = riskInk ?? 'brand-ink'
  return (
    <div className="stack-14">
      <div style={{ minHeight: 84, display: 'grid', placeItems: 'center' }}>
        {value == null ? (
          <span className="t-copy-lg-m c-muted">Drag to answer</span>
        ) : (
          <div className="stack center">
            <span className="t-display-xl figures" style={{ color: `rgb(var(--${readoutInk}))` }}>{number}</span>
            <span className="t-copy-m c-muted">{painting ? Pain.word(number) : 'out of 10'}</span>
          </div>
        )}
      </div>
      <input
        type="range" min={0} max={10} step={1} className="slider"
        value={number}
        style={{ ['--pct' as string]: `${(number / 10) * 100}%`, ['--tint' as string]: `var(--${tint})` }}
        onChange={(e) => onChange(Number(e.target.value))}
        onPointerDown={() => { if (value == null) onChange(0) }}
        aria-valuetext={value == null ? 'Not answered' : painting ? `${number}, ${Pain.word(number)}` : String(number)}
      />
      <div className="hstack">
        <span className="t-label c-muted">{painting ? 'No pain' : '0'}</span>
        <span className="spacer" />
        <span className="t-label c-muted">{painting ? 'Worst imaginable' : '10'}</span>
      </div>
    </div>
  )
}

/** Yes/no and the named choices, as full-width rows. */
function ChoiceAnswer({ options, value, onChange }: { options: string[]; value: AnswerValue | null; onChange: (v: AnswerValue | null) => void }) {
  return (
    <div className="stack-10">
      {options.map((opt) => {
        const selected = value === opt
        return (
          <button key={opt} type="button" className="choice-row" aria-pressed={selected}
            onClick={() => onChange(selected ? null : opt)}>
            <span className="mark"><Sym name={selected ? 'checkmark.circle.fill' : 'circle'} size={20} weight="regular" /></span>
            <span>{choiceLabels[opt] ?? opt.charAt(0).toUpperCase() + opt.slice(1)}</span>
          </button>
        )
      })}
    </div>
  )
}

function CheckinDone() {
  const [shown, setShown] = useState(false)
  useEffect(() => { const t = setTimeout(() => setShown(true), 150); return () => clearTimeout(t) }, [])
  return (
    <div className="stack-14 center fade-in" style={{ padding: '18vh 32px 0', alignItems: 'center' }} role="status">
      <div className="seal" style={{ opacity: shown ? 1 : 0 }} aria-hidden="true">
        <Sym name="checkmark" size={34} weight="semibold" />
      </div>
      <h1 className="t-display-s c-ink" style={{ margin: '8px 0 0' }}>Sent to your care team</h1>
      <span className="t-copy-lg c-muted">That’s today done. They’ll see it with their next review.</span>
    </div>
  )
}
