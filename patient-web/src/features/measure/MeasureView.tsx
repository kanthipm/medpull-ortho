/* MedPull's own measurements, taken with the phone and computed on the
   server the same way for every patient: a guided walk (gait), the
   six-minute walk (endurance) and a joint range-of-motion test (the phone
   as an inclinometer) (Features/Measure/MeasureView.swift). */

import { useEffect, useMemo, useState } from 'react'
import { messageFor, useApp } from '../../core/appModel'
import { deviceName } from '../../core/config'
import { Dates, type MotionWindowSummary, type RangeOfMotionResponse, type SixMinuteWalkResponse } from '../../core/models'
import { MotionCapture, Stature, useCapture } from '../../core/motion'
import { Card, Chip, ErrorBanner, NavBar, NavTextButton, PrimaryButton, Screen, SecondaryButton, Spinner, Toggle } from '../../ui/components'

function StatureField({ onChange }: { onChange: (cm: number | null) => void }) {
  const [text, setText] = useState('')
  return (
    <div className="stack-6">
      <span className="t-label secondary">Your height, in cm</span>
      <input className="field" inputMode="numeric" placeholder="e.g. 172" value={text} aria-label="Your height, in cm"
        onChange={(e) => {
          setText(e.target.value)
          const v = Number(e.target.value)
          if (v >= 100 && v <= 250) { onChange(v); Stature.store(v) } else onChange(null)
        }} />
      <span className="t-label secondary">Step length and walking speed are worked out from your height; Health did not have it.</span>
    </div>
  )
}

