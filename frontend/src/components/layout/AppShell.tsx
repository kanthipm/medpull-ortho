import { useLayoutEffect, useRef, type RefObject } from 'react'
import { Link, Outlet, useLocation } from 'react-router-dom'
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

/** The console shell.
 *
 *  ATMOSPHERE. `.ambient-host` is the full-bleed wrapper. Behind everything
 *  (z -1) sit the faint full-bleed `.ambient` echo and the `.sky-stage`,
 *  which holds ONE Aside-style rounded `.sky-window`: a static Medical Blue /
 *  Teal / indigo sky, framed with a hairline ring and a top highlight. The
 *  window takes the page's own centring and reaches --sky-pad into the
 *  gutter, so the bar's logo and the page head sit INSIDE the frame; its
 *  height follows the page head (useSkyHeight) and its tail fades out behind
 *  the first cards, which float over it.
 *
 *  WHY THE FRAME WRAPS ONLY THE HERO ZONE. Framing the whole page (Aside's
 *  marketing layout) would cost 2 x --sky-pad (56px at desktop, 16px on a
 *  phone) of column width on every card and table, on a console whose
 *  worklist rows already truncate at 1440px. Framing only the head costs
 *  NOTHING: the window is a background layer, the column keeps its full
 *  width, and the atmosphere still reads as an object (rounded top corners,
 *  ring, highlight) instead of a smear. Cards stay opaque, so no clinical
 *  number, row or risk pill ever sits on the sky.
 *
 *  GLASS BAR (R2). Sticky, transparent at scroll 0 (so it sits in the
 *  window like Aside's nav); once the scroll-edge sentinel leaves the
 *  viewport `data-scrolled` turns on the material (--panel at .73, blur 24,
 *  saturate 160, a top-edge sheen, hairline, float shadow). The bar carries
 *  ONLY ink. The kill switch, reduced transparency and missing
 *  backdrop-filter all make it opaque (index.css).
 *
 *  ALIGNMENT. The bar's inner row, the sky window and <main> all use the
 *  SAME per-route width class, so the logo lines up with the page's left
 *  edge on every page. */
export default function AppShell() {
  const { pathname } = useLocation()
  const { sentinelRef, scrolled } = useScrollEdge<HTMLSpanElement>()
  const active = useActiveRoute(NAV)
  const { trackRef, style } = useSlidingIndicator(active, NAV.length, 12)
  const pageClass = PAGE_CLASS[pageWidthFor(pathname)]
  const mainRef = useRef<HTMLElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  useSkyHeight(mainRef, stageRef, pathname)

  return (
    <div className="ambient-host flex min-h-screen flex-col">
      <div className="ambient" aria-hidden />
      <div ref={stageRef} className="sky-stage" aria-hidden>
        <div className={pageClass}>
          <div className="sky-window" />
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
        <div className={`${pageClass} flex min-h-bar items-center gap-3 sm:gap-6`}>
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
        ref={mainRef}
        id="main"
        tabIndex={-1}
        className={`${pageClass} flex-1 pb-16 pt-6 outline-0 [outline-style:none] sm:pt-8`}
      >
        <Outlet />
      </main>
    </div>
  )
}
