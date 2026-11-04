/* Records what the backend's mobility engine needs from one walk: device
   motion (total acceleration, rotation rate, the gravity estimate,
   timestamps) and — when the walk is outdoors and the person allowed it —
   the GPS path length. Nothing is computed here: the phone is the sensor,
   the server is the algorithm (Core/MotionCapture.swift, on the browser's
   DeviceMotion API).

   Where a browser differs from CoreMotion:
   - There is no pedometer and no barometer. The server counts steps from
     the window itself; the live count on screen is a rough peak detector
     and is NOT sent as the pedometer count.
   - Samples arrive at the browser's rate (about 60 Hz on an iPhone); the
     rate and the timestamps go with the window so the server can resample.
   - Sign conventions. CoreMotion's gravity points down (flat, face up:
     0, 0, -1). iOS WebKit reports accelerationIncludingGravity in the same
     frame and sign; Android browsers report the spec's reaction force
     (flat, face up: 0, 0, +9.81), so those are negated to match. */

import { useSyncExternalStore } from 'react'
import { isIOS, isTouchDevice } from './config'
import { Dates, type MotionWindowUpload } from './models'

export type CaptureState = 'idle' | 'recording' | 'finished'

const G = 9.80665
const MAX_SAMPLES = 36_000 // 12 minutes at 50 Hz: the server's ceiling

type MotionEventCtor = typeof DeviceMotionEvent & { requestPermission?: () => Promise<'granted' | 'denied'> }

export class MotionCapture {
  state: CaptureState = 'idle'
  elapsed = 0
  /** A rough live step count from the vertical acceleration; the server's
   *  own count is the one that lands on the chart. */
  steps = 0
  pedometerDistance: number | null = null
  sampleCount = 0
  liveTiltDegrees = 0
  unavailable: string | null = null

  get gpsDistance(): number { return this.location.distance }
  get gpsAccuracy(): number | null { return this.location.meanAccuracy }
  /** Motion sensors exist on a phone or tablet. A desktop browser defines
   *  the event and never fires it. */
  get isAvailable(): boolean { return typeof DeviceMotionEvent !== 'undefined' && isTouchDevice() }

  private location = new LocationTracker()
  startedAt: Date | null = null
  private firstStamp: number | null = null
  private accel: number[][] = []
  private gyro: number[][] = []
  private gravity: number[][] = []
  private stamps: number[] = []
  private minuteSteps: number[] = []
  private ticker: number | null = null
  private limit = 0
  private sign = isIOS() ? 1 : -1
  private lastStepAt = 0
  private stepArmed = true
  private lowPass: [number, number, number] | null = null
  private handler = (e: DeviceMotionEvent) => this.append(e)

  private listeners = new Set<() => void>()
  private version = 0
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  snapshot = () => this.version
  private notify() { this.version++; for (const fn of this.listeners) fn() }

  /** Start recording. `seconds` is the auto-stop; `outdoors` turns the GPS
   *  on. Must be called from a tap: iOS asks permission only then. */
  async start(seconds: number, outdoors: boolean): Promise<void> {
    if (this.state === 'recording') return
    if (!this.isAvailable) {
      this.unavailable = 'This device has no motion sensors.'
      this.notify()
      return
    }
    const ctor = DeviceMotionEvent as MotionEventCtor
    if (typeof ctor.requestPermission === 'function') {
      let answer: string
      try { answer = await ctor.requestPermission() } catch { answer = 'denied' }
      if (answer !== 'granted') {
        this.unavailable = 'Allow motion access in Safari (aA → Website Settings → Motion & Orientation) to record a walk.'
        this.notify()
        return
      }
    }
    this.reset()
    this.unavailable = null
    this.limit = seconds
    this.startedAt = new Date()
    this.state = 'recording'
    window.addEventListener('devicemotion', this.handler)
    if (outdoors) this.location.start()
    const started = performance.now()
    let lastMinute = 0
    let stepsAtMinute = 0
    this.ticker = window.setInterval(() => {
      if (this.state !== 'recording') return
      this.elapsed = (performance.now() - started) / 1000
      const minute = Math.floor(this.elapsed / 60)
      if (minute > lastMinute) {
        this.minuteSteps.push(this.steps - stepsAtMinute)
        stepsAtMinute = this.steps
        lastMinute = minute
      }
      if (this.elapsed >= this.limit) this.stop()
      else this.notify()
    }, 250)
    this.notify()
  }

