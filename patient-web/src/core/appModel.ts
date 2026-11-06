/* Root state: who is signed in, what the server says about them, and the
   feeds the tabs show (tasks, messages, progress). One instance, read by
   every screen through `useApp()`; a change to any field re-renders the
   screens that read it, the way SwiftUI's Observation does for the phone
   (Core/AppModel.swift). */

import { useSyncExternalStore } from 'react'
import { APIClient, APIError, isCancelled } from './api'
import { AppConfig } from './config'
import { HealthConnector } from './health'
import { Keychain } from './keychain'
import type {
  AgentResponse, Answers, ChatMessage, ConsentAcceptance, Me, PatientMetricsResponse,
  PortfolioMetric, ProgressDay, RecoveryTask, TasksResponse, WearableSummary,
} from './models'
import { isPersonalProfile } from './models'

export type Phase = 'launching' | 'onboarding' | 'home'
/** The four tabs of a hospital record: Today, Progress, Measure, Care. */
export type Tab = 'today' | 'progress' | 'measure' | 'care'
/** What one refresh did. Cancelled is its own answer: the screen moved on. */
export type Outcome = 'ok' | 'failed' | 'cancelled'

const TOKEN_KEY = 'session_token'
const tokenKeyFor = (patientId: string) => `session_token:${patientId}`

export class AppModel {
  phase: Phase = 'launching'
  readonly api = new APIClient()
  readonly health = new HealthConnector()

  me: Me | null = null
  tasks: TasksResponse = { open: [], recent: [] }
  messages: ChatMessage[] = []
  progress: ProgressDay[] = []
  portfolio: PortfolioMetric[] = []
  /** The patient's own metrics, in their words (Progress tab). */
  metrics: PatientMetricsResponse | null = null
  wearables: WearableSummary | null = null
  lastError: string | null = null

  /** Set by a `medpull://tasks/<id>` link or a thread button; Today opens it. */
  pendingTaskId: number | null = null
  selectedTab: Tab = 'today'
  /** Opens the Connections screen (Apple Health, wearables) from wherever
   *  the person is: the Today nudge, a `medpull://wearables` link. */
  showConnections = false

  // MARK: observation

  private listeners = new Set<() => void>()
  private version = 0

  subscribe = (fn: () => void) => {
    this.listeners.add(fn)
    return () => { this.listeners.delete(fn) }
  }
  snapshot = () => this.version
  /** Call after changing any field from outside the model's own methods. */
  notify(): void {
    this.version++
    for (const fn of this.listeners) fn()
  }
  private set<K extends keyof this>(key: K, value: this[K]): void {
    this[key] = value
    this.notify()
  }

  /** Whether the signed-in row is a subscriber's own space. The web app is
   *  the clinic version, so this is false for every account it signs in. */
  get isPersonal(): boolean { return this.me ? isPersonalProfile(this.me.patient) : false }

  // MARK: lifecycle

  async bootstrap(): Promise<void> {
    const stored = Keychain.get(TOKEN_KEY)
    if (stored) {
      this.api.token = stored
      this.set('phase', 'home')
      this.health.restore()
      await this.refreshAll()
    } else {
      this.set('phase', 'onboarding')
    }
  }

  /** Enrollment succeeded: keep the credential and act as this patient,
   *  but stay in onboarding so the Health and wearable steps can run. */
  adoptSession(token: string, me: Me): void {
    Keychain.set(token, TOKEN_KEY)
    Keychain.set(token, tokenKeyFor(me.patient.id))
    this.api.token = token
    this.me = me
    this.notify()
  }

  /** The beta consent, accepted in place by a signed-in account. */
  async acceptConsent(acceptance: ConsentAcceptance): Promise<void> {
    await this.api.acceptConsent(acceptance)
    await this.refreshMe(false)
  }

  enterHome(): void {
    this.set('phase', 'home')
    void this.refreshAll()
  }

  async signOut(): Promise<void> {
    try { await this.api.signOut() } catch { /* the session is going anyway */ }
    await this.health.disconnect()
    Keychain.delete(TOKEN_KEY)
    for (const p of this.me?.profiles ?? []) Keychain.delete(tokenKeyFor(p.patientId))
    if (this.me) Keychain.delete(tokenKeyFor(this.me.patient.id))
    this.api.token = null
    this.me = null
    this.tasks = { open: [], recent: [] }
    this.messages = []
    this.progress = []
    this.portfolio = []
    this.metrics = null
    this.wearables = null
    this.lastError = null
    this.pendingTaskId = null
    this.showConnections = false
    this.selectedTab = 'today'
    this.set('phase', 'onboarding')
  }

  // MARK: feeds

  private async refresh(surface: boolean, work: () => Promise<void>): Promise<Outcome> {
    try {
      await work()
      this.clearError()
      return 'ok'
    } catch (e) {
      if (isCancelled(e)) return 'cancelled'
      if (e instanceof APIError && e.isUnauthorized) {
        void this.signOut()
        return 'failed'
      }
      if (e instanceof APIError && e.isPaywalled) return 'failed'
      if (surface) this.set('lastError', (e as Error).message)
      return 'failed'
    }
  }

