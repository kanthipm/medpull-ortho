/* The app root (MedPullApp.swift + RootView.swift): bootstrap the model,
   then the launch spinner, the onboarding flow, or the four tabs of a
   hospital record. Devices and settings live behind the avatar. */

import { useEffect, useRef, useState } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { app, useApp } from './core/appModel'
import { needsConsent } from './core/models'
import { CareView } from './features/care/CareView'
import { ConsentGate } from './features/consent/ConsentView'
import { MeasureTab } from './features/measure/MeasureTab'
import { OnboardingFlow } from './features/onboarding/OnboardingFlow'
import { ConnectionsView } from './features/profile/ConnectionsView'
import { CareMetricDetailRoute } from './features/progress/CareMetricDetailView'
import { ProgressTab } from './features/progress/ProgressTab'
import { SignalDetailRoute } from './features/progress/SignalDetailView'
import { TaskDestination, TaskHistoryView } from './features/tasks/TasksView'
import { TodayView } from './features/today/TodayView'
import { Sheet, SheetHostProvider, Spinner } from './ui/components'
import { Sym } from './ui/icons'

export default function App() {
  useEffect(() => { void app.bootstrap() }, [])
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  )
}

/** The phone column, which also hosts the sheets. */
function Shell() {
  const [host, setHost] = useState<HTMLElement | null>(null)
  return (
    <div className="shell" ref={setHost}>
      <SheetHostProvider value={host}>
        <RootView />
      </SheetHostProvider>
    </div>
  )
}

function RootView() {
  const model = useApp()
  switch (model.phase) {
    case 'launching':
      return <div className="launch"><Spinner size={24} /></div>
    case 'onboarding':
      return <OnboardingFlow />
    case 'home':
      return <MainTabs />
  }
}

/** Four tabs for a hospital record. Each tab owns one question: Today
 *  (what now), Progress (am I getting better), Measure (MedPull's own
 *  tests), Care (the thread). */
function MainTabs() {
  const model = useApp()
  const lastRefresh = useRef(0)

  // Coming back to the tab after a while: the phone refreshes on foreground.
  useEffect(() => {
    lastRefresh.current = Date.now()
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return
      if (Date.now() - lastRefresh.current < 30_000) return
      lastRefresh.current = Date.now()
      void model.refreshAll()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [model])

  // The beta consent, for an account that has never accepted it or met a
  // new version: nothing else is usable until it is read.
  if (needsConsent(model.me)) return <ConsentGate />

  return (
    <>
      <Routes>
        <Route path="/today" element={<TodayView />} />
        <Route path="/today/tasks" element={<TaskHistoryView />} />
        <Route path="/today/tasks/:id" element={<TaskDestination />} />
        <Route path="/progress" element={<ProgressTab />} />
        <Route path="/progress/signals/:key" element={<SignalDetailRoute root="/progress" />} />
        <Route path="/progress/metrics/:id" element={<CareMetricDetailRoute />} />
        <Route path="/measure" element={<MeasureTab />} />
        <Route path="/measure/signals/:key" element={<SignalDetailRoute root="/measure" />} />
        <Route path="/care" element={<CareView />} />
        <Route path="/tasks/:id" element={<TaskLink />} />
        <Route path="/connections" element={<ConnectionsLink />} />
        <Route path="*" element={<Navigate to="/today" replace />} />
      </Routes>
      <TabBar />
      <Sheet open={model.showConnections} onClose={() => model.setShowConnections(false)}>
        <ConnectionsView onDone={() => model.setShowConnections(false)} />
      </Sheet>
    </>
  )
}

/** `medpull://tasks/<id>`, as a web link: Today opens the task. */
function TaskLink() {
  const { id } = useParams()
  const navigate = useNavigate()
  useEffect(() => {
    const n = Number(id)
    if (Number.isInteger(n)) app.setPendingTaskId(n)
    void app.refreshTasks()
    navigate('/today', { replace: true })
  }, [id, navigate])
  return null
}

/** `medpull://wearables`, as a web link: the Connections sheet. */
function ConnectionsLink() {
  const navigate = useNavigate()
  useEffect(() => {
    app.setShowConnections(true)
    void app.refreshWearables(true, false)
    navigate('/today', { replace: true })
  }, [navigate])
  return null
}

function TabBar() {
  const model = useApp()
  const open = model.tasks.open.length
  const unread = model.me?.unreadMessages ?? 0
  const tabs: { to: string; label: string; icon: string; badge: number }[] = [
    { to: '/today', label: 'Today', icon: 'sun.max.fill', badge: open },
    { to: '/progress', label: 'Progress', icon: 'chart.line.uptrend.xyaxis', badge: 0 },
    { to: '/measure', label: 'Measure', icon: 'figure.walk.motion', badge: 0 },
    { to: '/care', label: 'Care', icon: 'bubble.left.and.bubble.right.fill', badge: unread },
  ]
  return (
    <nav className="tabbar" aria-label="Tabs">
      {tabs.map((t) => (
        <NavLink key={t.to} to={t.to} className="tab" aria-label={t.badge > 0 ? `${t.label}, ${t.badge} new` : t.label}>
          <Sym name={t.icon} size={24} weight="medium" />
          <span>{t.label}</span>
          {t.badge > 0 && <span className="tab-badge" aria-hidden="true">{t.badge}</span>}
        </NavLink>
      ))}
    </nav>
  )
}
