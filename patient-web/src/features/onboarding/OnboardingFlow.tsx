/* The first screens a patient sees, and the only ones without a session
   (Features/Onboarding/OnboardingFlow.swift), the clinic path: Welcome,
   the beta consent, the hospital, how you are joining, your record (or a
   new one), the code by text, Apple Health (which needs the iPhone app),
   wearables, done. */

import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { messageFor, useApp } from '../../core/appModel'
import { DOT, isRecovery, type Candidate, type Hospital } from '../../core/models'
import {
  Card, Chip, cx, EmptyRow, ErrorBanner, IconTile, InsetDivider, MPButton, NavBar, PrimaryButton, Screen,
  Spinner, StatusPill, Toggle, type Category,
} from '../../ui/components'
import { Sym } from '../../ui/icons'
import { ConsentLoader } from '../consent/ConsentView'
import { isPastEnrollment, OnboardingModel, steps, useOnboarding, type Step } from './onboardingModel'

export function OnboardingFlow() {
  const model = useOnboarding(useMemo(() => new OnboardingModel(), []))
  const step = model.step
  switch (step) {
    case 'welcome': return <WelcomeStep model={model} />
    case 'consent': return <ConsentStep model={model} />
    case 'hospital': return <HospitalStep model={model} />
    case 'path': return <PathStep model={model} />
    case 'identity': return <IdentityStep model={model} />
    case 'join': return <JoinStep model={model} />
    case 'verify': return <VerifyStep model={model} />
    case 'wearable': return <WearableStep model={model} />
    case 'done': return <DoneStep model={model} />
  }
}

/** The title is never drawn (the dots take the principal slot); it is what
 *  the NEXT screen's back button says. */
function backTitle(step: Step): string {
  switch (step) {
    case 'welcome': return 'Welcome'
    case 'consent': return 'Consent'
    case 'hospital': return 'Hospital'
    case 'path': return 'Joining'
    case 'identity': return 'Your record'
    case 'join': return 'About you'
    case 'verify': return 'Code'
    case 'wearable': return 'Wearables'
    case 'done': return 'All set'
  }
}

/** Progress through the flow: reached segments are ink; the current step
 *  is the long capsule. */
function StepDots({ model }: { model: OnboardingModel }) {
  const current = model.step
  return (
    <span className="step-dots" aria-hidden="true">
      {model.stepsShown.map((s) => (
        <i key={s} className={cx(steps.indexOf(s) <= steps.indexOf(current) && 'reached', s === current && 'current')} />
      ))}
    </span>
  )
}

/** Every form step: eyebrow, a light display title, a lede, the content,
 *  and a footer pinned above the home indicator. */
function StepScaffold({ model, eyebrow, title, subtitle, children, footer, fogHeight = 520 }: {
  model: OnboardingModel; eyebrow: string; title: string; subtitle?: string; children: ReactNode; footer?: ReactNode; fogHeight?: number
}) {
  const step = model.step
  const previous = model.route.length > 1 ? model.route[model.route.length - 2] : 'welcome'
  return (
    <Screen
      fogHeight={fogHeight}
      nav={(scrolled) => (
        <NavBar scrolled={scrolled} principal={step !== 'done' ? <StepDots model={model} /> : undefined} title={backTitle(step)}
          back={!isPastEnrollment(step) ? { label: backTitle(previous), onClick: () => model.pop() } : undefined} />
      )}
      bottom={footer ? <div className="footer-strip">{footer}</div> : undefined}
    >
      <div className="stack-10" style={{ padding: '8px 22px 16px' }}>
        <span className="t-eyebrow">{eyebrow}</span>
        <h1 className="t-display-s c-ink" style={{ margin: 0 }}>{title}</h1>
        {subtitle && <span className="t-copy-lg c-body lh-2">{subtitle}</span>}
        <div style={{ paddingTop: 14 }}>{children}</div>
      </div>
    </Screen>
  )
}

/** The quiet tertiary action — Skip / Send a new code. */
function QuietAction({ title, onClick }: { title: string; onClick: () => void }) {
  return <MPButton kind="plain" fullWidth onClick={onClick}>{title}</MPButton>
}

/** A feature line in the Apple "welcome sheet" pattern: a category tile, a
 *  title and one sentence. */
function FeatureRow({ icon, family, title, detail }: { icon: string; family: Category; title: string; detail: string }) {
  return (
    <div className="hstack-top" style={{ gap: 16 }}>
      <IconTile name={icon} family={family} size={44} />
      <div className="stack-3 grow">
        <span className="t-copy-lg-m c-ink">{title}</span>
        <span className="t-copy c-body">{detail}</span>
      </div>
    </div>
  )
}

