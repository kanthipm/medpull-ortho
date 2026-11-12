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

// Its own prefix, not the patient app's `medpull.`: the two apps share one
// origin (the patient app lives at /patient/), and the patient app clears
// every key under its prefix when it signs a new patient in — which, on the
// demo screen, used to sign the therapist out of the console.
const TOKEN_KEY = 'medpull-console.token'

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

// --- the acting clinic ------------------------------------------------------------
//
// A staff console looks at one clinic at a time or at all of them: the choice
// made in the workspace menu (or carried once by `?clinic=<id>`). It is kept
// here and sent as a header on every console call, and the server narrows
// roster reads and the exercise calendar to that hospital. Nothing stored
// means "All clinics". An org credential is its own clinic already; the
// server ignores the header for it and the shell clears a stale choice.

const CLINIC_KEY = 'medpull-console.clinic'
export const CLINIC_HEADER = 'X-MedPull-Clinic'

/** A hospital id is a slug. Anything else — a mistyped `?clinic=`, a value
 *  with a character a header cannot carry — is treated as no choice, since
 *  `fetch` throws on such a header and every console call would fail. */
const CLINIC_ID = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$/

export function getActingClinic(): string | null {
  try {
    const id = window.localStorage.getItem(CLINIC_KEY)
    return id && CLINIC_ID.test(id) ? id : null
  } catch {
    return null
  }
}

const clinicListeners = new Set<() => void>()

/** Keep a clinic as the one this console acts for; `null` is "All clinics".
 *  Listeners hear a real change only: the shell resets the query cache on
 *  one, because every cached roster belongs to the old choice. */
export function setActingClinic(id: string | null) {
  const next = id && CLINIC_ID.test(id) ? id : null
  if (next === getActingClinic()) return
  try {
    if (next) window.localStorage.setItem(CLINIC_KEY, next)
    else window.localStorage.removeItem(CLINIC_KEY)
  } catch {
    // storage blocked: the console stays on "All clinics"
    return
  }
  clinicListeners.forEach((tell) => tell())
}

/** Sign-out: forget the choice without telling anyone. The page is about to
 *  reload, and a cache reset here would only refetch under no token. */
export function clearActingClinic() {
  try {
    window.localStorage.removeItem(CLINIC_KEY)
  } catch {
    // nothing stored to clear
  }
}

/** Hear the choice change: here (`setActingClinic`) or in another tab, which
 *  shares the storage and so the header. */
export function subscribeActingClinic(listener: () => void): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key === CLINIC_KEY || e.key === null) listener()
  }
  clinicListeners.add(listener)
  window.addEventListener('storage', onStorage)
  return () => {
    clinicListeners.delete(listener)
    window.removeEventListener('storage', onStorage)
  }
}

/** Reads `?clinic=<id>` or `?clinic=all` out of a query string. Returns the
 *  choice it names (`null` for "all") and the query string without it, or
 *  `undefined` when the parameter is absent. */
export function readClinicParam(
  search: string,
): { clinic: string | null; rest: string } | undefined {
  const params = new URLSearchParams(search)
  const raw = params.get('clinic')
  if (raw == null) return undefined
  params.delete('clinic')
  const rest = params.toString()
  const value = raw.trim()
  return { clinic: value === '' || value === 'all' ? null : value, rest: rest ? `?${rest}` : '' }
}

/** A console URL that arrives with `?clinic=` sets the acting clinic once,
 *  and the parameter is taken out of the address, so `/?clinic=hirt` is a
 *  bookmark for one clinic's room and a copied URL does not carry it on.
 *  Run before the first request, so nothing is fetched for the old choice;
 *  the shell does the same for a link followed inside the app. */
export function adoptClinicFromAddress() {
  if (typeof window === 'undefined') return
  const found = readClinicParam(window.location.search)
  if (!found) return
  setActingClinic(found.clinic)
  window.history.replaceState(
    window.history.state,
    '',
    window.location.pathname + found.rest + window.location.hash,
  )
}

/** What every console call carries: the bearer header (nothing while the
 *  console is open) and the acting clinic when one is chosen. Exported for
 *  the few calls that cannot go through fetchJson: a file's bytes in either
 *  direction. */
export function consoleAuthHeaders(): Record<string, string> {
  const token = getConsoleToken()
  const clinic = getActingClinic()
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(clinic ? { [CLINIC_HEADER]: clinic } : {}),
  }
}

/** Routes a patient reaches from a texted link, and the page a trainer is
 *  given; the token in the path is the credential, so no console header goes
 *  with them. */
function isPatientPath(path: string): boolean {
  return (
    path.startsWith('/api/checkin/') ||
    path.startsWith('/api/tasks/') ||
    path.startsWith('/api/links/') ||
    path.startsWith('/api/handoff/')
  )
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
