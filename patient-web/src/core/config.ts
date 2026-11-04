/* The app's few settings, kept the way the iPhone app keeps them
   (Core/AppConfig.swift): a built-in server address, an override the person
   can save on the Profile screen, and the version string the server records
   against each session. */

const BASE_URL_KEY = 'api_base_url'

export const AppConfig = {
  /** The URL scheme the iPhone app answers to; the web app maps the same
   *  links (`medpull://tasks/12`, `medpull://wearables`) onto its routes. */
  scheme: 'medpull',

  /** The base URL the app was built with. Empty means "this origin": the
   *  dev server proxies /api to the backend, and a deployment serves the
   *  API and the app from one host. */
  get builtInBaseURL(): string {
    const raw = (import.meta.env.VITE_MEDPULL_API_BASE_URL as string | undefined) ?? ''
    return raw.replace(/\/+$/, '')
  },

  /** The base URL in use: the one saved on the Profile screen, else the
   *  built-in. */
  get baseURL(): string {
    try {
      const stored = localStorage.getItem(BASE_URL_KEY)
      if (stored != null) return stored.replace(/\/+$/, '')
    } catch {
      /* storage unavailable */
    }
    return this.builtInBaseURL
  },
  set baseURL(value: string) {
    try {
      const clean = value.trim().replace(/\/+$/, '')
      if (clean === '' || clean === this.builtInBaseURL) localStorage.removeItem(BASE_URL_KEY)
      else localStorage.setItem(BASE_URL_KEY, clean)
    } catch {
      /* storage unavailable */
    }
  },

  /** What the server shows beside this session: the iPhone app sends its
   *  marketing version; the web build says it is the web. */
  appVersion: '1.0-web',
}

/** "Safari on iPhone", "Chrome on Mac": the device name the server lists
 *  against the session, where the iPhone app sends "iPhone · iOS 26". */
export function deviceName(): string {
  const ua = navigator.userAgent
  const browser = /Edg\//.test(ua)
    ? 'Edge'
    : /OPR\//.test(ua)
      ? 'Opera'
      : /Chrome\//.test(ua)
        ? 'Chrome'
        : /Firefox\//.test(ua)
          ? 'Firefox'
          : /Safari\//.test(ua)
            ? 'Safari'
            : 'Browser'
  const os = /iPhone/.test(ua)
    ? 'iPhone'
    : /iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)
      ? 'iPad'
      : /Android/.test(ua)
        ? 'Android'
        : /Macintosh/.test(ua)
          ? 'Mac'
          : /Windows/.test(ua)
            ? 'Windows'
            : 'the web'
  return `Web · ${browser} on ${os}`
}

/** A phone or tablet, as far as a browser will say: where a camera input
 *  opens the camera and the motion sensors can exist. */
export function isTouchDevice(): boolean {
  return navigator.maxTouchPoints > 0 || /iPhone|iPad|Android/.test(navigator.userAgent)
}

/** iOS WebKit (every iPhone browser): where DeviceMotion needs an explicit
 *  permission call and the accelerometer sign convention differs. */
export function isIOS(): boolean {
  return /iPhone|iPad|iPod/.test(navigator.userAgent)
    || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1)
}
