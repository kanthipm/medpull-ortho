import {
  Check,
  ChevronDown,
  LogOut,
  MonitorSmartphone,
  Plug,
  Settings,
  Stethoscope,
  Trophy,
  UserRound,
} from 'lucide-react'
import {
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
} from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { setActingClinic } from '../../api/client'
import type { ConsoleSession } from '../../api/types'
import type { Version, Workspaces } from '../../api/workspaces'
import { Popover } from '../Menu'
import { VERSION_LABEL } from './version'
import {
  workspaceGroups,
  workspacePlace,
  type WorkspaceAt,
  type WorkspaceRow,
} from './workspaceRows'

/** The workspace menu: the capsule at the right of the bar that says where
 *  the console is ("Clinic · H.I.R.T.", "Personal · Jordan Avery",
 *  "Sports · Rice MBB") and opens the list of everywhere it can go.
 *
 *  TRIGGER. A ringed capsule on the glass bar: the version's glyph tile, the
 *  version and the place, a chevron. Below 640px the place is dropped and
 *  only the version's name shows; below 400px the chevron goes too, so three
 *  tabs, the bell and this still fit a phone.
 *
 *  PANEL. A top-layer `Popover` (R5) with `role="menu"`. One group per
 *  version this console may use and has rows for (clinics with their chart
 *  count, members with their goal, teams with their program and roster), a
 *  check on the row that is on screen, then the pages that are not tabs:
 *  the demo screen, integrations, settings, and Sign out. A console with one
 *  workspace has nothing to switch between, so its panel names the workspace
 *  and lists only those pages.
 *
 *  Every row is a real link, so it can be opened in a new tab. A clinic row
 *  on a staff console is `/?clinic=<id>`: followed in place it sets the
 *  acting clinic and goes to the worklist; opened in a new tab the address
 *  does the same there.
 *
 *  KEYBOARD. Enter, Space or ArrowDown on the trigger opens with focus on the
 *  current row; ArrowUp/Down, Home and End move; Enter follows; Escape closes
 *  and returns focus to the trigger; Tab closes. */

const GLYPH: Record<Version, { tile: string; icon: ReactNode }> = {
  clinic: { tile: 'tile-teal', icon: <Stethoscope /> },
  personal: { tile: 'tile-indigo', icon: <UserRound /> },
  sports: { tile: 'tile-blue', icon: <Trophy /> },
}

const ITEMS = '[role="menuitem"], [role="menuitemradio"]'

function itemsIn(menuId: string): HTMLElement[] {
  return Array.from(document.getElementById(menuId)?.querySelectorAll<HTMLElement>(ITEMS) ?? [])
}

/** The quiet uppercase label over a group. `text-secondary`, not `.micro`'s
 *  --muted: inside an overlay the secondary role is --body, which clears
 *  4.5:1 on the dark overlay panel where --muted does not. */
const GROUP_LABEL = 'text-label font-medium uppercase tracking-eyebrow text-secondary'

const ROW =
  'flex min-h-9 w-full cursor-pointer items-start gap-2.5 rounded-control-sm px-2.5 py-2 text-left text-copy text-ink transition-colors duration-state ease-apple hover:bg-soft focus-visible:bg-soft focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus'

const ROW_ICON = 'mt-0.5 shrink-0 text-body'

/** A click the browser should handle itself: a new tab or window. */
function opensElsewhere(e: ReactMouseEvent): boolean {
  return e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey
}

