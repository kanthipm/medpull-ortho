import { useEffect, useRef, useState } from 'react'

/** The public demo's front door on app.medpull.org: a hazy glass screen over
 *  the worklist the first time a browser arrives, one line on what MedPull
 *  does, and a button that drops you on the product's own question — who
 *  needs a call today.
 *
 *  Shown once per browser (a localStorage flag, wrapped: a private window
 *  or blocked storage must not break the page or loop the screen). Gated to
 *  the public host so a developer's localhost and the clinic's own
 *  deployment never see it; `?welcome` forces it for a look. Escape, the
 *  button and the quiet link all dismiss it; focus lands on the button. */

const STORAGE_KEY = 'medpull.demo-welcomed'
const PUBLIC_HOST = 'app.medpull.org'

function wantsWelcome(): boolean {
  if (typeof window === 'undefined') return false
  const forced = new URLSearchParams(window.location.search).has('welcome')
  if (forced) return true
  if (window.location.hostname !== PUBLIC_HOST) return false
  try {
    return window.localStorage.getItem(STORAGE_KEY) == null
  } catch {
    return true
  }
}

function remember() {
  try {
    window.localStorage.setItem(STORAGE_KEY, new Date().toISOString())
  } catch {
    // storage blocked: the screen simply shows again next time
  }
}

export default function DemoWelcome() {
  const [open, setOpen] = useState(wantsWelcome)
  const [leaving, setLeaving] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)

  const close = () => {
    remember()
    setLeaving(true)
    window.setTimeout(() => setOpen(false), 220)
  }

  useEffect(() => {
    if (!open) return
    buttonRef.current?.focus({ preventScroll: true })
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="demo-welcome-title"
      className={`scrim fixed inset-0 z-[80] grid place-items-center p-6 transition-opacity duration-200 ${
        leaving ? 'opacity-0' : 'animate-fadeIn'
      }`}
    >
      <div className="panel animate-modalIn motion-reduce:animate-none w-full max-w-[520px] px-7 py-8 text-center sm:px-10 sm:py-10">
        <span className="tile tile-frost mx-auto !h-12 !w-12 !rounded-[14px]" aria-hidden>
          <img src="/medpull-mark.svg" alt="" width={24} height={24} />
        </span>
        <p className="meta mt-5 uppercase tracking-label">Public demo</p>
        <h1
          id="demo-welcome-title"
          className="display-title mt-2 text-[1.75rem] leading-tight text-ink sm:text-[2.125rem]"
        >
          Welcome to our public demo!
        </h1>
        <p className="mx-auto mt-4 max-w-[38ch] text-copy-lg text-body">
          MedPull listens to a patient&rsquo;s watch and phone after surgery and tells the care
          team who needs a call today, and why, before the patient has to ask.
        </p>
        <p className="mx-auto mt-2 max-w-[40ch] text-copy text-secondary">
          Every chart here runs on demo data. Hover any metric&rsquo;s{' '}
          <span className="font-medium text-ink">i</span> to see how it works, and watch a
          thin record count down the days until its readings show.
        </p>
        <div className="mt-7 flex flex-col items-center gap-3">
          <button ref={buttonRef} type="button" className="btn-filled" onClick={close}>
            <span className="dot-lime" aria-hidden />
            See who needs you today
          </button>
          <button type="button" className="btn-plain btn-sm" onClick={close}>
            Just look around
          </button>
        </div>
        <p className="meta mt-6">Monitoring signals for clinician review, not a diagnosis.</p>
      </div>
    </div>
  )
}
