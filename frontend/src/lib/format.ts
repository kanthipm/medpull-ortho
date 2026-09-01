const DAY_MS = 86_400_000

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return 'No check-in yet'
  const then = new Date(iso)
  const now = new Date()
  const time = then.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  if (then.getTime() >= startOfToday) return `Today · ${time}`
  if (then.getTime() >= startOfToday - DAY_MS) return `Yesterday · ${time}`
  // calendar days, not 24h windows — 11pm two nights ago is "2 days ago"
  const days = Math.ceil((startOfToday - then.getTime()) / DAY_MS)
  if (days < 7) return `${days} day${days === 1 ? '' : 's'} ago`
  return then.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function longDate(d: Date = new Date()): string {
  return d.toLocaleDateString([], { weekday: 'long', month: 'long', day: 'numeric' })
}

export function shortDate(iso: string): string {
  // Date-only strings parse as UTC midnight; anchor them to local time so
  // "2026-07-03" doesn't render as Jul 2 in the Americas.
  const local = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? `${iso}T00:00:00` : iso
  return new Date(local).toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function signedPct(pct: number | null | undefined): string {
  if (pct == null) return '—'
  const rounded = Math.round(pct)
  return `${rounded > 0 ? '+' : ''}${rounded}%`
}
