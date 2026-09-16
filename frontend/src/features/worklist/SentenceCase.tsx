import type { ReactNode } from 'react'

/** The worklist's one uppercase slot is the `.micro` "Patient panel" heading,
 *  so the AI attribution label above the briefing and the ask answer is set in
 *  sentence case here. AIAttribution applies `uppercase` on its own root span;
 *  the child selector (0,1,1) outranks that utility (0,1,0) without touching
 *  the shared component. Tracking drops to the UI value, which is what
 *  lowercase wants. */
export default function SentenceCase({ children }: { children: ReactNode }) {
  return <span className="contents [&>span]:normal-case [&>span]:tracking-ui">{children}</span>
}
