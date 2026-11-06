/* A hospital patient's day, in the order they ask about it: how am I doing
   (the recovery hero), what do I do now (the plan, with its one primary
   action), is a measurement due, and has my care team said anything. Each
   row opens the tab that owns it (Features/Today/TodayView.swift). */

import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { messageFor, useApp } from '../../core/appModel'
import {
  Dates, DOT, isOpenTask, isRecovery, scheduleLabel, toneForLevel, typeset,
  type CareTeamMember, type Me, type RecoveryTask,
} from '../../core/models'
import {
  Card, CardButton, cx, EmptyRow, ErrorBanner, GradientTile, Initials, InsetDivider, Menu, NavBar,
  PrimaryButton, Rise, Screen, Sheet, StatusPill, useGone, type Category,
} from '../../ui/components'
import { Sym } from '../../ui/icons'
import { CardTitleRow, Chevron, Glyph, ListRow, RowDivider, StateLabel } from '../../ui/rows'
import { RecoveryCurveArt } from '../../ui/tileArt'
import { flowTitle, measureFlows, measureStatus } from '../progress/progressModel'
import { ProfileView } from '../profile/ProfileView'

export function TodayView() {
  const app = useApp()
  const navigate = useNavigate()
  const [showProfile, setShowProfile] = useState(false)
  const [showDone, setShowDone] = useState(false)
  const [quickError, setQuickError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const headerRef = useRef<HTMLDivElement | null>(null)
  const greetingGone = useGone(headerRef, scrollRef)

  const me = app.me
  const hour = new Date().getHours()
  const part = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const checkin = app.tasks.open.find((t) => t.kind === 'checkin') ?? null
  const otherOpen = app.tasks.open.filter((t) => t.id !== checkin?.id)
  const doneToday = app.tasks.recent.filter((t) => {
    const at = Dates.parse(t.completedAt)
    return at ? Dates.isToday(at) : false
  })

  const openTask = useCallback((t: RecoveryTask) => navigate(`/today/tasks/${t.id}`, { state: { from: 'Today' } }), [navigate])

  // A `medpull://tasks/<id>` link or a thread button: open it once it is here.
  useEffect(() => {
    const id = app.pendingTaskId
    if (id == null) return
    const task = [...app.tasks.open, ...app.tasks.recent].find((t) => t.id === id)
    if (!task) return
    app.setPendingTaskId(null)
    openTask(task)
  }, [app, app.pendingTaskId, app.tasks, openTask])

  const markDone = async (t: RecoveryTask) => {
    setQuickError(null)
    try { await app.complete(t, {}) } catch (e) { setQuickError(messageFor(e)) }
  }

  const open = app.tasks.open
  const done = doneToday

  return (
    <>
      <Screen
        scrollRef={scrollRef}
        withTabBar
        nav={(scrolled) => (
          <NavBar
            title="Today"
            titleHidden={!greetingGone}
            scrolled={scrolled && greetingGone}
            leading={<BrandLockup hidden={greetingGone} />}
            trailing={<AvatarItem initials={me?.patient.initials ?? '··'} onClick={() => setShowProfile(true)} />}
          />
        )}
      >
        <div className="content">
          <Rise index={0}>
            <div ref={headerRef} className="stack-6" style={{ paddingTop: 6 }}>
              <h1 className="t-display-m c-ink" style={{ margin: 0, whiteSpace: 'pre-line' }}>
                {`${part},\n${me?.patient.firstName ?? 'there'}.`}
              </h1>
              {me && (
                <span className="t-copy-lg c-body">
                  {isRecovery(me.patient)
                    ? `Day ${me.patient.postopDay ?? 0}${DOT}${me.patient.procedureDisplay}`
                    : `${me.patient.hospital?.name ?? 'Your hospital'}${DOT}${me.patient.daysEnrolled === 0 ? 'joined today' : `${me.patient.daysEnrolled} days in`}`}
                </span>
              )}
            </div>
          </Rise>
          {me && <Rise index={1}><RecoveryHero me={me} onClick={() => navigate('/progress')} /></Rise>}

          <Rise index={2} id="plan">
            <Card padding={0}>
              <CardTitleRow
                title="Today’s plan"
                note={open.length === 0 && done.length === 0 ? null : `${done.length} of ${open.length + done.length} done`}
                actionTitle="All tasks"
                onAction={() => navigate('/today/tasks', { state: { from: 'Today' } })}
              />
              {open.length === 0 ? (
                <div style={{ paddingBottom: 4 }}>
                  <EmptyRow icon="checkmark" title={done.length === 0 ? 'Nothing waiting' : 'All done for today'}
                    detail={done.length === 0 ? 'New tasks from your care team show up here.' : 'Your care team will see what you did with their next review.'} />
                </div>
              ) : (
                <>
                  {checkin && (
                    <div className="stack-8" style={{ padding: `6px 16px ${otherOpen.length === 0 ? 16 : 12}px` }}>
                      <PrimaryButton title="Start today’s check-in" icon="text.bubble.fill" onClick={() => openTask(checkin)} />
                      <span className="t-label c-muted" style={{ padding: '0 4px' }}>
                        {checkin.inSmsConversation
                          ? 'You started this by text. Finishing it here is fine.'
                          : 'About two minutes. Every question can be skipped.'}
                      </span>
                    </div>
                  )}
                  {otherOpen.length > 0 && (
                    <>
                      {checkin && <InsetDivider leading={16} />}
                      {otherOpen.map((t, i) => (
                        <div key={t.id}>
                          <TaskRowButton task={t} onOpen={() => openTask(t)} onMarkDone={() => void markDone(t)} />
                          {i < otherOpen.length - 1 && <RowDivider />}
                        </div>
                      ))}
                    </>
                  )}
                </>
              )}
              {done.length > 0 && (
                <>
                  <InsetDivider leading={16} />
                  <button type="button" className="row-button" onClick={() => setShowDone((v) => !v)} aria-expanded={showDone}>
                    <div className="hstack-6 t-copy-m" style={{ padding: '12px 16px' }}>
                      <span className="c-risk-low"><Sym name="checkmark.circle.fill" size={16} weight="medium" /></span>
                      <span className="c-ink">Done today</span>
                      <span className="c-muted">{done.length}</span>
                      <span className="spacer" />
                      <span className="c-muted" style={{ transform: showDone ? 'rotate(180deg)' : 'none', transition: 'transform var(--dur-layout) var(--spring)' }}>
                        <Sym name="chevron.down" size={12} weight="semibold" />
                      </span>
                    </div>
                  </button>
                  {showDone && done.map((t) => (
                    <div key={t.id}>
                      <RowDivider />
                      <PlanRow task={t} />
                    </div>
                  ))}
                </>
              )}
              {done.length === 0 && <div style={{ height: 4 }} />}
            </Card>
          </Rise>

          <Rise index={3} id="measure"><MeasureRow onClick={() => navigate('/measure')} /></Rise>
          <Rise index={4} id="care"><CareRow onClick={() => navigate('/care')} /></Rise>
          {quickError && <ErrorBanner text={quickError} />}
          {app.lastError && <ErrorBanner text={app.lastError} />}
          <span className="footnote">Monitoring signals for your care team — not a diagnosis.</span>
        </div>
      </Screen>
      <Sheet open={showProfile} onClose={() => setShowProfile(false)}>
        <ProfileView onDone={() => setShowProfile(false)} />
      </Sheet>
    </>
  )
}

/** A task row that opens on tap and offers Open / Mark done on a long
 *  press or a right click (the phone's context menu). */
export function TaskRowButton({ task, onOpen, onMarkDone }: { task: RecoveryTask; onOpen: () => void; onMarkDone: () => void }) {
  const [menu, setMenu] = useState(false)
  const anchor = useRef<HTMLButtonElement | null>(null)
  const longPress = useLongPress(() => setMenu(true))
  const items = [{ label: 'Open', icon: 'arrow.up.forward.app', onSelect: onOpen }]
  if (task.questions.length === 0 && task.kind !== 'checkin') items.push({ label: 'Mark done', icon: 'checkmark.circle', onSelect: onMarkDone })
  return (
    <>
      <button ref={anchor} type="button" className="row-button" onClick={() => { if (!longPress.fired()) onOpen() }}
        onContextMenu={(e) => { e.preventDefault(); setMenu(true) }} {...longPress.handlers}>
        <PlanRow task={task} />
      </button>
      <Menu open={menu} onClose={() => setMenu(false)} anchor={anchor} items={items} />
    </>
  )
}

/** A long press (500ms) that does not also count as a tap. */
export function useLongPress(onLong: () => void) {
  const timer = useRef<number | null>(null)
  const firedRef = useRef(false)
  const clear = () => { if (timer.current != null) { clearTimeout(timer.current); timer.current = null } }
  return {
    fired: () => { const f = firedRef.current; firedRef.current = false; return f },
    handlers: {
      onPointerDown: (e: ReactPointerEvent) => {
        if (e.pointerType === 'mouse') return
        firedRef.current = false
        clear()
        timer.current = window.setTimeout(() => { firedRef.current = true; onLong() }, 500)
      },
      onPointerUp: clear,
      onPointerCancel: clear,
      onPointerMove: clear,
      onPointerLeave: clear,
    },
  }
}

// MARK: - Hero

/** The recovery tile: the one gradient on the screen. The typical curve
 *  dashed, the patient's own in white, the headline figure, and the care
 *  team's sentence on the solid-glass caption. */
export function RecoveryHero({ me, onClick }: { me: Me; onClick: () => void }) {
  const tone = toneForLevel(me.recovery.level)
  const traj = me.recovery.trajectory
  const pct = traj.state !== 'unknown' ? traj.pct : null
  const recovery = isRecovery(me.patient)
  const value = pct != null
    ? `${pct >= 0 ? '+' : '−'}${Math.abs(pct).toFixed(0)}%`
    : recovery && me.patient.postopDay != null ? `Day ${me.patient.postopDay}` : `${me.recovery.daysWithData ?? 0}`
  const unit = pct != null ? (recovery ? 'vs expected' : 'vs your baseline')
    : recovery && me.patient.postopDay != null ? 'of recovery' : 'days of data'
  const side: [string, string] | null = pct != null && recovery && me.patient.postopDay != null
    ? [`Day ${me.patient.postopDay}`, 'of recovery']
    : me.recovery.daysWithData != null && pct != null ? [`${me.recovery.daysWithData}`, 'days of data'] : null
  return (
    <GradientTile
      gradient="sage"
      kicker={recovery ? 'Your recovery' : 'Your signals'}
      value={value}
      unit={unit}
      side={side}
      onClick={onClick}
      ariaLabel={`${recovery ? 'Your recovery' : 'Your signals'}: ${value} ${unit}. ${me.recovery.label}. ${me.recovery.blurb}`}
      art={<div style={{ paddingTop: 4 }}><RecoveryCurveArt pct={pct} /></div>}
      caption={
        <div className="stack-8">
          <div className="hstack">
            <StatusPill text={me.recovery.label} tone={tone} />
            <span className="spacer" />
            <span className="hstack c-brand-ink" style={{ gap: 4 }}>
              <span className="t-label-m">Progress</span>
              <Sym name="chevron.right" size={11} weight="semibold" />
            </span>
          </div>
          <span className="t-copy-lg c-ink lh-2">{typeset(me.recovery.blurb)}</span>
        </div>
      }
    />
  )
}

// MARK: - Plan row

export function taskSymbol(kind: string): string {
  switch (kind) {
    case 'checkin': return 'text.bubble.fill'
    case 'exercise': return 'figure.strengthtraining.functional'
    case 'walk': return 'figure.walk'
    case 'medication': return 'pills.fill'
    case 'wound_check': return 'bandage.fill'
    case 'sleep': return 'bed.double.fill'
    default: return 'checklist'
  }
}

export function taskFamily(kind: string): Category {
  switch (kind) {
    case 'exercise': case 'walk': return 'teal'
    case 'medication': case 'wound_check': return 'violet'
    case 'sleep': return 'indigo'
    default: return 'blue'
  }
}

/** One task as a row: a category glyph, the title, one meta line, and a
 *  chevron (open) or the state glyph (done / skipped). */
export function PlanRow({ task }: { task: RecoveryTask }) {
  const isDone = task.status === 'done'
  const open = isOpenTask(task)
  let status: [string, string] | null = null
  if (isDone && task.completedVia) status = [`done by ${task.completedVia}`, 'c-muted']
  else if (task.inSmsConversation) status = ['in progress by text', 'c-risk-med']
  else if (task.dueAt) status = [`due ${Dates.relative(task.dueAt)}`, 'c-muted']
  else {
    const s = scheduleLabel(task)
    if (s) status = [s, 'c-muted']
  }
  return (
    <div className="row" aria-label={`${task.title}, ${task.kindLabel}${isDone ? ', done' : open ? '' : ', skipped'}`}>
      <Glyph name={taskSymbol(task.kind)} family={taskFamily(task.kind)} />
      <span className="row-main">
        <span className="row-title" style={isDone ? { textDecoration: 'line-through', textDecorationColor: 'rgb(var(--muted))' } : undefined}>{task.title}</span>
        <span className="t-label clamp-2">
          <span className="c-muted">{task.kindLabel}</span>
          {status && <><span className="c-muted">{DOT}</span><span className={status[1]}>{status[0]}</span></>}
        </span>
      </span>
      {open ? <Chevron /> : (
        <span className={cx(isDone ? 'c-risk-low' : 'c-muted')}>
          <Sym name={isDone ? 'checkmark.circle.fill' : 'minus.circle'} size={18} weight="regular" />
        </span>
      )}
    </div>
  )
}

// MARK: - Measure and care rows

function MeasureRow({ onClick }: { onClick: () => void }) {
  const app = useApp()
  const statuses = measureFlows.map((f) => measureStatus(f, app.portfolio))
  const due = statuses.filter((s) => s.isDue)
  let subtitle: string
  if (due.length > 0) {
    const names = due.map((s) => flowTitle[s.flow].toLowerCase())
    const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
    subtitle = due[0].lastDate == null && due.length === statuses.length
      ? 'Three short tests with your phone. Start with a guided walk.'
      : `${list.charAt(0).toUpperCase() + list.slice(1)} ${due.length === 1 ? 'is' : 'are'} due.`
  } else {
    const next = statuses.slice().sort((a, b) =>
      (a.cadenceDays - (a.daysSince ?? 0)) - (b.cadenceDays - (b.daysSince ?? 0)))[0]
    subtitle = `All caught up. ${next ? `${flowTitle[next.flow]} ${next.dueLabel.toLowerCase()}.` : ''}`
  }
  return (
    <CardButton onClick={onClick}>
      <Card padding={0}>
        <ListRow title="Measure" subtitle={subtitle} symbol="figure.walk.motion" family="teal"
          trailing={due.length > 0 ? <StateLabel text="Due" tone="med" /> : undefined} />
      </Card>
    </CardButton>
  )
}

function CareRow({ onClick }: { onClick: () => void }) {
  const app = useApp()
  const unread = app.me?.unreadMessages ?? 0
  const team = app.me?.patient.careTeam ?? []
  const last = [...app.messages].reverse().find((m) => m.sender !== 'patient')
  const subtitle = last && last.text ? last.text
    : team.length ? team.map((m) => m.name).join(', ')
      : 'Write to your care team, or tell MedPull how you feel.'
  return (
    <CardButton onClick={onClick}>
      <Card padding={0}>
        <div className="hstack" style={{ padding: '12px 16px' }}>
          <TeamAvatars team={team} />
          <span className="row-main">
            <span className="row-title">Care team</span>
            <span className="row-sub clamp-2">{subtitle}</span>
          </span>
          {unread > 0 && <span className="unread-badge figures" aria-label={`${unread} unread`}>{unread}</span>}
          <Chevron />
        </div>
      </Card>
    </CardButton>
  )
}

// MARK: - Toolbar pieces

/** The MedPull lockup on the leading edge of the bar: the mark on its white
 *  tile, then the wordmark in ink. Hidden once the greeting has scrolled off. */
export function BrandLockup({ hidden, badge }: { hidden: boolean; badge?: string }) {
  return (
    <span className="lockup" style={{ opacity: hidden ? 0 : 1 }} aria-hidden={hidden || undefined} aria-label={badge ? `MedPull ${badge}` : 'MedPull'}>
      <span className="lockup-mark"><img src={`${import.meta.env.BASE_URL}medpull-mark.svg`} alt="" /></span>
      <span className="hstack-6">
        <span className="lockup-word">MedPull</span>
        {badge && <span className="schedule-pill">{badge}</span>}
      </span>
    </span>
  )
}

/** The avatar on the trailing edge of the bar; opens Profile. */
export function AvatarItem({ initials, onClick }: { initials: string; onClick: () => void }) {
  return (
    <button type="button" className="avatar-btn" onClick={onClick} aria-label="Profile">
      <Initials text={initials} size={36} />
    </button>
  )
}

/** The care team as overlapping soft discs. */
export function TeamAvatars({ team, size = 34, onCanvas = false }: { team: CareTeamMember[]; size?: number; onCanvas?: boolean }) {
  if (team.length === 0) return <Glyph name="bubble.left.and.bubble.right.fill" family="blue" size={36} />
  return (
    <span className={cx('team-avatars', onCanvas && 'on-canvas')} aria-hidden="true">
      {team.slice(0, 3).map((m, i) => <Initials key={i} text={teamInitials(m.name)} size={size} tone="low" style="soft" />)}
    </span>
  )
}

/** "Dr. Priya Shah" -> "PS": honorifics end in a period. */
export function teamInitials(name: string): string {
  const words = name.split(' ').filter((w) => w && !w.endsWith('.'))
  const letters = [words[0], words.length > 1 ? words[words.length - 1] : undefined]
    .filter((w): w is string => !!w).map((w) => w.charAt(0))
  return letters.join('').toUpperCase()
}