  async refreshAll(): Promise<void> {
    // These share one banner, and the 14-day portfolio is the heaviest call
    // and the first to be throttled. The banner means what it says: nothing
    // got through. The five are independent, so they go out together — the
    // tabs fill in at once rather than one feed after another — and each
    // still records its own outcome. `refresh` never rejects.
    const outcomes: Outcome[] = await Promise.all([
      this.refresh(false, async () => { this.me = await this.api.me(); this.notify() }),
      this.refresh(false, async () => { this.tasks = await this.api.tasks(); this.notify() }),
      this.refresh(false, async () => { this.messages = await this.api.messages(); this.notify() }),
      this.refresh(false, async () => {
        this.portfolio = (await this.api.portfolio(14)).metrics
        this.notify()
      }),
      this.refreshMetrics(false),
    ])
    if (outcomes.includes('ok')) this.clearError()
    else if (outcomes.includes('failed')) {
      this.set('lastError', "Can't reach MedPull right now. Check your connection.")
    }
  }

  refreshMe(surface = true): Promise<Outcome> {
    return this.refresh(surface, async () => { this.me = await this.api.me(); this.notify() })
  }

  refreshTasks(surface = true): Promise<Outcome> {
    return this.refresh(surface, async () => { this.tasks = await this.api.tasks(); this.notify() })
  }

  refreshMessages(surface = true): Promise<Outcome> {
    return this.refresh(surface, async () => { this.messages = await this.api.messages(); this.notify() })
  }

  refreshProgress(surface = true): Promise<Outcome> {
    return this.refresh(surface, async () => {
      this.progress = (await this.api.progress(14)).days
      this.notify()
    })
  }

  refreshPortfolio(surface = true): Promise<Outcome> {
    return this.refresh(surface, async () => {
      this.portfolio = (await this.api.portfolio(14)).metrics
      this.notify()
    })
  }

  /** The care metrics as the patient sees them. */
  refreshMetrics(surface = true): Promise<Outcome> {
    return this.refresh(surface, async () => { this.metrics = await this.api.metrics(); this.notify() })
  }

  refreshWearables(force = false, surface = true): Promise<Outcome> {
    return this.refresh(surface, async () => {
      const r = force ? await this.api.refreshWearables() : await this.api.wearables()
      this.wearables = r.summary
      this.notify()
    })
  }

  // MARK: actions

  async complete(task: RecoveryTask, answers: Answers, via = 'app'): Promise<void> {
    await this.api.complete(task.id, answers, via)
    await this.refreshTasks()
    await this.refreshMe()
  }

  async skip(task: RecoveryTask): Promise<void> {
    await this.api.skip(task.id)
    await this.refreshTasks()
  }

  /** Write to the care team. A photo can be the whole message, so the text
   *  may be empty when something is attached. */
  async send(text: string, attachmentIds: number[] = []): Promise<void> {
    const m = await this.api.sendMessage(text, attachmentIds)
    this.messages = [...this.messages, m]
    this.notify()
  }

  async markMessagesRead(): Promise<void> {
    try { await this.api.markMessagesRead() } catch { /* nothing to mark */ }
    await this.refreshMe()
  }

  async ask(text: string, channel: string): Promise<AgentResponse> {
    const r = await this.api.agent(text, channel)
    await this.refreshTasks()
    await this.refreshMessages()
    return r
  }

  /** On the phone this opens the one Health sheet; here it cannot. */
  async connectAppleHealth(): Promise<boolean> {
    const ok = await this.health.connect()
    this.notify()
    return ok
  }

  // MARK: links

  /** A `medpull://` link, as the phone handles it, mapped onto this app. */
  handle(url: string): { tab: Tab } | null {
    let parsed: URL
    try { parsed = new URL(url) } catch { return null }
    if (parsed.protocol !== `${AppConfig.scheme}:`) return null
    switch (parsed.host) {
      case 'tasks': {
        const id = Number(parsed.pathname.split('/').filter(Boolean).pop())
        if (Number.isInteger(id)) {
          this.pendingTaskId = id
          this.selectedTab = 'today'
          this.notify()
          void this.refreshTasks()
          return { tab: 'today' }
        }
        return null
      }
      case 'wearables':
        this.showConnections = true
        this.notify()
        void this.refreshWearables(true)
        return { tab: 'today' }
      default:
        return null
    }
  }

  /** A successful request means the server is reachable again: drop a
   *  banner left over from an earlier failure. */
  private clearError(): void {
    if (this.lastError != null) this.set('lastError', null)
  }

  /** Surface a failure from an action the person is waiting on. */
  note(e: unknown): void {
    if (isCancelled(e)) return
    if (e instanceof APIError && e.isUnauthorized) {
      void this.signOut()
      return
    }
    this.set('lastError', (e as Error).message)
  }

  setPendingTaskId(id: number | null): void { this.set('pendingTaskId', id) }
  setShowConnections(on: boolean): void { this.set('showConnections', on) }
  setSelectedTab(tab: Tab): void { this.set('selectedTab', tab) }
}

/** What to show the person when an action fails, or null when there is
 *  nothing to say (a cancelled request is the screen going away). */
export function messageFor(e: unknown): string | null {
  if (isCancelled(e)) return null
  if (e instanceof Error) return e.message
  return String(e)
}

export const app = new AppModel()

/** The app model, subscribed: the component re-renders on every change. */
export function useApp(): AppModel {
  useSyncExternalStore(app.subscribe, app.snapshot, app.snapshot)
  return app
}
