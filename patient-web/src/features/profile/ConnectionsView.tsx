/* Where the data comes from: Apple Health and any linked wearable. A
   settings screen, reached from Profile, the Today nudge and a
   `medpull://wearables` link (Features/Profile/ConnectionsView.swift).
   On the web Apple Health cannot connect, so its card only reports what
   the phone connected and says where the connection is made. */

import { useEffect, useState } from 'react'
import { messageFor, useApp } from '../../core/appModel'
import { IPHONE_NEEDED } from '../../core/health'
import { Dates } from '../../core/models'
import { Card, CloseButton, ErrorBanner, InsetDivider, NavBar, Screen, SecondaryButton } from '../../ui/components'
import { Sym } from '../../ui/icons'
import { Glyph, ListRow, StateLabel } from '../../ui/rows'

export function ConnectionsView({ onDone }: { onDone: () => void }) {
  const app = useApp()
  const [linking, setLinking] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void app.refreshWearables(false, false)
    // Back from the wearable's sign-in page: ask the aggregator what changed.
    const onFocus = () => { void app.refreshWearables(true, false) }
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [app])

  const appleConnected = app.wearables?.appleHealth.connected ?? app.me?.wearables.appleHealth.connected ?? false
  const lastSync = app.wearables?.appleHealth.lastSyncAt ?? app.me?.wearables.appleHealth.lastSyncAt ?? null
  const junctionReady = app.me?.features.appleHealth ?? false
  const devices = app.wearables?.devices ?? app.me?.wearables.devices ?? []

  const addWearable = async () => {
    setLinking(true)
    setError(null)
    try {
      const r = await app.api.wearableLink()
      window.open(r.linkUrl, '_blank', 'noopener')
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setLinking(false)
    }
  }

  return (
    <Screen fogHeight={300} nav={(s) => <NavBar title="Connections" scrolled={s} trailing={<CloseButton onClick={onDone} />} />}>
      <div className="content" style={{ padding: '8px 18px 28px' }}>
        <Card>
          <div className="stack-12">
            <div className="hstack">
              <Glyph name="heart.fill" family="violet" size={40} />
              <div className="stack-3 grow">
                <h3 className="t-lede-m c-ink" style={{ margin: 0 }}>Apple Health</h3>
                <StateLabel text={appleConnected ? 'Connected' : 'Not connected'} tone={appleConnected ? 'low' : 'missing'} />
              </div>
            </div>
            {appleConnected ? (
              <>
                <span className="t-copy c-body">
                  {lastSync ? `Last data ${Dates.relative(lastSync)}` : 'Syncing in the background. Data reaches your care team as it arrives.'}
                </span>
                <span className="t-label c-muted">Syncing runs on your iPhone, where Health lives. Open the MedPull iPhone app to sync now or send walking data.</span>
              </>
            ) : (
              <div className="hstack-8" style={{ alignItems: 'flex-start' }}>
                <span className="c-muted" style={{ paddingTop: 2 }}><Sym name="iphone" size={16} weight="medium" /></span>
                <span className="t-copy c-body">{IPHONE_NEEDED}</span>
              </div>
            )}
          </div>
        </Card>

        <Card padding={0}>
          <div className="hstack" style={{ padding: 16 }}>
            <Glyph name="applewatch" family="blue" size={40} />
            <div className="stack-3 grow">
              <h3 className="t-lede-m c-ink" style={{ margin: 0 }}>Wearables</h3>
              <span className="t-label c-muted">{devices.length === 0 ? 'Oura, Garmin, WHOOP, Fitbit, Withings, Polar.' : `${devices.length} linked`}</span>
            </div>
          </div>
          {devices.length === 0 ? (
            <span className="t-copy c-body" style={{ display: 'block', padding: '0 16px 14px' }}>Sign in once on their page and it syncs on its own.</span>
          ) : (
            <>
              {devices.map((d) => (
                <div key={d.provider + d.model}>
                  <InsetDivider leading={16} />
                  <ListRow title={d.model} subtitle={d.lastSyncAt ? `Synced ${Dates.relative(d.lastSyncAt)}` : 'Waiting for first sync'} chevron={false}
                    trailing={<StateLabel text={d.status.charAt(0).toUpperCase() + d.status.slice(1)}
                      tone={d.status === 'connected' ? 'low' : d.status === 'error' ? 'high' : 'missing'} />} />
                </div>
              ))}
              <InsetDivider leading={16} />
            </>
          )}
          <div style={{ padding: 16 }}>
            <SecondaryButton title={devices.length === 0 ? 'Add a wearable' : 'Add another'} icon="link" loading={linking}
              disabled={!junctionReady} onClick={() => void addWearable()} />
          </div>
        </Card>
        {error && <ErrorBanner text={error} />}
        <span className="footnote px-4">Nothing is written to Health. Turn any type off in the Health app and MedPull simply won’t read it.</span>
      </div>
    </Screen>
  )
}
