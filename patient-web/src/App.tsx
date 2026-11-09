/* The app root (MedPullApp.swift + RootView.swift): bootstrap the model,
   then the launch spinner, the onboarding flow, or the four tabs of a
   hospital record. Devices and settings live behind the avatar. */

import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Navigate, NavLink, Route, Routes, useNavigate, useParams } from 'react-router-dom'
import { app, useApp } from './core/appModel'
import { needsConsent } from './core/models'
import { ConsentGate } from './features/consent/ConsentView'
import { TodayView } from './features/today/TodayView'
import { Sheet, SheetHostProvider, Spinner } from './ui/components'
import { Sym } from './ui/icons'

/* Code splitting by screen. Today is the home tab and ships in the entry
 * chunk with the shell and the consent gate; onboarding, the other three
 * tabs, their detail screens and the Connections sheet are each their own
 * chunk, so a returning patient's first paint no longer downloads the
 * measurement engine, the thread, or a sign-up flow they finished weeks ago.
 * `preloadTabs` fetches the tab chunks a moment after the home tab is up, and
 * react-router runs navigations inside React's startTransition, so a tap on
 * a tab keeps the current screen until the next one is ready — the fallback
 * below (the launch spinner) is only seen on a cold deep link. */
const loadOnboarding = () => import('./features/onboarding/OnboardingFlow')
const loadCare = () => import('./features/care/CareView')
const loadMeasure = () => import('./features/measure/MeasureTab')
const loadConnections = () => import('./features/profile/ConnectionsView')
const loadProgress = () => import('./features/progress/ProgressTab')
const loadSignalDetail = () => import('./features/progress/SignalDetailView')
const loadCareMetricDetail = () => import('./features/progress/CareMetricDetailView')
const loadTasks = () => import('./features/tasks/TasksView')
const loadExercise = () => import('./features/exercises/ExerciseDetailView')
const loadSession = () => import('./features/exercises/ExerciseSessionView')
const loadProgram = () => import('./features/exercises/ProgramView')

const OnboardingFlow = lazy(() => loadOnboarding().then((m) => ({ default: m.OnboardingFlow })))
const CareView = lazy(() => loadCare().then((m) => ({ default: m.CareView })))
const MeasureTab = lazy(() => loadMeasure().then((m) => ({ default: m.MeasureTab })))
const ConnectionsView = lazy(() => loadConnections().then((m) => ({ default: m.ConnectionsView })))
const ProgressTab = lazy(() => loadProgress().then((m) => ({ default: m.ProgressTab })))
const SignalDetailRoute = lazy(() => loadSignalDetail().then((m) => ({ default: m.SignalDetailRoute })))
const CareMetricDetailRoute = lazy(() =>
  loadCareMetricDetail().then((m) => ({ default: m.CareMetricDetailRoute })),
)
const TaskHistoryView = lazy(() => loadTasks().then((m) => ({ default: m.TaskHistoryView })))
const TaskDestination = lazy(() => loadTasks().then((m) => ({ default: m.TaskDestination })))
const ExerciseDestination = lazy(() => loadExercise().then((m) => ({ default: m.ExerciseDestination })))
const ExerciseSessionDestination = lazy(() => loadSession().then((m) => ({ default: m.ExerciseSessionDestination })))
const ProgramView = lazy(() => loadProgram().then((m) => ({ default: m.ProgramView })))

function preloadTabs() {
  void loadProgress()
  void loadSignalDetail()
  void loadCareMetricDetail()
  void loadMeasure()
  void loadCare()
  void loadTasks()
  void loadExercise()
  void loadSession()
  void loadProgram()
  void loadConnections()
}

/** The launch screen: the canvas and a spinner, which is also what a screen
 *  shows for the instant before its chunk lands on a cold deep link. */
function Launch() {
  return <div className="launch"><Spinner size={24} /></div>
}

export default function App() {
  useEffect(() => { void app.bootstrap() }, [])
  return (
    <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '')}>
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
      return <Launch />
    case 'onboarding':
      return <Suspense fallback={<Launch />}><OnboardingFlow /></Suspense>
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

  // The other tabs' code, fetched once the home tab is up so the first tap
  // on any of them is instant.
  useEffect(() => {
    const timer = window.setTimeout(preloadTabs, 1_500)
    return () => window.clearTimeout(timer)
  }, [])

  // The beta consent, for an account that has never accepted it or met a
  // new version: nothing else is usable until it is read.
  if (needsConsent(model.me)) return <ConsentGate />

  return (
    <>
      <Suspense fallback={<Launch />}>
        <Routes>
          <Route path="/today" element={<TodayView />} />
          <Route path="/today/tasks" element={<TaskHistoryView />} />
          <Route path="/today/tasks/:id" element={<TaskDestination />} />
          <Route path="/today/program" element={<ProgramView />} />
          <Route path="/today/exercises/:id" element={<ExerciseDestination />} />
          <Route path="/today/exercises/:id/session" element={<ExerciseSessionDestination />} />
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
      </Suspense>
      <TabBar />
      <Sheet open={model.showConnections} onClose={() => model.setShowConnections(false)}>
        <Suspense fallback={null}>
          <ConnectionsView onDone={() => model.setShowConnections(false)} />
        </Suspense>
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
