import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  clearActingClinic,
  clearConsoleToken,
  getConsoleToken,
  readClinicParam,
  setActingClinic,
  subscribeActingClinic,
} from '../../api/client'
import { useConsoleSession, useHealth } from '../../api/queries'
import {
  forgetWorkspaceChoices,
  rememberSubject,
  resetForClinicChange,
  useActingClinic,
  useWorkspaces,
} from '../../api/workspaces'
import { useReveal, useSpotlight } from '../../lib/useReveal'
import { useScrollEdge } from '../../lib/useScrollEdge'
import DemoWelcome from '../DemoWelcome'
import NotificationsPopover from '../NotificationsPopover'
import { useSlidingIndicator } from '../segmented'
import ThemeToggle from '../ThemeToggle'
import { PAGE_CLASS, pageWidthFor } from './pageWidth'
import {
  VERSIONS,
  homeFor,
  isMenuPage,
  isStaffPage,
  subjectIn,
  tabsFor,
  versionFor,
  type VersionTab,
} from './version'
import WorkspaceMenu from './WorkspaceMenu'
import { landingSubject } from './workspaceRows'

/** The page head the sky window wraps: an explicit `[data-hero]`, else the
 *  page's first <header>, else its h1. */
function findHero(main: HTMLElement): Element | null {
  return (
    main.querySelector('[data-hero]') ??
    main.querySelector(':scope > * > header') ??
    main.querySelector('h1')
  )
}

/** Sizes the sky window to the page head: `--sky-height` on the stage =
 *  the head's bottom + 24px + `--sky-tail` (the part that fades out behind
 *  the first cards). Re-measured when the page swaps content, resizes, or
 *  finishes its `.rise` entrance (whose translate the rect includes).
 *  With no head found, the CSS fallback (300px) applies. */
function useSkyHeight(
  mainRef: RefObject<HTMLElement | null>,
  stageRef: RefObject<HTMLDivElement | null>,
  pathname: string,
) {
  useLayoutEffect(() => {
    const main = mainRef.current
    const stage = stageRef.current
    if (!main || !stage) return
    let raf = 0
    let last = ''
    const apply = () => {
      const hero = findHero(main)
      let next = ''
      if (hero) {
        const bottom = hero.getBoundingClientRect().bottom - stage.getBoundingClientRect().top
        next = `calc(${Math.round(bottom)}px + 24px + var(--sky-tail))`
      }
      if (next === last) return
      last = next
      if (next) stage.style.setProperty('--sky-height', next)
      else stage.style.removeProperty('--sky-height')
    }
    const schedule = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(apply)
    }
    apply()
    const mo = new MutationObserver(schedule)
    mo.observe(main, { childList: true, subtree: true })
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(schedule) : undefined
    ro?.observe(main)
    main.addEventListener('animationend', schedule)
    window.addEventListener('resize', schedule)
    document.fonts?.ready.then(schedule).catch(() => {})
    return () => {
      cancelAnimationFrame(raf)
      mo.disconnect()
      ro?.disconnect()
      main.removeEventListener('animationend', schedule)
      window.removeEventListener('resize', schedule)
    }
  }, [mainRef, stageRef, pathname])
}

/** The current version's tabs with the sliding pill under the one that is
 *  open. The shell keys this by version, so a switch mounts a fresh nav: the
 *  pill is measured against the new tabs and appears in place rather than
 *  sliding in from where the last version's tab was. With no tab lit (a page
 *  opened from the menu) the pill hides. */
function PrimaryNav({ tabs, pathname }: { tabs: VersionTab[]; pathname: string }) {
  const active = tabs.find((tab) => tab.match(pathname))?.key
  const { trackRef, style } = useSlidingIndicator(active, tabs.length)
  return (
    <nav
      aria-label="Primary"
      className="relative min-w-0 overflow-x-auto [scrollbar-width:none] sm:mx-auto sm:shrink-0 lg:mx-0 [&::-webkit-scrollbar]:hidden"
    >
      <div ref={trackRef} className="relative flex items-center gap-0.5 py-2">
        <span aria-hidden className="nav-rule" style={style} />
        {tabs.map((tab) => {
          const current = tab.key === active
          return (
            <Link
              key={tab.key}
              to={tab.to}
              aria-current={current ? 'page' : undefined}
              data-segment-active={current ? 'true' : undefined}
              data-label={tab.label}
              className="appbar-link"
            >
              {tab.label}
            </Link>
          )
        })}
      </div>
    </nav>
  )
}

