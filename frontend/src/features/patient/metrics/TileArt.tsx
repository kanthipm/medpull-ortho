import type { ReactNode } from 'react'
import type { ChartSpec } from '../../../api/care'
import { fmtNum } from './chartText'

/* White line art for a gradient tile (the medpull.org bento): the metric's
   own chart, drawn in the site's vocabulary — a white curve that draws itself
   in with a light travelling along it, a dashed reference, a lime marker on
   the newest point, white bars that grow and breathe, signal meters, a dot
   matrix for adherence. Decorative (aria-hidden): the tile's number, status
   chip and caption carry the reading. Plain SVG, no chart library, so the
   whole tile animates on the compositor. */

const W = 600
const H = 220
const PAD = { top: 18, right: 22, bottom: 16, left: 10 }

type Pt = { x: number; y: number }

function num(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

/** Monotone cubic (Fritsch–Carlson): smooth, and never overshoots the data,
 *  so a flat stretch stays flat. */
function smoothPath(pts: Pt[]): string {
  if (pts.length === 0) return ''
  if (pts.length === 1) return `M${pts[0].x} ${pts[0].y}`
  const n = pts.length
  const dx: number[] = []
  const m: number[] = []
  for (let i = 0; i < n - 1; i++) {
    dx.push(pts[i + 1].x - pts[i].x || 1e-6)
    m.push((pts[i + 1].y - pts[i].y) / (pts[i + 1].x - pts[i].x || 1e-6))
  }
  const t: number[] = [m[0]]
  for (let i = 1; i < n - 1; i++) {
    t.push(m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2)
  }
  t.push(m[n - 2])
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) {
      t[i] = 0
      t[i + 1] = 0
      continue
    }
    const a = t[i] / m[i]
    const b = t[i + 1] / m[i]
    const s = a * a + b * b
    if (s > 9) {
      const k = 3 / Math.sqrt(s)
      t[i] = k * a * m[i]
      t[i + 1] = k * b * m[i]
    }
  }
  let d = `M${pts[0].x.toFixed(1)} ${pts[0].y.toFixed(1)}`
  for (let i = 0; i < n - 1; i++) {
    const h = dx[i] / 3
    d += `C${(pts[i].x + h).toFixed(1)} ${(pts[i].y + t[i] * h).toFixed(1)} ${(pts[i + 1].x - h).toFixed(1)} ${(
      pts[i + 1].y -
      t[i + 1] * h
    ).toFixed(1)} ${pts[i + 1].x.toFixed(1)} ${pts[i + 1].y.toFixed(1)}`
  }
  return d
}

/** Linear scales over the numeric x and every y the art will draw. */
function scales(xs: number[], ys: number[]) {
  const x0 = Math.min(...xs)
  const x1 = Math.max(...xs)
  let y0 = Math.min(...ys)
  let y1 = Math.max(...ys)
  if (y0 === y1) {
    y0 -= 1
    y1 += 1
  }
  const padY = (y1 - y0) * 0.12
  y0 -= padY
  y1 += padY
  const sx = (x: number) =>
    PAD.left + ((x - x0) / (x1 - x0 || 1)) * (W - PAD.left - PAD.right)
  const sy = (y: number) => PAD.top + (1 - (y - y0) / (y1 - y0)) * (H - PAD.top - PAD.bottom)
  return { sx, sy }
}

function Grid() {
  return <path className="art-grid" d="M0 204.5H600M0 146.5H600M0 88.5H600M0 30.5H600" />
}

function Marker({ x, y }: Pt) {
  return (
    <g className="pop-in">
      <circle className="pulse-ring" cx={x} cy={y} r="10" fill="none" stroke="rgb(212 241 74)" strokeWidth="2" />
      <circle cx={x} cy={y} r="14" fill="rgb(212 241 74 / .25)" />
      <circle className="art-dot" cx={x} cy={y} r="6.5" />
    </g>
  )
}

function Frame({ children }: { children: ReactNode }) {
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full overflow-visible" aria-hidden fill="none">
      {children}
    </svg>
  )
}

