import { ChevronLeft, ChevronRight, RefreshCw, Smartphone } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/client'
import type { DemoPatientSession } from '../../api/hep'
import { useDemoPatientSession, useHepOptions } from '../../api/hep'
import { useHealth } from '../../api/queries'
import { SkeletonCard } from '../../components/Skeleton'
import ScheduleBoard from './ScheduleBoard'

const LABEL = 'mb-1 block px-1 text-label font-medium tracking-label text-secondary'

/** The phone's points, and the bezel around its screen. */
const PHONE_W = 390
const PHONE_H = 844
const BEZEL = 12

/** `/demo/hirt` — the room's screen: the clinic's week on the left (two
 *  thirds, polling), a lifter's phone on the right (a 390×844 frame scaled
 *  to the viewport, holding the patient web app signed in through a demo
 *  session). Demo stacks only: anywhere else it says so in one line. */
export default function DemoScreenPage() {
  const health = useHealth()
  if (health.isLoading) return <SkeletonCard lines={3} />
  if (!health.data?.demo) {
    return (
      <div className="pb-10">
        <header data-hero>
          <h1 className="display-title text-display text-ink">Demo screen</h1>
        </header>
        <p className="mt-4 text-copy-lg text-body">This screen is for the demo stack.</p>
        <Link to="/exercise-schedule" className="btn-plain btn-sm -ml-3 mt-4">
          <ChevronLeft size={16} aria-hidden /> Back to the schedule
        </Link>
      </div>
    )
  }
  return <DemoScreen />
}

interface Frame {
  token: string
  patient: DemoPatientSession['patient']
  /** Changes on every sign-in and reload, so the iframe remounts. */
  nonce: number
}

function DemoScreen() {
  const options = useHepOptions()
  const session = useDemoPatientSession()
  const [patientId, setPatientId] = useState('')
  const [frame, setFrame] = useState<Frame | null>(null)
  const [error, setError] = useState<string | null>(null)
  const lifters = options.data?.patients ?? []

  const signIn = (id: string) => {
    setPatientId(id)
    setError(null)
    if (!id) {
      setFrame(null)
      return
    }
    session.mutate(id, {
      onSuccess: (r) => setFrame({ token: r.token, patient: r.patient, nonce: Date.now() }),
      onError: (e) =>
        setError(
          e instanceof ApiError && e.status === 404
            ? 'The demo session route is off here — this is not the demo stack.'
            : e instanceof Error && e.message
              ? e.message
              : 'The phone could not be signed in',
        ),
    })
  }

  return (
    <div
      className="flex min-h-[560px] flex-col"
      style={{ height: 'calc(100dvh - var(--bar-height) - 2 * var(--bar-inset) - 2rem)' }}
    >
      <header data-hero className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1">
        <h1 className="text-subhead font-medium text-ink">H.I.R.T. demo screen</h1>
        <p className="text-copy text-body">The clinic’s week on the left, the lifter’s phone on the right.</p>
        <Link to="/exercise-schedule" className="btn-plain btn-sm ml-auto">
          Schedule <ChevronRight size={14} aria-hidden />
        </Link>
      </header>

      <div className="mt-4 grid min-h-0 flex-1 gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(300px,1fr)]">
        <section aria-label="Schedule" className="min-h-0 overflow-auto pr-1">
          <ScheduleBoard live dense />
        </section>

        <aside aria-label="Lifter’s phone" className="flex min-h-0 flex-col">
          <div className="flex items-end gap-2">
            <label className="min-w-0 flex-1">
              <span className={LABEL}>Lifter</span>
              <select
                className="field cursor-pointer"
                value={patientId}
                disabled={options.isLoading}
                onChange={(e) => signIn(e.target.value)}
              >
                <option value="">Choose a lifter…</option>
                {lifters.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="btn-icon"
              aria-label="Reload the phone"
              disabled={!frame}
              onClick={() => frame && setFrame({ ...frame, nonce: Date.now() })}
            >
              <RefreshCw aria-hidden size={16} />
            </button>
          </div>
          <p className="meta mt-1.5 min-h-[1.25rem] px-1" role="status">
            {session.isPending
              ? 'Signing the phone in…'
              : error
                ? <span className="text-risk-high-ink">{error}</span>
                : frame
                  ? `Signed in as ${frame.patient.name}`
                  : options.isError
                    ? 'The lifters couldn’t be loaded.'
                    : 'Pick a lifter to sign the phone in.'}
          </p>
          <PhoneFrame frame={frame} pending={session.isPending} />
        </aside>
      </div>
    </div>
  )
}

/** A phone at 390×844 points inside a rounded bezel, scaled to whatever
 *  height and width the column has, holding the patient web app. The
 *  outer box takes the scaled size so the layout below it is right; the
 *  frame inside is laid out at full size and transformed down. */
function PhoneFrame({ frame, pending }: { frame: Frame | null; pending: boolean }) {
  const box = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.5)
  const outerW = PHONE_W + 2 * BEZEL
  const outerH = PHONE_H + 2 * BEZEL

  useEffect(() => {
    const el = box.current
    if (!el || typeof ResizeObserver === 'undefined') return
    // ResizeObserver reports once on observe, so the first measure needs no
    // call of its own.
    const ro = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect
      const s = Math.min(width / outerW, height / outerH)
      setScale(Math.max(0.2, Math.min(1, Number.isFinite(s) ? s : 0.5)))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [outerW, outerH])

  return (
    <div ref={box} className="mt-3 flex min-h-0 flex-1 items-start justify-center">
      <div style={{ width: outerW * scale, height: outerH * scale }} className="relative">
        <div
          aria-hidden={!frame}
          className="absolute left-0 top-0 origin-top-left rounded-[56px] bg-[#101010] shadow-float"
          style={{ width: outerW, height: outerH, padding: BEZEL, transform: `scale(${scale})` }}
        >
          <div className="relative h-full w-full overflow-hidden rounded-[44px] bg-white">
            {frame ? (
              <iframe
                key={frame.nonce}
                title={`${frame.patient.name}’s phone`}
                src={`/patient/#session=${encodeURIComponent(frame.token)}`}
                className="h-full w-full border-0"
                allow="camera; microphone; accelerometer; gyroscope; autoplay"
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-3 bg-canvas px-8 text-center">
                <Smartphone aria-hidden size={40} className="text-muted" />
                <p className="text-lede text-ink">
                  {pending ? 'Signing in…' : 'Choose a lifter to sign this phone in.'}
                </p>
                <p className="text-copy text-body">
                  Their Today screen appears here; an exercise you add on the left shows up on it within
                  seconds.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
