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
}

const memory = new Map<string, string>()
