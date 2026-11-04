/* The onboarding flow's state (Features/Onboarding/OnboardingModel.swift),
   the clinic path only: consent, hospital, how you are joining, find my
   record or start one, the code by text, Health, wearables, done. */

import { useSyncExternalStore } from 'react'
import { APIClient, APIError } from '../../core/api'
import type { AppModel } from '../../core/appModel'
import { Dates, type Candidate, type ConsentAcceptance, type EnrollResponse, type Hospital, type Procedure } from '../../core/models'

/** Every screen the flow can show. The order is load-bearing for
 *  `isPastEnrollment` only. */
export const steps = ['welcome', 'consent', 'hospital', 'path', 'identity', 'join', 'verify', 'health', 'wearable', 'done'] as const
export type Step = (typeof steps)[number]

/** Steps after the session exists. Going back from these would land on a
 *  form that has already done its job, so they hide the back button. */
export const isPastEnrollment = (s: Step) => steps.indexOf(s) >= steps.indexOf('health')

/** How the person is joining: on a hospital's roster already (find the
 *  record), or new to it (create one, with or without a surgery). */
export type Path = 'findRecord' | 'joinGeneral' | 'joinAfterSurgery'

export class OnboardingModel {
  /** The navigation stack. Welcome is the root and never appears in it. */
  route: Step[] = []
  path: Path = 'joinGeneral'
  /** "Already have an account? Sign in": straight to find-my-record once a
   *  hospital is picked. */
  signingIn = false

  hospitals: Hospital[] = []
  hospitalQuery = ''
  hospital: Hospital | null = null

  name = ''
  phone = ''
  candidates: Candidate[] = []
  searching = false
  selected: Candidate | null = null

  // join form
  dateOfBirth: string | null = null
  procedures: Procedure[] = []
  procedure: Procedure | null = null
  surgeryDate: string = Dates.dayString(new Date(Date.now() - 7 * 86_400_000))

  // the beta consent, accepted before any account exists and carried into
  // whichever call creates the session
  consent: ConsentAcceptance | null = null

  verificationId: number | null = null
  phoneMasked: string | null = null
  code = ''

  loading = false
  error: string | null = null

  private listeners = new Set<() => void>()
  private version = 0
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  snapshot = () => this.version
  notify(): void { this.version++; for (const fn of this.listeners) fn() }
  set<K extends keyof this>(key: K, value: this[K]): void { this[key] = value; this.notify() }

  get step(): Step { return this.route[this.route.length - 1] ?? 'welcome' }

  get canSearch(): boolean { return this.name.trim().length >= 2 }
  get phoneLooksValid(): boolean { return this.phone.replace(/\D/g, '').length >= 10 }
  get canEnroll(): boolean { return this.selected != null && this.phoneLooksValid && !this.loading }
  get canJoin(): boolean {
    return this.canSearch && this.phoneLooksValid && !this.loading && (this.path !== 'joinAfterSurgery' || this.procedure != null)
  }

  /** The dots in the bar, for the clinic path. */
  get stepsShown(): Step[] { return ['consent', 'hospital', 'path', 'identity', 'verify', 'health', 'wearable'] }

  /** "Step 3 of 5" for the screen, counted along the person's own path. */
  eyebrow(step: Step): string {
    const shown = this.stepsShown
    const i = shown.indexOf(step)
    return i < 0 ? 'Almost done' : `Step ${i + 1} of ${shown.length}`
  }

  /** Forward pushes; a step already on the stack pops back to it. */
  go(next: Step): void {
    this.error = null
    if (next === 'welcome') this.route = []
    else {
      const i = this.route.indexOf(next)
      this.route = i >= 0 ? this.route.slice(0, i + 1) : [...this.route, next]
    }
    this.notify()
  }

  pop(): void {
    this.error = null
    this.route = this.route.slice(0, -1)
    this.notify()
  }

  choose(path: Path): void {
    this.path = path
    this.candidates = []
    this.selected = null
    const next: Step = path === 'findRecord' ? 'identity' : 'join'
    // Switching between the two record forms replaces the form rather than
    // stacking one on the other, so Back still means "how are you joining?".
    const last = this.route[this.route.length - 1]
    if ((last === 'join' || last === 'identity') && last !== next) {
      this.error = null
      this.route = [...this.route.slice(0, -1), next]
      this.notify()
    } else {
      this.go(next)
    }
  }

  /** A hospital picked from the list: the record search starts over. */
  pickHospital(h: Hospital): void {
    this.hospital = h
    this.candidates = []
    this.selected = null
    if (this.signingIn) this.choose('findRecord')
    else this.go('path')
  }

