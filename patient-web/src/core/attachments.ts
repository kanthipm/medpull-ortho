/* Photos, clips, voice notes and files on the thread, on the app's side:
   getting one ready to send, recording one, and fetching one that arrived
   (Core/Attachments.swift). */

import { useSyncExternalStore } from 'react'
import type { APIClient } from './api'
import type { ChatAttachment } from './models'

export type Ready = { data: Blob; contentType: string; filename: string | null }

export const AttachmentPrep = {
  /** Long edge, in pixels. A wound photograph is read on a laptop, not
   *  enlarged in a darkroom. */
  maxEdge: 2048,
  quality: 0.82,
  /** The server's cap for a clip or a recording (blobs.MAX_MEDIA_BYTES). */
  maxMediaBytes: 48 * 1024 * 1024,
  /** What the file picker offers (app/storage/blobs.ALLOWED_TYPES). */
  accept: '.pdf,.jpg,.jpeg,.png,.webp,.heic,.heif,.mp4,.mov,.m4a,.mp3,.wav,application/pdf,image/*,video/mp4,video/quicktime,audio/*',

  /** A photo, as something the other side can open: re-encoded as JPEG
   *  within the long edge. A HEIC the browser cannot decode goes as it is
   *  (the server accepts it). */
  async photo(file: Blob, name?: string | null): Promise<Ready | null> {
    const bitmap = await decode(file)
    if (!bitmap) {
      if (file.type === 'image/heic' || file.type === 'image/heif' || /\.hei[cf]$/i.test(name ?? '')) {
        return { data: file, contentType: file.type || 'image/heic', filename: name ?? 'photo.heic' }
      }
      return null
    }
    const scale = Math.min(1, this.maxEdge / Math.max(bitmap.width, bitmap.height))
    const w = Math.max(1, Math.round(bitmap.width * scale))
    const h = Math.max(1, Math.round(bitmap.height * scale))
    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) return null
    ctx.drawImage(bitmap, 0, 0, w, h)
    if ('close' in bitmap) bitmap.close()
    const jpeg = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', this.quality))
    if (!jpeg) return null
    const base = (name ?? 'photo').replace(/\.[^.]+$/, '')
    return { data: jpeg, contentType: 'image/jpeg', filename: `${base}.jpg` }
  },

  /** A file the person chose. PDFs go as they are; images are re-encoded;
   *  a clip or a recording goes as it is when the server takes the type. */
  async file(file: File): Promise<Ready | null> {
    const type = file.type || typeFromName(file.name)
    if (type.startsWith('video/')) return this.video(file)
    if (type.startsWith('audio/')) return this.audio(file)
    if (type.startsWith('image/')) return this.photo(file, file.name)
    if (type === 'application/pdf') return { data: file, contentType: type, filename: file.name }
    return null
  },

  /** A clip. A browser cannot re-encode video, so the clip goes as the
   *  camera wrote it, within the server's cap and the types it plays. */
  async video(file: File): Promise<Ready | null> {
    const type = file.type || typeFromName(file.name)
    if (!['video/mp4', 'video/quicktime'].includes(type)) return null
    if (file.size === 0 || file.size > this.maxMediaBytes) return null
    return { data: file, contentType: type, filename: file.name }
  },

  /** A recording the person already has. */
  async audio(file: File): Promise<Ready | null> {
    if (file.size > this.maxMediaBytes) return null
    const ext = (file.name.split('.').pop() ?? '').toLowerCase()
    const mime = ext === 'm4a' || ext === 'aac' || ext === 'mp4' ? 'audio/mp4'
      : ext === 'mp3' ? 'audio/mpeg' : ext === 'wav' ? 'audio/wav'
        : file.type === 'audio/mp4' || file.type === 'audio/x-m4a' ? 'audio/mp4'
          : file.type === 'audio/mpeg' ? 'audio/mpeg' : file.type === 'audio/wav' || file.type === 'audio/x-wav' ? 'audio/wav' : null
    if (!mime) return null
    return { data: file, contentType: mime, filename: file.name }
  },

  /** The app's own voice note, straight off the recorder. */
  voiceNote(blob: Blob, contentType: string): Ready | null {
    if (blob.size > this.maxMediaBytes || blob.size === 0) return null
    const stamp = new Date().toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
    const ext = contentType === 'audio/wav' ? 'wav' : 'm4a'
    return { data: blob, contentType, filename: `Voice note ${stamp}.${ext}` }
  },
}

function typeFromName(name: string): string {
  const ext = (name.split('.').pop() ?? '').toLowerCase()
  const map: Record<string, string> = {
    jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', heic: 'image/heic', heif: 'image/heif',
    pdf: 'application/pdf', mp4: 'video/mp4', mov: 'video/quicktime', m4a: 'audio/mp4', mp3: 'audio/mpeg', wav: 'audio/wav',
  }
  return map[ext] ?? ''
}

