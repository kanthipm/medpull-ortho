import { Bell } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from '../api/queries'
import { relativeTime } from '../lib/format'

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
        className="relative grid h-8 w-8 cursor-pointer place-items-center rounded-btn border border-line bg-panel text-muted transition-colors duration-150 hover:bg-soft hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
      >
        <Bell size={15} />
        {unread > 0 && (
          <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-risk-high ring-2 ring-white" />
        )}
      </button>
      {open && (
        <>
          <div aria-hidden className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div
            role="dialog"
            aria-label="Notifications"
            className="absolute right-0 z-40 mt-2 w-96 animate-modalIn overflow-hidden rounded-card border border-line bg-panel shadow-glass"
          >
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <span className="micro">Notifications</span>
              {unread > 0 && (
                <button
                  type="button"
                  onClick={() => markAll.mutate()}
                  className="cursor-pointer text-[12px] font-medium text-brand hover:underline"
                >
                  Mark all read
                </button>
              )}
            </div>
            <div className="max-h-96 overflow-y-auto">
              {notifications.length === 0 && (
                <p className="px-4 py-8 text-center text-[13px] font-medium text-faint">
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
                  className="flex w-full cursor-pointer items-start gap-3 border-b border-line px-4 py-3 text-left transition-colors duration-150 last:border-0 hover:bg-soft/70"
                >
                  <span
                    className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                      n.status === 'unread' ? 'bg-risk-high' : 'bg-line'
                    }`}
                  />
                  <span>
                    <span className="block text-[13px] font-semibold tracking-[-.01em] text-ink">
                      {n.title}
                    </span>
                    <span className="block text-[12.5px] font-medium text-muted">{n.body}</span>
                    <span className="mt-0.5 block font-mono text-[11px] font-medium text-faint">
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
