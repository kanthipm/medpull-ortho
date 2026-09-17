import { Bell, BellRing } from 'lucide-react'
import { useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from '../api/queries'
import { relativeTime } from '../lib/format'
import ListRow, { ListGroup } from './ListRow'
import { Popover } from './Menu'
import Tile from './Tile'

/** The bell in the app bar and its popover.
 *
 *  The trigger is an ink `.btn-icon` (the bar carries ink only, R2). The
 *  unread badge is a risk-ink dot with a --panel ring; the count is in the
 *  accessible name, so the dot is never the only carrier.
 *
 *  The panel is a top-layer `Popover` (R5): 20px `.overlay`, soft layered
 *  shadow, opaque. Rows are ListRows with a blue Bell tile; every secondary
 *  line inside is --body (the overlay scope), because dark --muted on the
 *  overlay panel is 3.655:1 and --body is 4.955:1 (7.222 light). */
export default function NotificationsPopover() {
  const [open, setOpen] = useState(false)
  const { data } = useNotifications()
  const markRead = useMarkNotificationRead()
  const markAll = useMarkAllNotificationsRead()
  const navigate = useNavigate()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()
  const headingId = useId()

  const notifications = data?.notifications ?? []
  const unread = notifications.filter((n) => n.status === 'unread').length

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={`Notifications${unread ? `, ${unread} unread` : ''}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-controls={open ? panelId : undefined}
        className="btn-icon relative"
      >
        <Bell aria-hidden size={20} />
        {unread > 0 && (
          <span
            aria-hidden
            className="absolute right-[7px] top-[7px] h-2.5 w-2.5 rounded-pill bg-risk-high-ink ring-2 ring-panel"
          />
        )}
      </button>
      <Popover
        open={open}
        onClose={() => setOpen(false)}
        anchorRef={triggerRef}
        placement="bottom-end"
        id={panelId}
        aria-labelledby={headingId}
        className="w-[min(24rem,calc(100vw-16px))] overflow-hidden"
      >
        <div className="flex min-h-[52px] items-center justify-between gap-3 px-5 pb-1 pt-3">
          <h2 id={headingId} className="text-copy-lg font-semibold text-ink">
            Notifications
          </h2>
          {unread > 0 && (
            <button type="button" onClick={() => markAll.mutate()} className="btn-plain btn-sm -mr-2">
              Mark all read
            </button>
          )}
        </div>
        <div className="max-h-[min(28rem,70vh)] overflow-y-auto pb-2">
          {notifications.length === 0 ? (
            <div className="flex flex-col items-center px-6 pb-6 pt-4 text-center">
              <Tile family="blue" size="lg" icon={<BellRing />} />
              <p className="mt-3 text-copy font-medium text-ink">You're all caught up</p>
              <p className="mt-1 max-w-[28ch] text-copy text-secondary">
                Anything that needs your attention will show up here.
              </p>
            </div>
          ) : (
            <ListGroup embedded inset="tile" aria-label="Recent notifications">
              {notifications.map((n) => {
                const isUnread = n.status === 'unread'
                return (
                  <ListRow
                    key={n.id}
                    compact
                    leading={<Tile family="blue" icon={<Bell />} />}
                    title={n.title}
                    linkLabel={`${isUnread ? 'Unread: ' : ''}${n.title}`}
                    subtitle={n.body}
                    meta={<span className="tabular-nums">{relativeTime(n.created_at)}</span>}
                    onClick={() => {
                      if (isUnread) markRead.mutate(n.id)
                      setOpen(false)
                      navigate(`/patients/${n.patient_id}`)
                    }}
                    trailing={
                      isUnread ? (
                        <span
                          aria-hidden
                          className="pointer-events-none h-2 w-2 rounded-pill bg-brand"
                        />
                      ) : undefined
                    }
                    subtitleLines={2}
                  />
                )
              })}
            </ListGroup>
          )}
        </div>
      </Popover>
    </>
  )
}
