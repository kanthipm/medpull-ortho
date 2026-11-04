/* MedPull's own measurements, as a tab of their own: three short tests the
   phone runs and the server scores the same way for every patient, so the
   numbers compare week to week (Features/Measure/MeasureTab.swift). */

import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../../core/appModel'
import { signalFor } from '../../core/models'
import { Card, NavBar, PrimaryButton, Rise, Screen, SecondaryButton, Sheet, useGone } from '../../ui/components'
import { Glyph, RowDivider, SectionTitle, StateLabel } from '../../ui/rows'
import { SignalRow } from '../progress/ProgressTab'
import { flowSubtitle, flowSymbol, flowTitle, isMeasured, measureFlows, measureStatus, rank, type MeasureFlow, type MeasureStatus } from '../progress/progressModel'
import { GuidedWalkView, RangeOfMotionView } from './MeasureView'

export function MeasureTab() {
  const app = useApp()
  const navigate = useNavigate()
  const [flow, setFlow] = useState<MeasureFlow | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const titleRef = useRef<HTMLHeadingElement | null>(null)
  const titleGone = useGone(titleRef, scrollRef)

  const statuses = measureFlows.map((f) => measureStatus(f, app.portfolio))
  const results = app.portfolio.filter(isMeasured).sort((a, b) => rank(a.key) - rank(b.key))

  const close = () => {
    setFlow(null)
    void app.refreshPortfolio(false)
  }

  return (
    <>
      <Screen scrollRef={scrollRef} fogHeight={360} withTabBar nav={(s) => <NavBar title="Measure" titleHidden={!titleGone} scrolled={s} />}>
        <div className="content">
          <h1 ref={titleRef} className="large-title">Measure</h1>
          <span className="t-copy-lg c-body lh-2 px-4" style={{ marginTop: -8 }}>
            Your phone reads how you walk, how far you can go, and how far a joint bends. Same method every time, so a change is yours and not the device’s.
          </span>
          {statuses.map((s, i) => <Rise key={s.flow} index={i}><TestCard status={s} onStart={() => setFlow(s.flow)} /></Rise>)}
          {results.length > 0 && (
            <Rise index={3}>
              <div className="section">
                <SectionTitle title="Your readings" note="last two weeks" />
                <Card padding={0}>
                  {results.map((m, i) => (
                    <div key={m.key}>
                      <button type="button" className="row-button" onClick={() => navigate(`/measure/signals/${m.key}`)}>
                        <SignalRow metric={m} signal={signalFor(app.metrics, m.key)} />
                      </button>
                      {i < results.length - 1 && <RowDivider />}
                    </div>
                  ))}
                </Card>
              </div>
            </Rise>
          )}
          <span className="footnote px-4">Results go to your care team’s console beside your wearable data. Nothing here is a diagnosis.</span>
        </div>
      </Screen>
      <Sheet open={flow != null} onClose={close}>
        {flow === 'guidedWalk' && <GuidedWalkView sixMinute={false} onClose={close} />}
        {flow === 'sixMinuteWalk' && <GuidedWalkView sixMinute onClose={close} />}
        {flow === 'rangeOfMotion' && <RangeOfMotionView onClose={close} />}
      </Sheet>
    </>
  )
}

/** One test: what it is, how long it takes, when it was last done, and
 *  Start. The due test leads with the filled button; the rest are quiet. */
function TestCard({ status: s, onStart }: { status: MeasureStatus; onStart: () => void }) {
  return (
    <Card>
      <div className="stack-12">
        <div className="hstack-top">
          <Glyph name={flowSymbol[s.flow]} family="teal" size={40} />
          <div className="stack-3 grow">
            <div className="hstack-8" style={{ alignItems: 'baseline' }}>
              <h3 className="t-lede-m c-ink" style={{ margin: 0 }}>{flowTitle[s.flow]}</h3>
              <span className="spacer" />
              <StateLabel text={s.dueLabel} tone={s.isDue ? 'med' : 'low'} />
            </div>
            <span className="t-copy c-body">{flowSubtitle[s.flow]}</span>
            <span className="t-label c-muted figures">{s.lastLine ? `Last: ${s.lastLine}` : 'Nothing recorded yet.'}</span>
          </div>
        </div>
        {s.isDue
          ? <PrimaryButton title="Start" icon="play.fill" onClick={onStart} />
          : <SecondaryButton title="Do it again" icon="arrow.counterclockwise" onClick={onStart} />}
      </div>
    </Card>
  )
}
