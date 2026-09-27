"""The patient app's raw-measurement uploads: sensor windows from a walk,
the six-minute walk test and the phone-inclinometer range-of-motion test.

Every number the console shows from these is computed HERE, by
engine/mobility, from what the phone recorded — never by the phone vendor —
so a patient with an iPhone, an Android phone or no wearable at all gets the
same gait, stair, steadiness, endurance and joint-angle metrics by the same
rules. The rows land through the same ingest choke point as every wearable
delivery (plausibility bounds, the surgery window, idempotent dedupe) and the
engine recomputes the patient's assessment on the spot.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.mobile import current_patient
from app.connectors.base import CanonicalObservation
from app.connectors.ingest import PLAUSIBLE_RANGE, ingest_observations, partition_by_window
from app.database import get_db
from app.engine.mobility import (
    VERSION,
    MotionWindow,
    observations_for,
    process_window,
    range_of_motion,
    session_row,
    six_minute_walk,
)
from app.engine.mobility.active import PROTOCOLS
from app.models.enums import Granularity, MetricType, SourceProvider
from app.models.patient import Patient

router = APIRouter(prefix="/mobile", tags=["mobility"])

MAX_WINDOWS = 12
MAX_SAMPLES = 36_000        # 12 minutes at 50 Hz
MAX_ALTITUDE_SAMPLES = 4_000
MAX_HOLD_SAMPLES = 2_000
ROM_METRIC = {
    "flexion": MetricType.ROM_FLEXION,
    "extension": MetricType.ROM_EXTENSION,
    "abduction": MetricType.ROM_ABDUCTION,
}


class MotionWindowBody(BaseModel):
    started_at: datetime
    sample_rate_hz: float = Field(gt=5.0, le=200.0)
    # (N,3) total acceleration in m/s^2, device frame, gravity included
    accel: list[list[float]] = Field(min_length=50, max_length=MAX_SAMPLES)
    gyro: list[list[float]] | None = Field(default=None, max_length=MAX_SAMPLES)      # rad/s
    gravity: list[list[float]] | None = Field(default=None, max_length=MAX_SAMPLES)   # unit vectors
    timestamps: list[float] | None = Field(default=None, max_length=MAX_SAMPLES)      # s from start
    altitude: list[list[float]] | None = Field(default=None, max_length=MAX_ALTITUDE_SAMPLES)
    gps_distance_m: float | None = Field(default=None, ge=0.0, le=20_000.0)
    gps_accuracy_m: float | None = Field(default=None, ge=0.0, le=10_000.0)
    pedometer_steps: int | None = Field(default=None, ge=0, le=100_000)
    pedometer_distance_m: float | None = Field(default=None, ge=0.0, le=100_000.0)
    pocket_side: Literal["left", "right"] | None = None
    context: Literal["guided_walk", "six_minute_walk", "free_living"] = "guided_walk"


class MotionUpload(BaseModel):
    windows: list[MotionWindowBody] = Field(min_length=1, max_length=MAX_WINDOWS)
    height_cm: float | None = Field(default=None, ge=100.0, le=250.0)
    device_model: str | None = Field(default=None, max_length=80)


class SixMinuteWalkBody(BaseModel):
    started_at: datetime
    duration_s: float = Field(gt=60.0, le=600.0)
    steps: int | None = Field(default=None, ge=0, le=5_000)
    pedometer_distance_m: float | None = Field(default=None, ge=0.0, le=2_000.0)
    gps_distance_m: float | None = Field(default=None, ge=0.0, le=2_000.0)
    gps_accuracy_m: float | None = Field(default=None, ge=0.0, le=10_000.0)
    minute_steps: list[int] | None = Field(default=None, max_length=10)
    height_cm: float | None = Field(default=None, ge=100.0, le=250.0)
    device_model: str | None = Field(default=None, max_length=80)
    motion: MotionWindowBody | None = None    # the IMU recorded during the test


class RangeOfMotionBody(BaseModel):
    recorded_at: datetime
    protocol: str = Field(max_length=40)
    side: Literal["left", "right"]
    reference: list[list[float]] = Field(min_length=3, max_length=MAX_HOLD_SAMPLES)
    movement: list[list[float]] = Field(min_length=3, max_length=MAX_HOLD_SAMPLES)
    device_model: str | None = Field(default=None, max_length=80)


def _triplets(values: list[list[float]] | None, name: str, n: int | None = None) -> np.ndarray | None:
    if values is None:
        return None
    try:
        arr = np.asarray(values, dtype=float)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail=f"{name} must be a list of [x, y, z] triplets")
    if arr.ndim != 2 or arr.shape[1] != 3 or not np.all(np.isfinite(arr)):
        raise HTTPException(status_code=422, detail=f"{name} must be finite [x, y, z] triplets")
    if n is not None and len(arr) != n:
        raise HTTPException(status_code=422, detail=f"{name} must have one row per accel sample")
    return arr


def _local_naive(value: datetime, tz_id: str) -> datetime:
    """Observation times are stored as patient-local wall time (the seed and
    the gait upload do the same); an aware stamp from the phone is converted."""
    if value.tzinfo is None:
        return value
    return value.astimezone(ZoneInfo(tz_id)).replace(tzinfo=None)


def _window(body: MotionWindowBody, tz_id: str, height_cm: float | None,
            device_model: str | None) -> MotionWindow:
    n = len(body.accel)
    accel = _triplets(body.accel, "accel")
    gyro = _triplets(body.gyro, "gyro", n)
    gravity = _triplets(body.gravity, "gravity", n)
    timestamps = None
    if body.timestamps is not None:
        if len(body.timestamps) != n:
            raise HTTPException(status_code=422, detail="timestamps must match accel length")
        timestamps = np.asarray(body.timestamps, dtype=float)
    altitude = None
    if body.altitude is not None:
        alt = np.asarray(body.altitude, dtype=float)
        if alt.ndim != 2 or alt.shape[1] != 2:
            raise HTTPException(status_code=422, detail="altitude must be [t_s, metres] pairs")
        altitude = alt
    return MotionWindow(
        started_at=_local_naive(body.started_at, tz_id), fs=body.sample_rate_hz, accel=accel,
        gyro=gyro, gravity=gravity, timestamps=timestamps, altitude=altitude,
        gps_distance_m=body.gps_distance_m, gps_accuracy_m=body.gps_accuracy_m,
        pedometer_steps=body.pedometer_steps, pedometer_distance_m=body.pedometer_distance_m,
        height_cm=height_cm, pocket_side=body.pocket_side, context=body.context,
        device_model=device_model,
    )


def _store(db: Session, patient: Patient, rows: list[CanonicalObservation]) -> dict[str, int]:
    """Bounds, the surgery window, idempotent ingest, recompute — the same
    path the gait upload and every webhook take."""
    kept: list[CanonicalObservation] = []
    dropped = 0
    for row in rows:
        low, high = PLAUSIBLE_RANGE.get(str(row.metric_type), (float("-inf"), float("inf")))
        if row.value_num is None or not low <= row.value_num <= high:
            dropped += 1
            continue
        kept.append(row)
    inside, outside = partition_by_window(db, kept)
    ingested, updated, duplicates = ingest_observations(db, inside)
    if ingested or updated:
        from app.engine.pipeline import run_patient

        run_patient(db, patient.observations_from or patient.id)
    return {"ingested": ingested, "updated": updated, "duplicates": duplicates,
            "skipped_out_of_window": len(outside), "dropped_implausible": dropped}


@router.post("/observations/motion")
def upload_motion(
    body: MotionUpload, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> dict[str, Any]:
    target = patient.observations_from or patient.id
    rows: list[CanonicalObservation] = []
    summaries: list[dict[str, Any]] = []
    for item in body.windows:
        window = _window(item, patient.timezone, body.height_cm, body.device_model)
        result = process_window(window)
        rows.extend(observations_for(window, result, target, patient.timezone))
        if window.context in ("guided_walk", "six_minute_walk"):
            session = session_row(window, result, target, patient.timezone, window.context)
            if session is not None:
                rows.append(session)
        summaries.append(result.summary())
    counts = _store(db, patient, rows)
    return {"version": VERSION, "windows": summaries, "rows": len(rows), **counts}


@router.post("/tests/six-minute-walk")
def six_minute_walk_test(
    body: SixMinuteWalkBody, patient: Patient = Depends(current_patient),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    target = patient.observations_from or patient.id
    rows: list[CanonicalObservation] = []
    imu_distance = imu_steps = None
    motion_summary = None
    if body.motion is not None:
        window = _window(body.motion, patient.timezone, body.height_cm, body.device_model)
        window.context = "six_minute_walk"
        result = process_window(window)
        rows.extend(observations_for(window, result, target, patient.timezone))
        session = session_row(window, result, target, patient.timezone, "six_minute_walk")
        if session is not None:
            rows.append(session)
        motion_summary = result.summary()
        distances = [b.spatial.distance_m for b in result.bouts if b.spatial]
        imu_distance = float(sum(distances)) if distances else None
        imu_steps = result.n_steps or None
    test = six_minute_walk(
        body.duration_s, body.steps, body.height_cm,
        gps_distance_m=body.gps_distance_m, gps_accuracy_m=body.gps_accuracy_m,
        pedometer_distance_m=body.pedometer_distance_m, imu_distance_m=imu_distance,
        imu_steps=imu_steps, minute_steps=body.minute_steps,
    )
    if test is None:
        raise HTTPException(
            status_code=422,
            detail="No distance could be estimated: send steps and height, a pedometer "
                   "distance, a GPS distance, or the recorded motion.",
        )
    start = _local_naive(body.started_at, patient.timezone)
    rows.append(CanonicalObservation(
        patient_id=target, source_provider=SourceProvider.MEDPULL,
        metric_type=MetricType.SIX_MIN_WALK, unit="m", value_num=test.distance_m,
        value_json={"version": VERSION, "method": test.method, "steps": test.steps,
                    "cadence_spm": test.cadence_spm, "minute_cadence": test.minute_cadence,
                    "fade_pct": test.fade_pct, **test.detail},
        start_time=start, end_time=start + timedelta(seconds=body.duration_s),
        granularity=Granularity.SESSION,
        source_device_id=f"medpull:6mwt:{body.device_model or 'phone'}",
        timezone=patient.timezone,
    ))
    counts = _store(db, patient, rows)
    return {
        "version": VERSION,
        "distance_m": test.distance_m, "method": test.method, "steps": test.steps,
        "cadence_spm": test.cadence_spm, "fade_pct": test.fade_pct,
        "motion": motion_summary, **counts,
    }


@router.post("/tests/range-of-motion")
def range_of_motion_test(
    body: RangeOfMotionBody, patient: Patient = Depends(current_patient),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if body.protocol not in PROTOCOLS:
        raise HTTPException(status_code=422, detail=f"Unknown protocol; one of {sorted(PROTOCOLS)}")
    result = range_of_motion(
        body.protocol, _triplets(body.reference, "reference"), _triplets(body.movement, "movement")
    )
    if result is None:
        raise HTTPException(status_code=422, detail="Each hold needs at least three samples")
    target = patient.observations_from or patient.id
    at = _local_naive(body.recorded_at, patient.timezone)
    row = CanonicalObservation(
        patient_id=target, source_provider=SourceProvider.MEDPULL,
        metric_type=ROM_METRIC[result.movement], unit="deg", value_num=result.angle_deg,
        value_json={"version": VERSION, "method": "phone_inclinometer", "protocol": body.protocol,
                    "joint": result.joint, "movement": result.movement,
                    "tilt_reference_deg": result.tilt_reference_deg,
                    "tilt_movement_deg": result.tilt_movement_deg,
                    "reference_sd_deg": result.reference_sd_deg,
                    "movement_sd_deg": result.movement_sd_deg, "steady": result.steady},
        start_time=at, end_time=at + timedelta(seconds=1), granularity=Granularity.INSTANT,
        source_device_id=f"medpull:rom:{body.device_model or 'phone'}", timezone=patient.timezone,
        body_site=result.joint, side=body.side,
    )
    counts = _store(db, patient, [row])
    return {
        "version": VERSION, "joint": result.joint, "movement": result.movement,
        "side": body.side, "angle_deg": result.angle_deg, "steady": result.steady,
        "tilt_reference_deg": result.tilt_reference_deg,
        "tilt_movement_deg": result.tilt_movement_deg, **counts,
    }
