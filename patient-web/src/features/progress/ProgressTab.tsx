/* "Am I getting better?" First what the care team reads, in the patient's
   words; then every signal, grouped the way a patient thinks about them
   (movement, activity, rest, body) as quiet rows with a sparkline. A row
   opens the whole chart with the explanation behind it
   (Features/Progress/ProgressTab.swift). */

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../../core/appModel'
import { IPHONE_NEEDED } from '../../core/health'
import {
  Dates, DOT, hideUnit, isDailyTotal, isRecovery, isWaiting, latestText, signalFor, spokenText, toneForMetricState, typeset, unitOf,
  type Me, type PatientMetric, type PatientSignal, type PortfolioMetric, type Tone,
} from '../../core/models'
import { Card, InsetDivider, MPButton, NavBar, PrimaryButton, Rise, Screen, SecondaryButton, useGone } from '../../ui/components'
import { CardTitleRow, Chevron, Glyph, RowDivider, RowFigure, SectionTitle, Sparkline, StateLabel } from '../../ui/rows'
import { Sym } from '../../ui/icons'
import {
  careFamily, careSymbol, careTone, countdown, displayLabel, groupFor, groupTitle, isMeasured, metricFamily, metricSymbol, rank,
  signalGroups, type SignalGroup,
} from './progressModel'

export function ProgressTab() {
  const app = useApp()
  const navigate = useNavigate()
  const [showAll, setShowAll] = useState(false)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const titleRef = useRef<HTMLHeadingElement | null>(null)
  const titleGone = useGone(titleRef, scrollRef)

  useEffect(() => {
    if (app.portfolio.length === 0) void app.refreshPortfolio(false)
    if (!app.metrics) void app.refreshMetrics(false)
  }, [app])

  const grouped = signalGroups.map((g) => ({
    group: g,
    rows: app.portfolio.filter((m) => groupFor(m.key) === g).sort((a, b) => rank(a.key) - rank(b.key)),
  })).filter((e) => e.rows.length > 0)

  const metrics = app.metrics?.metrics ?? []
  const shown = showAll ? metrics : metrics.slice(0, 3)
  const waiting = app.metrics?.overall.waiting ?? 0

  return (
    <Screen scrollRef={scrollRef} fogHeight={360} withTabBar nav={(s) => <NavBar title="Progress" titleHidden={!titleGone} scrolled={s} />}>
      <div className="content">
        <h1 ref={titleRef} className="large-title">Progress</h1>
        {app.me && <Subtitle me={app.me} />}
        {metrics.length > 0 && (
          <Rise index={0}>
            <Card padding={0}>
              <CardTitleRow title="What your care team sees" note={waiting > 0 ? `${waiting} on the way` : null} />
              {app.metrics?.overall.blurb && (
                <p className="t-copy c-body lh-2" style={{ margin: '0 16px 10px' }}>{typeset(app.metrics.overall.blurb)}</p>
              )}
              <InsetDivider leading={16} />
              {shown.map((m, i) => (
                <div key={m.id}>
                  <button type="button" className="row-button" onClick={() => navigate(`/progress/metrics/${m.id}`)}>
                    <CareMetricRow metric={m} />
                  </button>
                  {i < shown.length - 1 && <RowDivider />}
                </div>
              ))}
              {metrics.length > 3 && (
                <>
                  <InsetDivider leading={16} />
                  <div style={{ padding: '10px 16px' }}>
                    <MPButton kind="plain" bare onClick={() => setShowAll((v) => !v)}>
                      {showAll ? 'Show fewer' : `Show all ${metrics.length}`}
                    </MPButton>
                  </div>
                </>
              )}
              {metrics.length <= 3 && <div style={{ height: 4 }} />}
            </Card>
          </Rise>
        )}
        {app.portfolio.length === 0 ? (
          <Rise index={1}><EmptyState /></Rise>
        ) : grouped.map((entry, i) => (
          <Rise key={entry.group} index={i + 1} id={entry.group}>
            <SignalSection group={entry.group} rows={entry.rows} onOpen={(m) => navigate(`/progress/signals/${m.key}`)} />
          </Rise>
        ))}
        <span className="footnote">Monitoring signals for your care team — not a diagnosis.</span>
      </div>
    </Screen>
  )
}

