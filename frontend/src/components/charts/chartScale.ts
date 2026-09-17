/* Non-component chart helpers, kept out of the component files so React
   Fast Refresh can hot-swap them (react-refresh/only-export-components). */

/** Pass as `wrapperStyle` on a Recharts <Tooltip> that renders <ChartTooltip>
 *  (components/charts/Sparkline): Recharts' own wrapper is hidden and the
 *  tooltip renders in the top layer instead. */
export const CHART_TOOLTIP_WRAPPER = { display: 'none' } as const

/** Which way a marker's label should run: into the plot. */
export function markerSide(x: number, xs: (number | string)[]): 'start' | 'end' {
  const nums = xs.filter((v): v is number => typeof v === 'number')
  if (nums.length === 0) return 'start'
  const mid = (Math.min(...nums) + Math.max(...nums)) / 2
  return x <= mid ? 'start' : 'end'
}

/** Y domain for LINE-like marks (HIG Charts: a line's lower bound need not be
 *  zero — a resting HR of 60–66 on a 0–75 axis is a flat line). Pads the data
 *  span by 12% each side; a flat series gets a small symmetric pad. Bar totals
 *  do NOT use this: they keep zero. */
export function lineDomain(values: (number | null | undefined)[]): [number, number] | ['auto', 'auto'] {
  const nums = values.filter((v): v is number => typeof v === 'number' && Number.isFinite(v))
  if (nums.length === 0) return ['auto', 'auto']
  const lo = Math.min(...nums)
  const hi = Math.max(...nums)
  const span = hi - lo
  const pad = span > 0 ? span * 0.12 : Math.max(Math.abs(hi) * 0.05, 1e-3)
  return [lo - pad, hi + pad]
}
