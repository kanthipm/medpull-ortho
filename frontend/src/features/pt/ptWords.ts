import { useState } from 'react'
import { ApiError } from '../../api/client'
import type { PtMember, PtSent } from '../../api/pt'

/** Small shared words and state of the between-visits screens. */

const AS_KEY = 'medpull-console.pt-as'

/** Who is clicking. Several writes need a clinician's name on them (a
 *  criterion ticked, a phase moved, a red-flag text approved), and an open
 *  console has no sign-in to take one from, so the screens ask once and
 *  remember it in this browser. Falls back to the first therapist. */
export function useActingAs(team: PtMember[] | undefined): [string, (id: string) => void] {
  const [stored, setStored] = useState<string>(() => {
    try {
      return window.localStorage.getItem(AS_KEY) ?? ''
    } catch {
      return ''
    }
  })
  const id = team?.some((m) => m.id === stored) ? stored : (team?.[0]?.id ?? '')
  const choose = (next: string) => {
    setStored(next)
    try {
      window.localStorage.setItem(AS_KEY, next)
    } catch {
      /* this page load only */
    }
  }
  return [id, choose]
}

/** What to say after an ask: texted, or in the app only and why. */
export function sentLine(first: string, sent: PtSent | undefined, what: string): [string, 'success' | 'info'] {
  if (!sent) return [`${what} is in ${first}’s app`, 'success']
  if (sent.reused) return [`${first} already has that waiting`, 'info']
  if (sent.sent) return [`${what} is in ${first}’s app, and texted`, 'success']
  return [`${what} is in ${first}’s app. Not texted: ${lowerFirst(sent.detail)}`, 'info']
}

const lowerFirst = (s: string) => (s ? s[0].toLowerCase() + s.slice(1) : s)

export const errorText = (e: unknown) =>
  e instanceof ApiError || e instanceof Error ? e.message : 'That did not go through'

/** Today as the browser's calendar day, ISO. */
export function todayIso(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export const signed = (n: number) => (n > 0 ? `+${n}` : `${n}`)
