/* Light, dark, or whatever the device is set to (UI/Appearance.swift).
   Every colour token is already a light/dark pair, so nothing here picks
   colours; it only decides which half of each pair the page renders. Light
   is the default, and Dark or System apply only once the patient picks them
   on the Profile screen. index.html applies the stored choice before the
   first frame; this keeps the page in step afterwards. */

import { useSyncExternalStore } from 'react'

export type AppearanceMode = 'light' | 'dark' | 'system'
export const APPEARANCE_KEY = 'medpull-patient-appearance'

export const appearanceLabel: Record<AppearanceMode, string> = {
  light: 'Light',
  dark: 'Dark',
  system: 'System',
}

const listeners = new Set<() => void>()
let mode: AppearanceMode = read()
let version = 0

function read(): AppearanceMode {
  try {
    const raw = localStorage.getItem(APPEARANCE_KEY)
    if (raw === 'light' || raw === 'dark' || raw === 'system') return raw
  } catch {
    /* storage unavailable */
  }
  return 'light'
}

function systemDark(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    && window.matchMedia('(prefers-color-scheme: dark)').matches
}

export function resolvedDark(): boolean {
  return mode === 'dark' || (mode === 'system' && systemDark())
}

function apply(): void {
  const dark = resolvedDark()
  const root = document.documentElement
  root.classList.toggle('dark', dark)
  root.style.colorScheme = dark ? 'dark' : 'light'
  const canvas = dark ? '#0b0b0c' : '#fbfbf9'
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', canvas)
  root.style.background = canvas
}

function emit(): void {
  version++
  for (const fn of listeners) fn()
}

export const appearance = {
  get mode(): AppearanceMode { return mode },
  /** Only a patient's own choice is ever stored, so an absent key means
   *  "never chose": light. */
  setMode(next: AppearanceMode): void {
    mode = next
    try { localStorage.setItem(APPEARANCE_KEY, next) } catch { /* ignore */ }
    apply()
    emit()
  },
  subscribe(fn: () => void): () => void {
    listeners.add(fn)
    return () => { listeners.delete(fn) }
  },
}

if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    if (mode === 'system') { apply(); emit() }
  })
  apply()
}

export function useAppearance(): { mode: AppearanceMode; dark: boolean; setMode: (m: AppearanceMode) => void } {
  useSyncExternalStore(appearance.subscribe, () => version, () => version)
  return { mode, dark: resolvedDark(), setMode: appearance.setMode }
}

/** The patient's reduce-motion setting, as the browser reports it. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (fn) => {
      const mql = window.matchMedia('(prefers-reduced-motion: reduce)')
      mql.addEventListener('change', fn)
      return () => mql.removeEventListener('change', fn)
    },
    () => window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    () => false,
  )
}
