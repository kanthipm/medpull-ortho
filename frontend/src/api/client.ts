export class ApiError extends Error {
  /** HTTP status, or 0 when no response ever arrived. */
  status: number
  /** True when the client abandoned the request before the server answered. */
  timedOut: boolean
  constructor(status: number, message: string, timedOut = false) {
    super(message)
    this.status = status
    this.timedOut = timedOut
  }
}

export interface FetchOptions extends RequestInit {
  /** Deadline for this one call; defaults to REQUEST_TIMEOUT_MS. */
  timeoutMs?: number
}

/** Nothing upstream can answer past this: CloudFront reads the origin for 30s
 *  and the Lambda behind it is capped at the same 30s, so a request still in
 *  flight afterwards is waiting on a response that will never arrive. */
export const REQUEST_TIMEOUT_MS = 30_000

// --- the console's access token ---------------------------------------------------
//
// One shared token, entered once on /login and sent as a bearer header on
// every console call. The patient pages (/checkin, /t) talk to routes with
// their own credential and never send it. localStorage, not sessionStorage:
// a clinician opening a second tab should not be asked again.

const TOKEN_KEY = 'medpull.console-token'

export function getConsoleToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setConsoleToken(token: string) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token)
  } catch {
    // storage blocked: the token lives for this page load only
  }
}

export function clearConsoleToken() {
  try {
    window.localStorage.removeItem(TOKEN_KEY)
  } catch {
    // nothing stored to clear
  }
}

/** The bearer header for a console call, or nothing while the console is
 *  open. For the few calls that cannot go through fetchJson: a file's bytes
 *  in either direction. */
export function consoleAuthHeaders(): Record<string, string> {
  const token = getConsoleToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** Routes a patient reaches from a texted link; they carry their own token. */
function isPatientPath(path: string): boolean {
  return path.startsWith('/api/checkin/') || path.startsWith('/api/tasks/')
}

/** A console call the server refused: forget the token and go sign in,
 *  remembering where we were. Never from /login itself, or a wrong token
 *  would loop the page. */
function sendToLogin() {
  if (typeof window === 'undefined') return
  if (window.location.pathname.startsWith('/login')) return
  clearConsoleToken()
  const next = window.location.pathname + window.location.search
  window.location.assign(`/login?next=${encodeURIComponent(next)}`)
}

export async function fetchJson<T>(path: string, init?: FetchOptions): Promise<T> {
  const { timeoutMs = REQUEST_TIMEOUT_MS, signal: caller, headers, ...rest } = init ?? {}
  const controller = new AbortController()
  const deadline = setTimeout(() => controller.abort(), timeoutMs)
  // the caller's own signal — TanStack cancels on unmount — still wins
  const relay = () => controller.abort()
  caller?.addEventListener('abort', relay, { once: true })
  try {
    const res = await fetch(path, {
      ...rest,
      headers: {
        'Content-Type': 'application/json',
        ...(isPatientPath(path) ? {} : consoleAuthHeaders()),
        ...headers,
      },
      signal: controller.signal,
    })
    if (!res.ok) {
      let detail = res.statusText
      try {
        const body = await res.json()
        if (typeof body.detail === 'string') {
          detail = body.detail
        } else if (Array.isArray(body.detail)) {
          // FastAPI request-validation errors arrive as a list of
          // {loc, msg, type}. Reading only the string form left the user
          // looking at "Unprocessable Entity" with no idea which field.
          const said = body.detail
            .map((e: { loc?: unknown[]; msg?: string }) => {
              const field = Array.isArray(e.loc) ? e.loc.filter((x) => x !== 'body').join('.') : ''
              return field ? `${field}: ${e.msg ?? 'invalid'}` : (e.msg ?? 'invalid')
            })
            .join('; ')
          if (said) detail = said
        }
      } catch {
        // non-JSON error body — keep statusText
      }
      if (res.status === 401 && !isPatientPath(path)) sendToLogin()
      throw new ApiError(res.status, detail)
    }
    return (await res.json()) as T
  } catch (err) {
    if (controller.signal.aborted && !caller?.aborted) {
      throw new ApiError(0, `No answer within ${timeoutMs}ms`, true)
    }
    throw err
  } finally {
    clearTimeout(deadline)
    caller?.removeEventListener('abort', relay)
  }
}

/** The query layer's retry policy. One retry covers a genuinely transient
 *  failure. A blown deadline is not one — the first request is still holding
 *  the same 30s ceiling, so a second only doubles the load behind it — and
 *  neither is anything the server answered deliberately. */
export function shouldRetry(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiError) {
    if (error.timedOut || error.status === 408 || error.status === 504) return false
    if (error.status >= 400 && error.status < 500) return false
  }
  return failureCount < 1
}