async function decode(file: Blob): Promise<ImageBitmap | HTMLImageElement | null> {
  try {
    if ('createImageBitmap' in window) return await createImageBitmap(file)
  } catch {
    /* fall through to an <img> */
  }
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => { URL.revokeObjectURL(url); resolve(img) }
    img.onerror = () => { URL.revokeObjectURL(url); resolve(null) }
    img.src = url
  })
}

// MARK: - Recording a voice note

class Observable {
  private listeners = new Set<() => void>()
  private version = 0
  subscribe = (fn: () => void) => { this.listeners.add(fn); return () => { this.listeners.delete(fn) } }
  snapshot = () => this.version
  protected notify() { this.version++; for (const fn of this.listeners) fn() }
}

/** The microphone, for a message rather than a transcript: AAC in an MP4
 *  container where the browser can write one (Safari), WAV everywhere
 *  else, which the server stores and the console's browser plays. Nothing
 *  is kept past the upload. */
export class VoiceNoteRecorder extends Observable {
  isRecording = false
  elapsed = 0
  /** 0...1, for the meter beside the clock. */
  level = 0
  errorText: string | null = null
  /** Long enough for a message, short enough to upload on a bad signal. */
  static maxSeconds = 180

  private stream: MediaStream | null = null
  private recorder: MediaRecorder | null = null
  private chunks: Blob[] = []
  private context: AudioContext | null = null
  private analyser: AnalyserNode | null = null
  private processor: ScriptProcessorNode | null = null
  private pcm: Float32Array[] = []
  private sampleRate = 44_100
  private ticker: number | null = null
  private startedAt = 0
  private mime: string = 'audio/wav'
  private done: ((blob: Blob | null) => void) | null = null

  get elapsedText(): string {
    const s = Math.floor(this.elapsed)
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
  }

  async start(): Promise<void> {
    if (this.isRecording) return
    this.errorText = null
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      this.errorText = 'Allow the microphone in your browser to record a voice note.'
      this.notify()
      return
    }
    this.stream = stream
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    this.context = new Ctx()
    this.sampleRate = this.context.sampleRate
    const source = this.context.createMediaStreamSource(stream)
    this.analyser = this.context.createAnalyser()
    this.analyser.fftSize = 512
    source.connect(this.analyser)
    const canMp4 = typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported?.('audio/mp4')
    if (canMp4) {
      this.mime = 'audio/mp4'
      this.chunks = []
      const r = new MediaRecorder(stream, { mimeType: 'audio/mp4', audioBitsPerSecond: 64_000 })
      r.ondataavailable = (e) => { if (e.data.size) this.chunks.push(e.data) }
      r.onstop = () => { this.done?.(this.chunks.length ? new Blob(this.chunks, { type: 'audio/mp4' }) : null) }
      r.start(250)
      this.recorder = r
    } else {
      this.mime = 'audio/wav'
      this.pcm = []
      this.processor = this.context.createScriptProcessor(4096, 1, 1)
      this.processor.onaudioprocess = (e) => { if (this.isRecording) this.pcm.push(new Float32Array(e.inputBuffer.getChannelData(0))) }
      source.connect(this.processor)
      this.processor.connect(this.context.destination)
    }
    this.isRecording = true
    this.elapsed = 0
    this.startedAt = performance.now()
    const data = new Uint8Array(this.analyser.frequencyBinCount)
    this.ticker = window.setInterval(() => {
      if (!this.isRecording) return
      this.elapsed = (performance.now() - this.startedAt) / 1000
      this.analyser?.getByteTimeDomainData(data)
      let peak = 0
      for (const v of data) peak = Math.max(peak, Math.abs(v - 128) / 128)
      this.level = Math.max(0, Math.min(1, peak * 2.2))
      if (this.elapsed >= VoiceNoteRecorder.maxSeconds) {
        // The time limit ran out: the composer notices isRecording flip
        // and treats it as a stop.
        this.isRecording = false
      }
      this.notify()
    }, 100)
    this.notify()
  }

  /** Stop and hand back the file, or null when nothing worth sending was
   *  recorded (under half a second is a tap, not a note). */
  async stop(): Promise<{ blob: Blob; contentType: string } | null> {
    if (!this.stream) return null
    const length = (performance.now() - this.startedAt) / 1000
    const blob = await this.finish()
    if (length < 0.5 || !blob) return null
    return { blob, contentType: this.mime }
  }

  async cancel(): Promise<void> {
    await this.finish()
  }

  private finish(): Promise<Blob | null> {
    return new Promise((resolve) => {
      if (this.ticker != null) { clearInterval(this.ticker); this.ticker = null }
      this.isRecording = false
      this.level = 0
      const wasMp4 = this.recorder != null
      if (wasMp4) {
        this.done = (b) => resolve(b)
        try { this.recorder!.stop() } catch { resolve(null) }
        this.recorder = null
      } else {
        this.processor?.disconnect()
        this.processor = null
        resolve(this.pcm.length ? encodeWav(this.pcm, this.sampleRate) : null)
        this.pcm = []
      }
      for (const t of this.stream?.getTracks() ?? []) t.stop()
      this.stream = null
      void this.context?.close()
      this.context = null
      this.analyser = null
      this.notify()
    })
  }
}

