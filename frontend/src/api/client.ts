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
      headers: { 'Content-Type': 'application/json', ...headers },
      signal: controller.signal,
    })
    if (!res.ok) {
      let detail = res.statusText
      try {
        const body = await res.json()
        if (typeof body.detail === 'string') detail = body.detail
      } catch {
        // non-JSON error body — keep statusText
      }
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