  private append(e: DeviceMotionEvent): void {
    if (this.state !== 'recording') return
    const total = e.accelerationIncludingGravity
    if (!total || total.x == null || total.y == null || total.z == null) return
    const now = performance.now() / 1000
    if (this.firstStamp == null) this.firstStamp = now
    const t = now - this.firstStamp
    // Into CoreMotion's frame and sign, in g.
    const ax = (total.x / G) * this.sign
    const ay = (total.y / G) * this.sign
    const az = (total.z / G) * this.sign
    let gx: number, gy: number, gz: number
    const user = e.acceleration
    if (user && user.x != null && user.y != null && user.z != null) {
      gx = ax - (user.x / G) * this.sign
      gy = ay - (user.y / G) * this.sign
      gz = az - (user.z / G) * this.sign
    } else {
      // No user-acceleration split: a slow low-pass stands in for gravity.
      const a = 0.1
      if (!this.lowPass) this.lowPass = [ax, ay, az]
      else this.lowPass = [this.lowPass[0] + a * (ax - this.lowPass[0]), this.lowPass[1] + a * (ay - this.lowPass[1]), this.lowPass[2] + a * (az - this.lowPass[2])]
      ;[gx, gy, gz] = this.lowPass
    }
    const r = e.rotationRate
    const rad = Math.PI / 180
    this.accel.push([r3(ax * G), r3(ay * G), r3(az * G)])
    this.gyro.push(r && r.beta != null && r.gamma != null && r.alpha != null
      ? [r3(r.beta * rad), r3(r.gamma * rad), r3(r.alpha * rad)] : [0, 0, 0])
    this.gravity.push([r3(gx), r3(gy), r3(gz)])
    this.stamps.push(Math.round(t * 1000) / 1000)
    this.sampleCount = this.accel.length
    // The phone's long-axis tilt from horizontal, for the range-of-motion
    // screen's live readout: atan2(-g_y, -g_z), the same rule the server uses.
    this.liveTiltDegrees = (Math.atan2(-gy, -gz) * 180) / Math.PI
    // The live step count: a peak in the magnitude of the user's
    // acceleration, armed again once it drops, at most every 300 ms.
    const mag = Math.sqrt((ax - gx) ** 2 + (ay - gy) ** 2 + (az - gz) ** 2)
    if (this.stepArmed && mag > 0.35 && now - this.lastStepAt > 0.3) {
      this.steps++
      this.lastStepAt = now
      this.stepArmed = false
    } else if (!this.stepArmed && mag < 0.15) {
      this.stepArmed = true
    }
    if (this.sampleCount >= MAX_SAMPLES) this.stop()
  }

  stop(): void {
    if (this.state !== 'recording') return
    window.removeEventListener('devicemotion', this.handler)
    this.location.stop()
    if (this.ticker != null) { clearInterval(this.ticker); this.ticker = null }
    if (this.startedAt) this.elapsed = (Date.now() - this.startedAt.getTime()) / 1000
    this.state = 'finished'
    this.notify()
  }

  reset(): void {
    if (this.state === 'recording') this.stop()
    this.state = 'idle'
    this.elapsed = 0
    this.steps = 0
    this.pedometerDistance = null
    this.sampleCount = 0
    this.liveTiltDegrees = 0
    this.startedAt = null
    this.firstStamp = null
    this.lowPass = null
    this.lastStepAt = 0
    this.stepArmed = true
    this.accel = []; this.gyro = []; this.gravity = []; this.stamps = []; this.minuteSteps = []
    this.location.reset()
    this.notify()
  }

