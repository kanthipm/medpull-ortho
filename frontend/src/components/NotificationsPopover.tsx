import { Bell } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from '../api/queries'
import { relativeTime } from '../lib/format'

/** The popover panel is a genuinely floating surface, so it is `.overlay`:
 *  the ambient shadow, dark's own 1px hairline and the forced-colors border,
 *  and no `border border-line shadow-card` double edge.
 *
 *  Every secondary line inside it is --body, not --muted. Dark's overlay panel
 *  is --n-700 #2A333D, where --muted #7F8A98 measures 3.655:1 — an AA failure.
 *  --body #98A2AF is 4.955:1 there and 7.222:1 on the light overlay panel. */
export default function NotificationsPopover() {
  const [open, setOpen] = useState(false)
  const { data } = useNotifications()
  const markRead = useMarkNotificationRead()
  const markAll = useMarkAllNotificationsRead()
  const navigate = useNavigate()
  const triggerRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (!open) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        triggerRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open])

  const notifications = data?.notifications ?? []
  const unread = notifications.filter((n) => n.status === 'unread').length

  return (
    <div className="relative">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        className="relative grid h-10 w-10 cursor-pointer place-items-center rounded-control text-body transition-colors duration-150 hover:bg-soft hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
      >
        <Bell size={20} />
        {unread > 0 && (
          <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-pill bg-risk-high-ink ring-2 ring-panel" />
        )}
      </button>
      {open && (
        <>
          <div aria-hidden className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div
            role="dialog"
            aria-label="Notifications"
            className="overlay absolute right-0 z-40 mt-seam w-96 animate-modalIn overflow-hidden"
          >
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              {/* Sentence case. An overlay opens over a page that has already
                  spent its one all-caps element, so the popover header does not
                  take the eyebrow recipe. */}
              <span className="text-label font-medium text-body">Notifications</span>
              {unread > 0 && (
                <button
                  type="button"
                  onClick={() => markAll.mutate()}
                  className="cursor-pointer text-label font-medium text-brand-ink hover:underline"
                >
                  Mark all read
                </button>
              )}
            </div>
            <div className="max-h-96 overflow-y-auto">
              {notifications.length === 0 && (
                <p className="px-4 py-8 text-center text-copy text-body">
                  Nothing needs your attention right now.
                </p>
              )}
              {notifications.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => {
                    if (n.status === 'unread') markRead.mutate(n.id)
                    setOpen(false)
                    navigate(`/patients/${n.patient_id}`)
                  }}
                  className="flex w-full cursor-pointer items-start gap-tight border-b border-line px-4 py-3 text-left transition-colors duration-150 last:border-0 hover:bg-soft focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand"
                >
                  <span
                    className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-pill ${
                      n.status === 'unread' ? 'bg-risk-high-ink' : 'bg-faint'
                    }`}
                  />
                  <span>
                    <span className="block text-copy font-medium text-ink">{n.title}</span>
                    <span className="block text-copy text-body">{n.body}</span>
                    <span className="mt-el block font-mono text-label text-body">
                      {relativeTime(n.created_at)}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
