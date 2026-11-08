/* One JSON client for /api/mobile, one for one with Core/APIClient.swift.
   The session token is attached to every call once set; a 401 clears the
   session upstream (AppModel). Keys are snake_case on the wire and camelCase
   here, converted both ways, like the Swift coders do. */

import { AppConfig, deviceName } from './config'
import type {
  AgentResponse, AppleSession, Candidate, ChatAttachment, ChatMessage, CompleteResponse,
  ConsentAcceptance, ConsentDocument, ConsentStatus, EnrollResponse, ExerciseAssignment,
  ExerciseCompletionBody, ExercisesResponse, GaitUpload, GaitUploadResponse,
  Hospital, LinkResponse, Me, MessagesResponse, MotionUpload, MotionUploadResponse, OKResponse,
  PatientMetricsResponse, PortfolioResponse, Procedure, ProgressResponse, RangeOfMotionUpload,
  RangeOfMotionResponse, SentMessageResponse, SixMinuteWalkUpload, SixMinuteWalkResponse,
  StagedUpload, TasksResponse, VerificationStatus, WearablesResponse, Answers,
} from './models'

export class APIError extends Error {
  status: number
  detail: string
  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'APIError'
    this.status = status
    this.detail = detail
  }
  get isUnauthorized() { return this.status === 401 }
  /** The personal tier's paywall; a hospital record never sees it. */
  get isPaywalled() { return this.status === 402 }
}

/** The screen went away while a request was in flight. Not a failure. */
export class CancelledError extends Error {
  constructor() {
    super('cancelled')
    this.name = 'CancelledError'
  }
}

export const isCancelled = (e: unknown) =>
  e instanceof CancelledError || (e instanceof DOMException && e.name === 'AbortError')

const UNREACHABLE = "Can't reach MedPull right now. Check your connection."

// MARK: - Key conversion

const toCamel = (k: string) => k.replace(/_([a-z0-9])/g, (_, c: string) => c.toUpperCase())
const toSnake = (k: string) => k.replace(/[A-Z]/g, (c) => `_${c.toLowerCase()}`)

function convertKeys(value: unknown, fn: (k: string) => string): unknown {
  if (Array.isArray(value)) return value.map((v) => convertKeys(v, fn))
  if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[fn(k)] = convertKeys(v, fn)
    return out
  }
  return value
}

export const camelize = <T>(v: unknown) => convertKeys(v, toCamel) as T
export const snakeize = (v: unknown) => convertKeys(v, toSnake)

type Method = 'GET' | 'POST' | 'PATCH' | 'DELETE'

export class APIClient {
  token: string | null = null

  get<T>(path: string, query: Record<string, string> = {}, signal?: AbortSignal): Promise<T> {
    return this.send<T>('GET', path, query, undefined, signal)
  }

