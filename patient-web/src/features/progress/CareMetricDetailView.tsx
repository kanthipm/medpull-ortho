/* One of the care team's metrics in full: its state in words, the one
   sentence, the chart the engine drew for it (post-op day on the x axis),
   and the explanation the server wrote. Served word for word; the app
   never invents a clinical line (Features/Progress/CareMetricDetailView.swift). */

import { useParams } from 'react-router-dom'
import { useApp } from '../../core/appModel'
import { isWaiting, readinessSentence, typeset, type PatientMetric, type PatientMetricChart } from '../../core/models'
import { Card, EmptyRow, InsetDivider, NavBar, Screen, StatusPill } from '../../ui/components'
import { BigFigure } from '../../ui/rows'
import { useBack } from '../../ui/useBack'
import { careTone, countdown } from './progressModel'
import { ExplainBlock } from './SignalDetailView'

export function CareMetricDetailRoute() {
  const app = useApp()
  const { id } = useParams()
  const back = useBack('/progress')
  const metric = app.metrics?.metrics.find((m) => m.id === id) ?? null
  const backItem = { label: 'Progress', onClick: back }
  if (!metric) {
    return (
      <Screen fogHeight={300} withTabBar nav={(s) => <NavBar title="Metric" scrolled={s} back={backItem} />}>
        <div className="content"><Card padding={0}><EmptyRow icon="chart.xyaxis.line" title="Not showing yet" detail="Your care team’s read on this is still on the way." /></Card></div>
      </Screen>
    )
  }
  return <CareMetricDetailView metric={metric} back={backItem} />
}

export function CareMetricDetailView({ metric, back }: { metric: PatientMetric; back: { label: string; onClick: () => void } }) {
  const waiting = isWaiting(metric)
  const line = readinessSentence(metric.readiness) ?? countdown(metric)
  const r = metric.readiness
  return (
    <Screen fogHeight={300} withTabBar nav={(s) => <NavBar title={metric.title} scrolled={s} back={back} />}>
      <div className="content" style={{ gap: 16, paddingTop: 4 }}>
        <div className="stack-8 px-4">
          {!waiting && metric.value && <BigFigure value={metric.value} unit={metric.unit} />}
          <span><StatusPill text={metric.stateLabel} tone={careTone(metric)} /></span>
          <span className="t-copy-lg c-ink lh-2">{typeset(metric.headline)}</span>
          {line && <span className="t-label c-muted">{line}</span>}
        </div>
        {metric.chart && metric.chart.points.length > 0 ? (
          <Card padding={0}>
            <div className="stack-8">
              <div style={{ padding: '16px 12px 0' }}><MetricPlot metric={metric} chart={metric.chart} /></div>
              <span className="t-label c-muted" style={{ padding: '0 16px 14px' }}>{metric.chart.xLabel ?? 'Post-op day'}</span>
            </div>
          </Card>
        ) : waiting && r && r.left > 0 ? (
          <Card>
            <span className="hstack-6" style={{ alignItems: 'baseline' }}>
              <span className="t-display-s c-ink figures">{r.left}</span>
              <span className="t-copy c-muted">more {r.left === 1 && r.unit.endsWith('s') ? r.unit.slice(0, -1) : r.unit} of data</span>
            </span>
          </Card>
        ) : null}
        {metric.explain && (
          <Card padding={0}>
            <div style={{ padding: '4px 0' }}>
              <ExplainBlock label="What it is" text={metric.explain.what} />
              <InsetDivider leading={16} />
              <ExplainBlock label="Why it matters" text={metric.explain.why} />
              <InsetDivider leading={16} />
              <ExplainBlock label="How to help it show" text={metric.explain.help} />
            </div>
          </Card>
        )}
        <span className="footnote px-4">Monitoring signals for your care team — not a diagnosis.</span>
      </div>
    </Screen>
  )
}

const W = 320
const H = 150
const PAD = { top: 12, right: 40, bottom: 20, left: 4 }

