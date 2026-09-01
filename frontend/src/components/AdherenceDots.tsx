/** 14-day adherence strip: 1 = verified, 0.5 = self-attested, 0 = missed. */
export default function AdherenceDots({ days, rate }: { days: number[]; rate: number }) {
  return (
    <div className="flex items-center gap-3">
      <div
        className="flex items-center gap-1.5"
        role="img"
        aria-label={`Adherence last 14 days, ${Math.round(rate * 100)}%`}
      >
        {days.map((d, i) => (
          <span
            key={i}
            className={
              d >= 1
                ? 'h-1.5 w-1.5 rounded-full bg-brand'
                : d >= 0.5
                  ? 'h-1.5 w-1.5 rounded-full bg-brand/35'
                  : 'h-1.5 w-1.5 rounded-full border border-line bg-transparent'
            }
          />
        ))}
      </div>
      <span className="font-mono text-[15px] font-medium tabular-nums tracking-tight text-ink">
        {Math.round(rate * 100)}%
      </span>
    </div>
  )
}
