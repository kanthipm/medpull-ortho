import { lazy, Suspense, useEffect, type ReactNode } from 'react'
import { Navigate, Route, Routes, useLocation, useParams } from 'react-router-dom'
import { adoptClinicFromAddress } from './api/client'
import AppShell from './components/layout/AppShell'
import { SkeletonCard } from './components/Skeleton'
import CheckinPage from './features/checkin/CheckinPage'
import { CALENDAR } from './features/hep/paths'
import LinkPage from './features/link/LinkPage'
import LoginPage from './features/login/LoginPage'
import { loadPatientDetailPage } from './features/patient/preload'
import TaskPage from './features/task/TaskPage'
import WorklistPage from './features/worklist/WorklistPage'

// `?clinic=<id>` on the address a browser arrives at sets the acting clinic
// before the first request goes out, so nothing is fetched for the old
// choice (api/client.ts). The shell does the same for a link followed inside
// the app.
adoptClinicFromAddress()

/* Route-level code splitting. The worklist is the landing page and ships in
 * the entry chunk with the shell; the pages a texted link opens (check-in,
 * task, link, login) stay there too — they are reached cold and are small.
 * Every other page is its own chunk, fetched on first navigation: the
 * patient page alone carried the charting library, a third of the old single
 * bundle, and a clinician who only triages never paid for it before.
 *
 * In practice the fetch happens earlier: `preloadRoutes` warms the likely
 * next pages once the first paint and the worklist's own request have had
 * their turn, and a worklist row warms the patient page as soon as the
 * pointer is on it. react-router runs route changes inside React's
 * startTransition, so the current page stays up while a chunk loads; the
 * fallback below is only ever seen on a cold deep link.
 *
 * The three versions of the console (Clinic, Personal, Sports) are one route
 * table; which one is on screen is read from the path
 * (components/layout/version.ts), and the tabs in the bar follow it. */
const PatientDetailPage = lazy(loadPatientDetailPage)

// Clinic · Calendar
const loadSchedulePage = () => import('./features/hep/SchedulePage')
const SchedulePage = lazy(loadSchedulePage)
const WeekReviewPage = lazy(() => import('./features/hep/WeekReviewPage'))
const ReviewPage = lazy(() => import('./features/hep/ReviewPage'))
const ProgramsPage = lazy(() => import('./features/hep/ProgramsPage'))
const ProgramEditorPage = lazy(() => import('./features/hep/ProgramEditorPage'))
const ExerciseLibraryPage = lazy(() => import('./features/hep/ExerciseLibraryPage'))
const ExercisePlansPage = lazy(() => import('./features/hep/ExercisePlansPage'))
const PlanEditorPage = lazy(() => import('./features/hep/PlanEditorPage'))
const DemoScreenPage = lazy(() => import('./features/hep/DemoScreenPage'))
const QuestionsPage = lazy(() => import('./features/pt/QuestionsPage'))
const RulesPage = lazy(() => import('./features/pt/RulesPage'))
const HandoffPage = lazy(() => import('./features/pt/HandoffPage'))

// Clinic · Data
const loadDataRosterPage = () => import('./features/data/DataRosterPage')
const DataRosterPage = lazy(loadDataRosterPage)
const DataPatientPage = lazy(() => import('./features/data/DataPatientPage'))
const DataDictionaryPage = lazy(() => import('./features/data/DataDictionaryPage'))

// Clinic · pages opened from the workspace menu
const IntegrationsPage = lazy(() => import('./features/integrations/IntegrationsPage'))
const NotificationSettingsPage = lazy(() => import('./features/settings/NotificationSettingsPage'))
const LibraryPage = lazy(() => import('./features/settings/LibraryPage'))

// Personal
const PersonalHomePage = lazy(() => import('./features/personal/PersonalHomePage'))
const PersonalTodayPage = lazy(() => import('./features/personal/PersonalTodayPage'))
const PersonalTrendsPage = lazy(() => import('./features/personal/PersonalTrendsPage'))
const PersonalDataPage = lazy(() => import('./features/personal/PersonalDataPage'))

// Sports
const loadTeamDashboardPage = () => import('./features/sports/TeamDashboardPage')
const loadAthleteDetailPage = () => import('./features/sports/AthleteDetailPage')
const TeamsIndexPage = lazy(() => import('./features/sports/TeamsIndexPage'))
const TeamDashboardPage = lazy(loadTeamDashboardPage)
const AthleteDetailPage = lazy(loadAthleteDetailPage)
const TeamCalendarPage = lazy(() => import('./features/sports/TeamCalendarPage'))
const TeamDataPage = lazy(() => import('./features/sports/TeamDataPage'))

/** Warm what the version on screen is likely to open next. */
function preloadRoutes(pathname: string) {
  if (pathname.startsWith('/sports')) {
    void loadTeamDashboardPage()
    void loadAthleteDetailPage()
    return
  }
  if (pathname.startsWith('/personal')) return
  void loadPatientDetailPage()
  void loadSchedulePage()
  void loadDataRosterPage()
}

/** Pages a patient reaches from a texted link, and the sign-in: nothing in
 *  the console is worth warming for them. */
