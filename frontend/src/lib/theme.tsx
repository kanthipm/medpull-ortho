import { createContext, useContext } from 'react'

/* Theme + glass state. The provider is lib/ThemeProvider.tsx; this file holds
   no components, so it can export the hooks (react-refresh). */

export type Theme = 'light' | 'dark'
/** The glass kill switch (R18). 'on' is the default: the app bar turns into
 *  translucent material once content scrolls under it. 'off' makes every
 *  blurred surface opaque (index.css `[data-glass='off']`). */
export type Glass = 'on' | 'off'

/** Written only when the clinician picks a mode. Light is the default, so an
 *  absent key means light; index.html's pre-paint script reads the same key. */
export const STORAGE_KEY = 'medpull-theme-choice'
/** Shared with index.html's pre-paint script, which applies 'off' before the
 *  first frame. This file owns the key at runtime. */
export const GLASS_KEY = 'medpull-glass'
export const REDUCED_TRANSPARENCY = '(prefers-reduced-transparency: reduce)'

export type ThemeContextValue = {
  theme: Theme
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
  /** The user's stored glass choice. */
  glass: Glass
  setGlass: (glass: Glass) => void
  toggleGlass: () => void
  /** True when the OS asks for reduced transparency. The CSS already makes the
   *  bar opaque in that case, whatever `glass` says; the Settings row should
   *  say so instead of pretending the toggle does something. */
  systemReducedTransparency: boolean
  /** What the viewer actually gets: glass === 'on' and the OS allows it. */
  glassActive: boolean
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}

/** The glass kill switch for the Settings row (R18):
 *    const { glass, setGlass, systemReducedTransparency } = useGlass()
 *  Render it as a switch (checked = glass === 'on'); when
 *  systemReducedTransparency is true, show the switch disabled with a note
 *  that the system setting already keeps the bar opaque. */
export function useGlass() {
  const { glass, setGlass, toggleGlass, systemReducedTransparency, glassActive } = useTheme()
  return { glass, setGlass, toggleGlass, systemReducedTransparency, glassActive }
}
