/* Every task, open and done (pushed from Today's "All tasks"), and the
   generic task form. The daily check-in gets its own one-question-at-a-time
   flow; every other kind uses the form here. Both post the same answers to
   the same endpoint (Features/Tasks/TasksView.swift). */

import { useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { messageFor, useApp } from '../../core/appModel'
import { isOpenTask, scheduleLabel, typeset, type AnswerValue, type Answers, type Question, type RecoveryTask } from '../../core/models'
import { Card, Chip, cx, EmptyRow, ErrorBanner, MPButton, NavBar, Screen, Spinner } from '../../ui/components'
import { Sym } from '../../ui/icons'
import { CardTitleRow, RowDivider } from '../../ui/rows'
import { useBack } from '../../ui/useBack'
import { CheckinView, ScaleAnswer, choiceLabels } from '../checkin/CheckinView'
import { PlanRow, TaskRowButton } from '../today/TodayView'

/** Every task, open and done. Today owns the day; this is the record. */
export function TaskHistoryView() {
  const app = useApp()
  const navigate = useNavigate()
  const back = useBack('/today')
  const [quickError, setQuickError] = useState<string | null>(null)
  const nothingAtAll = app.tasks.open.length === 0 && app.tasks.recent.length === 0

  useEffect(() => { void app.refreshTasks() }, [app])

  const markDone = async (t: RecoveryTask) => {
    setQuickError(null)
    try { await app.complete(t, {}) } catch (e) { setQuickError(messageFor(e)) }
  }

  const section = (title: string, tasks: RecoveryTask[]) => (
    <Card padding={0}>
      <CardTitleRow title={title} />
      {tasks.map((t, i) => (
        <div key={t.id}>
          {isOpenTask(t)
            ? <TaskRowButton task={t} onOpen={() => navigate(`/today/tasks/${t.id}`, { state: { from: 'Tasks' } })} onMarkDone={() => void markDone(t)} />
            : <PlanRow task={t} />}
          {i < tasks.length - 1 && <RowDivider />}
        </div>
      ))}
      <div style={{ height: 4 }} />
    </Card>
  )

  return (
    <Screen fogHeight={300} withTabBar nav={(s) => <NavBar title="Tasks" scrolled={s} back={{ label: 'Today', onClick: back }} />}>
      <div className="content" style={{ gap: 20, paddingTop: 4 }}>
        {quickError && <ErrorBanner text={quickError} />}
        {app.tasks.open.length === 0 ? (
          <div className="empty-row" style={{ padding: `${nothingAtAll ? 72 : 8}px 16px` }}>
            <span className="c-risk-low"><Sym name="checkmark.circle" size={44} weight="regular" /></span>
            <span className="t-subhead-sb c-ink">You’re all caught up</span>
            <span className="t-copy c-muted">New tasks from your care team show up here.</span>
          </div>
        ) : section('To do', app.tasks.open)}
        {app.tasks.recent.length > 0 && section('Done', app.tasks.recent)}
      </div>
    </Screen>
  )
}

/** Where a task opens (route `/today/tasks/:id`). */
export function TaskDestination() {
  const app = useApp()
  const { id } = useParams()
  const location = useLocation()
  const back = useBack('/today')
  const from = (location.state as { from?: string } | null)?.from ?? 'Today'
  const task = [...app.tasks.open, ...app.tasks.recent].find((t) => String(t.id) === id) ?? null
  const [waited, setWaited] = useState(false)
  useEffect(() => {
    if (task) return
    void app.refreshTasks(false).then(() => setWaited(true))
  }, [app, task])
  const backItem = { label: from, onClick: back }
  if (!task) {
    return (
      <Screen withTabBar nav={(s) => <NavBar title="Task" scrolled={s} back={backItem} />}>
        <div className="content">
          {waited ? <Card padding={0}><EmptyRow icon="checklist" title="That task isn’t here any more" detail="It may have been completed or taken back by your care team." /></Card>
            : <div className="hstack" style={{ justifyContent: 'center', color: 'rgb(var(--brand))', padding: 32 }}><Spinner /></div>}
        </div>
      </Screen>
    )
  }
  if (task.kind === 'checkin') return <CheckinView task={task} back={backItem} onDone={back} />
  return <TaskDetailView task={task} back={backItem} onDone={back} />
}

export function TaskDetailView({ task, back, onDone }: {
  task: RecoveryTask; back: { label: string; onClick: () => void }; onDone: () => void
}) {
  const app = useApp()
  const [answers, setAnswers] = useState<Answers>({})
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const answered = Object.keys(answers).length > 0

  const setAnswer = (id: string, v: AnswerValue | null) => setAnswers((a) => {
    const next = { ...a }
    if (v == null) delete next[id]
    else next[id] = v
    return next
  })

  const submit = async () => {
    setSending(true)
    setError(null)
    try {
      await app.complete(task, answers)
      setDone(true)
      setTimeout(onDone, 1200)
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setSending(false)
    }
  }
  const skip = async () => {
    try { await app.skip(task); onDone() } catch (e) { setError(messageFor(e)) }
  }

  const shown = task.kind === 'checkin' ? 'Send' : 'Mark done'
  const spokenLabel = task.kind === 'checkin' ? 'Send to my care team' : 'Mark done'
  const schedule = scheduleLabel(task)

  return (
    <Screen
      withTabBar
      nav={(s) => <NavBar title={task.kindLabel} scrolled={s} back={back} />}
      bottom={!done ? (
        <div className="action-bar" role="toolbar">
          <button type="button" className="btn-text" onClick={() => void skip()} disabled={sending}>Skip this one</button>
          <span className="spacer" />
          <MPButton kind="filled" size="large" disabled={sending || (task.kind === 'checkin' && !answered)}
            onClick={() => void submit()} ariaLabel={spokenLabel}>
            {sending ? <Spinner /> : <Sym name="checkmark" size={16} weight="semibold" />}
            <span>{shown}</span>
          </MPButton>
        </div>
      ) : undefined}
    >
      <div className="content" style={{ gap: 20, padding: '12px 20px 120px' }}>
        <div className="stack-8">
          {schedule && <span className="schedule-pill" style={{ alignSelf: 'flex-start' }}>{schedule}</span>}
          <h1 className="t-display-s c-ink" style={{ margin: 0 }}>{typeset(task.title)}</h1>
          {task.why && <span className="t-copy c-muted">{task.why}</span>}
          {task.inSmsConversation && <ErrorBanner text="You started this one by text. Finishing it here is fine — the text thread will close." />}
        </div>
        {done ? (
          <Card tint className="fade-in">
            <div className="hstack">
              <span className="c-risk-low"><Sym name="checkmark.seal.fill" size={24} weight="semibold" /></span>
              <div className="stack-2">
                <span className="t-copy-lg-m c-ink">Sent to your care team</span>
                <span className="t-copy secondary">They’ll see it with their next review.</span>
              </div>
            </div>
          </Card>
        ) : (
          <>
            {task.questions.map((q) => (
              <QuestionView key={q.id} question={q} value={answers[q.id] ?? null} onChange={(v) => setAnswer(q.id, v)} />
            ))}
            {error && <ErrorBanner text={error} />}
          </>
        )}
      </div>
    </Screen>
  )
}

/** One question, rendered by kind — the same chips as the web check-in. */
export function QuestionView({ question, value, onChange }: { question: Question; value: AnswerValue | null; onChange: (v: AnswerValue | null) => void }) {
  let input
  switch (question.kind) {
    case 'scale':
      input = <ScaleAnswer value={value} painting={question.id === 'pain'} onChange={onChange} />
      break
    case 'yes_no':
    case 'choice':
      input = <FlowChips options={question.options ?? ['yes', 'no']} labels={choiceLabels} value={value} onChange={onChange} />
      break
    case 'number': {
      const label = question.id === 'minutes' ? 'Minutes' : 'Number'
      input = (
        <input className="field" inputMode="numeric" pattern="[0-9]*" placeholder={label} aria-label={question.prompt}
          value={typeof value === 'number' ? String(value) : ''}
          onChange={(e) => { const n = parseInt(e.target.value, 10); onChange(Number.isFinite(n) ? n : null) }} />
      )
      break
    }
    default:
      input = (
        <textarea className="field" rows={3} placeholder="Optional" aria-label={question.prompt}
          value={typeof value === 'string' ? value : ''} onChange={(e) => onChange(e.target.value ? e.target.value : null)} />
      )
  }
  return (
    <div className="stack-10">
      <span className="t-copy-lg-m c-ink">{question.prompt}</span>
      {input}
    </div>
  )
}

export function FlowChips({ options, labels, value, onChange }: {
  options: string[]; labels: Record<string, string>; value: AnswerValue | null; onChange: (v: AnswerValue | null) => void
}) {
  return (
    <div className={cx('chip-row')}>
      {options.map((opt) => (
        <Chip key={opt} label={labels[opt] ?? opt.charAt(0).toUpperCase() + opt.slice(1)} selected={value === opt}
          onClick={() => onChange(value === opt ? null : opt)} />
      ))}
    </div>
  )
}