function Subtitle({ me }: { me: Me }) {
  const days = me.recovery.daysWithData ?? 0
  const full = me.recovery.daysUntilFullPicture
  const parts = [
    isRecovery(me.patient) && me.patient.postopDay != null ? `Day ${me.patient.postopDay}` : null,
    days > 0 ? `${days} days of data` : 'No data yet',
    full != null && full > 0 ? `full picture in ${full} ${full === 1 ? 'day' : 'days'}` : null,
  ].filter((p): p is string => !!p)
  return <span className="t-copy-lg c-body px-4" style={{ marginTop: -8 }}>{parts.join(DOT)}</span>
}

export function SignalSection({ group, rows, onOpen }: { group: SignalGroup; rows: PortfolioMetric[]; onOpen: (m: PortfolioMetric) => void }) {
  const app = useApp()
  return (
    <div className="section">
      <SectionTitle title={groupTitle[group]} note={group === 'movement' && rows.some(isMeasured) ? 'phone and watch' : null} />
      <Card padding={0}>
        {rows.map((m, i) => (
          <div key={m.key}>
            <button type="button" className="row-button" onClick={() => onOpen(m)}>
              <SignalRow metric={m} signal={signalFor(app.metrics, m.key)} />
            </button>
            {i < rows.length - 1 && <RowDivider />}
          </div>
        ))}
      </Card>
    </div>
  )
}

function EmptyState() {
  const app = useApp()
  const navigate = useNavigate()
  const me = app.me
  return (
    <Card>
      <div className="stack-14">
        <div className="hstack">
          <Glyph name="chart.xyaxis.line" family="teal" size={40} />
          <div className="stack-2 grow">
            <span className="t-copy-lg-m c-ink">Nothing to chart yet</span>
            <span className="t-copy c-body">Your signals arrive from Apple Health, a wearable, or a measurement with your phone.</span>
          </div>
        </div>
        {me && !me.wearables.appleHealth.connected && me.features.appleHealth && (
          <div className="stack-6">
            <PrimaryButton title="Connect Apple Health" icon="heart.fill" disabled />
            <span className="greyed-note">{IPHONE_NEEDED}</span>
          </div>
        )}
        <SecondaryButton title="Measure a walk with your phone" icon="figure.walk.motion" onClick={() => navigate('/measure')} />
      </div>
    </Card>
  )
}

/** One signal as a row: glyph, name, state in words, a two-week sparkline,
 *  the latest reading. */
export function SignalRow({ metric, signal }: { metric: PortfolioMetric; signal: PatientSignal | null }) {
  let stateLine: string
  let tone: Tone | null = null
  if (signal) {
    if (signal.state === 'waiting' && signal.daysLeftText) {
      stateLine = signal.daysLeftText.startsWith('waiting') ? 'Waiting on new data' : `Shows in ${signal.daysLeftText}`
    } else {
      switch (signal.state) {
        case 'good': stateLine = 'Steady'; break
        case 'watch': stateLine = 'Worth watching'; break
        case 'reviewing': stateLine = 'Team reviewing'; break
        default: stateLine = signal.stateLabel
      }
    }
    if (signal.state !== 'waiting') tone = toneForMetricState(signal.state)
  } else {
    const ago = Dates.agoWords(metric.latest.date)
    stateLine = ago.charAt(0).toUpperCase() + ago.slice(1)
  }
  return (
    <div className="row" style={{ minHeight: 56 }} aria-label={`${displayLabel(metric)}, ${spokenText(metric, metric.latest.value)}, ${stateLine}`}>
      <Glyph name={metricSymbol(metric.key)} family={metricFamily(metric)} />
      <span className="row-main" style={{ gap: 3 }}>
        <span className="row-title">{displayLabel(metric)}</span>
        {tone ? <StateLabel text={stateLine} tone={tone} /> : <span className="t-label c-muted">{stateLine}</span>}
      </span>
      {metric.series.length > 1 && <Sparkline values={metric.series.slice(-14).map((p) => p.value)} bars={isDailyTotal(metric)} />}
      <RowFigure value={latestText(metric)} unit={hideUnit(metric) ? null : unitOf(metric)} minWidth={56} />
      <Chevron />
    </div>
  )
}

/** One of the care team's metrics as a row: glyph, title, the state in
 *  words, and one sentence. */
export function CareMetricRow({ metric }: { metric: PatientMetric }) {
  const tone = careTone(metric)
  const text = isWaiting(metric) ? (countdown(metric) ?? metric.stateLabel) : metric.stateLabel
  return (
    <div className="row">
      <Glyph name={careSymbol(metric.id)} family={careFamily(metric.id)} />
      <span className="row-main" style={{ gap: 3 }}>
        <span className="row-title">{metric.title}</span>
        <StateLabel text={text} tone={tone} wrap />
      </span>
      <Chevron />
    </div>
  )
}

export { Sym }