/** A card that is a choice: tile, title, detail, chevron. */
function ChoiceCard({ icon, family, title, detail, onClick }: { icon: string; family: Category; title: string; detail: string; onClick: () => void }) {
  return (
    <button type="button" className="card-button" onClick={onClick}>
      <Card>
        <div className="hstack-top" style={{ gap: 14 }}>
          <IconTile name={icon} family={family} size={44} />
          <div className="stack-4 grow">
            <span className="t-lede-m c-ink">{title}</span>
            <span className="t-copy secondary lh-2">{detail}</span>
          </div>
          <span className="c-muted" style={{ paddingTop: 14 }}><Sym name="chevron.right" size={13} weight="semibold" /></span>
        </div>
      </Card>
    </button>
  )
}

// MARK: - Steps

function WelcomeStep({ model }: { model: OnboardingModel }) {
  return (
    <Screen fogHeight={760}>
      <div className="stack" style={{ minHeight: '100%', justifyContent: 'space-between', paddingTop: 32 }}>
        <div className="stack-18" style={{ padding: '0 24px' }}>
          <div className="hstack" style={{ gap: 14 }}>
            <span className="brand-mark" style={{ ['--side' as string]: '60px' }} aria-hidden="true"><img src={`${import.meta.env.BASE_URL}medpull-mark.svg`} alt="" /></span>
            <span className="t-subhead-m c-ink" style={{ letterSpacing: '-0.6px' }}>MedPull</span>
          </div>
          <div className="stack-12 rise" style={{ ['--i' as string]: 1 }}>
            <div className="hstack-8" style={{ flexWrap: 'wrap', paddingBottom: 2 }}>
              <span className="sky-badge glass-solid"><span className="lime-dot" style={{ ['--size' as string]: '7px' }} />Your recovery, with your care team</span>
              <StatusPill text="Beta" tone="med" />
            </div>
            <h1 className="t-display-m c-ink" style={{ margin: 0, whiteSpace: 'pre-line' }}>{'Hi there.\nLet’s get you set up.'}</h1>
            <span className="t-lede c-body lh-2">Your watch and your phone, read properly, with your care team after an operation or while they follow your everyday health. About two minutes.</span>
          </div>
          <div className="stack-18" style={{ paddingTop: 10 }}>
            <div className="rise" style={{ ['--i' as string]: 2 }}>
              <FeatureRow icon="figure.walk" family="teal" title="Your everyday signals"
                detail="Steps, sleep, HRV and heart rate flow in from Apple Health or your wearable. No typing." />
            </div>
            <div className="rise" style={{ ['--i' as string]: 3 }}>
              <FeatureRow icon="gauge.with.dots.needle.67percent" family="indigo" title="What your care team sees"
                detail="Walking, sleep, heart and your own check-ins, in plain words, with the reasons." />
            </div>
            <div className="rise" style={{ ['--i' as string]: 4 }}>
              <FeatureRow icon="person.2.fill" family="blue" title="One thread with your team"
                detail="Messages, tasks and the daily check-in in one place, with MedPull’s assistant on hand." />
            </div>
          </div>
        </div>
        <div className="stack-12 rise" style={{ ['--i' as string]: 5, padding: '28px 22px 18px' }}>
          <PrimaryButton title="Get started" icon="arrow.right" onClick={() => model.begin(false)} />
          <MPButton kind="plain" fullWidth onClick={() => model.begin(true)}>
            Already have an account? Sign in
          </MPButton>
          <span className="t-label c-body center">Monitoring signals for your care team — not a diagnosis.</span>
        </div>
      </div>
    </Screen>
  )
}

/** The beta consent, read before any account exists. What it records goes
 *  out with the call that creates the session. */
function ConsentStep({ model }: { model: OnboardingModel }) {
  return (
    <Screen nav={(s) => <NavBar scrolled={s} principal={<StepDots model={model} />} back={{ label: 'Welcome', onClick: () => model.pop() }} />}>
      <ConsentLoader onAgree={async (accepted) => model.acceptConsent(accepted)} />
    </Screen>
  )
}