const OUTSIDE_SHELL = ['/checkin/', '/t/', '/a/', '/h/', '/login']

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

/** An address from before the exercise pages became the Calendar: forwarded
 *  to where the page lives now, with its query string and fragment intact
 *  (a bookmarked `/exercise-programs/12?from=…` still lands on that
 *  program). */
function Moved({ to }: { to: string | ((id: string) => string) }) {
  const { id = '' } = useParams()
  const { search, hash } = useLocation()
  const pathname = typeof to === 'string' ? to : to(id)
  return <Navigate to={{ pathname, search, hash }} replace />
}

export default function App() {
  const { pathname } = useLocation()
  const inShell = !OUTSIDE_SHELL.some((prefix) => pathname.startsWith(prefix))
  useEffect(() => {
    if (!inShell) return
    // After the first paint and the page's own request have had their turn,
    // and in an idle slot where the browser offers one (Safari does not).
    const warm = () => preloadRoutes(window.location.pathname)
    const timer = window.setTimeout(() => {
      if ('requestIdleCallback' in window) window.requestIdleCallback(warm)
      else warm()
    }, 2_000)
    return () => window.clearTimeout(timer)
  }, [inShell])
  return (
    <Routes>
      <Route path="checkin/:token" element={<CheckinPage />} />
      <Route path="t/:token" element={<TaskPage />} />
      <Route path="a/:token" element={<LinkPage />} />
      <Route path="h/:token" element={<Page><HandoffPage /></Page>} />
      <Route path="login" element={<LoginPage />} />
      <Route element={<AppShell />}>
        {/* Clinic · Worklist */}
        <Route index element={<WorklistPage />} />
        <Route path="patients/:id" element={<Page><PatientDetailPage /></Page>} />

        {/* Clinic · Calendar (paths in features/hep/paths.ts) */}
        <Route path="calendar" element={<Page><SchedulePage /></Page>} />
        <Route path="calendar/week" element={<Page><WeekReviewPage /></Page>} />
        <Route path="calendar/review" element={<Page><ReviewPage /></Page>} />
        <Route path="calendar/programs" element={<Page><ProgramsPage /></Page>} />
        <Route path="calendar/programs/:id" element={<Page><ProgramEditorPage /></Page>} />
        <Route path="calendar/library" element={<Page><ExerciseLibraryPage /></Page>} />
        <Route path="calendar/plans" element={<Page><ExercisePlansPage /></Page>} />
        <Route path="calendar/plans/:id" element={<Page><PlanEditorPage /></Page>} />
        <Route path="calendar/questions" element={<Page><QuestionsPage /></Page>} />
        <Route path="calendar/rules" element={<Page><RulesPage /></Page>} />
        <Route path="demo/hirt" element={<Page><DemoScreenPage /></Page>} />
        <Route path="demo" element={<Navigate to={CALENDAR.demoScreen} replace />} />
        <Route path="exercise-schedule" element={<Moved to={CALENDAR.schedule} />} />
        <Route path="exercise-review" element={<Moved to={CALENDAR.review} />} />
        <Route path="exercise-programs" element={<Moved to={CALENDAR.programs} />} />
        <Route path="exercise-programs/:id" element={<Moved to={CALENDAR.program} />} />
        <Route path="exercise-library" element={<Moved to={CALENDAR.library} />} />
        <Route path="exercise-plans" element={<Moved to={CALENDAR.plans} />} />
        <Route path="exercise-plans/:id" element={<Moved to={CALENDAR.plan} />} />

        {/* Clinic · Data */}
        <Route path="data" element={<Page><DataRosterPage /></Page>} />
        <Route path="data/patients/:id" element={<Page><DataPatientPage /></Page>} />
        <Route path="data/dictionary" element={<Page><DataDictionaryPage /></Page>} />

        {/* Clinic · opened from the workspace menu */}
        <Route path="integrations" element={<Page><IntegrationsPage /></Page>} />
        <Route path="settings" element={<Navigate to="/settings/notifications" replace />} />
        <Route path="settings/notifications" element={<Page><NotificationSettingsPage /></Page>} />
        <Route path="settings/library" element={<Page><LibraryPage /></Page>} />

        {/* Personal: one member at a time */}
        <Route path="personal" element={<Page><PersonalHomePage /></Page>} />
        <Route path="personal/:memberId" element={<Page><PersonalTodayPage /></Page>} />
        <Route path="personal/:memberId/trends" element={<Page><PersonalTrendsPage /></Page>} />
        <Route path="personal/:memberId/data" element={<Page><PersonalDataPage /></Page>} />

        {/* Sports: one team at a time */}
        <Route path="sports" element={<Page><TeamsIndexPage /></Page>} />
        <Route path="sports/teams/:teamId" element={<Page><TeamDashboardPage /></Page>} />
        <Route path="sports/teams/:teamId/calendar" element={<Page><TeamCalendarPage /></Page>} />
        <Route path="sports/teams/:teamId/data" element={<Page><TeamDataPage /></Page>} />
        <Route
          path="sports/teams/:teamId/athletes/:id"
          element={<Page><AthleteDetailPage /></Page>}
        />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
