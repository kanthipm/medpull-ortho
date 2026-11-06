import { lazy, Suspense, useEffect, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import { SkeletonCard } from './components/Skeleton'
import CheckinPage from './features/checkin/CheckinPage'
import LoginPage from './features/login/LoginPage'
import { loadPatientDetailPage } from './features/patient/preload'
import TaskPage from './features/task/TaskPage'
import WorklistPage from './features/worklist/WorklistPage'

/* Route-level code splitting. The worklist is the landing page and ships in
 * the entry chunk with the shell; the pages a texted link opens (check-in,
 * task, login) stay there too — they are reached cold and are small. Every
 * other page is its own chunk, fetched on first navigation: the patient page
 * alone carried the charting library, a third of the old single bundle, and
 * a clinician who only triages never paid for it before.
 *
 * In practice the fetch happens earlier: `preloadRoutes` warms the likely
 * next pages once the first paint and the worklist's own request have had
 * their turn, and a worklist row warms the patient page as soon as the
 * pointer is on it. react-router runs route changes inside React's
 * startTransition, so the current page stays up while a chunk loads; the
 * fallback below is only ever seen on a cold deep link. */
const PatientDetailPage = lazy(loadPatientDetailPage)
const loadTeamsIndexPage = () => import('./features/sports/TeamsIndexPage')
const loadTeamDashboardPage = () => import('./features/sports/TeamDashboardPage')
const loadAthleteDetailPage = () => import('./features/sports/AthleteDetailPage')
const TeamsIndexPage = lazy(loadTeamsIndexPage)
const TeamDashboardPage = lazy(loadTeamDashboardPage)
const AthleteDetailPage = lazy(loadAthleteDetailPage)
const IntegrationsPage = lazy(() => import('./features/integrations/IntegrationsPage'))
const NotificationSettingsPage = lazy(() => import('./features/settings/NotificationSettingsPage'))
const LibraryPage = lazy(() => import('./features/settings/LibraryPage'))

function preloadRoutes() {
  void loadPatientDetailPage()
  void loadTeamsIndexPage()
  void loadTeamDashboardPage()
  void loadAthleteDetailPage()
}

/** Pages a patient reaches from a texted link, and the sign-in: nothing in
 *  the console is worth warming for them. */
const OUTSIDE_SHELL = ['/checkin/', '/t/', '/login']

/** What a lazily loaded page shows for the instant before its chunk lands:
 *  the shimmer cards every page uses while its own data loads. */
function RouteFallback() {
  return (
    <div className="space-y-stack pb-4 pt-8" role="status" aria-label="Loading">
      <SkeletonCard lines={3} />
      <SkeletonCard rows={4} />
    </div>
  )
}

function Page({ children }: { children: ReactNode }) {
  return <Suspense fallback={<RouteFallback />}>{children}</Suspense>
}

export default function App() {
  const { pathname } = useLocation()
  const inShell = !OUTSIDE_SHELL.some((prefix) => pathname.startsWith(prefix))
  useEffect(() => {
    if (!inShell) return
    // After the first paint and the page's own request have had their turn,
    // and in an idle slot where the browser offers one (Safari does not).
    const timer = window.setTimeout(() => {
      if ('requestIdleCallback' in window) window.requestIdleCallback(preloadRoutes)
      else preloadRoutes()
    }, 2_000)
    return () => window.clearTimeout(timer)
  }, [inShell])
  return (
    <Routes>
      <Route path="checkin/:token" element={<CheckinPage />} />
      <Route path="t/:token" element={<TaskPage />} />
      <Route path="login" element={<LoginPage />} />
      <Route element={<AppShell />}>
        <Route index element={<WorklistPage />} />
        <Route path="patients/:id" element={<Page><PatientDetailPage /></Page>} />
        <Route path="sports" element={<Page><TeamsIndexPage /></Page>} />
        <Route path="sports/teams/:teamId" element={<Page><TeamDashboardPage /></Page>} />
        <Route
          path="sports/teams/:teamId/athletes/:id"
          element={<Page><AthleteDetailPage /></Page>}
        />
        <Route path="integrations" element={<Page><IntegrationsPage /></Page>} />
        <Route path="settings/notifications" element={<Page><NotificationSettingsPage /></Page>} />
        <Route path="settings/library" element={<Page><LibraryPage /></Page>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