  /** The consent accepted in onboarding: carried into the call that
   *  creates the session, and the signature doubles as the name. */
  acceptConsent(accepted: ConsentAcceptance): void {
    this.consent = accepted
    if (!this.name && accepted.signature) this.name = accepted.signature
    this.go('hospital')
  }

  /** Welcome's two doors: set up, or sign back in. */
  begin(signingIn: boolean): void {
    this.signingIn = signingIn
    this.go(this.consent ? 'hospital' : 'consent')
  }

  async loadHospitals(api: APIClient): Promise<void> {
    try { this.set('hospitals', await api.hospitals()) } catch (e) { this.set('error', (e as Error).message) }
  }

  async loadProcedures(api: APIClient): Promise<void> {
    if (this.procedures.length) return
    try { this.set('procedures', await api.procedures()) } catch { /* the chips stay empty */ }
  }

  get filteredHospitals(): Hospital[] {
    const q = this.hospitalQuery.trim().toLowerCase()
    if (!q) return this.hospitals
    return this.hospitals.filter((h) =>
      h.name.toLowerCase().includes(q) || (h.system ?? '').toLowerCase().includes(q) || h.city.toLowerCase().includes(q))
  }

  /** Runs as the name is typed (the view debounces). Keeps a chosen
   *  candidate only while it is still in the results. */
  async search(api: APIClient): Promise<void> {
    if (!this.hospital || !this.canSearch) {
      this.candidates = []
      this.selected = null
      this.notify()
      return
    }
    this.set('searching', true)
    try {
      const found = await api.search(this.hospital.id, this.name, this.phoneLooksValid ? this.phone : null)
      this.candidates = found
      if (this.selected && !found.some((c) => c.patientId === this.selected!.patientId)) this.selected = null
      if (found.length === 1) this.selected = found[0]
    } catch {
      this.candidates = []
    } finally {
      this.set('searching', false)
    }
  }

  async enroll(api: APIClient, app: AppModel): Promise<void> {
    if (!this.selected || !this.hospital) return
    this.loading = true
    this.set('error', null)
    try {
      const r = await api.enroll(this.selected.patientId, this.hospital.id, this.phone, this.consent)
      this.handle(r, app)
    } catch (e) {
      this.error = (e as Error).message
    } finally {
      this.set('loading', false)
    }
  }

  async join(api: APIClient, app: AppModel): Promise<void> {
    if (!this.hospital) return
    this.loading = true
    this.set('error', null)
    try {
      const r = await api.join({
        hospitalId: this.hospital.id, name: this.name, phone: this.phone, dateOfBirth: this.dateOfBirth,
        hadSurgery: this.path === 'joinAfterSurgery', procedureType: this.procedure?.id ?? null,
        surgeryDate: this.surgeryDate, consent: this.consent,
      })
      this.handle(r, app)
    } catch (e) {
      if (e instanceof APIError && e.status === 409) {
        // The number is already on a record here. Don't dead-end: take them
        // to find-my-record, where the phone match lists that record.
        this.choose('findRecord')
        this.error = `This number is already on a record at ${this.hospital.name}. Pick it below and you’re in.`
      } else {
        this.error = (e as Error).message
      }
    } finally {
      this.set('loading', false)
    }
  }

  async verify(api: APIClient, app: AppModel): Promise<void> {
    if (this.verificationId == null) return
    this.loading = true
    this.set('error', null)
    try {
      this.handle(await api.verify(this.verificationId, this.code, this.consent), app)
    } catch (e) {
      this.error = (e as Error).message
    } finally {
      this.set('loading', false)
    }
  }

  /** Re-send: whichever call started the verification. */
  async resend(api: APIClient, app: AppModel): Promise<void> {
    if (this.path === 'findRecord') await this.enroll(api, app)
    else await this.join(api, app)
  }

  private handle(r: EnrollResponse, app: AppModel): void {
    switch (r.status) {
      case 'verification_required':
        this.verificationId = r.verificationId ?? null
        this.phoneMasked = r.phoneMasked ?? null
        this.code = ''
        this.go('verify')
        break
      case 'enrolled':
        if (!r.sessionToken || !r.me) throw new APIError(0, 'The server didn’t return a session.')
        app.adoptSession(r.sessionToken, r.me)
        this.go('health')
        break
      default:
        throw new APIError(0, `Unexpected status ${r.status}`)
    }
  }
}

export function useOnboarding(model: OnboardingModel): OnboardingModel {
  useSyncExternalStore(model.subscribe, model.snapshot, model.snapshot)
  return model
}