function niceTicks(lo: number, hi: number, includeZero: boolean, count: number): number[] {
  let min = includeZero ? Math.min(0, lo) : lo
  let max = hi
  if (min === max) { min -= 1; max += 1 }
  const rough = (max - min) / count
  const mag = Math.pow(10, Math.floor(Math.log10(rough)))
  const norm = rough / mag
  const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag
  const out: number[] = []
  for (let v = Math.floor(min / step) * step; v <= Math.ceil(max / step) * step + step / 2; v += step) out.push(Math.round(v * 1e6) / 1e6)
  return out
}

/** The engine's own series for a care metric, in ink. */
function MetricPlot({ metric, chart }: { metric: PatientMetric; chart: PatientMetricChart }) {
  const pts = chart.points
  const bars = chart.kind === 'bars'
  const xsAll = pts.map((p) => p.x)
  const x0 = Math.min(...xsAll)
  const x1 = Math.max(...xsAll)
  const plotW = W - PAD.left - PAD.right
  const plotH = H - PAD.top - PAD.bottom
  const xTicks = niceTicks(x0, x1, false, 4)
  const dx0 = bars ? x0 - 0.5 : Math.min(x0, xTicks[0])
  const dx1 = bars ? x1 + 0.5 : Math.max(x1, xTicks[xTicks.length - 1])
  const sx = (x: number) => PAD.left + ((x - dx0) / Math.max(dx1 - dx0, 1e-9)) * plotW
  const yTicks = niceTicks(Math.min(...pts.map((p) => p.y)), Math.max(...pts.map((p) => p.y)), bars, 3)
  const y0 = yTicks[0]
  const y1 = yTicks[yTicks.length - 1]
  const sy = (y: number) => PAD.top + (1 - (y - y0) / Math.max(y1 - y0, 1e-9)) * plotH
  const last = pts[pts.length - 1]
  const barW = Math.max(3, (plotW / Math.max(pts.length, 1)) * 0.6)
  let d = ''
  if (!bars && pts.length > 1) {
    const q = pts.map((p) => ({ x: sx(p.x), y: sy(p.y) }))
    const n = q.length
    const m: number[] = []
    for (let i = 0; i < n - 1; i++) m.push((q[i + 1].y - q[i].y) / Math.max(q[i + 1].x - q[i].x, 1e-6))
    const t = new Array<number>(n).fill(0)
    t[0] = m[0]; t[n - 1] = m[n - 2]
    for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2
    d = `M${q[0].x.toFixed(1)} ${q[0].y.toFixed(1)}`
    for (let i = 0; i < n - 1; i++) {
      const h = (q[i + 1].x - q[i].x) / 3
      d += `C${(q[i].x + h).toFixed(1)} ${(q[i].y + t[i] * h).toFixed(1)} ${(q[i + 1].x - h).toFixed(1)} ${(q[i + 1].y - t[i + 1] * h).toFixed(1)} ${q[i + 1].x.toFixed(1)} ${q[i + 1].y.toFixed(1)}`
    }
  }
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} style={{ height: H, width: '100%' }} role="img" aria-label={`${metric.title}, ${pts.length} days`}>
      {yTicks.map((v) => (
        <g key={v}>
          <line className="grid" x1={PAD.left} x2={W - PAD.right} y1={sy(v)} y2={sy(v)} />
          <text x={W - PAD.right + 6} y={sy(v) + 3.5}>{fmt(v)}</text>
        </g>
      ))}
      {xTicks.filter((v) => v >= dx0 && v <= dx1).map((v) => (
        <text key={v} x={sx(v)} y={H - 4} textAnchor="middle">{fmt(v)}</text>
      ))}
      {bars ? pts.map((p, i) => {
        const top = sy(p.y)
        const base = sy(Math.max(y0, 0))
        return <rect key={i} x={sx(p.x) - barW / 2} y={top} width={barW} height={Math.max(0, base - top)} rx={2}
          fill={p === last ? 'rgb(var(--brand))' : 'rgb(var(--chart-s1) / 0.5)'} />
      }) : (
        <>
          <path className="series" d={d} />
          {last && <circle cx={sx(last.x)} cy={sy(last.y)} r={4.7} fill="rgb(var(--brand))" />}
        </>
      )}
    </svg>
  )
}

function fmt(v: number): string {
  return v === Math.round(v) ? String(v) : v.toFixed(1)
}
