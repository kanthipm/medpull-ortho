import { useQueryClient } from '@tanstack/react-query'
import { KeyRound } from 'lucide-react'
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, clearConsoleToken, fetchJson, setConsoleToken } from '../../api/client'
import { CONSOLE_SESSION_KEY } from '../../api/queries'
import type { ConsoleSession, Health } from '../../api/types'

/** `/login` — the console's one door, with two ways through it.
 *
 *  A token typed into the form, or a token carried by a sign-in link in the
 *  URL *fragment* (`/login#token=…`). A fragment, never a query string: the
 *  browser keeps it to itself, so it reaches no server, no access log and no
 *  referrer. It is read once, erased from the address bar before anything
 *  else happens, and then checked the way a typed token is — through
 *  `GET /api/console/session`, which answers with the token's scope or a 401
 *  — before it is kept for this browser.
 *
 *  An open deployment (no `console_auth` on /api/health) is sent straight
 *  through only when no fragment token arrived: an org's token narrows even
 *  an open console, so a link must be honoured there too. */

/** The token in the URL fragment, if a sign-in link brought one, consumed:
 *  the address bar is rewritten without it so a copied URL, a bookmark or the
 *  history never carries the credential. */
function takeFragmentToken(): string | null {
  if (typeof window === 'undefined') return null
  const hash = window.location.hash
  if (hash.length < 2) return null
  const token = new URLSearchParams(hash.slice(1)).get('token')?.trim() || null
  if (token) {
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
  }
  return token
}

/** Keep the token for this browser and ask the server what it is good for.
 *  A refused token is forgotten again before the error reaches the caller. */
async function verify(token: string): Promise<ConsoleSession> {
  setConsoleToken(token)
  try {
    return await fetchJson<ConsoleSession>('/api/console/session')
  } catch (err) {
    clearConsoleToken()
    throw err
  }
}

export default function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [token, setToken] = useState('')
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  // Read once: StrictMode runs the effect twice in development, and the
  // second run must find the same token, not an already-cleared fragment.
  const fragment = useRef<string | null | undefined>(undefined)

  useEffect(() => {
    if (fragment.current === undefined) fragment.current = takeFragmentToken()
    const linked = fragment.current
    let cancelled = false
    if (linked) {
      setChecking(true)
      verify(linked)
        .then((session) => {
          if (cancelled) return
          queryClient.setQueryData(CONSOLE_SESSION_KEY, session)
          navigate(next, { replace: true })
        })
        .catch((err: unknown) => {
          if (cancelled) return
          setError(
            err instanceof ApiError && err.status === 401
              ? 'That sign-in link is not valid any more. Enter the access token instead.'
              : "Can't reach MedPull right now. Check your connection and try again.",
          )
        })
        .finally(() => {
          if (!cancelled) setChecking(false)
        })
    } else {
      fetchJson<Health>('/api/health')
        .then((h) => {
          if (!cancelled && !h.console_auth) navigate(next, { replace: true })
        })
        .catch(() => {
          // Unreachable server: stay here and let the form say so on submit.
        })
    }
    return () => {
      cancelled = true
    }
  }, [navigate, next, queryClient])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const value = token.trim()
    if (!value) return
    setChecking(true)
    setError(null)
    try {
      const session = await verify(value)
      queryClient.setQueryData(CONSOLE_SESSION_KEY, session)
      navigate(next, { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('That access token is not right.')
      } else {
        setError("Can't reach MedPull right now. Check your connection and try again.")
      }
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="grid min-h-screen place-items-center p-6">
      <form
        onSubmit={submit}
        className="panel w-full max-w-[440px] px-7 py-8 text-center sm:px-10 sm:py-10"
      >
        <span className="tile tile-frost mx-auto !h-12 !w-12 !rounded-[14px]" aria-hidden>
          <KeyRound size={22} />
        </span>
        <p className="meta mt-5 uppercase tracking-label">Provider console</p>
        <h1 className="display-title mt-2 text-[1.75rem] leading-tight text-ink">Sign in</h1>
        <p className="mx-auto mt-3 max-w-[34ch] text-copy text-body">
          Enter the access token your clinic was given. It is remembered on this browser.
        </p>
        <label htmlFor="console-token" className="sr-only">
          Access token
        </label>
        <input
          id="console-token"
          name="console-token"
          type="password"
          autoComplete="current-password"
          autoFocus
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className="field mt-6 w-full text-center"
          placeholder="Access token"
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? 'console-token-error' : undefined}
        />
        {error && (
          <p id="console-token-error" role="alert" className="mt-3 text-copy text-risk-high">
            {error}
          </p>
        )}
        <button
          type="submit"
          className="btn-filled mt-5 w-full"
          disabled={checking || !token.trim()}
        >
          {checking ? 'Checking…' : 'Open the console'}
        </button>
        <p className="meta mt-6">Monitoring signals for clinician review, not a diagnosis.</p>
      </form>
    </div>
  )
}

/** Only ever send someone back to a path on this site. */
function safeNext(raw: string | null): string {
  if (!raw || !raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/login')) return '/'
  return raw
}
