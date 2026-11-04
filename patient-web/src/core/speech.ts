/* Speech in, spoken replies out (Core/SpeechController.swift and
   Core/SpokenVoice.swift), on the browser's Web Speech API. The transcript
   goes to the backend copilot; nothing is recorded or kept. */

import { useSyncExternalStore } from 'react'

type RecognitionCtor = new () => SpeechRecognitionLike
type SpeechRecognitionLike = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null
  onerror: ((e: { error: string }) => void) | null
  onend: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null
}

class Observable {
  private listeners = new Set<() => void>()
  private version = 0
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  snapshot = () => this.version
  protected notify() { this.version++; for (const fn of this.listeners) fn() }
}

export class SpeechController extends Observable {
  transcript = ''
  isListening = false
  isSpeaking = false
  authorized = false
  errorText: string | null = null

  private recognition: SpeechRecognitionLike | null = null
  private finalText = ''

  get isAvailable(): boolean { return recognitionCtor() != null }

  /** The microphone prompt, once. */
  async requestAuthorization(): Promise<boolean> {
    if (!this.isAvailable) {
      this.errorText = "Speech recognition isn't available in this browser."
      this.notify()
      return false
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      for (const t of stream.getTracks()) t.stop()
      this.authorized = true
    } catch {
      this.authorized = false
      this.errorText = 'Allow the microphone in your browser to talk to MedPull.'
    }
    this.notify()
    return this.authorized
  }

  startListening(): void {
    if (this.isListening) return
    this.stopSpeaking()
    this.errorText = null
    this.transcript = ''
    this.finalText = ''
    const Ctor = recognitionCtor()
    if (!Ctor) {
      this.errorText = "Speech recognition isn't available right now."
      this.notify()
      return
    }
    const r = new Ctor()
    r.lang = 'en-US'
    r.continuous = true
    r.interimResults = true
    r.onresult = (e) => {
      let finalText = ''
      let interim = ''
      for (let i = 0; i < e.results.length; i++) {
        const res = e.results[i] as ArrayLike<{ transcript: string }> & { isFinal?: boolean }
        const text = res[0]?.transcript ?? ''
        if (res.isFinal) finalText += text
        else interim += text
      }
      this.finalText = finalText
      this.transcript = (finalText + interim).trim()
      this.notify()
    }
    r.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return
      this.errorText = e.error === 'not-allowed'
        ? 'Allow the microphone in your browser to talk to MedPull.'
        : `Couldn't start the microphone: ${e.error}`
      this.tearDown()
    }
    r.onend = () => { if (this.isListening) this.tearDown() }
    try {
      r.start()
      this.recognition = r
      this.isListening = true
      this.notify()
    } catch (e) {
      this.errorText = `Couldn't start the microphone: ${(e as Error).message}`
      this.tearDown()
    }
  }

  /** Stops the microphone and returns what was heard. */
  stopListening(): string {
    const heard = (this.transcript || this.finalText).trim()
    this.tearDown()
    return heard
  }

  private tearDown(): void {
    const r = this.recognition
    this.recognition = null
    if (r) {
      r.onresult = null
      r.onend = null
      r.onerror = null
      try { r.stop() } catch { /* already stopped */ }
    }
    this.isListening = false
    this.notify()
  }

  speak(text: string): void {
    if (!text || !('speechSynthesis' in window)) return
    this.stopSpeaking()
    const u = new SpeechSynthesisUtterance(text)
    const voice = spokenVoice.voice
    if (voice) u.voice = voice
    u.lang = 'en-US'
    u.rate = 0.95
    u.onend = () => { this.isSpeaking = false; this.notify() }
    u.onerror = () => { this.isSpeaking = false; this.notify() }
    this.isSpeaking = true
    this.notify()
    speechSynthesis.speak(u)
  }

  stopSpeaking(): void {
    if ('speechSynthesis' in window && speechSynthesis.speaking) speechSynthesis.cancel()
    this.isSpeaking = false
  }
}

