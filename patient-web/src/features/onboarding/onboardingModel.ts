/* The onboarding flow's state (Features/Onboarding/OnboardingModel.swift),
   the clinic path only: consent, hospital, how you are joining, find my
   record or start one, the code by text, wearables, done. The phone's
   Apple Health step has no web equivalent and is left out. */

import { useSyncExternalStore } from 'react'
import { APIClient, APIError } from '../../core/api'
import type { AppModel } from '../../core/appModel'
import { codeIsOut, Dates, needsConsent, type Candidate, type ConsentAcceptance, type EnrollResponse, type Hospital, type Procedure } from '../../core/models'

/** Every screen the flow can show. The order is load-bearing for
 *  `isPastEnrollment` only. */
export const steps = ['welcome', 'consent', 'hospital', 'path', 'identity', 'join', 'verify', 'wearable', 'done'] as const
export type Step = (typeof steps)[number]

/** Steps after the session exists. Going back from these would land on a
 *  form that has already done its job, so they hide the back button. */
export const isPastEnrollment = (s: Step) => steps.indexOf(s) >= steps.indexOf('wearable')

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
  /** Text-first: the server could not text the code yet, because on
   *  Sendblue's free plan a number has to text the line once before it can
   *  be reached. The verify step then asks for that one text and polls;
   *  cleared the moment the code goes out. */
  textFirst = false
  textTo: string | null = null
  textBody: string | null = null

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

  /** The dots in the bar, for the clinic path. The consent sits where it is
   *  asked — before a new record is created — and not at all for a returning
   *  patient finding their record: the server says whether that account
   *  still has a form to sign, and `handle` shows it then. */
  get stepsShown(): Step[] {
    return this.path === 'findRecord'
      ? ['hospital', 'path', 'identity', 'verify', 'wearable']
      : ['hospital', 'path', 'consent', 'join', 'verify', 'wearable']
  }

  /** Whether `s` is at or before the current step along THIS path, so a
   *  step shown out of declaration order (the consent) lights up where it
   *  is walked. */
  reached(s: Step): boolean {
    const shown = this.stepsShown
    const here = shown.indexOf(this.step)
    const there = shown.indexOf(s)
    if (here < 0 || there < 0) return steps.indexOf(s) <= steps.indexOf(this.step)
    return there <= here
  }

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
    // Finding an existing record asks nothing here: the server reports
    // whether that account still needs to sign. Starting a record creates an
    // account, so the consent comes first — once.
    const next: Step = path === 'findRecord' ? 'identity' : this.consent ? 'join' : 'consent'
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

  /** The consent agreed to. Before any account exists it is carried into the
   *  call that creates the session (and the signature doubles as the name).
   *  Asked after an enrolment the server reported as still needing a
   *  signature, it is recorded there and then against the session. */
  async agree(accepted: ConsentAcceptance, app: AppModel): Promise<void> {
    if (app.me) {
      await app.acceptConsent(accepted)
      this.go('wearable')
      return
    }
    this.consent = accepted
    if (!this.name && accepted.signature) this.name = accepted.signature
    this.go('join')
  }

  /** Welcome's two doors: set up, or sign back in. Neither asks for the
   *  consent up front: a returning patient has signed already, and the
   *  server says so. */
  begin(signingIn: boolean): void {
    this.signingIn = signingIn
    this.go('hospital')
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
      if (e instanceof APIError && e.status === 409 && e.message.toLowerCase().includes('sign in')) {
        // The number is on a MedPull Personal account, not a hospital
        // record, so the record search would never find it: the server's
        // own words say which door to use.
        this.error = e.message
      } else if (e instanceof APIError && e.status === 409) {
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

  // MARK: Text us first

  /** The `sms:` link that opens Messages with the first text already
   *  written. iOS takes `&body=`, Android `?body=`. */
  textFirstLink(): string | null {
    if (!this.textTo) return null
    const body = encodeURIComponent(this.textBody ?? 'Hi MedPull')
    const android = /Android/i.test(navigator.userAgent)
    return `sms:${this.textTo}${android ? '?' : '&'}body=${body}`
  }

  /** "I've sent it — send my code": the webhook may already have sent it
   *  when the text landed; if not, the server tries again now that the
   *  number is known to the provider. */
  async continueAfterText(api: APIClient, app: AppModel): Promise<void> {
    if (this.verificationId == null) return
    this.loading = true
    this.set('error', null)
    try {
      if (codeIsOut(await api.verificationStatus(this.verificationId))) {
        this.textFirst = false
        return
      }
      this.handle(await api.resendVerification(this.verificationId), app)
      if (this.textFirst) this.error = 'We haven’t got your text yet — give it a moment, or send it again.'
    } catch (e) {
      this.error = (e as Error).message
    } finally {
      this.set('loading', false)
    }
  }

  /** Polled while the step waits: the code goes out the moment the text
   *  lands, and the field appears by itself. */
  async pollForCode(api: APIClient): Promise<void> {
    if (this.verificationId == null || !this.textFirst) return
    try {
      if (codeIsOut(await api.verificationStatus(this.verificationId))) {
        this.error = null
        this.set('textFirst', false)
      }
    } catch {
      // keep waiting; the next tick asks again
    }
  }

  private handle(r: EnrollResponse, app: AppModel): void {
    switch (r.status) {
      case 'verification_required':
        this.verificationId = r.verificationId ?? null
        this.phoneMasked = r.phoneMasked ?? null
        this.code = ''
        // `codeSent` false means the number has never texted MedPull and the
        // server is waiting on that text before it can send anything.
        this.textFirst = (r.textFirst ?? false) && !(r.codeSent ?? true)
        this.textTo = r.textTo ?? null
        this.textBody = r.textBody ?? null
        this.go('verify')
        break
      case 'enrolled':
        if (!r.sessionToken || !r.me) throw new APIError(0, 'The server didn’t return a session.')
        app.adoptSession(r.sessionToken, r.me)
        // A returning account signs nothing it has already signed: the form
        // is shown only when the server says this account needs it (never
        // accepted, or the version moved), and `agree` records it against
        // the session that now exists.
        //
        // No Apple Health step here: a browser cannot reach HealthKit, so the
        // phone app owns that connection and the web flow goes straight to
        // the wearables.
        this.go(needsConsent(r.me) ? 'consent' : 'wearable')
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