  post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return this.send<T>('POST', path, {}, body ?? {}, signal)
  }

  patch<T>(path: string, body: unknown): Promise<T> {
    return this.send<T>('PATCH', path, {}, body)
  }

  delete<T>(path: string): Promise<T> {
    return this.send<T>('DELETE', path, {}, undefined)
  }

  url(path: string, query: Record<string, string> = {}): string {
    const base = AppConfig.baseURL
    const q = new URLSearchParams(query).toString()
    return `${base}${path}${q ? `?${q}` : ''}`
  }

  private headers(contentType?: string): Record<string, string> {
    const h: Record<string, string> = { Accept: 'application/json' }
    if (contentType) h['Content-Type'] = contentType
    if (this.token) h.Authorization = `Bearer ${this.token}`
    return h
  }

  private async send<T>(
    method: Method, path: string, query: Record<string, string>, body: unknown, signal?: AbortSignal,
  ): Promise<T> {
    const init: RequestInit = {
      method,
      headers: this.headers(body !== undefined ? 'application/json' : undefined),
      signal,
    }
    if (body !== undefined) init.body = JSON.stringify(snakeize(body))
    // A GET is safe to repeat, and the server's hiccups are short: a cold
    // start, or a burst of console traffic. One retry after a short pause
    // hides most of them.
    let r = await this.attempt(this.url(path, query), init)
    if (method === 'GET' && (r.status === 0 || r.status === 429 || r.status >= 500)) {
      await sleep(1500, signal)
      r = await this.attempt(this.url(path, query), init)
    }
    this.check(r)
    try {
      return camelize<T>(r.json)
    } catch (e) {
      throw new APIError(r.status, `Unexpected answer from the server (${(e as Error).message}).`)
    }
  }

  /** The status check the JSON path applies, for the requests that build
   *  their own request (an upload body, a file download). */
  private check(r: Attempt): void {
    if (r.status === 0) throw new APIError(0, UNREACHABLE)
    if (r.status < 200 || r.status >= 300) {
      let detail = r.statusText || `HTTP ${r.status}`
      const obj = r.json as { detail?: unknown } | null
      if (obj && typeof obj.detail === 'string') detail = obj.detail
      throw new APIError(r.status, detail)
    }
  }

  /** One HTTP attempt. A transport failure (no network, DNS) comes back as
   *  status 0 rather than throwing, so the caller can decide whether to
   *  retry. Cancellation is not a transport failure. */
  private async attempt(url: string, init: RequestInit): Promise<Attempt> {
    let res: Response
    try {
      res = await fetch(url, init)
    } catch (e) {
      if (isCancelled(e)) throw new CancelledError()
      return { status: 0, statusText: '', json: null, bytes: null }
    }
    const type = res.headers.get('content-type') ?? ''
    if (type.includes('application/json')) {
      const json: unknown = await res.json().catch(() => null)
      return { status: res.status, statusText: res.statusText, json, bytes: null }
    }
    const bytes = await res.arrayBuffer()
    return { status: res.status, statusText: res.statusText, json: null, bytes }
  }

  // MARK: - Endpoints

  async hospitals(query = ''): Promise<Hospital[]> {
    const r = await this.get<{ hospitals: Hospital[] }>('/api/mobile/hospitals', query ? { q: query } : {})
    return r.hospitals
  }

  async search(hospitalId: string, name: string, phone: string | null): Promise<Candidate[]> {
    const r = await this.post<{ candidates: Candidate[] }>('/api/mobile/patients/search',
      { hospitalId, name, phone })
    return r.candidates
  }

  enroll(patientId: string, hospitalId: string, phone: string,
         consent: ConsentAcceptance | null = null): Promise<EnrollResponse> {
    return this.post('/api/mobile/enroll', {
      patientId, hospitalId, phone, consent, deviceName: deviceName(), appVersion: AppConfig.appVersion,
    })
  }

  verify(verificationId: number, code: string, consent: ConsentAcceptance | null = null): Promise<EnrollResponse> {
    return this.post('/api/mobile/enroll/verify', {
      verificationId, code, consent, deviceName: deviceName(), appVersion: AppConfig.appVersion,
    })
  }

  /** While the person texts MedPull for the first time: has the code gone out? */
  verificationStatus(verificationId: number): Promise<VerificationStatus> {
    return this.get(`/api/mobile/enroll/verification/${verificationId}`)
  }

  /** "I've sent it — send my code": the same verification, tried again. */
  resendVerification(verificationId: number): Promise<EnrollResponse> {
    return this.post(`/api/mobile/enroll/verification/${verificationId}/resend`)
  }

  async procedures(): Promise<Procedure[]> {
    const r = await this.get<{ procedures: Procedure[] }>('/api/mobile/procedures')
    return r.procedures
  }

  join(args: {
    hospitalId: string; name: string; phone: string; dateOfBirth: string | null
    hadSurgery: boolean; procedureType: string | null; surgeryDate: string | null
    consent: ConsentAcceptance | null
  }): Promise<EnrollResponse> {
    return this.post('/api/mobile/join', {
      ...args,
      procedureType: args.hadSurgery ? args.procedureType : null,
      surgeryDate: args.hadSurgery ? args.surgeryDate : null,
      deviceName: deviceName(), appVersion: AppConfig.appVersion,
    })
  }

  portfolio(days = 14, signal?: AbortSignal): Promise<PortfolioResponse> {
    return this.get('/api/mobile/portfolio', { days: String(days) }, signal)
  }

  me(signal?: AbortSignal): Promise<Me> { return this.get('/api/mobile/me', {}, signal) }
  metrics(signal?: AbortSignal): Promise<PatientMetricsResponse> { return this.get('/api/mobile/metrics', {}, signal) }
  tasks(signal?: AbortSignal): Promise<TasksResponse> { return this.get('/api/mobile/tasks', {}, signal) }

  complete(taskId: number, answers: Answers, via: string): Promise<CompleteResponse> {
    return this.post(`/api/mobile/tasks/${taskId}/complete`, { answers, via })
  }

  skip(taskId: number): Promise<CompleteResponse> {
    return this.post(`/api/mobile/tasks/${taskId}/skip`)
  }

  // MARK: - The exercise schedule (docs/dev/hep-schedule.md)

  /** The day's assignments and the week around them. No `date` means the
   *  server's own day; Today passes the phone's. */
  exercises(date?: string, signal?: AbortSignal): Promise<ExercisesResponse> {
    return this.get('/api/mobile/exercises', date ? { date } : {}, signal)
  }

  /** "Mark done": the pain after, a note, and the clip that was staged in
   *  storage — the server confirms the clip and writes the thread line. The
   *  contract answers `{ assignment }`; a bare assignment is read too. */
  async completeExercise(assignmentId: number, body: ExerciseCompletionBody): Promise<ExerciseAssignment> {
    const v = body.video
    const video = v ? {
      // Exactly the keys the contract names on the storage path; the direct
      // path (no object store) has no key to name, so it says which row.
      storageKey: v.storageKey ?? undefined,
      attachmentId: v.storageKey ? undefined : v.attachmentId ?? undefined,
      contentType: v.contentType, byteSize: v.byteSize, filename: v.filename,
    } : null
    const r = await this.post<{ assignment: ExerciseAssignment } | ExerciseAssignment>(
      `/api/mobile/exercises/${assignmentId}/complete`, { painAfter: body.painAfter, note: body.note, video },
    )
    return unwrapAssignment(r)
  }

  /** "Can't do it today": the row is skipped with the reason, in the
   *  patient's words or none. */
  async skipExercise(assignmentId: number, reason: string): Promise<ExerciseAssignment> {
    const r = await this.post<{ assignment: ExerciseAssignment } | ExerciseAssignment>(
      `/api/mobile/exercises/${assignmentId}/skip`, { reason },
    )
    return unwrapAssignment(r)
  }

  /** A demonstration clip's link, when it is an API path rather than a
   *  presigned object link: it has to be fetched under this session, and a
   *  `<video src>` cannot carry the header. */
  needsSession(url: string): boolean {
    if (url.startsWith('/')) return true
    try {
      const u = new URL(url, window.location.origin)
      const api = new URL(AppConfig.baseURL || window.location.origin, window.location.origin)
      return u.origin === api.origin && u.pathname.startsWith('/api/')
    } catch {
      return false
    }
  }

  /** The bytes behind such a link, as a Blob for an object URL. */
  async mediaBlob(url: string): Promise<Blob> {
    let res: Response
    try {
      res = await fetch(url.startsWith('/') ? this.url(url) : url, { headers: this.headers() })
    } catch {
      throw new APIError(0, UNREACHABLE)
    }
    if (!res.ok) throw new APIError(res.status, 'The video could not be loaded.')
    return res.blob()
  }

  async messages(sinceId = 0, signal?: AbortSignal): Promise<ChatMessage[]> {
    const r = await this.get<MessagesResponse>('/api/mobile/messages', { since_id: String(sinceId) }, signal)
    return r.messages
  }

  /** A photo can be the whole message, so the text may be empty as long as
   *  something is attached. */
  async sendMessage(text: string, attachmentIds: number[] = []): Promise<ChatMessage> {
    const r = await this.post<SentMessageResponse>('/api/mobile/messages', { text, attachmentIds })
    return r.message
  }

  async markMessagesRead(): Promise<void> {
    await this.post<{ ok: boolean; count: number }>('/api/mobile/messages/read')
  }

  agent(text: string, channel: string): Promise<AgentResponse> {
    return this.post('/api/mobile/agent', { text, channel })
  }

  appleSession(): Promise<AppleSession> { return this.post('/api/mobile/wearables/apple/session') }
  wearables(): Promise<WearablesResponse> { return this.get('/api/mobile/wearables') }
  refreshWearables(): Promise<WearablesResponse> { return this.post('/api/mobile/wearables/refresh') }
  wearableLink(): Promise<LinkResponse> { return this.post('/api/mobile/wearables/link') }
  progress(days = 14): Promise<ProgressResponse> { return this.get('/api/mobile/progress', { days: String(days) }) }
  uploadGait(upload: GaitUpload): Promise<GaitUploadResponse> { return this.post('/api/mobile/observations/gait', upload) }
  // MedPull's own measurements: the server computes every metric from the
  // raw window (backend app/engine/mobility), the app only records.
  uploadMotion(upload: MotionUpload): Promise<MotionUploadResponse> {
    return this.post('/api/mobile/observations/motion', upload)
  }
  sixMinuteWalk(upload: SixMinuteWalkUpload): Promise<SixMinuteWalkResponse> {
    return this.post('/api/mobile/tests/six-minute-walk', upload)
  }
  rangeOfMotion(upload: RangeOfMotionUpload): Promise<RangeOfMotionResponse> {
    return this.post('/api/mobile/tests/range-of-motion', upload)
  }
  async signOut(): Promise<void> { await this.post<OKResponse>('/api/mobile/signout') }

  // MARK: - Consent

  consentDocument(): Promise<ConsentDocument> { return this.get('/api/mobile/consent') }

  async acceptConsent(a: ConsentAcceptance): Promise<ConsentStatus> {
    const r = await this.post<{ ok: boolean; consent: ConsentStatus }>('/api/mobile/consent', {
      version: a.version, scopes: a.scopes, signature: a.signature,
      deviceName: deviceName(), appVersion: AppConfig.appVersion,
    })
    return r.consent
  }

  // MARK: - Attachments

  /** Store one file on this patient's chart and return the row. Uploading
   *  happens when the file is picked, so the send that follows only ever
   *  carries ids; a row nobody claims with a message is swept server-side. */
  async upload(data: Blob, contentType: string, filename: string | null): Promise<ChatAttachment> {
    const ticket = await this.ticket(data, contentType)
    if (ticket.direct || !ticket.upload) return this.uploadDirect(data, contentType, filename)
    await this.uploadPresigned(ticket.upload, data, contentType, filename)
    const confirmed = await this.post<{ attachment: ChatAttachment }>('/api/mobile/attachments', {
      storageKey: ticket.storageKey, contentType, byteSize: data.size, filename,
    })
    return confirmed.attachment
  }

  /** Put a file in storage and stop before confirming it: the request that
   *  gives the file its meaning (an exercise's "Mark done") confirms it, so
   *  the row is written beside what it belongs to. `onProgress` is the share
   *  of the bytes sent, 0...1. With no object store the bytes go through the
   *  API, which confirms as it stores; the staged upload then names the row. */
  async stageUpload(
    data: Blob, contentType: string, filename: string | null, onProgress?: (fraction: number) => void,
  ): Promise<StagedUpload> {
    const ticket = await this.ticket(data, contentType)
    if (ticket.direct || !ticket.upload) {
      const a = await this.uploadDirect(data, contentType, filename, onProgress)
      return { storageKey: null, attachmentId: a.id, contentType: a.contentType, byteSize: a.byteSize, filename: a.filename }
    }
    await this.uploadPresigned(ticket.upload, data, contentType, filename, onProgress)
    return { storageKey: ticket.storageKey, attachmentId: null, contentType, byteSize: data.size, filename }
  }

  /** Where to put a file, and the cap it must fit under. */
  private async ticket(data: Blob, contentType: string): Promise<UploadTicket> {
    const ticket = await this.get<UploadTicket>('/api/mobile/attachments/upload-ticket', {
      content_type: contentType, byte_size: String(data.size),
    })
    if (data.size > ticket.maxBytes) {
      throw new APIError(413, `That file is over ${Math.floor(ticket.maxBytes / 1_048_576)} MB.`)
    }
    return ticket
  }

  /** The bytes as the request body — no multipart. */
  private async uploadDirect(
    data: Blob, contentType: string, filename: string | null, onProgress?: (fraction: number) => void,
  ): Promise<ChatAttachment> {
    const url = this.url('/api/mobile/attachments/direct', filename ? { filename } : {})
    const r = await this.sendBytes(url, this.headers(contentType), data, onProgress)
    this.check(r)
    return camelize<{ attachment: ChatAttachment }>(r.json).attachment
  }

  /** A presigned POST carries its own authorization in the signed fields,
   *  so it goes out with none of ours attached — and the file part must be
   *  last, which the storage service requires. */
  private async uploadPresigned(
    upload: UploadTicket['upload'] & object, data: Blob, contentType: string, filename: string | null,
    onProgress?: (fraction: number) => void,
  ): Promise<void> {
    const form = new FormData()
    for (const [k, v] of Object.entries(upload.fields)) form.append(k, v)
    form.append('file', new File([data], filename ?? 'upload', { type: contentType }))
    const r = await this.sendBytes(upload.url, {}, form, onProgress)
    if (r.status === 0) throw new APIError(0, UNREACHABLE)
    if (r.status < 200 || r.status >= 300) throw new APIError(r.status, 'The upload was refused by storage.')
  }

  /** One upload, as an XMLHttpRequest: `fetch` cannot report how much of a
   *  body has gone out, and a clip is big enough that the person waits on
   *  it. The answer is shaped like `attempt`'s. */
  private sendBytes(
    url: string, headers: Record<string, string>, body: Blob | FormData, onProgress?: (fraction: number) => void,
  ): Promise<Attempt> {
    return new Promise((resolve) => {
      const x = new XMLHttpRequest()
      x.open('POST', url)
      for (const [k, v] of Object.entries(headers)) x.setRequestHeader(k, v)
      if (onProgress) {
        x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(Math.min(1, e.loaded / e.total)) }
      }
      x.onerror = () => resolve({ status: 0, statusText: '', json: null, bytes: null })
      x.onabort = () => resolve({ status: 0, statusText: '', json: null, bytes: null })
      x.onload = () => {
        onProgress?.(1)
        let json: unknown = null
        if ((x.getResponseHeader('content-type') ?? '').includes('application/json')) {
          try { json = JSON.parse(x.responseText) } catch { json = null }
        }
        resolve({ status: x.status, statusText: x.statusText, json, bytes: null })
      }
      x.send(body)
    })
  }

  /** The bytes of one attachment, ready to draw, as an object URL. Where
   *  there is object storage the server hands back a short-lived link and
   *  this fetches it directly; where there is not, the API streams it. */
  async attachmentBlob(id: number): Promise<Blob> {
    const path = `/api/mobile/attachments/${id}`
    const wrapper = await this.get<{ attachment: { url: string | null } }>(path)
    if (wrapper.attachment.url) {
      let res: Response
      try {
        res = await fetch(wrapper.attachment.url)
      } catch {
        throw new APIError(0, UNREACHABLE)
      }
      if (!res.ok) throw new APIError(res.status, 'The file could not be loaded.')
      return res.blob()
    }
    let res: Response
    try {
      res = await fetch(this.url(`${path}/raw`), { headers: this.headers() })
    } catch {
      throw new APIError(0, UNREACHABLE)
    }
    if (!res.ok) throw new APIError(res.status, 'The file could not be loaded.')
    return res.blob()
  }

  /** Take back a file. The bytes go; the line says something was removed. */
  async withdrawAttachment(id: number): Promise<void> {
    await this.delete<OKResponse>(`/api/mobile/attachments/${id}`)
  }
}

type Attempt = { status: number; statusText: string; json: unknown; bytes: ArrayBuffer | null }

/** The complete and skip routes answer `{ assignment }`; read a bare row too. */
function unwrapAssignment(r: { assignment: ExerciseAssignment } | ExerciseAssignment): ExerciseAssignment {
  return 'assignment' in r && r.assignment && typeof r.assignment === 'object' ? r.assignment : (r as ExerciseAssignment)
}

/** Where to put a file. The server decides: a deployment with object
 *  storage presigns an upload, one without takes the bytes itself. */
type UploadTicket = {
  storageKey: string
  direct: boolean
  maxBytes: number
  upload: { url: string; fields: Record<string, string>; expiresIn: number } | null
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      reject(new CancelledError())
    }, { once: true })
  })
}
