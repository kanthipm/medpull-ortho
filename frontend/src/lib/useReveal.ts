import { useEffect, type RefObject } from 'react'

/** The site's motion plumbing, for everything under `rootRef`:
 *
 *  - `.reveal` blocks start hidden (opacity 0, 22px down) and get `.is-shown`
 *    as they scroll into view, once. Stagger with `style={{ '--d': n }}`.
 *  - `[data-loop]` blocks (drifting fog, comets, breathing bars) get
 *    `.is-paused` while they are off screen, so no loop animates unseen.
 *
 *  `html.js-reveal` arms the hidden state only once this runs, so a page
 *  without JS, or before hydration, never renders invisible content.
 *  New nodes (route changes, data arriving) are picked up by a
 *  MutationObserver. Reduced motion is handled in CSS: `.reveal` has no
 *  transition and no offset there. */
export function useReveal(rootRef: RefObject<HTMLElement | null>, key?: unknown) {
  useEffect(() => {
    const root = rootRef.current
    if (!root || typeof IntersectionObserver === 'undefined') return
    document.documentElement.classList.add('js-reveal')

    const shown = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('is-shown')
            shown.unobserve(e.target)
          }
        }
      },
      { rootMargin: '0px 0px -6% 0px', threshold: 0.01 },
    )
    const loops = new IntersectionObserver((entries) => {
      for (const e of entries) e.target.classList.toggle('is-paused', !e.isIntersecting)
    })

    const seen = new WeakSet<Element>()
    const scan = () => {
      root.querySelectorAll('.reveal:not(.is-shown)').forEach((el) => {
        if (seen.has(el)) return
        seen.add(el)
        shown.observe(el)
      })
      root.querySelectorAll('[data-loop]').forEach((el) => {
        if (seen.has(el)) return
        seen.add(el)
        loops.observe(el)
      })
    }
    scan()
    let raf = 0
    const mo = new MutationObserver(() => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(scan)
    })
    mo.observe(root, { childList: true, subtree: true })

    return () => {
      cancelAnimationFrame(raf)
      mo.disconnect()
      shown.disconnect()
      loops.disconnect()
    }
  }, [rootRef, key])
}

/** Sets `--mx` / `--my` on `.spotlight` elements under `rootRef` as the
 *  pointer moves over them (the site's hover light). One delegated listener,
 *  batched to one write per frame; fine pointers only. */
export function useSpotlight(rootRef: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const root = rootRef.current
    if (!root || !window.matchMedia?.('(hover: hover) and (pointer: fine)').matches) return
    let raf = 0
    let last: PointerEvent | null = null
    const apply = () => {
      raf = 0
      const e = last
      if (!e) return
      const el = (e.target as Element | null)?.closest?.('.spotlight') as HTMLElement | null
      if (!el) return
      const r = el.getBoundingClientRect()
      el.style.setProperty('--mx', `${e.clientX - r.left}px`)
      el.style.setProperty('--my', `${e.clientY - r.top}px`)
    }
    const onMove = (e: PointerEvent) => {
      last = e
      if (!raf) raf = requestAnimationFrame(apply)
    }
    root.addEventListener('pointermove', onMove, { passive: true })
    return () => {
      root.removeEventListener('pointermove', onMove)
      cancelAnimationFrame(raf)
    }
  }, [rootRef])
}
