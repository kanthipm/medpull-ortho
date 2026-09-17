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

/** `theme-color` tints the browser chrome above the page, so it follows the
 *  canvas. index.html sets it before the first frame; this keeps it in step
 *  on every toggle, reading --canvas so the two can never drift. */
function canvasColor(root: HTMLElement): string | null {
  const raw = getComputedStyle(root).getPropertyValue('--canvas').trim()
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
  // Read --canvas AFTER the class flip, so the value matches the mode being set.
  const canvas = canvasColor(root)
  if (canvas) {
    meta?.setAttribute('content', canvas)
    // The pre-paint script painted <html>; keep it on the canvas so an
    // overscroll never shows the other mode.
    root.style.background = canvas
  }
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
  // Light unless the clinician chose dark. The OS setting is deliberately not
  // consulted: the console is designed light-first.
  const [theme, setThemeState] = useState<Theme>(() =>
    typeof window === 'undefined' ? 'light' : (readStoredTheme() ?? 'light'),
  )

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const remember = useCallback((next: Theme) => {
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* ignore */
    }
  }, [])

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

  const setTheme = useCallback(
    (next: Theme) => {
      remember(next)
      setThemeState(next)
    },
    [remember],
  )
  const setGlass = useCallback((next: Glass) => setGlassState(next), [])
  const toggleGlass = useCallback(
    () => setGlassState((g) => (g === 'off' ? 'on' : 'off')),
    [],
  )
  const toggleTheme = useCallback(
    () =>
      setThemeState((t) => {
        const next = t === 'dark' ? 'light' : 'dark'
        remember(next)
        return next
      }),
    [remember],
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