  /** The sample rate the browser actually delivered. */
  private get sampleRate(): number {
    const n = this.stamps.length
    if (n < 2) return 60
    const span = this.stamps[n - 1] - this.stamps[0]
    return span > 0 ? Math.round(((n - 1) / span) * 10) / 10 : 60
  }

  /** The recorded window in the server's shape, or null when too short. */
  window(context: string, pocketSide: string | null): MotionWindowUpload | null {
    if (!this.startedAt || this.accel.length < 50) return null
    return {
      startedAt: Dates.iso(this.startedAt),
      sampleRateHz: this.sampleRate,
      accel: this.accel,
      gyro: this.gyro,
      gravity: this.gravity,
      timestamps: this.stamps,
      altitude: null,
      gpsDistanceM: this.location.distance > 0 ? this.location.distance : null,
      gpsAccuracyM: this.location.meanAccuracy,
      pedometerSteps: null,
      pedometerDistanceM: null,
      pocketSide,
      context,
    }
  }

  /** Gravity samples from the last `seconds` of the recording — the hold
   *  the range-of-motion test reads its angle from. */
  recentGravity(seconds: number): number[][] {
    const n = Math.min(this.gravity.length, Math.round(seconds * this.sampleRate))
    return this.gravity.slice(-n)
  }

  get minuteStepCounts(): number[] { return this.minuteSteps }
}

const r3 = (v: number) => Math.round(v * 1000) / 1000

/** GPS path length while a walk is being recorded. Fixes worse than
 *  `maxAccuracy` are skipped, and the mean accuracy of the ones used travels
 *  with the distance so the server can decide whether to trust it. */
class LocationTracker {
  private watch: number | null = null
  private last: GeolocationCoordinates | null = null
  private total = 0
  private accuracies: number[] = []
  private readonly maxAccuracy = 20

  get distance(): number { return this.total }
  get meanAccuracy(): number | null {
    return this.accuracies.length ? this.accuracies.reduce((a, b) => a + b, 0) / this.accuracies.length : null
  }

  start(): void {
    if (!('geolocation' in navigator) || this.watch != null) return
    this.watch = navigator.geolocation.watchPosition(
      (pos) => {
        const c = pos.coords
        if (!(c.accuracy > 0 && c.accuracy <= this.maxAccuracy)) return
        if (this.last) this.total += haversine(this.last, c)
        this.last = c
        this.accuracies.push(c.accuracy)
      },
      () => { /* denied or unavailable: the distance stays 0 */ },
      { enableHighAccuracy: true, maximumAge: 0 },
    )
  }

  stop(): void {
    if (this.watch != null) navigator.geolocation.clearWatch(this.watch)
    this.watch = null
  }

  reset(): void {
    this.last = null
    this.total = 0
    this.accuracies = []
  }
}

function haversine(a: GeolocationCoordinates, b: GeolocationCoordinates): number {
  const R = 6_371_000
  const rad = Math.PI / 180
  const dLat = (b.latitude - a.latitude) * rad
  const dLon = (b.longitude - a.longitude) * rad
  const s = Math.sin(dLat / 2) ** 2 + Math.cos(a.latitude * rad) * Math.cos(b.latitude * rad) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(s))
}

/** Subscribe a component to a capture's ticks. */
export function useCapture(capture: MotionCapture): MotionCapture {
  useSyncExternalStore(capture.subscribe, capture.snapshot, capture.snapshot)
  return capture
}

// MARK: - Stature (the step-length model needs it once)

const STATURE_KEY = 'stature_cm'

export const Stature = {
  get storedCm(): number | null {
    try {
      const v = Number(localStorage.getItem(STATURE_KEY))
      return v > 0 ? v : null
    } catch {
      return null
    }
  },
  store(cm: number): void {
    try { localStorage.setItem(STATURE_KEY, String(cm)) } catch { /* ignore */ }
  },
}
