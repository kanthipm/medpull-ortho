import { Navigate, Route, Routes } from 'react-router-dom'
import AppShell from './components/layout/AppShell'
import IntegrationsPage from './features/integrations/IntegrationsPage'
import PatientDetailPage from './features/patient/PatientDetailPage'
import NotificationSettingsPage from './features/settings/NotificationSettingsPage'
import WorklistPage from './features/worklist/WorklistPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<WorklistPage />} />
        <Route path="patients/:id" element={<PatientDetailPage />} />
        <Route path="integrations" element={<IntegrationsPage />} />
        <Route path="settings/notifications" element={<NotificationSettingsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}
