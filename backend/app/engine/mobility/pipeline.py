"""One raw sensor window in, canonical observation rows out.

``process_window`` runs the chain
    align -> walking bouts -> steps -> (thigh phases) -> step length & speed
          -> steadiness -> stairs
and returns a ``WindowResult`` with one ``BoutResult`` per accepted bout and
one ``StairEvent`` per flight. ``observations_for`` turns that into the rows
the ingest path stores: one INTERVAL row per bout per metric, timed on the
bout, so the daily series the engine reads is the mean over the day's bouts
(engine/dataload) and every row keeps its own provenance in value_json
(method, step count, calibration, phone side, quality flags).

Everything is deterministic: the same window always yields the same rows,
and the same rows always carry the same dedupe key, so an upload the phone
retries cannot double-count a walk.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timedelta
from typing import Any

import numpy as np

from app.connectors.base import CanonicalObservation
from app.engine.mobility.bouts import detect_bouts
from app.engine.mobility.frames import Aligned, MotionWindow, align
from app.engine.mobility.phases import Phases, alternating_asymmetry, phases
from app.engine.mobility.spatial import Spatial, spatial
from app.engine.mobility.stability import Stability, stability
from app.engine.mobility.stairs import StairEvent, stair_events
from app.engine.mobility.steps import StepTiming, detect_steps, timing
from app.models.enums import Granularity, MetricType, SourceProvider

VERSION = "mobility-1"
DEVICE_PREFIX = "medpull:imu"


@dataclass
class BoutResult:
    start_s: float
    end_s: float
    steps: StepTiming
    phases: Phases | None
    spatial: Spatial | None
    stability: Stability | None
    asymmetry_pct: float | None       # signed when from phases, unsigned fallback otherwise
    asymmetry_method: str | None

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


@dataclass
class WindowResult:
    bouts: list[BoutResult]
    stairs: list[StairEvent]
    rejected_bouts: int
    gravity_source: str
    duration_s: float
    notes: list[str] = field(default_factory=list)

    @property
    def n_steps(self) -> int:
        return sum(b.steps.n_steps for b in self.bouts)

    @property
    def walking_s(self) -> float:
        return sum(b.duration_s for b in self.bouts)

    def summary(self) -> dict[str, Any]:
        speeds = [b.spatial.speed_mps for b in self.bouts if b.spatial]
        return {
            "version": VERSION,
            "duration_s": round(self.duration_s, 1),
            "walking_s": round(self.walking_s, 1),
            "bouts": len(self.bouts),
            "rejected_bouts": self.rejected_bouts,
            "steps": self.n_steps,
            "cadence_spm": _mean([b.steps.cadence_spm for b in self.bouts]),
            "walking_speed_mps": _mean(speeds),
            "step_length_m": _mean([b.spatial.distance_m / max(len(b.spatial.step_lengths), 1)
                                    for b in self.bouts if b.spatial]),
            "asymmetry_pct": _mean([b.asymmetry_pct for b in self.bouts
                                    if b.asymmetry_pct is not None]),
            "double_support_pct": _mean([b.phases.double_support_pct for b in self.bouts
                                         if b.phases]),
            "steadiness": _mean([b.stability.index for b in self.bouts if b.stability]),
            "stairs": [asdict(s) for s in self.stairs],
            "gravity_source": self.gravity_source,
            "notes": self.notes,
        }


def _mean(values: list[float]) -> float | None:
    vals = [float(v) for v in values if v is not None and np.isfinite(v)]
    return round(float(np.mean(vals)), 3) if vals else None


def process_window(window: MotionWindow) -> WindowResult:
    aligned: Aligned = align(window)
    fs = aligned.fs
    height_m = window.height_cm / 100.0 if window.height_cm else None
    bouts_idx = detect_bouts(aligned.a_mag, fs)
    bouts: list[BoutResult] = []
    rejected = 0
    all_step_times: list[float] = []
    for s, e in bouts_idx:
        peaks = detect_steps(aligned.a_mag[s:e], fs)
        step = timing(peaks, fs)
        if not step.valid:
            rejected += 1
            continue
        duration = (e - s) / fs
        all_step_times.extend(((peaks + s) / fs).tolist())
        ph = phases(aligned.gyro[s:e], fs, peaks) if aligned.gyro is not None else None
        if ph is not None and not ph.valid:
            ph = None
        # GPS distance describes the whole window; it is only attributed to a
        # bout when that bout IS the walk (one bout covering most of the window).
        bout_gps = window.gps_distance_m if (
            window.gps_distance_m and len(bouts_idx) == 1 and duration >= 0.8 * aligned.t[-1]
        ) else None
        sp = spatial(
            aligned.a_vert[s:e], peaks, fs, duration, height_m,
            gps_distance_m=bout_gps, gps_accuracy_m=window.gps_accuracy_m,
        )
        speed = sp.speed_mps if sp else None
        stab = stability(aligned.a_vert[s:e], fs, step.step_time_cv, step.stride_time_s, speed)
        if ph is not None:
            asym, method = ph.asymmetry_pct, "thigh_gyro_phases"
        else:
            asym = alternating_asymmetry(step.step_times)
            method = "alternating_step_times" if asym is not None else None
        bouts.append(BoutResult(
            start_s=float(aligned.t[s]), end_s=float(aligned.t[min(e, aligned.n) - 1]),
            steps=step, phases=ph, spatial=sp, stability=stab,
            asymmetry_pct=round(asym, 2) if asym is not None else None,
            asymmetry_method=method,
        ))
    stairs = stair_events(window.altitude, np.asarray(all_step_times))
    notes = list(window.notes)
    if height_m is None:
        notes.append("no stature on file: step length and speed need height_cm (or GPS)")
    if aligned.gyro is None:
        notes.append("no gyroscope: asymmetry is unsigned, double support not computed")
    return WindowResult(
        bouts=bouts, stairs=stairs, rejected_bouts=rejected,
        gravity_source=aligned.gravity_source,
        duration_s=float(aligned.t[-1]) if aligned.n else 0.0, notes=notes,
    )


def observations_for(
    window: MotionWindow, result: WindowResult, patient_id: str, tz_id: str,
) -> list[CanonicalObservation]:
    """Canonical rows for one processed window. Rows are INTERVAL, timed on
    the bout / flight, provider MEDPULL, device ``medpull:imu:<model>``."""
    device = f"{DEVICE_PREFIX}:{window.device_model or 'phone'}"
    rows: list[CanonicalObservation] = []

    def row(metric: MetricType, unit: str, value: float, start_s: float, end_s: float,
            detail: dict[str, Any], side: str | None = None,
            granularity: Granularity = Granularity.INTERVAL) -> None:
        start = window.started_at + timedelta(seconds=start_s)
        end = window.started_at + timedelta(seconds=max(end_s, start_s + 1.0))
        rows.append(CanonicalObservation(
            patient_id=patient_id, source_provider=SourceProvider.MEDPULL,
            metric_type=metric, unit=unit, value_num=round(float(value), 4),
            value_json={"version": VERSION, "context": window.context, **detail},
            start_time=start, end_time=end, granularity=granularity,
            source_device_id=device, timezone=tz_id, side=side,
        ))

    for b in result.bouts:
        base = {"n_steps": b.steps.n_steps, "duration_s": round(b.duration_s, 1),
                "step_time_cv": round(b.steps.step_time_cv, 4)}
        row(MetricType.CADENCE, "spm", b.steps.cadence_spm, b.start_s, b.end_s, base)
        if b.spatial is not None:
            sp = b.spatial
            spatial_detail = {**base, "method": sp.method, "k": None if np.isnan(sp.k_used)
                              else round(sp.k_used, 3), "calibrated": sp.calibrated}
            row(MetricType.WALKING_SPEED, "m/s", sp.speed_mps, b.start_s, b.end_s, spatial_detail)
            row(MetricType.STEP_LENGTH, "m", sp.distance_m / max(len(sp.step_lengths), 1),
                b.start_s, b.end_s, spatial_detail)
        if b.asymmetry_pct is not None:
            detail = {**base, "method": b.asymmetry_method, "signed": b.phases is not None,
                      "pocket_side": window.pocket_side}
            if b.phases is not None:
                detail.update({"ipsi_step_s": round(float(b.phases.ipsi_step_s.mean()), 3),
                               "contra_step_s": round(float(b.phases.contra_step_s.mean()), 3),
                               "n_strides": b.phases.n_strides})
            row(MetricType.WALKING_ASYMMETRY_PCT, "%", abs(b.asymmetry_pct), b.start_s, b.end_s,
                {**detail, "signed_value": b.asymmetry_pct}, side=window.pocket_side)
        if b.phases is not None:
            row(MetricType.DOUBLE_SUPPORT_PCT, "%", b.phases.double_support_pct, b.start_s,
                b.end_s, {**base, "method": "thigh_gyro_phases",
                          "swing_fraction": round(float(np.mean(b.phases.swing_s / b.phases.stride_s)), 3),
                          "n_strides": b.phases.n_strides, "pocket_side": window.pocket_side},
                side=window.pocket_side)
        if b.stability is not None:
            row(MetricType.WALKING_STEADINESS, "score", b.stability.index, b.start_s, b.end_s,
                {**base, "method": "gait_variability_index", "level": b.stability.level,
                 "features": {k: round(v, 4) for k, v in b.stability.features.items()}})
    for ev in result.stairs:
        metric = MetricType.STAIR_SPEED_UP if ev.direction == "up" else MetricType.STAIR_SPEED_DOWN
        row(metric, "m/s", ev.speed_mps, ev.start_s, ev.end_s,
            {"method": "barometer_vertical_speed", "height_m": ev.height_m, "n_steps": ev.n_steps})
    return rows


def session_row(
    window: MotionWindow, result: WindowResult, patient_id: str, tz_id: str, kind: str,
) -> CanonicalObservation | None:
    """The walk as one EXERCISE_SESSION row with per-minute cadence and speed,
    which is what the guided-walk task verification and the walking-economy /
    endurance-fade care metrics read."""
    if not result.bouts or result.duration_s < 60:
        return None
    minutes = int(result.duration_s // 60)
    cadence_by_min: list[float] = []
    speed_by_min: list[float] = []
    for m in range(minutes):
        lo, hi = m * 60.0, (m + 1) * 60.0
        cad, spd, weight = 0.0, 0.0, 0.0
        for b in result.bouts:
            overlap = max(0.0, min(hi, b.end_s) - max(lo, b.start_s))
            if overlap <= 0:
                continue
            cad += b.steps.cadence_spm * overlap
            spd += (b.spatial.speed_mps if b.spatial else 0.0) * overlap
            weight += overlap
        cadence_by_min.append(round(cad / weight, 1) if weight else 0.0)
        speed_by_min.append(round(spd / weight, 3) if weight else 0.0)
    return CanonicalObservation(
        patient_id=patient_id, source_provider=SourceProvider.MEDPULL,
        metric_type=MetricType.EXERCISE_SESSION, unit="min",
        value_num=round(result.duration_s / 60.0, 2),
        value_json={"kind": kind, "minutes": round(result.duration_s / 60.0, 2),
                    "cadence_spm": cadence_by_min, "speed_mps": speed_by_min,
                    "steps": result.n_steps, "version": VERSION},
        start_time=window.started_at,
        end_time=window.started_at + timedelta(seconds=max(result.duration_s, 1.0)),
        granularity=Granularity.SESSION,
        source_device_id=f"{DEVICE_PREFIX}:{window.device_model or 'phone'}", timezone=tz_id,
    )
