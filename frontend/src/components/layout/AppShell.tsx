import { NavLink, Outlet } from 'react-router-dom'
import NotificationsPopover from '../NotificationsPopover'
import { NavSegmentedControl } from '../SegmentedControl'
import ThemeToggle from '../ThemeToggle'

const NAV = [
  {
    key: 'worklist',
    label: 'Worklist',
    to: '/',
    end: true,
    match: (pathname: string) => pathname === '/' || pathname.startsWith('/patients/'),
  },
  {
    key: 'integrations',
    label: 'Integrations',
    to: '/integrations',
  },
  {
    key: 'settings',
    label: 'Settings',
    to: '/settings/notifications',
    match: (pathname: string) => pathname.startsWith('/settings'),
  },
]

/** Solid Medical Blue top app bar — the kiosk's primary-colour chrome. */
export default function AppShell() {
  return (
    <div className="min-h-screen">
      <header className="glass sticky top-0 z-20 text-white shadow-card">
        <div className="mx-auto flex h-[64px] w-full items-center gap-3 px-[clamp(14px,3vw,44px)] sm:gap-5">
          <NavLink to="/" className="flex shrink-0 items-center gap-3">
            <img src="/medpull-logo.svg" alt="" aria-hidden className="h-[30px] w-auto" />
            <span className="hidden flex-col leading-none md:flex">
              <span className="text-[20px] font-medium text-white">MedPull</span>
              <span className="mt-1 text-[11px] font-medium uppercase tracking-[.08em] text-white/75">
                Recovery Copilot
              </span>
            </span>
          </NavLink>
          <NavSegmentedControl options={NAV} tone="primary" className="md:ml-4" />
          <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
            <ThemeToggle />
            <NotificationsPopover />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full px-[clamp(14px,3vw,44px)] py-[clamp(24px,3vh,40px)]">
        <Outlet />
      </main>
    </div>
  )
}