function HospitalStep({ model }: { model: OnboardingModel }) {
  const app = useApp()
  useEffect(() => { void model.loadHospitals(app.api) }, [model, app])
  const list = model.filteredHospitals
  const pick = (h: Hospital) => model.pickHospital(h)
  return (
    <StepScaffold model={model} eyebrow="Step 1 of 5" title="Which hospital are you with?"
      subtitle="Your care team there will see what you share. You can pick by name, system or city.">
      <div className="stack-14">
        <label className="search">
          <Sym name="magnifyingglass" size={15} weight="medium" />
          <input placeholder="Search hospitals" value={model.hospitalQuery} autoCorrect="off" aria-label="Search hospitals"
            onChange={(e) => model.set('hospitalQuery', e.target.value)} />
          {model.hospitalQuery && (
            <button type="button" className="clear" onClick={() => model.set('hospitalQuery', '')} aria-label="Clear search">
              <Sym name="xmark.circle.fill" size={17} weight="regular" />
            </button>
          )}
        </label>
        {model.hospitals.length === 0 ? (
          model.error ? <ErrorBanner text={model.error} /> : <div className="center" style={{ padding: 16, color: 'rgb(var(--brand))' }}><Spinner /></div>
        ) : list.length === 0 ? (
          <Card><EmptyRow icon="building.2" title="No hospitals match" detail="Try the city, or just part of the name." /></Card>
        ) : (
          <Card padding={0}>
            {list.map((h, i) => (
              <div key={h.id}>
                <button type="button" className="row-button" onClick={() => pick(h)}>
                  <div className="hstack" style={{ gap: 14, padding: '12px 16px' }}>
                    <IconTile name="building.2.fill" family="blue" />
                    <span className="stack-2 grow">
                      <span className="t-copy-lg-m c-ink">{h.name}</span>
                      <span className="t-label c-muted">{[h.system, `${h.city}, ${h.state}`].filter(Boolean).join(DOT)}</span>
                    </span>
                    <span className="c-muted"><Sym name="chevron.right" size={13} weight="semibold" /></span>
                  </div>
                </button>
                {i < list.length - 1 && <InsetDivider />}
              </div>
            ))}
          </Card>
        )}
      </div>
    </StepScaffold>
  )
}

function PathStep({ model }: { model: OnboardingModel }) {
  return (
    <StepScaffold model={model} eyebrow="Step 2 of 5" title="How are you joining?"
      subtitle={`${model.hospital?.name ?? 'Your hospital'} looks after people with and without a surgery. Either way, what your care team sees is what you see here.`}>
      <div className="stack-12">
        <ChoiceCard icon="person.text.rectangle.fill" family="blue" title="My care team set me up"
          detail="The clinic already has a record for you, or you’ve used MedPull before. We’ll find it so their messages reach you here."
          onClick={() => model.choose('findRecord')} />
        <ChoiceCard icon="sparkles" family="violet" title="I’m new here"
          detail="Start a record now, with or without a surgery. Your activity, sleep and vitals build a picture your care team can see."
          onClick={() => model.choose('joinGeneral')} />
      </div>
    </StepScaffold>
  )
}

function IdentityStep({ model }: { model: OnboardingModel }) {
  const app = useApp()
  useEffect(() => {
    const t = setTimeout(() => { void model.search(app.api) }, 350)
    return () => clearTimeout(t)
  }, [model, app, model.name, model.phone])
  return (
    <StepScaffold model={model} eyebrow="Step 3 of 5" title="Let’s find your record"
      subtitle={`Your name as it’s on file at ${model.hospital?.name ?? 'the hospital'}, and a mobile number we can text. If the clinic already has your number, that finds you on its own.`}
      footer={<PrimaryButton title={model.selected ? 'That’s me — continue' : 'Find my record'} loading={model.loading} disabled={!model.canEnroll}
        onClick={() => void model.enroll(app.api, app)} />}>
      <div className="stack-14">
        <input className="field" placeholder="Full name" autoComplete="name" autoCorrect="off" value={model.name} aria-label="Full name"
          onChange={(e) => model.set('name', e.target.value)} autoFocus />
        <input className="field" placeholder="Mobile number" type="tel" autoComplete="tel" value={model.phone} aria-label="Mobile number"
          onChange={(e) => model.set('phone', e.target.value)} />
        {model.canSearch && (
          <div className="stack-8" style={{ paddingTop: 6 }}>
            <span className="hstack-8">
              <span className="t-label-m c-muted">{model.searching ? 'Looking you up…' : model.candidates.length === 0 ? 'No match yet' : 'Is this you?'}</span>
              {model.searching && <Spinner size={14} className="c-muted" />}
            </span>
            {model.candidates.map((c) => <CandidateRow key={c.patientId} c={c} selected={model.selected?.patientId === c.patientId} onClick={() => model.set('selected', c)} />)}
            {!model.searching && model.candidates.length === 0 && (
              <>
                <span className="t-copy c-body">Check the spelling, or ask the clinic which name they used. If they have your number, typing it above finds you too.</span>
                <MPButton kind="plain" bare onClick={() => model.choose('joinGeneral')}>Not on the list? Join as a new patient</MPButton>
              </>
            )}
          </div>
        )}
        {model.error && <ErrorBanner text={model.error} />}
      </div>
    </StepScaffold>
  )
}

