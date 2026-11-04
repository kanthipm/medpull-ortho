/* The beta consent form: the words the server publishes, one switch per
   permission (the required ones locked on, the research one a real
   choice), a typed name as signature, and Agree. Used in onboarding before
   any account exists, and as a gate over the app for an account that
   predates the form or meets a new version (Features/Personal/ConsentView.swift). */

import { useEffect, useState, type ReactNode } from 'react'
import { messageFor, useApp } from '../../core/appModel'
import { Dates, typeset, type ConsentAcceptance, type ConsentDocument } from '../../core/models'
import {
  Card, CardHeader, ErrorBanner, InsetDivider, MPButton, NavBar, NavTextButton, PrimaryButton, Screen,
  SecondaryButton, Spinner, StatusPill, Toggle,
} from '../../ui/components'

export function ConsentForm({ document, onAgree, busy = false, error }: {
  document: ConsentDocument
  onAgree: (a: ConsentAcceptance) => void
  busy?: boolean
  error?: string | null
}) {
  // Every permission starts on, including the optional one: the choice is
  // presented, and the row says it can be turned off here or later.
  const [scopes, setScopes] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(document.scopes.map((s) => [s.key, true])))
  const [signature, setSignature] = useState('')
  const [readAll, setReadAll] = useState(false)

  const requiredMet = document.scopes.filter((s) => s.required).every((s) => scopes[s.key])
  const canAgree = requiredMet && signature.trim().length >= 2 && !busy
  const paragraphs = document.text.split('\n\n').map((p) => p.trim()).filter(Boolean)

  return (
    <div className="stack-16">
      <div className="hstack-8">
        <StatusPill text="Beta" tone="med" />
        <span className="t-label c-muted">Version {document.version}</span>
      </div>
      <h1 className="t-display-s c-ink" style={{ margin: 0 }}>Before we start</h1>
      <p className="t-copy-lg c-body lh-2" style={{ margin: 0 }}>
        MedPull is a beta. Please read what we collect, where it goes and what you can do about it, then tick what you agree to and sign with your name.
      </p>

      <Card padding={0}>
        <CardHeader title="The form" />
        <div className="stack" style={{ paddingTop: 4 }}>
          {paragraphs.slice(0, readAll ? paragraphs.length : 3).map((para, i) => (
            <p key={i} className="t-copy c-body lh-3" style={{ margin: '0 16px 10px' }}>{typeset(para)}</p>
          ))}
          {paragraphs.length > 3 && (
            <div style={{ padding: '0 16px 12px' }}>
              <MPButton kind="plain" bare onClick={() => setReadAll((v) => !v)}>
                {readAll ? 'Show less' : 'Read the whole form'}
              </MPButton>
            </div>
          )}
        </div>
      </Card>

      <Card padding={0}>
        <CardHeader title="What you agree to" />
        {document.scopes.map((scope, i) => (
          <div key={scope.key}>
            <div className="switch-row" style={{ padding: '12px 16px', alignItems: 'flex-start' }}>
              <div className="grow" style={{ gap: 3 }}>
                <span className="t-copy-lg-m c-ink">{typeset(scope.label)}</span>
                <span className="t-label c-muted">{typeset(scope.detail)}</span>
                {scope.required
                  ? <span className="t-label c-brand-ink">Needed to use MedPull</span>
                  : <span className="t-label c-muted">Your choice. Change it later in Profile.</span>}
              </div>
              <Toggle checked={scopes[scope.key] ?? false} label={scope.label}
                onChange={(on) => setScopes((s) => ({ ...s, [scope.key]: on }))} />
            </div>
            {i < document.scopes.length - 1 && <InsetDivider leading={16} />}
          </div>
        ))}
        <div style={{ height: 4 }} />
      </Card>

      <div className="stack-8">
        <span className="t-label-m c-muted">Sign with your full name</span>
        <input className="field" placeholder="Full name" value={signature} autoComplete="name"
          onChange={(e) => setSignature(e.target.value)} aria-label="Full name" />
      </div>
      {error && <ErrorBanner text={error} />}
      <PrimaryButton title="Agree and continue" icon="checkmark" loading={busy} disabled={!canAgree} onClick={() => {
        onAgree({
          version: document.version,
          scopes: Object.fromEntries(document.scopes.map((s) => [s.key, scopes[s.key] ?? false])),
          signature: signature.trim(),
        })
      }} />
      <span className="t-label c-muted">Guidance for training and recovery — not medical advice. Questions: hello@medpull.org.</span>
    </div>
  )
}

