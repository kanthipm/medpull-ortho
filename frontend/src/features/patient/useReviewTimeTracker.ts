import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { rtmKeys } from '../../api/queries'

/** Quietly logs time spent reviewing a patient record to the RTM time ledger
 *  (chart-review activity, CPT 98980 clock).
 *
 *  Counts only engaged time, the way billing timers must: the clock pauses
 *  while the tab is hidden, and an engagement segment ends after two minutes
 *  without any interaction — a chart left open in a background tab accrues
 *  nothing. Posts once on leave via keepalive fetch; sub-15-second totals are
 *  discarded server-side. A logged segment moves the RTM minute count, so the
 *  readiness card and the practice strip are invalidated once it lands —
 *  otherwise the provider never sees the minutes they just earned.
 */
const IDLE_MS = 2 * 60_000

export default function useReviewTimeTracker(patientId: string) {
  const qc = useQueryClient()

  useEffect(() => {
    let accumulatedMs = 0
    let lastActivity = Date.now()
    // start of the current engaged segment; null while hidden/idle-flushed
    let segmentStart: number | null =
      document.visibilityState === 'visible' ? Date.now() : null
    let posted = false

    const closeSegment = () => {
      if (segmentStart == null) return
      // an idle tail never counts beyond the idle window after last activity
      const end = Math.min(Date.now(), lastActivity + IDLE_MS)
      if (end > segmentStart) accumulatedMs += end - segmentStart
      segmentStart = null
    }

    const onActivity = () => {
      const now = Date.now()
      if (document.visibilityState !== 'visible') return
      if (segmentStart == null) {
        segmentStart = now
      } else if (now - lastActivity > IDLE_MS) {
        // idle gap inside a segment: close it at the idle cutoff, start fresh
        closeSegment()
        segmentStart = now
      }
      lastActivity = now
    }

    const onVisibility = () => {
      if (document.visibilityState === 'hidden') {
        closeSegment()
      } else {
        segmentStart = Date.now()
        lastActivity = segmentStart
      }
    }

    const post = () => {
      if (posted) return
      posted = true
      closeSegment()
      const seconds = Math.round(accumulatedMs / 1000)
      if (seconds < 15) return
      fetch(`/api/patients/${patientId}/rtm/review-time`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seconds }),
        keepalive: true,
      })
        .then((res) => {
          if (!res.ok) return
          for (const queryKey of rtmKeys(patientId)) qc.invalidateQueries({ queryKey })
        })
        .catch(() => {})
    }

    const activityEvents = ['pointerdown', 'pointermove', 'keydown', 'wheel', 'scroll'] as const
    for (const event of activityEvents) {
      window.addEventListener(event, onActivity, { passive: true })
    }
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('pagehide', post)
    return () => {
      for (const event of activityEvents) window.removeEventListener(event, onActivity)
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pagehide', post)
      post()
    }
  }, [patientId, qc])
}
