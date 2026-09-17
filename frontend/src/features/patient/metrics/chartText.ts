import type { ChartSpec } from '../../../api/care'
import { fmtNum as fmtRaw } from './labels'

/* Axis and label text for the care charts. Kept out of CareChart.tsx so that
   file exports components only (react-refresh/only-export-components). */

/** fmtNum with a true minus (U+2212) — R19: a negative reading never shows a
 *  hyphen. */
export const fmtNum = (v: number) => fmtRaw(v).replace('-', '\u2212')

export function xText(spec: ChartSpec, x: number | string, label?: string): string {
  if (label) return label
  if (typeof x === 'string') return x
  const axis = spec.x_label || 'Post-op day'
  return /^post-?op day$/i.test(axis) ? `Post-op day ${fmtNum(x)}` : `${axis} ${fmtNum(x)}`
}

export function xTick(spec: ChartSpec, x: number | string): string {
  if (typeof x === 'string') return x
  const axis = spec.x_label || 'Post-op day'
  // fmtNum carries the true minus, so pre-op days read "D−5".
  if (/^post-?op day$/i.test(axis)) return `D${fmtNum(x)}`
  if (/^day/i.test(axis)) return `D${fmtNum(x)}`
  if (/^hour/i.test(axis)) return `${fmtNum(x)}h`
  if (/^minute/i.test(axis)) return `${fmtNum(x)}m`
  return fmtNum(x)
}

/** "Post-op day 19" for the newest plotted point — the date line under a
 *  metric's value, like the app's portfolio tiles. Null when nothing is
 *  plotted or the chart is not a series (gauge / heat). */
export function latestLabel(spec: ChartSpec | null): string | null {
  if (!spec || spec.kind === 'gauge' || spec.kind === 'heat') return null
  const pts = spec.series.filter((p) => p.y != null)
  // A categorical bar chart (M12's per-signal share) has no "newest" point:
  // its last bar is a signal name, not a day.
  if (spec.kind === 'bars' && pts.some((p) => typeof p.x === 'string' && !p.label)) return null
  if (pts.length === 0) return null
  let last = pts[pts.length - 1]
  if (pts.every((p) => typeof p.x === 'number')) {
    last = pts.reduce((a, b) => ((b.x as number) > (a.x as number) ? b : a))
  }
  return xText(spec, last.x, last.label)
}

/** Bars tall enough to read at tile size (at least a tenth of the tallest).
 *  M12 with one dominant signal draws one bar and two 1px dashes, which reads
 *  as a broken chart; the caller swaps in a baseline-distance gauge instead. */
export function visibleBars(spec: ChartSpec): number {
  const ys = spec.series.map((p) => p.y).filter((y): y is number => typeof y === 'number')
  const max = Math.max(0, ...ys)
  if (max <= 0) return 0
  return ys.filter((y) => y >= max * 0.1).length
}
