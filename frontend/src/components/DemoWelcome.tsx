import { ArrowRight, Stethoscope, Trophy, UserRound } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useIsDemo } from '../api/queries'
import { useWorkspaces, type Version, type Workspaces } from '../api/workspaces'
import { VERSION_HOME, VERSION_LABEL } from './layout/version'

/** The public demo's front door: a hazy glass screen over the console the
 *  first time a browser arrives. One sentence on what MedPull is, then the
 *  three versions of it as three cards, each going to that version's landing
 *  page, and a quiet way to stay where you are.
 *
 *  A card is offered only for a version this console can open and has
 *  something to show in: the open demo gets all three, an org's credential
 *  its own.
 *
 *  Shown once per browser (a localStorage flag, wrapped: a private window
 *  or blocked storage must not break the page or loop the screen). Gated on
 *  the server's own word (`demo` on /api/health), so a developer's localhost
 *  and the real deployment never see it; `?welcome` forces it for a look.
 *  Escape, a card and the quiet link all dismiss it; focus lands on the
 *  first card. The shell leaves it off the presenter's demo screen, and it
 *  is never on a page outside the shell (/login, /t, /a, /checkin). */

const STORAGE_KEY = 'medpull-console.demo-welcomed'

function forcedByUrl(): boolean {
  if (typeof window === 'undefined') return false
  return new URLSearchParams(window.location.search).has('welcome')
}

function alreadyWelcomed(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) != null
  } catch {
    return false
  }
}

function remember() {
  try {
    window.localStorage.setItem(STORAGE_KEY, new Date().toISOString())
  } catch {
    // storage blocked: the screen simply shows again next time
  }
}

const CARDS: Record<Version, { tile: string; icon: ReactNode; who: string; what: string }> = {
  clinic: {
    tile: 'tile-teal',
    icon: <Stethoscope />,
    who: 'For a clinic following patients between visits',
    what: 'Who needs a call today, the exercise calendar, and the data underneath.',
  },
  personal: {
    tile: 'tile-indigo',
    icon: <UserRound />,
    who: 'For a member reading their own body',
    what: 'Today’s read on recovery, thirteen weeks of trends, and every signal behind them.',
  },
  sports: {
    tile: 'tile-blue',
    icon: <Trophy />,
    who: 'For a team’s performance and medical staff',
    what: 'The morning board, the team calendar, and the roster’s data.',
  },
}

/** The versions worth a card: allowed for this console, and not empty. */
function offered(workspaces: Workspaces): Version[] {
  return workspaces.versions.filter(
    (version) =>
      version === 'clinic' ||
      (version === 'personal' ? workspaces.members.length > 0 : workspaces.teams.length > 0),
  )
}

export default function DemoWelcome() {
  const demo = useIsDemo()
  const workspaces = useWorkspaces().data
  const [dismissed, setDismissed] = useState(false)
  const [leaving, setLeaving] = useState(false)
  const firstRef = useRef<HTMLAnchorElement>(null)
  // The cards come from the workspaces, so the screen waits for them rather
  // than opening with three and settling on fewer.
  const open = !dismissed && workspaces != null && (forcedByUrl() || (demo && !alreadyWelcomed()))

  const close = () => {
    remember()
    setLeaving(true)
    window.setTimeout(() => setDismissed(true), 220)
  }

  useEffect(() => {
    if (!open) return
    firstRef.current?.focus({ preventScroll: true })
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!open) return null
  const versions = offered(workspaces)

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="demo-welcome-title"
      className={`scrim fixed inset-0 z-[80] overflow-y-auto transition-opacity duration-200 ${
        leaving ? 'opacity-0' : 'animate-fadeIn'
      }`}
    >
      <div className="grid min-h-full place-items-center p-4 sm:p-6">
        <div className="panel animate-modalIn motion-reduce:animate-none w-full max-w-[760px] px-5 py-7 text-center sm:px-10 sm:py-10">
          <span className="tile tile-frost mx-auto !h-12 !w-12 !rounded-[14px]" aria-hidden>
            <img src="/medpull-mark.svg" alt="" width={24} height={24} />
          </span>
          <p className="meta mt-4 uppercase tracking-label sm:mt-5">Public demo</p>
          <h1
            id="demo-welcome-title"
            className="display-title mt-2 text-[1.75rem] leading-tight text-ink sm:text-[2.125rem]"
          >
            Welcome to MedPull
          </h1>
          <p className="mx-auto mt-3 max-w-[46ch] text-copy-lg text-body sm:mt-4">
            MedPull reads a person’s watch and phone between visits and shows the people looking
            after them who needs attention today, and why. It comes in three versions.
          </p>

          <ul
            className={`mt-6 grid gap-3 text-left sm:mt-7 ${
              versions.length === 3 ? 'sm:grid-cols-3' : versions.length === 2 ? 'sm:grid-cols-2' : ''
            }`}
          >
            {versions.map((version, i) => {
              const card = CARDS[version]
              return (
                <li key={version} className="flex">
                  <Link
                    ref={i === 0 ? firstRef : undefined}
                    to={VERSION_HOME[version]}
                    onClick={close}
                    className="well group flex w-full items-start gap-3 p-4 transition-colors duration-state ease-apple hover:bg-[rgb(var(--fill))] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus sm:flex-col sm:gap-0 sm:p-5"
                  >
                    <span className={`tile ${card.tile} tile-lg`} aria-hidden>
                      {card.icon}
                    </span>
                    <span className="min-w-0 flex-1 sm:mt-4">
                      <span className="flex items-center gap-1.5 text-copy-lg font-medium text-ink">
                        {VERSION_LABEL[version]}
                        <ArrowRight
                          size={16}
                          aria-hidden
                          className="text-body transition-transform duration-state group-hover:translate-x-0.5"
                        />
                      </span>
                      <span className="mt-1 block text-copy text-ink">{card.who}</span>
                      <span className="mt-1.5 hidden text-copy text-secondary sm:block">{card.what}</span>
                    </span>
                  </Link>
                </li>
              )
            })}
          </ul>

          <div className="mt-5 sm:mt-6">
            <button type="button" className="btn-plain btn-sm" onClick={close}>
              Just look around
            </button>
          </div>
          <p className="meta mt-4 sm:mt-5">
            Every chart here runs on demo data. Monitoring signals for clinician review, not a
            diagnosis.
          </p>
        </div>
      </div>
    </div>
  )
}
