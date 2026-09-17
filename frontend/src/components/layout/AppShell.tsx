import { useLayoutEffect, useRef, type RefObject } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
import { useReveal, useSpotlight } from '../../lib/useReveal'
import { useScrollEdge } from '../../lib/useScrollEdge'
import NotificationsPopover from '../NotificationsPopover'
import { useActiveRoute, useSlidingIndicator } from '../segmented'
import ThemeToggle from '../ThemeToggle'
import { PAGE_CLASS, pageWidthFor } from './pageWidth'

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
 *  nav centred with a sliding pill under the current item, and the icon
 *  buttons. It strengthens (more opaque, larger shadow) once content scrolls
 *  under it. The flat modes make it opaque with a real edge (index.css).
 *
 *  ALIGNMENT. The bar's row and <main> use the same per-route width class,
 *  so the logo lines up with the page's left edge on every page. */
export default function AppShell() {
  const { pathname } = useLocation()
  const { sentinelRef, scrolled } = useScrollEdge<HTMLSpanElement>()
  const active = useActiveRoute(NAV)
  const { trackRef, style } = useSlidingIndicator(active, NAV.length)
  const pageClass = PAGE_CLASS[pageWidthFor(pathname)]
  const shellRef = useRef<HTMLDivElement>(null)
  const mainRef = useRef<HTMLElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  useSkyHeight(mainRef, stageRef, pathname)
  useReveal(shellRef, pathname)
  useSpotlight(shellRef)

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
        <div className={pageClass}>
          <div className="appbar-inner flex items-center gap-2 sm:gap-4">
            <Link
              to="/"
              aria-label="MedPull home"
              className="brand-lockup shrink-0 rounded-pill pr-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
            >
              <span className="app-icon">
                <img src="/medpull-mark.png" alt="" aria-hidden width={22} height={22} />
              </span>
              <span className="hidden sm:inline">MedPull</span>
            </Link>

            <nav
              aria-label="Primary"
              className="relative min-w-0 overflow-x-auto [scrollbar-width:none] sm:mx-auto [&::-webkit-scrollbar]:hidden"
            >
              <div ref={trackRef} className="relative flex items-center gap-0.5 py-2">
                <span aria-hidden className="nav-rule" style={style} />
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
              </div>
            </nav>

            <div className="ml-auto flex shrink-0 items-center gap-0.5 sm:ml-0">
              {/* Phones hide the toggle (Settings has the same switch) so the
                  three nav items fit next to the bell. */}
              <span className="hidden sm:contents">
                <ThemeToggle />
              </span>
              <NotificationsPopover />
            </div>
          </div>
        </div>
      </header>

      <main
        ref={mainRef}
        id="main"
        tabIndex={-1}
        className={`${pageClass} flex-1 pb-20 pt-8 outline-0 [outline-style:none] sm:pt-12`}
      >
        <Outlet />
      </main>
    </div>
  )
}