/** The console shell, in the medpull.org language.
 *
 *  ATMOSPHERE. `.ambient` is a fixed, static layer of faint fog and grain
 *  behind everything. `.sky-stage` holds the site's hero canvas: one rounded
 *  `.sky-window` with drifting fog (`.aurora`, transform-only, paused off
 *  screen via data-loop), grain and a dot grid. Its height follows the page
 *  head (useSkyHeight) and its tail fades out behind the first cards, which
 *  float over it. Cards are opaque-enough glass, so no clinical number ever
 *  sits on raw fog.
 *
 *  BAR. The site's floating glass capsule: the app-icon tile and name, the
 *  current version's three tabs with a sliding pill under the open one, and
 *  on the right the theme toggle, the bell (Clinic only) and the workspace
 *  menu. From 1024px the tabs sit at the bar's centre whatever is beside
 *  them; below that they share the row. The bar strengthens (more opaque,
 *  larger shadow) once content scrolls under it. The flat modes make it
 *  opaque with a real edge (index.css).
 *
 *  ALIGNMENT. The bar's row and <main> use the same per-route width class,
 *  so the logo lines up with the page's left edge on every page.
 *
 *  VERSIONS. Clinic, Personal and Sports are one app; the path says which is
 *  on screen (version.ts) and the workspace menu moves between them.
 *  Integrations and Settings are reached from that menu and light no tab.
 *
 *  SCOPE. `GET /api/console/workspaces` says which versions the stored
 *  credential may use. A path in a version it may not use is sent to the
 *  credential's home (the landing page of its first version, which is always
 *  one it may use, so the redirect cannot loop). Until that answer is in, a
 *  stored token gets no tabs and no menu rather than every one; with no
 *  token at all the console is open and the path's own version shows at
 *  once.
 *
 *  ACTING CLINIC. A staff console looks at one clinic or at all of them; the
 *  choice rides on every request as a header (api/client.ts). The shell
 *  resets the query cache when it changes, adopts `?clinic=` from a link
 *  followed inside the app, and drops a stored choice the server no longer
 *  lists. */