/** PCM float chunks -> a 16-bit mono WAV, downsampled to 16 kHz: a minute
 *  is under 2 MB, and every player reads it. */
function encodeWav(chunks: Float32Array[], inputRate: number): Blob {
  const total = chunks.reduce((n, c) => n + c.length, 0)
  const all = new Float32Array(total)
  let o = 0
  for (const c of chunks) { all.set(c, o); o += c.length }
  const outRate = 16_000
  const ratio = inputRate / outRate
  const n = Math.floor(all.length / ratio)
  const out = new Int16Array(n)
  for (let i = 0; i < n; i++) {
    const start = Math.floor(i * ratio)
    const end = Math.min(all.length, Math.floor((i + 1) * ratio))
    let sum = 0
    for (let j = start; j < end; j++) sum += all[j]
    const v = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)))
    out[i] = v < 0 ? v * 0x8000 : v * 0x7fff
  }
  const buffer = new ArrayBuffer(44 + out.length * 2)
  const view = new DataView(buffer)
  const str = (off: number, s: string) => { for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i)) }
  str(0, 'RIFF'); view.setUint32(4, 36 + out.length * 2, true); str(8, 'WAVE')
  str(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, outRate, true); view.setUint32(28, outRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  str(36, 'data'); view.setUint32(40, out.length * 2, true)
  new Int16Array(buffer, 44).set(out)
  return new Blob([buffer], { type: 'audio/wav' })
}

// MARK: - Drawing one that arrived

/** Decoded files, kept by content hash as object URLs. The links that
 *  serve them are minted per request and expire in minutes, so the bytes
 *  cannot be cached by URL — but the hash is the bytes, so the same photo
 *  is fetched once however many times the thread redraws. */
export class AttachmentCache extends Observable {
  private urls = new Map<string, string>()
  private order: string[] = []
  private failed = new Set<string>()
  private loading = new Set<string>()
  private readonly limit = 48

  private key(a: ChatAttachment): string { return a.sha256 ?? `id:${a.id}` }

  url(a: ChatAttachment): string | null { return this.urls.get(this.key(a)) ?? null }
  didFail(a: ChatAttachment): boolean { return this.failed.has(this.key(a)) }
  isLoading(a: ChatAttachment): boolean { return this.loading.has(this.key(a)) }

  async load(a: ChatAttachment, api: APIClient): Promise<void> {
    const k = this.key(a)
    if (this.urls.has(k) || this.failed.has(k) || this.loading.has(k)) return
    this.loading.add(k)
    this.notify()
    try {
      const blob = await api.attachmentBlob(a.id)
      this.store(k, URL.createObjectURL(blob))
    } catch {
      this.failed.add(k)
    } finally {
      this.loading.delete(k)
      this.notify()
    }
  }

  private store(k: string, url: string): void {
    this.urls.set(k, url)
    this.order.push(k)
    while (this.order.length > this.limit) {
      const oldest = this.order.shift()!
      if (oldest !== k) {
        const old = this.urls.get(oldest)
        if (old) URL.revokeObjectURL(old)
        this.urls.delete(oldest)
      }
    }
  }
}

export const attachmentCache = new AttachmentCache()

/** One recording playing at a time, app-wide: tapping a second note stops
 *  the first, the way Messages does it. */
export class AudioClipPlayer extends Observable {
  playingKey: string | null = null
  progress = 0
  private audio: HTMLAudioElement | null = null
  private ticker: number | null = null

  isPlaying(key: string): boolean { return this.playingKey === key }

  toggle(key: string, url: string): void {
    if (this.playingKey === key) { this.stop(); return }
    this.stop()
    const a = new Audio(url)
    a.onended = () => this.stop()
    a.onerror = () => this.stop()
    void a.play().catch(() => this.stop())
    this.audio = a
    this.playingKey = key
    this.ticker = window.setInterval(() => {
      if (!this.audio) return
      this.progress = this.audio.duration > 0 ? this.audio.currentTime / this.audio.duration : 0
      this.notify()
    }, 100)
    this.notify()
  }

  stop(): void {
    if (this.ticker != null) { clearInterval(this.ticker); this.ticker = null }
    if (this.audio) { this.audio.pause(); this.audio = null }
    this.playingKey = null
    this.progress = 0
    this.notify()
  }

  static duration(url: string): Promise<number | null> {
    return new Promise((resolve) => {
      const a = new Audio(url)
      a.onloadedmetadata = () => resolve(Number.isFinite(a.duration) ? a.duration : null)
      a.onerror = () => resolve(null)
    })
  }
}

export const audioClips = new AudioClipPlayer()

export function useObservable<T extends Observable>(o: T): T {
  useSyncExternalStore(o.subscribe, o.snapshot, o.snapshot)
  return o
}
