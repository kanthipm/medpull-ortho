import type { ReactNode } from 'react'
import type { PtMember } from '../../api/pt'

/** Small shared pieces of the between-visits screens. */

export function ActingAs({
  team,
  value,
  onChange,
  className = '',
}: {
  team: PtMember[]
  value: string
  onChange: (id: string) => void
  className?: string
}) {
  if (team.length === 0) return null
  return (
    <label className={`inline-flex items-center gap-1.5 text-label text-secondary ${className}`}>
      <span>As</span>
      <select
        className="field !h-8 !min-h-0 !w-auto !rounded-pill !py-0 !pl-3 !pr-7 text-label"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label="Who is making these changes"
      >
        {team.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
          </option>
        ))}
      </select>
    </label>
  )
}

/** A labelled group inside a card: a small sentence-case label, then content. */
export function Group({
  label,
  aside,
  children,
  className = '',
}: {
  label: ReactNode
  aside?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={className}>
      <div className="mb-1.5 flex min-h-7 flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <h3 className="text-label font-medium tracking-label text-secondary">{label}</h3>
        {aside}
      </div>
      {children}
    </div>
  )
}

export type PillTone = 'plain' | 'good' | 'warn' | 'alert' | 'brand'

export function Pill({ tone = 'plain', children, title }: { tone?: PillTone; children: ReactNode; title?: string }) {
  const tones: Record<PillTone, string> = {
    plain: 'bg-soft text-secondary',
    good: 'bg-risk-low-tint text-risk-low-ink',
    warn: 'bg-risk-med-tint text-risk-med-ink',
    alert: 'bg-risk-high-tint text-risk-high-ink',
    brand: 'bg-brand-tint text-on-brand-tint',
  }
  return (
    <span
      title={title}
      className={`inline-flex min-h-[22px] items-center gap-1 whitespace-nowrap rounded-pill px-2 text-label font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  )
}