export default function AppShell() {
  const { pathname, search, hash } = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { sentinelRef, scrolled } = useScrollEdge<HTMLSpanElement>()
  const scope = useConsoleSession().data?.scope
  const workspaces = useWorkspaces().data
  const health = useHealth().data
  const clinic = useActingClinic()
  const signedIn = getConsoleToken() != null
  const staff = scope?.kind === 'all'
  // What the credential may use is known once both have answered.
  const known = scope != null && workspaces != null
  const versions = workspaces ? workspaces.versions : signedIn ? [] : VERSIONS
  const home = homeFor(versions)

  const here = versionFor(pathname)
  const inScope =
    !known || (isMenuPage(pathname) ? staff || !isStaffPage(pathname) : versions.includes(here))
  // The version the bar speaks for. A page opened from the menu belongs to
  // Clinic, except for a credential with no Clinic: its bar stays its own.
  const version = known && !versions.includes(here) ? (versions[0] ?? here) : here
  // The member or team the tabs are about: the one in the address, else (on
  // a menu page) the one a bare landing would open.
  let subject: string | null = null
  if (version !== 'clinic') {
    subject =
      version === here
        ? subjectIn(pathname)
        : workspaces
          ? landingSubject(workspaces, version)
          : null
  }
  // The Calendar rides on the server's HEP flag: until health has answered
  // (or where it is off) the bar keeps the other tabs. The pages themselves
  // stay reachable either way.
  const hep = health?.hep === true
  const tabs = versions.includes(version)
    ? tabsFor(version, subject).filter(
        (tab) => hep || version !== 'clinic' || tab.key !== 'calendar',
      )
    : []

  const width = pageWidthFor(pathname)
  const pageClass = PAGE_CLASS[width]
  // A full-bleed page (the demo screen) takes the whole viewport under the
  // bar; the bar itself keeps the container width, so the nav capsule looks
  // as it does on every other page.
  const full = width === 'full'
  const barClass = full ? PAGE_CLASS.wide : pageClass
  const shellRef = useRef<HTMLDivElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  useSkyHeight(mainRef, stageRef, pathname)
  useReveal(shellRef, pathname)
  useSpotlight(shellRef)

  // Every cached roster belongs to the acting clinic it was read under.
  useEffect(
    () => subscribeActingClinic(() => resetForClinicChange(queryClient)),
    [queryClient],
  )

  // `?clinic=` on a link followed inside the app (a full load is handled
  // before the first request, in App.tsx): set it once, take it out of the
  // address.
  useEffect(() => {
    const found = readClinicParam(search)
    if (!found) return
    setActingClinic(found.clinic)
    navigate({ pathname, search: found.rest, hash }, { replace: true })
  }, [pathname, search, hash, navigate])

  // A stored choice the server does not list (another deployment's clinic, a
  // mistyped `?clinic=`, a credential that is one clinic already) would
  // narrow every roster to nothing while the bar said otherwise.
  useEffect(() => {
    if (!scope || !workspaces || clinic == null) return
    if (scope.kind !== 'all' || !workspaces.clinics.some((c) => c.id === clinic)) {
      setActingClinic(null)
    }
  }, [scope, workspaces, clinic])

  // `/personal` and `/sports` reopen whoever was on screen last.
  const subjectHere = here === 'clinic' ? null : subjectIn(pathname)
  useEffect(() => {
    if (here !== 'clinic' && subjectHere) rememberSubject(here, subjectHere)
  }, [here, subjectHere])

  const signOut = () => {
    // A full load, not a route change: every cached query belongs to the
    // token being dropped, and so do the choices made under it.
    clearConsoleToken()
    clearActingClinic()
    forgetWorkspaceChoices()
    window.location.assign('/login')
  }

  return (
    <div ref={shellRef} className="ambient-host flex min-h-screen flex-col">
      <div className="ambient" aria-hidden />
      <div ref={stageRef} className="sky-stage" aria-hidden>
        <div className="sky-window" data-loop>
          <div className="aurora">
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
        </div>
      </div>
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
        <div className={barClass}>
          <div className="appbar-inner flex items-center gap-2 sm:gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
            <Link
              to={home}
              aria-label="MedPull home"
              className="brand-lockup shrink-0 justify-self-start rounded-pill pr-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              <span className="app-icon">
                <img src="/medpull-mark.svg" alt="" aria-hidden width={22} height={22} />
              </span>
              <span className="hidden md:inline">MedPull</span>
            </Link>

            <PrimaryNav key={version} tabs={tabs} pathname={pathname} />

            <div className="ml-auto flex min-w-0 shrink-0 items-center gap-0.5 sm:ml-0 sm:shrink lg:justify-self-end [&_.btn-icon]:shrink-0">
              {/* Below 768px the toggle goes (Settings has the same switch)
                  and the brand is its icon alone, so the three tabs fit next
                  to the bell and the workspace menu; when the row is still
                  short of room it is the menu's label that truncates. */}
              <span className="hidden md:contents">
                <ThemeToggle />
              </span>
              {/* Alerts are about clinic charts; the other versions have none. */}
              {version === 'clinic' && versions.includes('clinic') && <NotificationsPopover />}
              {scope && workspaces && (
                <span className="ml-1 flex min-w-0">
                  <WorkspaceMenu
                    workspaces={workspaces}
                    scope={scope}
                    at={{ version, subject, clinic }}
                    demo={health?.demo === true}
                    onSignOut={signedIn ? signOut : undefined}
                  />
                </span>
              )}
            </div>
          </div>
        </div>
      </header>

      <main
        ref={mainRef}
        id="main"
        tabIndex={-1}
        className={`${pageClass} flex-1 outline-0 [outline-style:none] ${
          full ? 'pb-4 pt-4' : 'pb-20 pt-8 sm:pt-12'
        }`}
      >
        {inScope ? <Outlet /> : <Navigate to={home} replace />}
      </main>
      {/* the presenter's demo screen is not a visitor's first page */}
      {!pathname.startsWith('/demo') && <DemoWelcome />}
    </div>
  )
}
