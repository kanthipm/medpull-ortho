/** 14-day adherence strip: 1 = verified, 0.5 = self-attested, 0 = missed.
 *  Verified is a filled brand dot, self-attested a brand ring, missed a
 *  --line-strong ring (3.834 / 5.671 on panel) — three shapes, not three
 *  opacities, so the states survive greyscale. The percentage is the value;
 *  the strip is a labelled image. */
export default function AdherenceDots({ days, rate }: { days: number[]; rate: number }) {
  const pct = Math.round(rate * 100)
  return (
    <div className="flex items-center gap-3">
      <div
        className="flex items-center gap-1.5"
        role="img"
        aria-label={`Adherence last ${days.length} days, ${pct}%`}
      >
        {days.map((d, i) => (
          <span
            key={i}
            className={
              d >= 1
                ? 'h-2.5 w-2.5 rounded-pill bg-brand'
                : d >= 0.5
                  ? 'h-2.5 w-2.5 rounded-pill border-2 border-brand bg-transparent'
                  : 'h-2.5 w-2.5 rounded-pill border border-line-strong bg-transparent'
            }
          />
        ))}
      </div>
      <span className="text-copy-lg font-medium tabular-nums text-ink">{pct}%</span>
    </div>
  )
}