export default function WorkspaceMenu({
  workspaces,
  scope,
  at,
  demo,
  onSignOut,
}: {
  workspaces: Workspaces
  scope: ConsoleSession['scope']
  at: WorkspaceAt
  /** The demo stack: the room's demo screen is offered to staff. */
  demo: boolean
  /** Present when a token is stored: the menu then ends with Sign out. */
  onSignOut?: () => void
}) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuId = useId()
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const staff = scope.kind === 'all'

  const groups = workspaceGroups(workspaces, staff, at)
  const place = workspacePlace(workspaces, staff, at)
  // With one workspace there is nothing to switch between: the panel names
  // it instead of listing it.
  const switchable = groups.reduce((n, g) => n + g.rows.length, 0) > 1
  const glyph = GLYPH[at.version]

  // Focus lands on the row that is on screen, else the first; one frame
  // late, once the panel has its position and can take focus.
  useEffect(() => {
    if (!open) return
    const frame = requestAnimationFrame(() => {
      const all = itemsIn(menuId)
      const current = all.find(
        (el) => el.getAttribute('aria-checked') === 'true' || el.hasAttribute('aria-current'),
      )
      ;(current ?? all[0])?.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [open, menuId])

  const close = () => {
    setOpen(false)
    triggerRef.current?.focus({ preventScroll: true })
  }

  const onMenuKey = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Tab') {
      setOpen(false)
      return
    }
    const move: Record<string, (i: number, n: number) => number> = {
      ArrowDown: (i, n) => (i + 1) % n,
      ArrowUp: (i, n) => (i - 1 + n) % n,
      Home: () => 0,
      End: (_, n) => n - 1,
    }
    const step = move[e.key]
    if (!step) return
    const all = itemsIn(menuId)
    if (all.length === 0) return
    e.preventDefault()
    all[step(all.indexOf(document.activeElement as HTMLElement), all.length)].focus()
  }

  const pick = (row: WorkspaceRow) => (e: ReactMouseEvent) => {
    if (opensElsewhere(e)) return
    close()
    if (row.clinic === undefined) return
    // A staff clinic row: set the header before anything is fetched for the
    // worklist, then go there. The address needs no `?clinic=`.
    e.preventDefault()
    setActingClinic(row.clinic)
    navigate('/')
  }

  const follow = (e: ReactMouseEvent) => {
    if (!opensElsewhere(e)) close()
  }

  const label = `Workspace: ${VERSION_LABEL[at.version]}${place ? `, ${place}` : ''}`

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((o) => !o)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' && !open) {
            e.preventDefault()
            setOpen(true)
          }
        }}
        className="group inline-flex h-10 min-w-0 cursor-pointer items-center gap-1.5 rounded-pill pl-1 pr-2.5 text-copy text-ink shadow-[inset_0_0_0_1px_rgb(var(--line))] transition-colors duration-state ease-apple hover:bg-[rgb(var(--fill))] aria-expanded:bg-[rgb(var(--fill))] min-[400px]:gap-2 min-[400px]:pl-1.5"
      >
        <span
          aria-hidden
          className={`tile ${glyph.tile} !h-6 !w-6 !rounded-[8px] min-[400px]:!h-7 min-[400px]:!w-7 min-[400px]:!rounded-[9px] [&_svg]:!h-3.5 [&_svg]:!w-3.5`}
        >
          {glyph.icon}
        </span>
        <span className="min-w-0 truncate">
          <span className="font-medium">{VERSION_LABEL[at.version]}</span>
          {place && <span className="hidden text-body sm:inline"> · {place}</span>}
        </span>
        <ChevronDown
          aria-hidden
          size={14}
          className="hidden shrink-0 text-body transition-transform duration-state group-aria-expanded:rotate-180 min-[400px]:block"
        />
      </button>
      <Popover
        open={open}
        onClose={() => setOpen(false)}
        anchorRef={triggerRef}
        placement="bottom-end"
        variant="menu"
        role="menu"
        id={menuId}
        aria-label="Workspaces"
        autoFocus={false}
        onKeyDown={onMenuKey}
        className="max-h-[min(38rem,calc(100dvh-5.5rem))] w-[min(21rem,calc(100vw-16px))] overflow-y-auto overscroll-contain"
      >
        {switchable ? (
          groups.map((group, i) => (
            <WorkspaceGroupRows
              key={group.version}
              label={group.label}
              rows={group.rows}
              first={i === 0}
              onPick={pick}
            />
          ))
        ) : (
          <div className="px-2.5 pb-1.5 pt-2">
            <p className={GROUP_LABEL}>{VERSION_LABEL[at.version]}</p>
            <p className="mt-1 text-copy font-medium text-ink">{groups[0]?.rows[0]?.title ?? scope.name}</p>
            {groups[0]?.rows[0]?.detail && <p className="meta mt-0.5">{groups[0].rows[0].detail}</p>}
          </div>
        )}

        <div role="separator" className="mx-1 my-1.5 h-px bg-hairline" />

        {demo && staff && (
          <Link
            role="menuitem"
            tabIndex={-1}
            to="/demo/hirt"
            onClick={follow}
            aria-current={pathname.startsWith('/demo/') ? 'page' : undefined}
            className={ROW}
          >
            <MonitorSmartphone aria-hidden size={16} className={ROW_ICON} />
            <span className="font-medium">Demo screen</span>
          </Link>
        )}
        {staff && (
          <Link
            role="menuitem"
            tabIndex={-1}
            to="/integrations"
            onClick={follow}
            aria-current={pathname.startsWith('/integrations') ? 'page' : undefined}
            className={ROW}
          >
            <Plug aria-hidden size={16} className={ROW_ICON} />
            <span className="font-medium">Integrations</span>
          </Link>
        )}
        <Link
          role="menuitem"
          tabIndex={-1}
          to="/settings/notifications"
          onClick={follow}
          aria-current={pathname.startsWith('/settings') ? 'page' : undefined}
          className={ROW}
        >
          <Settings aria-hidden size={16} className={ROW_ICON} />
          <span className="font-medium">Settings</span>
        </Link>
        {onSignOut && (
          <button
            type="button"
            role="menuitem"
            tabIndex={-1}
            onClick={() => {
              setOpen(false)
              onSignOut()
            }}
            className={ROW}
          >
            <LogOut aria-hidden size={16} className={ROW_ICON} />
            <span className="min-w-0">
              <span className="block font-medium">Sign out</span>
              <span className="meta mt-0.5 block truncate">Signed in as {scope.label}</span>
            </span>
          </button>
        )}
      </Popover>
    </>
  )
}

/** One version's rows under its quiet uppercase label. The rows are a
 *  single-choice set, so each is a `menuitemradio` and the one on screen is
 *  checked (and carries the check mark, since the state is never colour). */
function WorkspaceGroupRows({
  label,
  rows,
  first,
  onPick,
}: {
  label: string
  rows: WorkspaceRow[]
  first: boolean
  onPick: (row: WorkspaceRow) => (e: ReactMouseEvent) => void
}) {
  const labelId = useId()
  return (
    <div role="group" aria-labelledby={labelId} className={first ? '' : 'mt-1.5'}>
      <p id={labelId} className={`${GROUP_LABEL} px-2.5 pb-1 pt-2`}>
        {label}
      </p>
      {rows.map((row) => (
        <Link
          key={row.key}
          role="menuitemradio"
          aria-checked={row.current}
          tabIndex={-1}
          to={row.to}
          onClick={onPick(row)}
          className={ROW}
        >
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium">{row.title}</span>
            {row.detail && <span className="meta mt-0.5 block truncate">{row.detail}</span>}
          </span>
          {row.current && <Check aria-hidden size={16} className="mt-0.5 shrink-0" />}
        </Link>
      ))}
    </div>
  )
}
