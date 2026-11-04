/* White line art for gradient tiles — the medpull.org vocabulary: a curve
   that draws itself in with a light travelling along it, a dashed
   reference, a lime marker on the newest point with a pulsing ring, and
   white bars that grow in. Decorative (UI/TileArt.swift). */

export type Pt = { x: number; y: number }

/** A monotone cubic through `points` (Fritsch–Carlson): smooth, and it
 *  never overshoots the data, so a flat stretch stays flat. Points are
 *  unit points, scaled into `w` × `h`. */
export function smoothPath(points: Pt[], w: number, h: number): string {
  if (points.length < 2) return ''
  const p = points.map((q) => ({ x: q.x * w, y: q.y * h }))
  const n = p.length
  const m: number[] = []
  for (let i = 0; i < n - 1; i++) {
    const dx = Math.max(p[i + 1].x - p[i].x, 0.0001)
    m.push((p[i + 1].y - p[i].y) / dx)
  }
  const t: number[] = new Array(n).fill(0)
  t[0] = m[0]
  t[n - 1] = m[n - 2]
  for (let i = 1; i < n - 1; i++) t[i] = m[i - 1] * m[i] <= 0 ? 0 : (m[i - 1] + m[i]) / 2
  for (let i = 0; i < n - 1; i++) {
    if (m[i] === 0) continue
    const a = t[i] / m[i]
    const b = t[i + 1] / m[i]
    const s = a * a + b * b
    if (s > 9) {
      const k = 3 / Math.sqrt(s)
      t[i] = k * a * m[i]
      t[i + 1] = k * b * m[i]
    }
  }
  let d = `M${p[0].x.toFixed(1)} ${p[0].y.toFixed(1)}`
  for (let i = 0; i < n - 1; i++) {
    const hh = (p[i + 1].x - p[i].x) / 3
    d += `C${(p[i].x + hh).toFixed(1)} ${(p[i].y + t[i] * hh).toFixed(1)} ${(p[i + 1].x - hh).toFixed(1)} ${(p[i + 1].y - t[i + 1] * hh).toFixed(1)} ${p[i + 1].x.toFixed(1)} ${p[i + 1].y.toFixed(1)}`
  }
  return d
}

/** Values -> unit points (x 0...1, y 0...1 top-down) with headroom. */
export function unitPoints(values: number[], pad = 0.14): Pt[] {
  if (values.length < 2) return []
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const span = hi - lo === 0 ? 1 : hi - lo
  const low = lo - span * pad
  const high = hi + span * pad
  return values.map((v, i) => ({ x: i / (values.length - 1), y: 1 - (v - low) / (high - low) }))
}

const W = 320

/** The lime marker: a dot, its halo and a ring that pulses outward. */
export function LimeMarker({ x, y }: Pt) {
  return (
    <g className="pop-in">
      <circle className="pulse-ring" cx={x} cy={y} r={10} fill="none" stroke="rgb(212 241 74)" strokeWidth={2} />
      <circle cx={x} cy={y} r={14} fill="rgb(212 241 74 / 0.25)" />
      <circle className="art-dot" cx={x} cy={y} r={6} />
    </g>
  )
}

/** Faint horizontal rules behind the art. */
export function ArtGrid({ h, lines = 4 }: { h: number; lines?: number }) {
  const d = Array.from({ length: lines }, (_, i) => {
    const y = (h * i) / Math.max(lines - 1, 1)
    return `M0 ${y.toFixed(1)}H${W}`
  }).join('')
  return <path className="art-grid" d={d} />
}

/** A curve tile: an optional dashed reference, the patient's line drawing
 *  itself in, a light travelling along it, and the lime marker at the end. */
export function CurveArt({ points, reference, height = 120 }: { points: Pt[]; reference?: Pt[] | null; height?: number }) {
  const d = smoothPath(points, W, height)
  const last = points[points.length - 1]
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none" style={{ height }} aria-hidden="true" fill="none">
      <ArtGrid h={height} />
      {reference && reference.length > 1 && <path className="art-dash" d={smoothPath(reference, W, height)} />}
      {d && <path className="art-line draw-in" pathLength={1} d={d} />}
      {d && <path className="comet" pathLength={1} d={d} />}
      {last && <LimeMarker x={last.x * W} y={last.y * height} />}
    </svg>
  )
}

const typical: Pt[] = Array.from({ length: 9 }, (_, i) => {
  const x = i / 8
  return { x, y: 0.9 - 0.72 * (1 - Math.pow(1 - x, 2.2)) }
})

/** The recovery tile's art from one number: the typical curve (dashed) and
 *  the patient's own, ending `pct` percent above or below it. With no
 *  number, the typical curve alone. */
export function RecoveryCurveArt({ pct }: { pct: number | null }) {
  if (pct == null) return <CurveArt points={[]} reference={typical} />
  const shift = Math.max(-40, Math.min(40, pct)) / 100
  const patient = typical.map((p) => ({
    x: p.x,
    y: Math.min(0.95, Math.max(0.08, p.y - shift * 0.9 * Math.pow(p.x, 1.4))),
  }))
  return <CurveArt points={patient} reference={typical} />
}

/** White columns that grow in on the spring; the newest is outlined in lime. */
export function BarsArt({ values, height = 110 }: { values: number[]; height?: number }) {
  const shown = values.slice(-14)
  const top = Math.max(...shown, 0.0001)
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 5, height }} aria-hidden="true">
      {shown.map((v, i) => {
        const last = i === shown.length - 1
        const h = height * Math.max(0.05, v / top)
        return (
          <i
            key={i}
            className="grow-y"
            style={{
              ['--i' as string]: i,
              flex: 1,
              display: 'block',
              height: h,
              borderRadius: '5px 5px 2px 2px',
              background: last ? 'rgb(255 255 255 / 0.35)' : 'rgb(255 255 255 / 0.9)',
              boxShadow: last ? 'inset 0 0 0 1.5px rgb(212 241 74), 0 0 12px rgb(212 241 74 / 0.5)' : undefined,
            }}
          />
        )
      })}
    </div>
  )
}