/** Line, band and dual charts: the site's curve tile. */
function Curve({ spec }: { spec: ChartSpec }) {
  const main = spec.series
    .map((p) => ({ x: num(p.x), y: num(p.y) }))
    .filter((p): p is Pt => p.x != null && p.y != null)
  const second = spec.series
    .map((p) => ({ x: num(p.x), y: num(p.y2) }))
    .filter((p): p is Pt => p.x != null && p.y != null)
  const band = (spec.band ?? []).filter((b) => num(b.x) != null)
  const fit = (spec.fit ?? []).filter((f) => num(f.x) != null && num(f.y) != null)
  if (main.length < 2) return <Sparse />

  // Dual charts put their second series on its own scale.
  const dual = spec.kind === 'dual' && second.length >= 2
  const xs = [...main.map((p) => p.x), ...band.map((b) => b.x), ...fit.map((f) => f.x)]
  const ys = [
    ...main.map((p) => p.y),
    ...band.flatMap((b) => [b.lo, b.hi]),
    ...fit.map((f) => f.y),
    ...(spec.reference != null ? [spec.reference] : []),
  ]
  const { sx, sy } = scales(xs, ys)
  const s2 = dual ? scales(xs, second.map((p) => p.y)).sy : sy
  const line = main.map((p) => ({ x: sx(p.x), y: sy(p.y) }))
  const last = line[line.length - 1]
  const d = smoothPath(line)

  const bandPath =
    band.length >= 2
      ? `${smoothPath(band.map((b) => ({ x: sx(b.x), y: sy(b.hi) })))}L${band
          .slice()
          .reverse()
          .map((b) => `${sx(b.x).toFixed(1)} ${sy(b.lo).toFixed(1)}`)
          .join('L')}Z`
      : null

  return (
    <Frame>
      <Grid />
      {bandPath && <path d={bandPath} fill="rgb(255 255 255 / .16)" />}
      {spec.reference != null && (
        <path className="art-dash dash-flow" d={`M0 ${sy(spec.reference).toFixed(1)}H600`} />
      )}
      {fit.length >= 2 && (
        <path
          className="art-dash"
          d={smoothPath(fit.map((f) => ({ x: sx(f.x), y: sy(f.y) })))}
        />
      )}
      {dual && (
        <path
          className="art-line draw-in"
          pathLength={1}
          strokeOpacity={0.55}
          strokeWidth={1.8}
          d={smoothPath(second.map((p) => ({ x: sx(p.x), y: s2(p.y) })))}
        />
      )}
      {spec.marker_x != null && num(spec.marker_x) != null && (
        <path
          d={`M${sx(spec.marker_x).toFixed(1)} 24V204`}
          stroke="rgb(255 255 255 / .55)"
          strokeDasharray="2 5"
        />
      )}
      <path className="art-line draw-in" pathLength={1} d={d} />
      <path className="comet" pathLength={1} d={d} />
      <Marker x={last.x} y={last.y} />
    </Frame>
  )
}

/** Scatter: white points, the white fit, the newest point in lime. */
function Scatter({ spec }: { spec: ChartSpec }) {
  const pts = spec.series
    .map((p) => ({ x: num(p.x), y: num(p.y) }))
    .filter((p): p is Pt => p.x != null && p.y != null)
  const fit = (spec.fit ?? []).filter((f) => num(f.x) != null && num(f.y) != null)
  if (pts.length < 2) return <Sparse />
  const { sx, sy } = scales(
    [...pts.map((p) => p.x), ...fit.map((f) => f.x)],
    [...pts.map((p) => p.y), ...fit.map((f) => f.y)],
  )
  const fitLine = fit.length >= 2 ? fit.map((f) => ({ x: sx(f.x), y: sy(f.y) })) : null
  const newest = pts.reduce((a, b) => (b.x >= a.x ? b : a))
  return (
    <Frame>
      <Grid />
      {fitLine && <path className="art-line draw-in" pathLength={1} d={smoothPath(fitLine)} />}
      {fitLine && <path className="comet" pathLength={1} d={smoothPath(fitLine)} />}
      {pts.map((p, i) => (
        <circle
          key={i}
          className="art-node pop-in"
          style={{ animationDelay: `${0.5 + i * 0.06}s` }}
          cx={sx(p.x)}
          cy={sy(p.y)}
          r="6"
          fillOpacity={0.9}
        />
      ))}
      <Marker x={sx(newest.x)} y={sy(newest.y)} />
    </Frame>
  )
}

