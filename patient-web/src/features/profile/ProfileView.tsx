/* The profile sheet: one card per group, a quiet header inside it, rows
   split by inset dividers, and footers as muted text under the card
   (Features/Profile/ProfileView.swift). */

import { useState, type ReactNode } from 'react'
import { useApp } from '../../core/appModel'
import { AppConfig } from '../../core/config'
import { Dates, DOT, isRecovery, type Me } from '../../core/models'
import { useSpokenVoice } from '../../core/speech'
import { appearanceLabel, useAppearance, type AppearanceMode } from '../../ui/appearance'
import { Card, CardHeader, CloseButton, IconTile, Initials, InsetDivider, NavBar, Screen, Segmented, Sheet, Spinner, type Category } from '../../ui/components'
import { Sym } from '../../ui/icons'
import { Glyph, ListRow } from '../../ui/rows'
import { ConsentReadView } from '../consent/ConsentView'

export function ProfileView({ onDone }: { onDone: () => void }) {
  const app = useApp()
  const { mode, setMode } = useAppearance()
  const voice = useSpokenVoice()
  const [serverURL, setServerURL] = useState(AppConfig.baseURL)
  const [signingOut, setSigningOut] = useState(false)
  const [reading, setReading] = useState(false)
  const me = app.me

  const saveServer = () => {
    const clean = serverURL.trim()
    if (clean === '' || /^https?:\/\//.test(clean)) {
      AppConfig.baseURL = clean
      void app.refreshAll()
    }
  }

  return (
    <>
      <Screen nav={(s) => <NavBar title="Profile" scrolled={s} trailing={<CloseButton onClick={onDone} />} />}>
        <div className="content" style={{ gap: 22, padding: '8px 18px 28px' }}>
          {me && (
            <>
              <AboutCard me={me} />
              {me.patient.careTeam.length > 0 && (
                <Group title="Care team">
                  {me.patient.careTeam.map((m, i) => (
                    <div key={i}>
                      {i > 0 && <InsetDivider leading={16} />}
                      <Row label={m.role.charAt(0).toUpperCase() + m.role.slice(1)} value={m.name} />
                    </div>
                  ))}
                </Group>
              )}
              <Group title="Connections" footer="Task texts come from your care team’s MedPull number. Reply 1 to any of them to do the task by text, or open it here.">
                <ListRow title="Apple Health and wearables" subtitle={connectionsLine(me)} symbol="heart.fill" family="violet"
                  onClick={() => app.setShowConnections(true)} />
                <InsetDivider leading={16} />
                <Row label="Texts from MedPull" value={me.features.sms ? 'On' : 'Not set up on this server'} icon="message.fill" family="blue" />
                {me.consent?.acceptedAt && (
                  <>
                    <InsetDivider leading={16} />
                    <button type="button" className="row-button" onClick={() => setReading(true)}>
                      <div className="hstack" style={{ gap: 14, padding: '0 16px', minHeight: 48 }}>
                        <IconTile name="doc.text.fill" family="violet" />
                        <span className="stack-2 grow">
                          <span className="t-copy-lg c-ink">Beta consent</span>
                          <span className="t-label c-muted">Accepted {Dates.displayDate(me.consent.acceptedAt)}</span>
                        </span>
                        <span className="c-muted"><Sym name="chevron.right" size={13} weight="semibold" /></span>
                      </div>
                    </button>
                  </>
                )}
              </Group>
            </>
          )}

          <Group title="Appearance" footer="Light is the default. System follows your device’s own light or dark setting.">
            <div style={{ padding: '12px 16px' }}>
              <Segmented<AppearanceMode>
                label="Appearance"
                value={mode}
                onChange={setMode}
                options={(['light', 'dark', 'system'] as AppearanceMode[]).map((m) => ({ value: m, label: appearanceLabel[m] }))}
              />
            </div>
          </Group>

          <Group title="Voice" footer={voice.advice}>
            <Row label="Spoken replies" value={voice.label} icon="waveform" family="indigo" />
          </Group>

          <Group title="Developer" footer={`Where this app talks to. Leave it empty to use the address this page was opened from. Built-in: ${AppConfig.builtInBaseURL || 'this origin'}`}>
            <input className="t-copy-lg c-ink" style={{ width: '100%', minHeight: 48, padding: '0 16px', border: 0, background: 'none' }}
              placeholder="Server URL" value={serverURL} inputMode="url" autoCapitalize="none" autoCorrect="off" aria-label="Server URL"
              onChange={(e) => setServerURL(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') saveServer() }} />
            <InsetDivider leading={16} />
            <ActionRow title="Save server" onClick={saveServer} />
          </Group>

          <Group>
            <button type="button" className="row-button" disabled={signingOut}
              onClick={() => { setSigningOut(true); void app.signOut().then(onDone) }}>
              <div className="hstack c-risk-high" style={{ padding: '0 16px', minHeight: 50 }}>
                <span className="t-copy-lg-m">Sign out</span>
                <span className="spacer" />
                {signingOut && <Spinner size={16} className="c-muted" />}
              </div>
            </button>
          </Group>
        </div>
      </Screen>
      <Sheet open={reading} onClose={() => setReading(false)}>
        <ConsentReadView onDone={() => setReading(false)} />
      </Sheet>
    </>
  )
}

function connectionsLine(me: Me): string {
  const apple = me.wearables.appleHealth.connected
  const n = me.wearables.devices.length
  const parts = [apple ? 'Apple Health connected' : 'Apple Health not connected']
  if (n > 0) parts.push(`${n} wearable${n === 1 ? '' : 's'}`)
  return parts.join(DOT)
}

/** Identity on top, then the facts about this patient's enrolment. */
function AboutCard({ me }: { me: Me }) {
  return (
    <Card padding={0}>
      <div className="hstack" style={{ gap: 14, padding: 16 }}>
        <Initials text={me.patient.initials} size={56} />
        <div className="stack-2 grow">
          <span className="t-subhead-sb c-ink">{me.patient.name}</span>
          <span className="t-copy c-muted">{me.patient.procedureDisplay}</span>
        </div>
      </div>
      <InsetDivider leading={16} />
      {isRecovery(me.patient) && me.patient.surgeryDate ? (
        <>
          <Row label="Surgery" value={Dates.displayDate(me.patient.surgeryDate)} />
          <InsetDivider leading={16} />
          <Row label="Post-op day" value={String(me.patient.postopDay ?? 0)} />
        </>
      ) : (
        <Row label="Joined" value={Dates.displayDate(me.patient.joinedDate)} />
      )}
      {me.patient.hospital && <><InsetDivider leading={16} /><Row label="Hospital" value={me.patient.hospital.name} /></>}
      {me.patient.phoneMasked && <><InsetDivider leading={16} /><Row label="Mobile" value={me.patient.phoneMasked} /></>}
      <div style={{ height: 4 }} />
    </Card>
  )
}

/** A titled card with an optional footer under it. */
function Group({ title, footer, children }: { title?: string; footer?: string; children: ReactNode }) {
  return (
    <div className="stack-8">
      <Card padding={0}>
        {title && <CardHeader title={title} />}
        {children}
        {title && <div style={{ height: 4 }} />}
      </Card>
      {footer && <span className="t-label c-muted px-16">{footer}</span>}
    </div>
  )
}

function Row({ label, value, icon, family = 'blue' }: { label: string; value: string; icon?: string; family?: Category }) {
  return (
    <div className="hstack" style={{ padding: '10px 16px', minHeight: 48 }}>
      <span className="hstack" style={{ gap: 14 }}>
        {icon && <Glyph name={icon} family={family} />}
        <span className="t-copy-lg c-ink">{label}</span>
      </span>
      <span className="spacer" />
      <span className="t-copy-lg c-muted" style={{ textAlign: 'right' }}>{value}</span>
    </div>
  )
}

function ActionRow({ title, onClick }: { title: string; onClick: () => void }) {
  return (
    <button type="button" className="row-button" onClick={onClick}>
      <span className="t-copy-lg-m c-brand-ink" style={{ display: 'flex', alignItems: 'center', minHeight: 48, padding: '0 16px' }}>{title}</span>
    </button>
  )
}
