/* One signal in full: the latest reading, its state in the care team's
   words, the two-week chart you can scrub, the numbers behind it, and the
   explanation the server wrote for it. Everything in ink on a card: a
   clinical number never sits on a gradient (Features/Progress/SignalDetailView.swift). */

import { useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useApp } from '../../core/appModel'
import {
  axisText, Dates, DOT, hideUnit, isDailyTotal, metricAverage, metricText, monthDayOf, pointDay, readinessSentence, signalFor,
  spokenText, toneForMetricState, typeset, unitOf,
  type MetricExplain, type MetricReadiness, type PortfolioMetric, type PortfolioPoint,
} from '../../core/models'
import { Card, EmptyRow, InsetDivider, NavBar, Screen, StatusPill } from '../../ui/components'
import { BigFigure } from '../../ui/rows'
import { useBack } from '../../ui/useBack'
import { displayLabel, isMeasured } from './progressModel'

export function SignalDetailRoute({ root }: { root: '/progress' | '/measure' }) {
  const app = useApp()
  const { key } = useParams()
  const back = useBack(root)
  const metric = app.portfolio.find((m) => m.key === key) ?? null
  const label = root === '/progress' ? 'Progress' : 'Measure'
  if (!metric) {
    return (
      <Screen fogHeight={300} withTabBar nav={(s) => <NavBar title="Signal" scrolled={s} back={{ label, onClick: back }} />}>
        <div className="content"><Card padding={0}><EmptyRow icon="chart.xyaxis.line" title="Nothing to chart yet" detail="This signal has no readings in the last two weeks." /></Card></div>
      </Screen>
    )
  }
  return <SignalDetailView metric={metric} back={{ label, onClick: back }} />
}