/** Which voice the app speaks with, resolved live: the best English voice
 *  the browser has, Ava first where she is installed. A browser cannot
 *  download a voice either, so the Profile row says where to get one. */
class SpokenVoice extends Observable {
  voice: SpeechSynthesisVoice | null = null
  static wantedName = 'Ava'
  private static preferred = ['Ava', 'Evan', 'Zoe', 'Nathan', 'Joelle', 'Samantha', 'Google US English']
  private static unusable = ['Eloquence', 'Albert', 'Bad News', 'Bahh', 'Bells', 'Boing', 'Bubbles', 'Cellos',
    'Good News', 'Jester', 'Organ', 'Superstar', 'Trinoids', 'Whisper', 'Wobble', 'Zarvox', 'Fred', 'Junior',
    'Kathy', 'Ralph', 'Grandma', 'Grandpa', 'Rocko', 'Shelley', 'Flo', 'Eddy', 'Reed', 'Sandy']

  constructor() {
    super()
    if ('speechSynthesis' in window) {
      this.refresh()
      speechSynthesis.addEventListener?.('voiceschanged', () => this.refresh())
      window.addEventListener('focus', () => this.refresh())
    }
  }

  refresh(): void {
    const next = SpokenVoice.resolve()
    if (next?.voiceURI !== this.voice?.voiceURI) { this.voice = next; this.notify() }
  }

  private static resolve(): SpeechSynthesisVoice | null {
    if (!('speechSynthesis' in window)) return null
    const all = speechSynthesis.getVoices().filter((v) => !SpokenVoice.unusable.some((n) => v.name.includes(n)))
    const ava = all.find((v) => v.name.startsWith(SpokenVoice.wantedName) && v.lang.startsWith('en'))
    if (ava) return ava
    const enUS = all.filter((v) => v.lang === 'en-US' || v.lang === 'en_US')
    const en = all.filter((v) => v.lang.startsWith('en'))
    const pool = enUS.length ? enUS : en.length ? en : all
    if (!pool.length) return null
    const rank = (v: SpeechSynthesisVoice) => {
      const i = SpokenVoice.preferred.findIndex((n) => v.name.startsWith(n))
      return [v.localService ? 0 : 1, i < 0 ? SpokenVoice.preferred.length : i, v.name] as const
    }
    return pool.slice().sort((a, b) => {
      const ra = rank(a), rb = rank(b)
      return ra[0] - rb[0] || ra[1] - rb[1] || ra[2].localeCompare(rb[2])
    })[0]
  }

  get label(): string {
    if (!('speechSynthesis' in window)) return 'Spoken replies are not available in this browser'
    return this.voice ? this.voice.name : 'No usable voice installed'
  }
  get isNatural(): boolean {
    return !!this.voice && /premium|enhanced|natural|neural/i.test(`${this.voice.name} ${this.voice.voiceURI}`)
  }
  get hasWantedVoice(): boolean { return !!this.voice && this.voice.name.startsWith(SpokenVoice.wantedName) }
  /** The sentence under the Profile row. */
  get advice(): string {
    if (!('speechSynthesis' in window)) return 'This browser cannot speak. Spoken replies work in Safari, Chrome and Edge.'
    if (this.hasWantedVoice) return 'MedPull is speaking with Ava. This is the voice on the Care tab when you use the mic.'
    return 'MedPull speaks with the best voice your browser offers. On an iPhone, a downloaded voice (Settings → Accessibility → Spoken Content → Voices → English → Ava) is used as soon as it lands.'
  }
}

export const spokenVoice = new SpokenVoice()

export function useSpokenVoice(): SpokenVoice {
  useSyncExternalStore(spokenVoice.subscribe, spokenVoice.snapshot, spokenVoice.snapshot)
  return spokenVoice
}

export function useSpeech(speech: SpeechController): SpeechController {
  useSyncExternalStore(speech.subscribe, speech.snapshot, speech.snapshot)
  return speech
}
