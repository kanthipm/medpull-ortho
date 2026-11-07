import { KeyRound } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, clearConsoleToken, fetchJson, setConsoleToken } from '../../api/client'
import type { Health } from '../../api/types'

/** `/login` — the console's one door. The server says on /api/health whether
 *  it wants a token at all; an open deployment is sent straight through. A
 *  token is checked against a cheap console route before it is kept, so a
 *  typo is caught here and not on the worklist. */

export default function LoginPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const next = safeNext(params.get('next'))
  const [token, setToken] = useState('')
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchJson<Health>('/api/health')
      .then((h) => {
        if (!cancelled && !h.console_auth) navigate(next, { replace: true })
      })
      .catch(() => {
        // Unreachable server: stay here and let the form say so on submit.
      })
    return () => {
      cancelled = true
    }
  }, [navigate, next])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const value = token.trim()
    if (!value) return
    setChecking(true)
    setError(null)
    setConsoleToken(value)
    try {
      await fetchJson('/api/notifications?status=unread')
      navigate(next, { replace: true })
    } catch (err) {
      clearConsoleToken()
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
