import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  GLASS_KEY,
  REDUCED_TRANSPARENCY,
  STORAGE_KEY,
  ThemeContext,
  type Glass,
  type Theme,
} from './theme'

function readStoredTheme(): Theme | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw === 'light' || raw === 'dark') return raw
  } catch {
    /* ignore */
  }
  return null
}

function systemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

/** The app bar is a --panel material in both modes (transparent over the
 *  ambient wash at scroll 0, --panel at --bar-alpha once scrolled), so
 *  `theme-color` — which tints the browser and OS chrome directly above that
 *  bar — is --panel too.
 *
 *  WHICH FILE WINS, and why it matters. There are two writers of this meta tag
 *  and they disagreed:
 *
 *    index.html:52   pre-paint inline script   '#0d47a1' dark / '#1976d2' light
 *    this file       applyTheme(), on mount    '#004ba0' dark / '#1976d2' light
 *
 *  index.html paints first and THIS FILE wins a frame later, on every mount and
 *  every toggle — so #004ba0 was the value users actually got in dark mode.
 *  #004BA0 is not a token at all: it is the OLD dark app-bar blue (`--glass-bg:
 *  0 75 160`, retired at cb086cbd), orphaned by the same change that made the
 *  bar --panel. So the runtime winner was an off-ramp hex and dark mode flashed
 *  #0d47a1 -> #004ba0 on load.
 *
 *  The fix is to stop naming a colour here at all: read --panel off the
 *  document. This file cannot then drift from the token file again, and it
 *  holds no hex of its own — so the ONE remaining question, which file wins,
 *  gets a clean answer instead of a race between two literals:
 *
 *    index.html owns the PRE-PAINT value, because it is the only code that
 *    runs before the first frame and it is not this file's to edit.
 *    This file owns the RUNTIME value, on mount and on every toggle, and it
 *    takes that value from --panel rather than from a literal.
 *
 *  They now agree: index.html writes '#141c24' dark / '#ffffff' light before
 *  the first frame, and this file writes the same values from --panel after
 *  it, so there is no frame in which the two differ. */

/** `rgb(var(--panel))` resolved to a hex `content=` value. Returns null before
 *  the stylesheet has parsed; the meta tag is then left as index.html set it,
 *  which is deliberately the only pre-paint authority. */
function panelColor(root: HTMLElement): string | null {
  const raw = getComputedStyle(root).getPropertyValue('--panel').trim()
  const parts = raw.split(/[\s,]+/).filter(Boolean).map(Number)
  if (parts.length < 3 || parts.some((n) => !Number.isFinite(n))) return null
  return `#${parts
    .slice(0, 3)
    .map((n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0'))
    .join('')}`
}

function applyTheme(theme: Theme) {
  const root = document.documentElement
  root.classList.toggle('dark', theme === 'dark')
  root.style.colorScheme = theme
  const meta = document.querySelector('meta[name="theme-color"]')
  // Read --panel AFTER the class flip, so the value matches the mode being set.
  const panel = panelColor(root)
  if (meta && panel) meta.setAttribute('content', panel)
}

function readStoredGlass(): Glass {
  try {
    return localStorage.getItem(GLASS_KEY) === 'off' ? 'off' : 'on'
  } catch {
    return 'on'
  }
}

/** Mirror the choice onto <html data-glass>. 'on' removes the attribute, so
 *  the default document carries nothing and the CSS default applies. */
function applyGlass(glass: Glass) {
  const root = document.documentElement
  if (glass === 'off') root.setAttribute('data-glass', 'off')
  else root.removeAttribute('data-glass')
}

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia(query).matches
      : false,
  )
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    onChange()
    mql.addEventListener?.('change', onChange)
    return () => mql.removeEventListener?.('change', onChange)
  }, [query])
  return matches
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === 'undefined') return 'light'
    return readStoredTheme() ?? systemTheme()
  })

  useEffect(() => {
    applyTheme(theme)
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      /* ignore */
    }
  }, [theme])

  const [glass, setGlassState] = useState<Glass>(() =>
    typeof window === 'undefined' ? 'on' : readStoredGlass(),
  )
  const systemReducedTransparency = useMediaQuery(REDUCED_TRANSPARENCY)

  useEffect(() => {
    applyGlass(glass)
    try {
      if (glass === 'off') localStorage.setItem(GLASS_KEY, 'off')
      else localStorage.setItem(GLASS_KEY, 'on')
    } catch {
      /* ignore */
    }
  }, [glass])

  const setTheme = useCallback((next: Theme) => setThemeState(next), [])
  const setGlass = useCallback((next: Glass) => setGlassState(next), [])
  const toggleGlass = useCallback(
    () => setGlassState((g) => (g === 'off' ? 'on' : 'off')),
    [],
  )
  const toggleTheme = useCallback(
    () => setThemeState((t) => (t === 'dark' ? 'light' : 'dark')),
    [],
  )

  const value = useMemo(
    () => ({
      theme,
      setTheme,
      toggleTheme,
      glass,
      setGlass,
      toggleGlass,
      systemReducedTransparency,
      glassActive: glass === 'on' && !systemReducedTransparency,
    }),
    [theme, setTheme, toggleTheme, glass, setGlass, toggleGlass, systemReducedTransparency],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export default ThemeProvider
