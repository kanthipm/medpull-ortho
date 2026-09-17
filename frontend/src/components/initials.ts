/* Kept out of Avatar.tsx so that file exports components only (react-refresh). */

/** Up to two initials from a display name ("Marcus Reyes" -> "MR"). */
export function initialsOf(name: string): string {
  const parts = name
    .replace(/[^\p{L}\p{N}\s'-]/gu, ' ')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (parts.length === 0) return '?'
  const first = parts[0][0] ?? ''
  const last = parts.length > 1 ? (parts[parts.length - 1][0] ?? '') : ''
  return (first + last).toUpperCase()
}
