import { useEffect, useRef, useState, type RefObject } from 'react'

/** Scroll-edge detection for the glass app bar (R2).
 *
 *  Render the returned `sentinelRef` on a 1px element pinned to the very top
 *  of the document (AppShell does this). While that sentinel is on screen the
 *  page is at scroll 0 and the bar stays transparent over the ambient wash;
 *  once it leaves, `scrolled` is true and the bar turns into the material.
 *
 *  An IntersectionObserver does the work (no per-frame scroll handler). Where
 *  IntersectionObserver is missing it falls back to a passive scroll listener. */
export function useScrollEdge<T extends HTMLElement = HTMLSpanElement>(): {
  sentinelRef: RefObject<T | null>
  scrolled: boolean
} {
  const sentinelRef = useRef<T | null>(null)
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const el = sentinelRef.current
    if (typeof IntersectionObserver === 'undefined' || !el) {
      const onScroll = () => setScrolled(window.scrollY > 0)
      onScroll()
      window.addEventListener('scroll', onScroll, { passive: true })
      return () => window.removeEventListener('scroll', onScroll)
    }
    const io = new IntersectionObserver(([entry]) => setScrolled(!entry.isIntersecting), {
      threshold: 0,
    })
    io.observe(el)
    return () => io.disconnect()
  }, [])

  return { sentinelRef, scrolled }
}

/** True once `targetRef`'s element has scrolled up underneath the app bar
 *  (its bottom edge is above `offset` px from the viewport top). Use it for
 *  an optional compact title in the bar: when the page h1 is covered, show
 *  the name in the bar — ink text only, never a risk pill or a number (R2).
 *  `offset` defaults to the 56px bar height. */
export function useScrolledPast(
  targetRef: RefObject<HTMLElement | null>,
  { offset = 56 }: { offset?: number } = {},
): boolean {
  const [past, setPast] = useState(false)

  useEffect(() => {
    const el = targetRef.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') {
      const onScroll = () => setPast(el.getBoundingClientRect().bottom < offset)
      onScroll()
      window.addEventListener('scroll', onScroll, { passive: true })
      return () => window.removeEventListener('scroll', onScroll)
    }
    const io = new IntersectionObserver(
      ([entry]) => setPast(!entry.isIntersecting && entry.boundingClientRect.bottom < offset),
      { rootMargin: `-${offset}px 0px 0px 0px`, threshold: 0 },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [targetRef, offset])

  return past
}