function clock(t: number): string {
  const s = Math.max(0, Math.round(t))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function Stat({ value, label }: { value: string; label: string }) {
  return <div className="stat"><b className="figures">{value}</b><span>{label}</span></div>
}

// MARK: - Guided walk / six-minute walk

export function GuidedWalkView({ sixMinute, onClose }: { sixMinute: boolean; onClose: () => void }) {
  const app = useApp()
  const capture = useCapture(useMemo(() => new MotionCapture(), []))
  const [pocket, setPocket] = useState('left')
  const [outdoors, setOutdoors] = useState(false)
  const [heightCm, setHeightCm] = useState<number | null>(() => Stature.storedCm)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [walkResult, setWalkResult] = useState<MotionWindowSummary | null>(null)
  const [testResult, setTestResult] = useState<SixMinuteWalkResponse | null>(null)

  const seconds = sixMinute ? 360 : 180
  const title = sixMinute ? 'Six-minute walk' : 'Guided walk'

  useEffect(() => () => { if (capture.state === 'recording') capture.stop() }, [capture])

  const send = async () => {
    const window = capture.window(sixMinute ? 'six_minute_walk' : 'guided_walk', pocket)
    if (!window) { setError('The recording was too short to use.'); return }
    setUploading(true)
    setError(null)
    try {
      if (sixMinute) {
        const r = await app.api.sixMinuteWalk({
          startedAt: window.startedAt, durationS: capture.elapsed, steps: null,
          pedometerDistanceM: null,
          gpsDistanceM: outdoors && capture.gpsDistance > 0 ? capture.gpsDistance : null,
          gpsAccuracyM: outdoors ? capture.gpsAccuracy : null,
          minuteSteps: null, heightCm, deviceModel: deviceName(), motion: window,
        })
        setTestResult(r)
      } else {
        const r = await app.api.uploadMotion({ windows: [window], heightCm, deviceModel: deviceName() })
        setWalkResult(r.windows[0] ?? null)
      }
      await app.refreshPortfolio()
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setUploading(false)
    }
  }

  const intro = (
    <Card>
      <div className="stack-14">
        <span className="t-copy c-body">
          {sixMinute
            ? 'Walk as far as you can in six minutes at a steady pace, turning around as needed. Stop and rest if you need to; the timer keeps going.'
            : 'Walk for three minutes at your usual pace, on level ground, without stopping. The phone reads your steps, rhythm and balance.'}
        </span>
        <span className="t-copy-m c-ink">Put the phone in a FRONT trouser pocket, top end up, then start.</span>
        <div className="stack-6">
          <span className="t-label secondary">Which pocket?</span>
          <div className="chip-row">
            <Chip label="Left" selected={pocket === 'left'} onClick={() => setPocket('left')} />
            <Chip label="Right" selected={pocket === 'right'} onClick={() => setPocket('right')} />
          </div>
        </div>
        <div className="hstack" style={{ gap: 14 }}>
          <div className="stack-2 grow">
            <span className="t-copy-m c-ink">Outdoors</span>
            <span className="t-label secondary">Uses your location to measure the distance</span>
          </div>
          <Toggle checked={outdoors} onChange={setOutdoors} label="Outdoors" />
        </div>
        {heightCm == null && <StatureField onChange={setHeightCm} />}
        {capture.unavailable && <ErrorBanner text={capture.unavailable} />}
        <PrimaryButton title="Start" icon="play.fill" disabled={!capture.isAvailable} onClick={() => { setError(null); void capture.start(seconds, outdoors) }} />
      </div>
    </Card>
  )

  const recording = (
    <Card tint>
      <div className="stack-12">
        <span className="t-label secondary">Recording</span>
        <span className="figures c-ink" style={{ fontSize: 56, fontWeight: 300, letterSpacing: '-2.7px', lineHeight: 1 }} aria-label={`${Math.round(seconds - capture.elapsed)} seconds left`}>
          {clock(seconds - capture.elapsed)}
        </span>
        <div className="hstack" style={{ gap: 18 }}>
          <Stat value={String(capture.steps)} label="steps" />
          {outdoors && <Stat value={`${capture.gpsDistance.toFixed(0)} m`} label="by GPS" />}
        </div>
        <span className="t-copy secondary">Keep walking. The phone stops on its own at {clock(seconds)}.</span>
        <SecondaryButton title="Stop early" icon="stop.fill" onClick={() => capture.stop()} />
      </div>
    </Card>
  )

  const finished = (
    <div className="stack-14">
      <Card>
        <div className="stack-12">
          {walkResult && !sixMinute ? (
            <>
              <span className="t-copy-lg-m c-ink">Your walk</span>
              <div className="result-grid">
                <Stat value={walkResult.cadenceSpm != null ? walkResult.cadenceSpm.toFixed(0) : '—'} label="steps / min" />
                <Stat value={walkResult.walkingSpeedMps != null ? walkResult.walkingSpeedMps.toFixed(2) : '—'} label="m/s" />
                <Stat value={walkResult.stepLengthM != null ? walkResult.stepLengthM.toFixed(2) : '—'} label="m per step" />
                <Stat value={walkResult.asymmetryPct != null ? `${walkResult.asymmetryPct.toFixed(0)}%` : '—'} label="asymmetry" />
                <Stat value={walkResult.doubleSupportPct != null ? `${walkResult.doubleSupportPct.toFixed(0)}%` : '—'} label="double support" />
                <Stat value={walkResult.steadiness != null ? walkResult.steadiness.toFixed(0) : '—'} label="steadiness" />
              </div>
              {walkResult.bouts === 0 && <span className="t-copy secondary">No steady walking was found in the recording. Try again with the phone in a front pocket.</span>}
              {walkResult.notes.map((n) => <span key={n} className="t-label secondary">{n}</span>)}
            </>
          ) : testResult ? (
            <>
              <span className="t-copy-lg-m c-ink">Six-minute walk</span>
              <div className="result-grid">
                <Stat value={testResult.distanceM.toFixed(0)} label="metres" />
                <Stat value={testResult.steps != null ? String(testResult.steps) : '—'} label="steps" />
                <Stat value={testResult.cadenceSpm != null ? testResult.cadenceSpm.toFixed(0) : '—'} label="steps / min" />
                <Stat value={testResult.fadePct != null ? `${testResult.fadePct >= 0 ? '+' : ''}${testResult.fadePct.toFixed(0)}%` : '—'} label="last vs first minute" />
              </div>
              <span className="t-label secondary">Distance by {testResult.method.replace(/_/g, ' ')}.</span>
            </>
          ) : (
            <>
              <span className="t-copy-m c-ink figures">Recorded {clock(capture.elapsed)} · {capture.steps} steps</span>
              <span className="t-copy secondary">Send it and the server works out your walking numbers.</span>
              {heightCm == null && <StatureField onChange={setHeightCm} />}
              <PrimaryButton title="Send" icon="arrow.up.circle.fill" loading={uploading} onClick={() => void send()} />
            </>
          )}
        </div>
      </Card>
      {walkResult || testResult
        ? <PrimaryButton title="Done" onClick={onClose} />
        : <SecondaryButton title="Discard and retry" onClick={() => capture.reset()} />}
    </div>
  )

  return (
    <Screen nav={(s) => (
      <NavBar title={title} scrolled={s} leading={
        <NavTextButton onClick={() => { if (capture.state === 'recording') capture.stop(); else onClose() }}>
          {capture.state === 'recording' ? 'Stop' : 'Close'}
        </NavTextButton>
      } />
    )}>
      <div className="content" style={{ gap: 14, padding: '8px 18px 24px' }}>
        {capture.state === 'idle' ? intro : capture.state === 'recording' ? recording : finished}
        {error && <ErrorBanner text={error} />}
      </div>
    </Screen>
  )
}

// MARK: - Range of motion

const protocols: [string, string, string, string][] = [
  // key, title, reference instruction, movement instruction
  ['knee_flexion_supine', 'Knee: bend',
    'Lie on your back, leg straight. Rest the phone’s long edge on your shin, top end toward the knee, screen up.',
    'Slide your heel toward you and bend the knee as far as you comfortably can. Hold.'],
  ['knee_extension_supine', 'Knee: straighten',
    'Lie on your back. Rest the phone on the bed beside you, screen up, top end toward your head.',
    'Rest the phone on your shin, heel propped on a towel, and press the knee down as straight as it goes. Hold.'],
  ['hip_flexion_supine', 'Hip: bend',
    'Lie on your back, leg straight. Rest the phone on the front of your thigh, top end toward the hip.',
    'Bring the knee toward your chest as far as you comfortably can. Hold.'],
  ['shoulder_flexion_standing', 'Shoulder: raise forward',
    'Stand, arm hanging. Hold the phone against the outside of your upper arm, top end toward the shoulder.',
    'Raise the arm forward and up as far as you comfortably can. Hold.'],
  ['shoulder_abduction_standing', 'Shoulder: raise sideways',
    'Stand, arm hanging. Hold the phone against the outside of your upper arm, top end toward the shoulder.',
    'Raise the arm out to the side and up as far as you comfortably can. Hold.'],
]

export function RangeOfMotionView({ onClose }: { onClose: () => void }) {
  const app = useApp()
  const capture = useCapture(useMemo(() => new MotionCapture(), []))
  const [protocolKey, setProtocolKey] = useState('knee_flexion_supine')
  const [side, setSide] = useState('left')
  const [step, setStep] = useState(0) // 0 setup · 1 reference hold · 2 movement hold · 3 result
  const [holding, setHolding] = useState(false)
  const [reference, setReference] = useState<number[][]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<RangeOfMotionResponse | null>(null)
  const current = protocols.find((p) => p[0] === protocolKey) ?? protocols[0]

  useEffect(() => () => { if (capture.state === 'recording') capture.stop() }, [capture])

  const send = async (movement: number[][]) => {
    setStep(3)
    setUploading(true)
    setError(null)
    try {
      setResult(await app.api.rangeOfMotion({
        recordedAt: Dates.iso(new Date()), protocol: protocolKey, side, reference, movement, deviceModel: deviceName(),
      }))
    } catch (e) {
      setError(messageFor(e))
    } finally {
      setUploading(false)
    }
  }

  const captureHold = () => {
    setHolding(true)
    setTimeout(() => {
      const samples = capture.recentGravity(2)
      setHolding(false)
      if (step === 1) {
        setReference(samples)
        setStep(2)
      } else {
        capture.stop()
        void send(samples)
      }
    }, 2000)
  }

  const setup = (
    <Card>
      <div className="stack-14">
        <span className="t-copy c-body">The phone is the goniometer: two short holds, and the server reads the angle between them.</span>
        <div className="stack-6">
          <span className="t-label secondary">Movement</span>
          <div className="chip-row column">
            {protocols.map((p) => <Chip key={p[0]} label={p[1]} selected={protocolKey === p[0]} onClick={() => setProtocolKey(p[0])} />)}
          </div>
        </div>
        <div className="stack-6">
          <span className="t-label secondary">Side</span>
          <div className="chip-row">
            <Chip label="Left" selected={side === 'left'} onClick={() => setSide('left')} />
            <Chip label="Right" selected={side === 'right'} onClick={() => setSide('right')} />
          </div>
        </div>
        {capture.unavailable && <ErrorBanner text={capture.unavailable} />}
        <PrimaryButton title="Begin" icon="angle" disabled={!capture.isAvailable} onClick={() => { setError(null); setReference([]); setStep(1) }} />
      </div>
    </Card>
  )

  const hold = (
    <Card tint={holding}>
      <div className="stack-12">
        <span className="t-label secondary">{step === 1 ? '1 of 2 · Starting position' : '2 of 2 · As far as it goes'}</span>
        <span className="t-copy c-body">{step === 1 ? current[2] : current[3]}</span>
        {capture.state === 'recording' && (
          <>
            <span className="figures c-ink" style={{ fontSize: 56, fontWeight: 300, letterSpacing: '-2.7px', lineHeight: 1 }}>{capture.liveTiltDegrees.toFixed(0)}°</span>
            <span className="t-label secondary">{holding ? 'Hold still…' : 'Live tilt'}</span>
          </>
        )}
        {!holding && (
          <PrimaryButton title={capture.state === 'recording' ? 'Capture this position' : 'Ready'}
            icon={capture.state === 'recording' ? 'checkmark.circle.fill' : 'play.fill'}
            onClick={() => { if (capture.state !== 'recording') void capture.start(600, false); else captureHold() }} />
        )}
      </div>
    </Card>
  )

  const done = (
    <div className="stack-14">
      <Card>
        <div className="stack-10">
          {result ? (
            <>
              <span className="t-copy-lg-m c-ink">{current[1]}</span>
              <span className="figures c-ink" style={{ fontSize: 56, fontWeight: 300, letterSpacing: '-2.7px', lineHeight: 1 }}>{result.angleDeg.toFixed(0)}°</span>
              <span className="t-copy secondary">
                {`${result.joint.charAt(0).toUpperCase()}${result.joint.slice(1)} ${result.movement}, ${result.side} side${result.steady ? '' : ' · the phone moved during a hold; consider repeating'}`}
              </span>
            </>
          ) : uploading ? (
            <div className="hstack-8" style={{ color: 'rgb(var(--brand))' }}><Spinner /><span className="t-copy secondary">Working out the angle…</span></div>
          ) : null}
        </div>
      </Card>
      {result ? (
        <>
          <PrimaryButton title="Done" onClick={onClose} />
          <SecondaryButton title="Measure again" onClick={() => { setResult(null); capture.reset(); setStep(0) }} />
        </>
      ) : !uploading ? (
        <SecondaryButton title="Try again" onClick={() => { capture.reset(); setStep(0) }} />
      ) : null}
    </div>
  )

  return (
    <Screen nav={(s) => <NavBar title="Range of motion" scrolled={s} leading={<NavTextButton onClick={onClose}>Close</NavTextButton>} />}>
      <div className="content" style={{ gap: 14, padding: '8px 18px 24px' }}>
        {step === 0 ? setup : step === 3 ? done : hold}
        {error && <ErrorBanner text={error} />}
      </div>
    </Screen>
  )
}