function CandidateRow({ c, selected, onClick }: { c: Candidate; selected: boolean; onClick: () => void }) {
  return (
    <button type="button" className="select-card glass-solid" aria-pressed={selected} onClick={onClick}>
      <span className="mark"><Sym name={selected ? 'checkmark.circle.fill' : 'circle'} size={22} weight="regular" /></span>
      <span className="stack-2 grow">
        <span className="t-copy-lg-m c-ink">{c.displayName}</span>
        <span className="t-label c-body">{c.procedureDisplay}{DOT}{c.surgeryMonth}</span>
      </span>
      {c.phoneMatch && <StatusPill text="Number matches" tone="low" />}
    </button>
  )
}

function JoinStep({ model }: { model: OnboardingModel }) {
  const app = useApp()
  const [hasDOB, setHasDOB] = useState(false)
  const surgical = model.path === 'joinAfterSurgery'
  useEffect(() => { if (surgical) void model.loadProcedures(app.api) }, [surgical, model, app])
  const first = model.hospital?.name.split(' ')[0] ?? 'hospital'
  return (
    <StepScaffold model={model} eyebrow="Step 3 of 5" title="Tell us about you"
      subtitle={`This starts your record at ${model.hospital?.name ?? 'the hospital'}. Had an operation? Add it and we’ll follow your recovery. If not, we’ll follow your everyday signals.`}
      footer={<PrimaryButton title={surgical ? 'Create my record' : `Join ${first}`} loading={model.loading} disabled={!model.canJoin}
        onClick={() => void model.join(app.api, app)} />}>
      <div className="stack-14">
        <input className="field" placeholder="Full name" autoComplete="name" autoCorrect="off" value={model.name} aria-label="Full name" onChange={(e) => model.set('name', e.target.value)} />
        <input className="field" placeholder="Mobile number" type="tel" autoComplete="tel" value={model.phone} aria-label="Mobile number" onChange={(e) => model.set('phone', e.target.value)} />
        <Card padding={0}>
          <div className="switch-row">
            <IconTile name="calendar" family="indigo" />
            <span className="t-copy-lg-m c-ink grow">Add date of birth</span>
            <Toggle checked={hasDOB} label="Add date of birth" onChange={(on) => { setHasDOB(on); if (!on) model.set('dateOfBirth', null) }} />
          </div>
          {hasDOB && (
            <>
              <InsetDivider />
              <div style={{ padding: '6px 16px 6px 60px' }}>
                <input type="date" className="field date-input" max={new Date().toISOString().slice(0, 10)} aria-label="Date of birth"
                  value={model.dateOfBirth ?? ''} onChange={(e) => model.set('dateOfBirth', e.target.value || null)} />
              </div>
            </>
          )}
          <InsetDivider />
          <div className="switch-row">
            <IconTile name="cross.case.fill" family="violet" />
            <span className="t-copy-lg-m c-ink grow">I’m recovering from an operation</span>
            <Toggle checked={surgical} label="I’m recovering from an operation" onChange={(on) => model.set('path', on ? 'joinAfterSurgery' : 'joinGeneral')} />
          </div>
        </Card>
        {surgical && (
          <div className="stack-10 fade-in" style={{ paddingTop: 4 }}>
            <span className="t-label-m c-muted">Which operation?</span>
            {model.procedures.length === 0 ? <Spinner size={14} className="c-muted" /> : (
              <div className="chip-row" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
                {model.procedures.map((p) => (
                  <Chip key={p.id} label={p.label} selected={model.procedure?.id === p.id}
                    onClick={() => model.set('procedure', model.procedure?.id === p.id ? null : p)} />
                ))}
              </div>
            )}
            <label className="stack-6">
              <span className="t-copy-lg-m c-ink">Surgery date</span>
              <input type="date" className="field date-input" max={new Date().toISOString().slice(0, 10)} value={model.surgeryDate}
                onChange={(e) => { if (e.target.value) model.set('surgeryDate', e.target.value) }} />
            </label>
          </div>
        )}
        {model.error && <ErrorBanner text={model.error} />}
      </div>
    </StepScaffold>
  )
}

