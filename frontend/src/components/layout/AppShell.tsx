import { Link, Outlet, useLocation } from 'react-router-dom'
import { useScrollEdge } from '../../lib/useScrollEdge'
import NotificationsPopover from '../NotificationsPopover'
import { useActiveRoute, useSlidingIndicator } from '../SegmentedControl'
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

/** Content width per page (R3). The wash and the bar stay full-bleed; only
 *  the content column is capped and centred.
 *    worklist  1080px   ('/')
 *    patient   1240px   ('/patients/…')
 *    settings   960px   ('/settings…', '/integrations')
 *    wide      --container-max (any other route) */
export type PageWidth = 'worklist' | 'patient' | 'settings' | 'wide'

export function pageWidthFor(pathname: string): PageWidth {
  if (pathname === '/') return 'worklist'
  if (pathname.startsWith('/patients/')) return 'patient'
  if (pathname.startsWith('/settings') || pathname.startsWith('/integrations')) return 'settings'
  return 'wide'
}

const PAGE_CLASS: Record<PageWidth, string> = {
  worklist: 'page page-worklist',
  patient: 'page page-patient',
  settings: 'page page-settings',
  wide: 'page',
}

/** The console shell.
 *
 *  AMBIENT WASH. `.ambient-host` is the full-bleed wrapper and `.ambient` its
 *  first child, so the brand/teal wash runs under the bar (R2) and behind the
 *  page head. Cards are opaque --panel; only the date line, h1 and patient
 *  header sit on the wash. Hidden under Increase Contrast / forced colours.
 *
 *  GLASS BAR (R2). Sticky, transparent at scroll 0; once the scroll-edge
 *  sentinel leaves the viewport `data-scrolled` turns on the material
 *  (--panel at --bar-alpha .73, blur 24, saturate 160, hairline, float
 *  shadow). The bar carries ONLY ink: the wordmark, the nav (ink 400 idle,
 *  ink 600 current, plus the 2px `.nav-rule`) and ink icon buttons. At .73
 *  ink holds >= 7:1 over solid black (light) / solid white (dark) with no
 *  blur credit; body, muted and brand-ink text do NOT, so never add them
 *  here. The kill switch, reduced transparency and missing backdrop-filter
 *  all make it opaque (index.css).
 *
 *  The bar's inner row is capped at the widest page (patient, 1240px) so it
 *  does not shift between pages; the content column below uses the page's
 *  own cap. */
export default function AppShell() {
  const { pathname } = useLocation()
  const { sentinelRef, scrolled } = useScrollEdge<HTMLSpanElement>()
  const active = useActiveRoute(NAV)
  const { trackRef, style } = useSlidingIndicator(active, NAV.length, 12)
  const width = pageWidthFor(pathname)

  return (
    <div className="ambient-host flex min-h-screen flex-col">
      <div className="ambient" aria-hidden />
      <span
        ref={sentinelRef}
        aria-hidden
        className="pointer-events-none absolute left-0 top-0 h-px w-px"
      />
      <a
        href="#main"
        className="btn-filled btn-sm sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-2 focus:z-50"
      >
        Skip to content
      </a>

      <header className="appbar" data-scrolled={scrolled ? '' : undefined}>
        <div className="page page-patient flex min-h-bar items-center gap-3 sm:gap-6">
          <Link
            to="/"
            aria-label="MedPull home"
            className="flex shrink-0 items-center gap-2 rounded-control-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
          >
            <img src="/medpull-logo.svg" alt="" aria-hidden className="h-7 w-auto" />
            <span className="hidden text-copy-lg font-semibold text-ink sm:inline">MedPull</span>
          </Link>

          <nav
            aria-label="Primary"
            className="relative min-w-0 self-stretch overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
          >
            <div ref={trackRef} className="relative flex h-[calc(100%-1px)] items-center gap-1 px-1">
              {NAV.map((item) => {
                const current = item.key === active
                return (
                  <Link
                    key={item.key}
                    to={item.to}
                    aria-current={current ? 'page' : undefined}
                    data-segment-active={current ? 'true' : undefined}
                    data-label={item.label}
                    className="appbar-link"
                  >
                    {item.label}
                  </Link>
                )
              })}
              <span aria-hidden className="nav-rule" style={style} />
            </div>
          </nav>

          <div className="ml-auto flex shrink-0 items-center gap-1">
            {/* Phones hide the toggle (Settings has the same switch) so the
                three nav items fit next to the bell. */}
            <span className="hidden sm:contents">
              <ThemeToggle />
            </span>
            <NotificationsPopover />
          </div>
        </div>
      </header>

      <main
        id="main"
        tabIndex={-1}
        className={`${PAGE_CLASS[width]} flex-1 pb-16 pt-6 outline-none sm:pt-8`}
      >
        <Outlet />
      </main>
    </div>
  )
}
