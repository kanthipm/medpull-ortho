import { useQuery } from '@tanstack/react-query'
import { Globe, Smartphone } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { ApiError, fetchJson } from '../../api/client'
import { PatientShell, PatientStatus, PatientTitle } from '../checkin/CheckinPage'

/**
 * The page a texted link opens in a browser (/a/<token>). On a phone with
 * the MedPull app the link opens the app itself and this page is never seen;
 * everywhere else it offers the two ways on: the app, through its URL scheme
 * (a tap, because a browser only follows a custom scheme from a real
 * gesture), or the patient web app, which redeems the same token.
 *
 * Where the link may sign the person in (`signin`, the demo stack), the page
 * carries on to the browser by itself after two seconds, unless the app
 * button was tapped first. Reading the link has no side effect on the
 * server, so a message preview fetching this address changes nothing.
 *
 * Patient-facing, on an unknown and often older device, so it follows the
 * /checkin house rules (see CheckinPage): no glass, a 16px --ink body floor,
 * 56px targets, no uppercase, no 12px text. It never names a diagnosis: only
 * the clinic, the first name and the kind of thing the link opens.
 */

/** GET /api/links/{token} */
interface AppLink {
  kind: string
  ref_id: string | number | null
  day: string | null
  expires_at: string | null
  /** The link may start an app session by itself (the demo stack). */
  signin: boolean
  patient: { first_name: string }
  clinic: { name: string } | null
  app: { scheme: string; url: string }
  /** Where the patient web app redeems it: `/patient/#link=<token>`. */
  web: string
}

/** What the link opens, as the object of "sent you …". */
const THING: Record<string, string> = {
  today: 'your plan for today',
  exercise: 'an exercise to do',
  program: 'your program',
  task: 'something to do',
  checkin: 'a check-in',
  thread: 'a message',
  measure: 'something to measure',
  progress: 'your progress',
}

const AUTO_CONTINUE_MS = 2_000

/** The app's own scheme only: never a web address or a script. */
function appUrl(link: AppLink): string | null {
  const url = link.app?.url
  if (typeof url !== 'string') return null
  const scheme = /^([a-z][a-z0-9+.-]*):\/\//i.exec(url)?.[1].toLowerCase()
  if (!scheme || ['http', 'https', 'javascript', 'data', 'file', 'blob', 'vbscript'].includes(scheme)) {
    return null
  }
  return url
}

/** A path on this site only; the documented address when the answer's is not one. */
function webPath(link: AppLink, token: string): string {
  const web = link.web
  if (typeof web === 'string' && web.startsWith('/') && !web.startsWith('//')) return web
  return `/patient/#link=${encodeURIComponent(token)}`
}

export default function LinkPage() {
  const { token = '' } = useParams<{ token: string }>()
  const [tappedApp, setTappedApp] = useState(false)

  const { data, isLoading, error, refetch, isFetching } = useQuery<AppLink>({
    queryKey: ['app-link', token],
    queryFn: () => fetchJson(`/api/links/${encodeURIComponent(token)}`),
    retry: false,
    refetchOnWindowFocus: false,
  })

  const web = data ? webPath(data, token) : null
  const auto = data?.signin === true && !tappedApp

  useEffect(() => {
    if (!auto || !web) return
    const timer = window.setTimeout(() => window.location.assign(web), AUTO_CONTINUE_MS)
    return () => window.clearTimeout(timer)
  }, [auto, web])

  if (isLoading)
    return (
      <PatientShell width="md">
        <PatientStatus tone="loading" title="Opening your link…" />
      </PatientShell>
    )

  if (error || !data || !web) {
    const gone = error instanceof ApiError && error.status === 404
    return (
      <PatientShell width="md">
        <PatientStatus
          tone="error"
          title={gone ? 'This link has expired or was already replaced' : 'Can’t reach MedPull right now'}
        >
          {gone
            ? 'Open the newest text from your clinic, or ask them to send it again.'
            : 'Check your connection, then try again.'}
        </PatientStatus>
        {!gone && (
          <button
            type="button"
            className="btn-filled btn-lg mt-6 min-h-14 w-full text-lede"
            disabled={isFetching}
            onClick={() => void refetch()}
          >
            {isFetching ? 'Trying…' : 'Try again'}
          </button>
        )}
      </PatientShell>
    )
  }

  const app = appUrl(data)
  const sender = data.clinic?.name ?? 'Your care team'
  const thing = THING[data.kind] ?? 'a link'

  return (
    <PatientShell
      width="md"
      hero={
        <>
          <p className="text-copy-lg font-medium text-ink">{sender}</p>
          <PatientTitle className="mt-3">
            {data.patient?.first_name ? `Hi ${data.patient.first_name}` : 'Hello'}
          </PatientTitle>
          <p className="mt-3 text-copy-lg text-ink">
            {sender} sent you {thing}. Open it in the MedPull app, or carry on here in the browser.
          </p>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        {app && (
          <a
            href={app}
            onClick={() => setTappedApp(true)}
            className="btn-filled btn-lg min-h-14 w-full text-lede forced-colors:border-[LinkText]"
          >
            <Smartphone size={20} aria-hidden />
            Open in the MedPull app
          </a>
        )}
        <a
          href={web}
          className={`${app ? 'btn-gray' : 'btn-filled'} btn-lg min-h-14 w-full text-lede forced-colors:border-[LinkText]`}
        >
          <Globe size={20} aria-hidden />
          Continue in the browser
        </a>
      </div>

      <p className="mt-6 min-h-[3rem] text-center text-copy-lg text-ink" role="status" aria-live="polite">
        {auto
          ? 'Carrying on in the browser in a moment…'
          : tappedApp
            ? 'If the app did not open, continue in the browser.'
            : ''}
      </p>
    </PatientShell>
  )
}
