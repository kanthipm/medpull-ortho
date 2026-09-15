import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import CheckinPage from './features/checkin/CheckinPage'
import TaskPage from './features/task/TaskPage'
import IntegrationsPage from './features/integrations/IntegrationsPage'
import PatientDetailPage from './features/patient/PatientDetailPage'
import LibraryPage from './features/settings/LibraryPage'
import NotificationSettingsPage from './features/settings/NotificationSettingsPage'
import WorklistPage from './features/worklist/WorklistPage'

export default function App() {
  return (
    <Routes>
      <Route path="checkin/:token" element={<CheckinPage />} />
      <Route path="t/:token" element={<TaskPage />} />
      <Route element={<AppShell />}>
        <Route index element={<WorklistPage />} />
        <Route path="patients/:id" element={<PatientDetailPage />} />
        <Route path="integrations" element={<IntegrationsPage />} />
        <Route path="settings/notifications" element={<NotificationSettingsPage />} />
        <Route path="settings/library" element={<LibraryPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