/** Loads the form and shows it. The onboarding step and the gate both use it. */
export function ConsentLoader({ onAgree, footer }: {
  onAgree: (a: ConsentAcceptance) => Promise<void>
  footer?: ReactNode
}) {
  const app = useApp()
  const [document, setDocument] = useState<ConsentDocument | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let alive = true
    app.api.consentDocument().then(
      (doc) => { if (alive) { setDocument(doc); setLoadError(null) } },
      (e) => { if (alive) setLoadError(messageFor(e)) },
    )
    return () => { alive = false }
  }, [app, attempt])

  return (
    <div className="stack-16" style={{ padding: '8px 22px 28px' }}>
      {document ? (
        <ConsentForm document={document} busy={busy} error={error} onAgree={async (accepted) => {
          setBusy(true)
          setError(null)
          try { await onAgree(accepted) } catch (e) { setError(messageFor(e)) } finally { setBusy(false) }
        }} />
      ) : loadError ? (
        <>
          <ErrorBanner text={loadError} />
          <SecondaryButton title="Try again" icon="arrow.counterclockwise" onClick={() => setAttempt((a) => a + 1)} />
        </>
      ) : (
        <div className="hstack" style={{ paddingTop: 24, color: 'rgb(var(--brand))' }}>
          <Spinner />
          <span className="t-copy-lg c-body">Loading the form…</span>
        </div>
      )}
      {footer}
    </div>
  )
}

/** The gate: an account signed in without a current consent sees the form
 *  and nothing else until it agrees. Signing out is the only other door. */
export function ConsentGate() {
  const app = useApp()
  return (
    <Screen nav={(scrolled) => <NavBar title="Consent" scrolled={scrolled} />}>
      <ConsentLoader
        onAgree={(accepted) => app.acceptConsent(accepted)}
        footer={<MPButton kind="plain" fullWidth onClick={() => void app.signOut()}>Sign out instead</MPButton>}
      />
    </Screen>
  )
}

/** The consent, read back from Profile. */
export function ConsentReadView({ onDone }: { onDone: () => void }) {
  const app = useApp()
  const [document, setDocument] = useState<ConsentDocument | null>(null)
  useEffect(() => {
    app.api.consentDocument().then(setDocument).catch(() => setDocument(null))
  }, [app])
  const status = app.me?.consent
  return (
    <Screen nav={(scrolled) => (
      <NavBar title="Consent" scrolled={scrolled} trailing={<NavTextButton onClick={onDone}>Done</NavTextButton>} />
    )}>
      <div className="stack-14" style={{ padding: '8px 22px 28px' }}>
        {status?.acceptedAt && (
          <Card tint>
            <div className="stack-4">
              <span className="t-copy-lg-m c-ink">Accepted {Dates.displayDate(status.acceptedAt)}</span>
              <span className="t-label secondary">Version {status.version ?? '—'}</span>
            </div>
          </Card>
        )}
        {document ? (
          document.text.split('\n\n').map((para, i) => (
            <p key={i} className="t-copy c-body lh-3" style={{ margin: 0 }}>{typeset(para)}</p>
          ))
        ) : (
          <span style={{ color: 'rgb(var(--brand))' }}><Spinner /></span>
        )}
      </div>
    </Screen>
  )
}