export function SignalDetailView({ metric, back }: { metric: PortfolioMetric; back: { label: string; onClick: () => void } }) {
  const app = useApp()
  const signal = signalFor(app.metrics, metric.key)
  const [picked, setPicked] = useState<Date | null>(null)
  const pickedPoint = useMemo(() => nearest(metric.series, picked), [metric.series, picked])
  const shown = pickedPoint ?? metric.latest
  const values = metric.series.map((p) => p.value)
  const average = metricAverage(metric)
  const first = metric.series[0] ? pointDay(metric.series[0]) : null
  const last = metric.series.length ? pointDay(metric.series[metric.series.length - 1]) : null
  const range = first && last && first.getTime() > 0 ? `${monthDayOf(first)} – ${monthDayOf(last)}` : null

  return (
    <Screen fogHeight={300} withTabBar nav={(s) => <NavBar title={displayLabel(metric)} scrolled={s} back={back} />}>
      <div className="content" style={{ gap: 16, paddingTop: 4 }}>
        <div className="stack-8 px-4">
          <div className="hstack" style={{ alignItems: 'baseline', gap: 10 }} aria-label={`${displayLabel(metric)}, ${spokenText(metric, shown.value)}, ${Dates.monthDay(shown.date)}`}>
            <BigFigure value={metricText(metric, shown.value)} unit={hideUnit(metric) ? null : unitOf(metric)} />
            <span className="spacer" />
            <span className="t-label c-muted figures">{pickedPoint ? Dates.monthDay(shown.date) : `Latest${DOT}${Dates.monthDay(shown.date)}`}</span>
          </div>
          {signal && signal.state !== 'waiting' ? (
            <div className="stack-6">
              <span><StatusPill text={signal.stateLabel} tone={toneForMetricState(signal.state)} /></span>
              <span className="t-copy-lg c-ink lh-2">{typeset(signal.headline)}</span>
            </div>
          ) : signal?.daysLeftText ? (
            <span className="t-copy c-body">
              {signal.daysLeftText.startsWith('waiting') ? 'Waiting on new data from your watch or phone.' : `Your care team’s read on this shows after ${signal.daysLeftText} of data.`}
            </span>
          ) : null}
        </div>
        <Card padding={0}>
          <div style={{ padding: '16px 12px 0' }}>
            <SeriesChart metric={metric} picked={picked} onPick={setPicked} />
          </div>
          <div className="stack-8" style={{ padding: '14px 16px 16px' }}>
            <div className="stats-grid">
              <Stat label="Average" value={average != null ? metricText(metric, average) : '—'} />
              <Stat label="Low" value={values.length ? metricText(metric, Math.min(...values)) : '—'} />
              <Stat label="High" value={values.length ? metricText(metric, Math.max(...values)) : '—'} />
              <Stat label="Days" value={String(metric.daysWithData)} />
            </div>
            {range && <span className="t-label c-muted figures">{range}{DOT}last two weeks</span>}
          </div>
        </Card>
        {signal?.explain && <ExplainCard explain={signal.explain} readiness={signal.readiness} />}
        {isMeasured(metric) && (
          <span className="t-label c-muted px-4">Measured by MedPull from your phone’s motion sensors, the same way for every patient, so week-to-week changes are yours and not the device’s.</span>
        )}
        <span className="footnote px-4">Monitoring signals for your care team — not a diagnosis.</span>
      </div>
    </Screen>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return <div className="stat"><span>{label}</span><b>{value}</b></div>
}

export function ExplainCard({ explain, readiness }: { explain: MetricExplain; readiness: MetricReadiness | null }) {
  const line = readinessSentence(readiness)
  return (
    <Card padding={0}>
      <div style={{ padding: '4px 0' }}>
        <ExplainBlock label="What it is" text={explain.what} />
        <InsetDivider leading={16} />
        <ExplainBlock label="Why it matters" text={explain.why} />
        <InsetDivider leading={16} />
        <ExplainBlock label="How to help it show" text={explain.help} />
        {line && <><InsetDivider leading={16} /><ExplainBlock label="Where it stands" text={line} /></>}
      </div>
    </Card>
  )
}

/** A label and a paragraph, one block of an explanation card. */
export function ExplainBlock({ label, text }: { label: string; text: string }) {
  return (
    <div className="stack-4" style={{ padding: '12px 16px' }}>
      <span className="t-label-m c-muted">{label}</span>
      <span className="t-copy c-ink lh-2">{typeset(text)}</span>
    </div>
  )
}

function nearest(series: PortfolioPoint[], picked: Date | null): PortfolioPoint | null {
  if (!picked || series.length === 0) return null
  const same = series.find((p) => Dates.sameDay(pointDay(p), picked))
  if (same) return same
  return series.reduce((best, p) =>
    Math.abs(pointDay(p).getTime() - picked.getTime()) < Math.abs(pointDay(best).getTime() - picked.getTime()) ? p : best)
}

// MARK: - The chart

const W = 320
const PAD = { top: 18, right: 44, bottom: 22, left: 4 }

/** Nice tick values for a y axis (about three of them). */
function ticks(lo: number, hi: number, includeZero: boolean, count = 3): number[] {
  let min = includeZero ? Math.min(0, lo) : lo
  let max = hi
  if (min === max) { min -= 1; max += 1 }
  const span = max - min
  const rough = span / count
  const mag = Math.pow(10, Math.floor(Math.log10(rough)))
  const norm = rough / mag
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag
  const start = Math.floor(min / step) * step
  const end = Math.ceil(max / step) * step
  const out: number[] = []
  for (let v = start; v <= end + step / 2; v += step) out.push(Math.round(v * 1e6) / 1e6)
  return out
}

/** The two-week series in ink: bars for a daily total, a line for a
 *  sampled reading; the newest mark in the brand fill; the average as a
 *  dashed rule; a scrub shows any day's value on an opaque capsule. */
export function SeriesChart({ metric, picked, onPick, height = 160 }: {
  metric: PortfolioMetric; picked: Date | null; onPick: (d: Date | null) => void; height?: number
}) {
  const svgRef = useRef<SVGSVGElement | null>(null)
  const bars = isDailyTotal(metric)
  const series = metric.series
  const days = series.map(pointDay)
  const xs = days.map((d) => d.getTime())
  const x0 = Math.min(...xs)
  const x1 = Math.max(...xs)
  const dayMs = 86_400_000
  const domain0 = bars ? x0 - dayMs / 2 : x0
  const domain1 = bars ? x1 + dayMs / 2 : x1
  const plotW = W - PAD.left - PAD.right
  const plotH = height - PAD.top - PAD.bottom
  const sx = (t: number) => PAD.left + ((t - domain0) / Math.max(domain1 - domain0, 1)) * plotW
  const ys = series.map((p) => p.value)
  const yTicks = ticks(Math.min(...ys), Math.max(...ys), bars)
  const y0 = yTicks[0]
  const y1 = yTicks[yTicks.length - 1]
  const sy = (v: number) => PAD.top + (1 - (v - y0) / Math.max(y1 - y0, 1e-9)) * plotH
  const pickedPoint = nearest(series, picked)
  const lastId = series.length ? series[series.length - 1].date : null
  const average = metricAverage(metric)
  const barW = Math.max(3, (plotW / Math.max(series.length, 1)) * 0.6)
  const stride = series.length > 8 ? 4 : 2

  const linePath = useMemo(() => {
    if (bars || series.length < 2) return ''
    const pts = series.map((p) => ({ x: sx(pointDay(p).getTime()), y: sy(p.value) }))
    const n = pts.length
    const m: number[] = []
    for (let i = 0; i < n - 1; i++) m.push((pts[i + 1].y - pts[i].y) / Math.max(pts[i + 1].x - pts[i].x, 1e-6))
    const t = new Array<number>(n).fill(0)
    t[0] = m[0]; t[n - 1] = m[n - 2]
    for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2
    let d = `M${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`
    for (let i = 0; i < n - 1; i++) {
      const h = (pts[i + 1].x - pts[i].x) / 3
      d += `C${(pts[i].x + h).toFixed(1)} ${(pts[i].y + t[i] * h).toFixed(1)} ${(pts[i + 1].x - h).toFixed(1)} ${(pts[i + 1].y - t[i + 1] * h).toFixed(1)} ${pts[i + 1].x.toFixed(1)} ${pts[i + 1].y.toFixed(1)}`
    }
    return d
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metric, height])

  const pick = (clientX: number) => {
    const svg = svgRef.current
    if (!svg) return
    const r = svg.getBoundingClientRect()
    const x = ((clientX - r.left) / r.width) * W
    const t = domain0 + ((x - PAD.left) / plotW) * (domain1 - domain0)
    onPick(new Date(t))
  }

  if (series.length === 0) return null

  return (
    <svg
      ref={svgRef}
      className="chart"
      viewBox={`0 0 ${W} ${height}`}
      style={{ height, width: '100%', touchAction: 'pan-y' }}
      role="img"
      aria-label={`${metric.label}, last two weeks: ${series.length} days, latest ${spokenText(metric, metric.latest.value)}${average != null ? `, average ${spokenText(metric, average)}` : ''}`}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); pick(e.clientX) }}
      onPointerMove={(e) => { if (e.buttons > 0) pick(e.clientX) }}
      onPointerUp={() => onPick(null)}
      onPointerCancel={() => onPick(null)}
    >
      {yTicks.map((v) => (
        <g key={v}>
          <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={sy(v)} y2={sy(v)} />
          <text x={W - PAD.right + 6} y={sy(v) + 3.5}>{axisText(metric, v)}</text>
        </g>
      ))}
      {series.map((p, i) => (i % stride === 0 ? (
        <text key={p.date} x={sx(pointDay(p).getTime())} y={height - 6} textAnchor="middle">{monthDayOf(pointDay(p))}</text>
      ) : null))}
      {bars ? series.map((p, i) => {
        const x = sx(pointDay(p).getTime())
        const top = sy(p.value)
        const base = sy(Math.max(y0, 0))
        const h = Math.max(0, base - top)
        const dim = pickedPoint && pickedPoint.date !== p.date
        return (
          <rect key={p.date} className="grow-y" style={{ ['--i' as string]: i }} x={x - barW / 2} y={top} width={barW} height={h} rx={3}
            fill={p.date === lastId ? 'rgb(var(--brand))' : 'rgb(var(--chart-s1) / 0.5)'} opacity={dim ? 0.4 : 1} />
        )
      }) : (
        <>
          <path className="series" d={linePath} />
          {series.map((p) => {
            const r = p.date === lastId ? 4.7 : pickedPoint?.date === p.date ? 4 : 2.1
            return <circle key={p.date} cx={sx(pointDay(p).getTime())} cy={sy(p.value)} r={r}
              fill={p.date === lastId ? 'rgb(var(--brand))' : 'rgb(var(--chart-s1))'} />
          })}
        </>
      )}
      {!pickedPoint && average != null && series.length > 1 && (
        <g aria-hidden="true">
          <line className="ref" x1={PAD.left} x2={W - PAD.right} y1={sy(average)} y2={sy(average)} />
          <text x={W - PAD.right - 2} y={sy(average) - 4} textAnchor="end">avg</text>
        </g>
      )}
      {pickedPoint && (() => {
        const x = sx(pointDay(pickedPoint).getTime())
        const label = metricText(metric, pickedPoint.value)
        const date = monthDayOf(pointDay(pickedPoint))
        const w = Math.min(W - 8, label.length * 7.2 + date.length * 6 + 26)
        const left = Math.max(4, Math.min(W - w - 4, x - w / 2))
        return (
          <g aria-hidden="true">
            <line className="scrub" x1={x} x2={x} y1={PAD.top - 4} y2={height - PAD.bottom} />
            <rect x={left} y={0} width={w} height={22} rx={11} fill="rgb(var(--panel))" stroke="rgb(var(--line))" />
            <text x={left + 10} y={15} style={{ fontSize: 14, fontWeight: 500, fill: 'rgb(var(--ink))' }}>{label}</text>
            <text x={left + w - 8} y={15} textAnchor="end" style={{ fontSize: 12, fill: 'rgb(var(--body))' }}>{date}</text>
          </g>
        )
      })()}
    </svg>
  )
}