/** Categorical bars with word labels — the site's "what drives the change"
 *  meters. */
function Signals({ spec }: { spec: ChartSpec }) {
  const rows = spec.series
    .map((p) => ({ label: String(p.label ?? p.x), v: num(p.y) ?? 0 }))
    .slice(0, 5)
  const max = Math.max(...rows.map((r) => r.v), 1)
  const pct = /%/.test(spec.y_label)
  return (
    <div className="grid w-full gap-2.5" aria-hidden>
      {rows.map((r, i) => (
        <div key={r.label} className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)_2.75rem] items-center gap-2.5 text-label">
          <span className="truncate">{r.label}</span>
          <span className="meter meter-on-tile h-1.5">
            <span
              className="meter-fill"
              style={{ width: `${Math.max(2, (r.v / max) * 100)}%`, animationDelay: `${0.2 + i * 0.08}s` }}
            />
          </span>
          <span className="text-right font-medium tabular-nums">
            {fmtNum(Math.round(r.v))}
            {pct ? '%' : ''}
          </span>
        </div>
      ))}
    </div>
  )
}

/** Numeric bars: white columns that grow in and breathe; the newest one is
 *  outlined in lime. */
function Bars({ spec }: { spec: ChartSpec }) {
  const vals = spec.series.map((p) => num(p.y))
  const max = Math.max(...vals.map((v) => v ?? 0), spec.reference ?? 0, 1e-6)
  const shown = vals.slice(-10)
  const labels = spec.series.slice(-10).map((p) => (p.label ? String(p.label) : ''))
  return (
    <div className="relative w-full" aria-hidden>
      {spec.reference != null && (
        <span
          className="absolute inset-x-0 z-[1] border-t-2 border-dashed border-lime"
          style={{ bottom: `${20 + (spec.reference / max) * 0.82 * 124}px` }}
        />
      )}
      <div className="grid h-36 items-end gap-2.5 pb-5" style={{ gridTemplateColumns: `repeat(${shown.length}, minmax(0, 1fr))` }}>
        {shown.map((v, i) => {
          const today = i === shown.length - 1
          const h = v == null ? 6 : Math.max(4, (v / max) * 82)
          return (
            <span key={i} className="relative h-full">
              <i
                className={`grow-y absolute inset-x-0 bottom-0 block rounded-t-lg rounded-b ${
                  v == null
                    ? 'bg-white/10 shadow-[inset_0_0_0_1.2px_rgb(255_255_255_/_.7)]'
                    : today
                      ? 'bg-white/35 shadow-[inset_0_0_0_1.5px_rgb(212_241_74),0_0_16px_rgb(212_241_74_/_.55)]'
                      : 'bg-white/90'
                }`}
                style={{ height: `${h}%`, ['--i' as string]: i }}
              />
              {labels[i] && (
                <span className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[11px] opacity-90">
                  {labels[i].slice(0, 3)}
                </span>
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
}

/** A 0–max gauge: the site's arc, white fill, lime tick at the value. */
function Arc({ value, min, max }: { value: number; min: number; max: number }) {
  const p = Math.max(0, Math.min(1, (value - min) / (max - min || 1)))
  const a = Math.PI * (1 - p)
  const x = 100 + 80 * Math.cos(a)
  const y = 100 - 80 * Math.sin(a)
  const x2 = 100 + 92 * Math.cos(a)
  const y2 = 100 - 92 * Math.sin(a)
  return (
    <svg viewBox="0 0 200 118" className="mx-auto block w-[min(220px,100%)] overflow-visible" aria-hidden fill="none">
      <path d="M20 100A80 80 0 0 1 180 100" stroke="rgb(255 255 255 / .28)" strokeWidth="14" strokeLinecap="round" />
      <path
        className="gauge-fill"
        pathLength={1}
        d="M20 100A80 80 0 0 1 180 100"
        stroke="#fff"
        strokeWidth="14"
        strokeLinecap="round"
        style={{ ['--off' as string]: 1 - p }}
      />
      <path d={`M${x.toFixed(1)} ${y.toFixed(1)}L${x2.toFixed(1)} ${y2.toFixed(1)}`} stroke="rgb(212 241 74)" strokeWidth="3" strokeLinecap="round" />
      <text x="20" y="116" textAnchor="middle" fill="#fff" fontSize="11" fontWeight="500">
        {fmtNum(min)}
      </text>
      <text x="180" y="116" textAnchor="middle" fill="#fff" fontSize="11" fontWeight="500">
        {fmtNum(max)}
      </text>
    </svg>
  )
}

/** Task adherence, day by day: the site's "no wearable data" dot matrix.
 *  Filled = done and verified, ring = self-reported, hollow faint = missed. */
function Dots({ spec }: { spec: ChartSpec }) {
  const rows = new Map<string, (number | null)[]>()
  for (const p of spec.series) {
    const key = String(p.row ?? '')
    if (!rows.has(key)) rows.set(key, [])
    rows.get(key)!.push(num(p.v))
  }
  const list = [...rows.entries()].slice(0, 3)
  return (
    <div className="grid w-full gap-3" aria-hidden>
      {list.map(([row, vals]) => (
        <div key={row} className="grid grid-cols-[minmax(0,6rem)_1fr] items-center gap-2.5 text-label">
          <span className="truncate">{row}</span>
          <span className="flex justify-between gap-1">
            {vals.slice(-7).map((v, i, arr) => (
              <i
                key={i}
                className={`block h-3 w-3 rounded-full ${
                  i === arr.length - 1
                    ? 'now-dot bg-lime shadow-[0_0_0_4px_rgb(212_241_74_/_.38),0_0_14px_rgb(212_241_74_/_.8)]'
                    : v != null && v >= 1
                      ? 'bg-white/90'
                      : v != null && v >= 0.5
                        ? 'shadow-[inset_0_0_0_1.5px_rgb(255_255_255_/_.9)]'
                        : 'shadow-[inset_0_0_0_1.2px_rgb(255_255_255_/_.45)]'
                }`}
              />
            ))}
          </span>
        </div>
      ))}
    </div>
  )
}

/** Not enough data yet: a faint expected path and nothing pretending to be a
 *  reading. */
function Sparse() {
  return (
    <Frame>
      <Grid />
      <path className="art-dash dash-flow" d="M0 196C90 176 170 134 260 104C350 74 470 56 600 48" />
    </Frame>
  )
}

export default function TileArt({ spec, sigma }: { spec: ChartSpec | null; sigma?: number | null }) {
  if (!spec) return <Sparse />
  if (sigma != null && spec.kind !== 'bars') return <Arc value={sigma} min={0} max={5} />
  switch (spec.kind) {
    case 'line':
    case 'band':
    case 'dual':
      return <Curve spec={spec} />
    case 'scatter':
      return <Scatter spec={spec} />
    case 'bars': {
      // Word categories (M12's per-signal shares) read as meters; day
      // columns read as bars.
      const words = spec.series.every((p) => typeof p.x === 'string' && !/^D?[−-]?\d+$/.test(String(p.x)))
      return words && spec.series.length <= 6 ? <Signals spec={spec} /> : <Bars spec={spec} />
    }
    case 'gauge': {
      const e = spec.extra as { value?: number; min?: number; max?: number }
      return num(e.value) != null ? (
        <Arc value={e.value!} min={num(e.min) ?? 0} max={num(e.max) ?? 100} />
      ) : (
        <Sparse />
      )
    }
    case 'heat':
      return spec.series.length ? <Dots spec={spec} /> : <Sparse />
    default:
      return <Sparse />
  }
}