function VerifyStep({ model }: { model: OnboardingModel }) {
  const app = useApp()
  return (
    <StepScaffold model={model} eyebrow={model.eyebrow('verify')} title="Check your texts"
      subtitle={`We sent a code to ${model.phoneMasked ?? 'your number'}. It’s good for 10 minutes.`}
      footer={
        <>
          <PrimaryButton title="Verify" loading={model.loading} disabled={model.code.length < 4} onClick={() => void model.verify(app.api, app)} />
          <QuietAction title="Send a new code" onClick={() => void model.resend(app.api, app)} />
        </>
      }>
      <div className="stack-14">
        <input className="field figures" placeholder="6-digit code" inputMode="numeric" autoComplete="one-time-code" value={model.code} aria-label="6-digit code"
          onChange={(e) => model.set('code', e.target.value)} autoFocus
          onKeyDown={(e) => { if (e.key === 'Enter' && model.code.length >= 4) void model.verify(app.api, app) }} />
        {model.error && <ErrorBanner text={model.error} />}
      </div>
    </StepScaffold>
  )
}

const brands = ['Oura', 'Garmin', 'WHOOP', 'Fitbit', 'Withings', 'Polar']

function WearableStep({ model }: { model: OnboardingModel }) {
  const app = useApp()
  const [working, setWorking] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  useEffect(() => {
    const onFocus = () => { void app.refreshWearables(true, false) }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [app])
  return (
    <StepScaffold model={model} eyebrow="Almost done" title="Wear something else?"
      subtitle="Sign in once and it syncs on its own. An Apple Watch syncs through the MedPull iPhone app instead."
      footer={
        <>
          <PrimaryButton title="Add a wearable" icon="link" loading={working} disabled={!(app.me?.features.appleHealth ?? false)} onClick={async () => {
            setWorking(true)
            try { window.open((await app.api.wearableLink()).linkUrl, '_blank', 'noopener') } catch (e) { setFailure(messageFor(e)) } finally { setWorking(false) }
          }} />
          <QuietAction title="Skip" onClick={() => model.go('done')} />
        </>
      }>
      <div className="stack-12">
        <div className="chip-row" aria-label={`Works with ${brands.join(', ')}`}>
          {brands.map((b) => <span key={b} className="tag">{b}</span>)}
        </div>
        {failure && <ErrorBanner text={failure} />}
      </div>
    </StepScaffold>
  )
}

function DoneStep({ model }: { model: OnboardingModel }) {
  const app = useApp()
  const me = app.me
  const recovery = me ? isRecovery(me.patient) : false
  void model
  return (
    <Screen fogHeight={760}>
      <div className="stack" style={{ minHeight: '100%', justifyContent: 'space-between', paddingTop: 24 }}>
        <div className="stack-18" style={{ padding: '0 24px' }}>
          <div className="seal" style={{ width: 88, height: 88 }} aria-hidden="true"><Sym name="checkmark" size={35} weight="semibold" /></div>
          <div className="stack-10 rise" style={{ ['--i' as string]: 1 }}>
            <h1 className="t-display-m c-ink" style={{ margin: 0 }}>You’re all set, {me?.patient.firstName ?? 'there'}.</h1>
            <span className="t-lede c-body">Welcome to MedPull. Here’s what happens next.</span>
          </div>
          <div className="stack-18" style={{ paddingTop: 6 }}>
            {recovery ? (
              <>
                <div className="rise" style={{ ['--i' as string]: 2 }}><FeatureRow icon="message.fill" family="blue" title="We’ll text you" detail="When a task is ready, answer right in Messages or open the app. Either way your care team sees it." /></div>
                <div className="rise" style={{ ['--i' as string]: 3 }}><FeatureRow icon="checklist" family="teal" title="Small steps each day" detail="Exercises, walks and quick check-ins, sized for where you are in your recovery." /></div>
              </>
            ) : (
              <>
                <div className="rise" style={{ ['--i' as string]: 2 }}><FeatureRow icon="chart.line.uptrend.xyaxis" family="teal" title="Your picture fills in" detail="Your portfolio grows as your data arrives. Give it a day or two." /></div>
                <div className="rise" style={{ ['--i' as string]: 3 }}><FeatureRow icon="message.fill" family="blue" title="We’ll text you" detail="When your care team asks for something, answer by text or right here in the app." /></div>
              </>
            )}
            <div className="rise" style={{ ['--i' as string]: 4 }}><FeatureRow icon="waveform" family="indigo" title="Talk any time" detail="Tell MedPull how you’re doing in your own words. Anything important goes to your care team." /></div>
          </div>
        </div>
        <div className="rise" style={{ ['--i' as string]: 5, padding: '28px 22px 18px' }}>
          <PrimaryButton title="Open MedPull" icon="arrow.right" onClick={() => app.enterHome()} />
        </div>
      </div>
    </Screen>
  )
}
