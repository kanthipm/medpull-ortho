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

/** Top app bar: an opaque panel with a bottom hairline, and a Medical Blue
 *  rule under the active tab. The bar was a solid Medical Blue slab until the
 *  redesign — brand now reads as the active-tab rule and the wordmark, not as
 *  the largest saturated area on screen.
 *
 *  LAYOUT. The console had no container cap, so a patient table stretched to
 *  2472px on a 2560px display. `max-w-container` is max(1440px, 75vw): pixel-
 *  stable to 1440 and proportional above it, on the bar and the page alike so
 *  the nav lines up with the content below it. The horizontal padding is
 *  `px-gutter` (--page-gutter, max(12px, .625vw)) instead of the hand-rolled
 *  clamp(14px, 3vw, 44px): above 1440px the cap supplies the margin and the
 *  gutter is only the inner breathing room, so the two must not both grow.
 *
 *  The wordmark's "Recovery Copilot" line is SENTENCE CASE. The rule is one
 *  all-caps element per screen and this bar is on every screen, so if the
 *  chrome spent that budget no page could ever have an eyebrow. The slot is
 *  left to the page's own eyebrow recipe. (Worded without the class names on
 *  purpose: a grep-based audit should not count this comment as a use.) */
export default function AppShell() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-line bg-panel">
        <div className="mx-auto flex h-16 w-full max-w-container items-center gap-tight px-gutter sm:gap-block">
          <NavLink to="/" className="flex shrink-0 items-center gap-tight">
            <img src="/medpull-logo.svg" alt="" aria-hidden className="h-[30px] w-auto" />
            <span className="hidden flex-col leading-none md:flex">
              <span className="text-subhead font-medium text-ink">MedPull</span>
              <span className="mt-el text-label font-medium text-muted">Recovery Copilot</span>
            </span>
          </NavLink>
          <NavSegmentedControl options={NAV} tone="primary" className="md:ml-4" />
          <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-tight">
            <ThemeToggle />
            <NotificationsPopover />
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-container px-gutter py-region">
        <Outlet />
      </main>
    </div>
  )
}
