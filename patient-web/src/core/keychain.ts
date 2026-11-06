/* The one secret the app holds is its session token. The iPhone app keeps
   it in the keychain; a browser has localStorage, scoped to this origin,
   which is what every signed-in web app relies on. */

const PREFIX = 'medpull.'

export const Keychain = {
  set(value: string, key: string): void {
    try {
      localStorage.setItem(PREFIX + key, value)
    } catch {
      /* private mode or storage full: the session lasts the page */
      memory.set(key, value)
    }
  },
  get(key: string): string | null {
    try {
      const v = localStorage.getItem(PREFIX + key)
      if (v != null) return v
    } catch {
      /* fall through */
    }
    return memory.get(key) ?? null
  },
  delete(key: string): void {
    try {
      localStorage.removeItem(PREFIX + key)
    } catch {
      /* ignore */
    }
    memory.delete(key)
  },
  /** Every item this app stored: the session token and each per-space
   *  token, whichever account they belong to. Signing out must leave none
   *  of them behind, including the ones `me` no longer knows about. */
  clear(): void {
    try {
      const mine = Object.keys(localStorage).filter((k) => k.startsWith(PREFIX))
      for (const k of mine) localStorage.removeItem(k)
    } catch {
      /* ignore */
    }
    memory.clear()
  },
}

const memory = new Map<string, string>()
