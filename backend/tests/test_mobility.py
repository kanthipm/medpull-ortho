"""MedPull's own mobility engine (app/engine/mobility) and the patient app's
raw-measurement uploads (app/api/mobility).

The algorithm tests run on synthetic pocket-phone signals whose ground truth
is known (tests/synth_motion.py); they check that each estimator recovers
the number it was built to find, and that the engine refuses what it should
(a phone that is not walking, a hold that is not steady). They are
self-consistency checks, not clinical validation — that plan is in
docs/methods/custom-metrics-methodology.md.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import delete, select

from app.engine.mobility import (
    observations_for,
    process_window,
    range_of_motion,
    six_minute_walk,
    stress_index_series,
)
from app.engine.mobility.frames import MotionWindow
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as P
from app.models.observation import Observation
from tests.synth_motion import synth_walk
from tests.test_mobile import _enroll


# --- gait ------------------------------------------------------------------------


def test_steps_and_cadence_match_the_synthetic_walk():
    window, truth = synth_walk()
    result = process_window(window)
    assert len(result.bouts) == 1 and result.rejected_bouts == 0
    assert abs(result.n_steps - truth["n_steps"]) <= 3
    assert abs(result.bouts[0].steps.cadence_spm - truth["cadence"]) < 1.0
    assert result.bouts[0].steps.step_time_cv < 0.05


@pytest.mark.parametrize("ratio", [1.0, 1.15, 0.9])
def test_thigh_phases_give_signed_asymmetry_and_double_support(ratio):
    window, truth = synth_walk(ipsi_ratio=ratio)
    bout = process_window(window).bouts[0]
    assert bout.asymmetry_method == "thigh_gyro_phases"
    assert bout.phases is not None and bout.phases.valid
    assert abs(bout.asymmetry_pct - truth["asymmetry_pct"]) < 4.0
    assert np.sign(round(bout.asymmetry_pct)) == np.sign(round(truth["asymmetry_pct"])) or ratio == 1.0
    assert abs(bout.phases.double_support_pct - truth["double_support_pct"]) < 5.0


@pytest.mark.parametrize("kw", [dict(), dict(cadence=125, step_len=0.75, height_m=1.62),
                                dict(cadence=90, step_len=0.55)])
def test_inverted_pendulum_recovers_step_length_and_speed(kw):
    window, truth = synth_walk(**kw)
    bout = process_window(window).bouts[0]
    assert bout.spatial is not None and bout.spatial.method == "inverted_pendulum"
    assert not bout.spatial.calibrated
    typical = bout.spatial.distance_m / len(bout.spatial.step_lengths)
    assert abs(typical - truth["step_len"]) / truth["step_len"] < 0.12
    assert abs(bout.spatial.speed_mps - truth["speed"]) / truth["speed"] < 0.12


def test_gps_distance_calibrates_the_pendulum():
    window, truth = synth_walk(duration_s=90.0)
    window.gps_distance_m = truth["speed"] * window.duration_s
    window.gps_accuracy_m = 5.0
    bout = process_window(window).bouts[0]
    assert bout.spatial.calibrated and bout.spatial.method == "inverted_pendulum+gps"
    assert abs(bout.spatial.speed_mps - truth["speed"]) / truth["speed"] < 0.05
    # a poor fix is ignored
    window.gps_accuracy_m = 40.0
    assert not process_window(window).bouts[0].spatial.calibrated


def test_stairs_from_the_barometer_need_steps_and_a_flight():
    window, truth = synth_walk(cadence=80, step_len=0.45, stairs=True)
    result = process_window(window)
    found = {(s.direction, round(s.speed_mps, 2)) for s in result.stairs}
    assert {d for d, _ in found} == {"up", "down"}
    for direction, speed in truth["stairs"]:
        got = next(s for s in result.stairs if s.direction == direction)
        assert abs(got.speed_mps - speed) < 0.06
        assert got.n_steps >= 6 and got.height_m >= 2.5
    # an elevator: the same altitude trace with no steps under it
    quiet = MotionWindow(started_at=window.started_at, fs=50.0,
                         accel=np.tile([0.0, -9.80665, 0.0], (3000, 1)) + np.random.default_rng(1).normal(0, 0.02, (3000, 3)),
                         altitude=window.altitude, height_cm=175)
    assert process_window(quiet).stairs == [] and process_window(quiet).bouts == []


def test_without_a_gyroscope_asymmetry_is_unsigned_and_double_support_absent():
    window, _ = synth_walk(with_gyro=False)
    bout = process_window(window).bouts[0]
    assert bout.phases is None and bout.asymmetry_method == "alternating_step_times"
    assert 0.0 <= bout.asymmetry_pct < 4.0
    rows = observations_for(window, process_window(window), "p", "America/New_York")
    assert str(M.DOUBLE_SUPPORT_PCT) not in {str(r.metric_type) for r in rows}


def test_gravity_is_estimated_when_the_phone_does_not_send_it():
    window, truth = synth_walk(with_gravity=False)
    result = process_window(window)
    assert result.gravity_source == "lowpass"
    assert abs(result.bouts[0].steps.cadence_spm - truth["cadence"]) < 1.0


def test_steadiness_ranks_a_brisk_regular_walk_above_a_slow_one():
    brisk = process_window(synth_walk()[0]).bouts[0].stability
    slow = process_window(synth_walk(cadence=80, step_len=0.45)[0]).bouts[0].stability
    assert brisk.index > slow.index
    assert brisk.level == "ok"
    assert set(brisk.features) == {"step_time_cv", "stride_regularity", "harmonic_ratio", "speed_mps"}


def test_a_lead_in_of_standing_is_not_walking():
    window, truth = synth_walk(duration_s=80.0, lead_in_s=20.0)
    result = process_window(window)
    assert len(result.bouts) == 1
    assert result.bouts[0].start_s >= 15.0
    assert abs(result.n_steps - truth["n_steps"]) <= 4


def test_rows_are_deterministic_idempotent_and_carry_provenance():
    window, _ = synth_walk(pocket_side="right")
    result = process_window(window)
    rows = observations_for(window, result, "p", "America/New_York")
    again = observations_for(window, process_window(window), "p", "America/New_York")
    assert [r.dedupe_key for r in rows] == [r.dedupe_key for r in again]
    assert {str(r.metric_type) for r in rows} == {
        "cadence", "walking_speed", "step_length", "walking_asymmetry_pct",
        "double_support_pct", "walking_steadiness",
    }
    for r in rows:
        assert str(r.source_provider) == "medpull"
        assert r.source_device_id == "medpull:imu:synthetic"
        assert r.value_json["version"] == "mobility-1"
    asym = next(r for r in rows if str(r.metric_type) == "walking_asymmetry_pct")
    assert asym.side == "right" and asym.value_json["signed"] is True
    assert asym.value_num >= 0 and "signed_value" in asym.value_json


# --- the active tests ------------------------------------------------------------


def _gravity(tilt_deg: float, n: int = 100, sd: float = 0.4, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.radians(tilt_deg + rng.normal(0.0, sd, n))
    return np.stack([np.zeros(n), -np.sin(t), -np.cos(t)], axis=1)


def test_range_of_motion_reads_the_full_arc_and_flags_an_unsteady_hold():
    flexion = range_of_motion("knee_flexion_supine", _gravity(1.0), _gravity(121.0))
    assert flexion.joint == "knee" and flexion.movement == "flexion"
    assert abs(flexion.angle_deg - 120.0) < 1.5 and flexion.steady
    deficit = range_of_motion("knee_extension_supine", _gravity(0.0), _gravity(7.0))
    assert abs(deficit.angle_deg - 7.0) < 1.0
    hyper = range_of_motion("knee_extension_supine", _gravity(0.0), _gravity(-4.0))
    assert abs(hyper.angle_deg + 4.0) < 1.0
    shaky = range_of_motion("shoulder_flexion_standing", _gravity(-89.0), _gravity(60.0, sd=6.0))
    assert not shaky.steady
    assert range_of_motion("nonsense", _gravity(0.0), _gravity(10.0)) is None


def test_six_minute_walk_method_precedence_and_fade():
    gps = six_minute_walk(360, steps=600, height_cm=170, gps_distance_m=402.0, gps_accuracy_m=6.0,
                          pedometer_distance_m=380.0, minute_steps=[105, 104, 102, 100, 98, 94])
    assert gps.method == "gps" and gps.distance_m == 402.0
    assert gps.cadence_spm == 100.0 and gps.fade_pct == pytest.approx(-10.5, abs=0.1)
    ped = six_minute_walk(360, steps=600, height_cm=170, gps_distance_m=402.0, gps_accuracy_m=50.0,
                          pedometer_distance_m=380.0)
    assert ped.method == "pedometer" and ped.distance_m == 380.0
    imu = six_minute_walk(360, steps=None, height_cm=None, imu_distance_m=371.5, imu_steps=590)
    assert imu.method == "imu_inverted_pendulum" and imu.steps == 590
    fallback = six_minute_walk(360, steps=600, height_cm=170)
    assert fallback.method == "steps_x_height" and fallback.distance_m == pytest.approx(423.3, abs=0.1)
    short = six_minute_walk(300, steps=500, height_cm=170)
    assert short.detail["scaled"] and short.distance_m == pytest.approx(500 * 0.415 * 1.7 * 1.2, abs=0.2)
    assert six_minute_walk(360, steps=None, height_cm=None) is None


# --- the stress index -----------------------------------------------------------


def test_stress_index_sits_at_fifty_on_baseline_and_rises_with_strain():
    rng = np.random.default_rng(3)
    days = list(range(-10, 21))
    hrv = pd.Series(45.0 + rng.normal(0, 4.0, len(days)), index=days)
    rhr = pd.Series(62.0 + rng.normal(0, 1.8, len(days)), index=days)
    rr = pd.Series(14.5 + rng.normal(0, 0.7, len(days)), index=days)
    hrv.loc[15:] -= 12.0   # HRV suppressed, resting rate up: the strain pattern
    rhr.loc[15:] += 6.0
    index = stress_index_series({"hrv_rmssd": hrv, "resting_hr": rhr, "respiratory_rate": rr})
    assert index is not None
    assert -10 not in index.index and -5 in index.index   # needs five baseline days first
    assert 40.0 <= index.loc[0:14].mean() <= 60.0
    assert index.loc[15:].mean() >= 75.0          # the flag band, on average
    assert (index.loc[15:] >= 62.5).all()         # never below the watch band
    assert index.max() <= 100.0 and index.min() >= 0.0


def test_stress_index_uses_sdnn_when_that_is_what_the_device_ships_and_needs_inputs():
    days = list(range(-8, 6))
    sdnn = pd.Series(50.0 + np.arange(len(days)) * 0.1, index=days)
    only = stress_index_series({"hrv_sdnn": sdnn})
    assert only is not None and len(only) > 0
    assert stress_index_series({}) is None
    assert stress_index_series({"steps": pd.Series([1.0, 2.0], index=[0, 1])}) is None


# --- the daily series prefers MedPull's own rows ---------------------------------


def test_daily_series_prefers_inhouse_rows_over_the_vendor_on_the_same_day(db):
    from app.connectors.base import CanonicalObservation
    from app.connectors.ingest import ingest_observations
    from app.engine.dataload import load_daily_series
    from app.models.enums import Granularity
    from app.models.patient import Patient

    patient = db.get(Patient, "steve")
    day = date.today() - timedelta(days=1)
    prior = load_daily_series(db, "steve", patient.surgery_date).get("walking_speed")
    idx = (day - patient.surgery_date).days
    rows = [
        CanonicalObservation("steve", P.APPLE, M.WALKING_SPEED, "m/s",
                             datetime.combine(day, datetime.min.time()),
                             datetime.combine(day, datetime.max.time().replace(microsecond=0)),
                             Granularity.DAILY_SUMMARY, value_num=1.0, source_device_id="test:apple"),
        CanonicalObservation("steve", P.MEDPULL, M.WALKING_SPEED, "m/s",
                             datetime.combine(day, datetime.min.time()) + timedelta(hours=9),
                             datetime.combine(day, datetime.min.time()) + timedelta(hours=9, minutes=3),
                             Granularity.INTERVAL, value_num=0.8, source_device_id="test:medpull"),
        CanonicalObservation("steve", P.MEDPULL, M.WALKING_SPEED, "m/s",
                             datetime.combine(day, datetime.min.time()) + timedelta(hours=15),
                             datetime.combine(day, datetime.min.time()) + timedelta(hours=15, minutes=3),
                             Granularity.INTERVAL, value_num=0.6, source_device_id="test:medpull"),
    ]
    try:
        ingest_observations(db, rows)
        series = load_daily_series(db, "steve", patient.surgery_date)["walking_speed"]
        assert series.loc[idx] == pytest.approx(0.7)      # the two MedPull bouts, not Apple's 1.0
    finally:
        db.execute(delete(Observation).where(Observation.patient_id == "steve",
                                             Observation.source_device_id.in_(["test:apple", "test:medpull"])))
        db.commit()
        after = load_daily_series(db, "steve", patient.surgery_date).get("walking_speed")
        assert (prior is None and after is None) or (prior is not None and after is not None and prior.equals(after))


# --- the API -----------------------------------------------------------------------


def _payload(window: MotionWindow, **extra) -> dict:
    body = {
        "started_at": window.started_at.isoformat(),
        "sample_rate_hz": window.fs,
        "accel": np.round(window.accel, 3).tolist(),
        "gyro": np.round(window.gyro, 3).tolist() if window.gyro is not None else None,
        "gravity": np.round(window.gravity, 3).tolist() if window.gravity is not None else None,
        "altitude": np.round(window.altitude, 2).tolist() if window.altitude is not None else None,
        "pocket_side": window.pocket_side,
        "context": window.context,
    }
    body.update(extra)
    return body


def _forget_medpull_rows(db, patient_id: str = "steve") -> None:
    db.execute(delete(Observation).where(Observation.patient_id == patient_id,
                                         Observation.source_provider == str(P.MEDPULL)))
    db.commit()


def test_motion_upload_computes_inhouse_rows_and_is_idempotent(client, db):
    headers, _ = _enroll(client)
    window, truth = synth_walk(duration_s=75.0, stairs=True, cadence=90, step_len=0.55)
    window.started_at = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=10)
    try:
        resp = client.post("/api/mobile/observations/motion", headers=headers, json={
            "windows": [_payload(window)], "height_cm": 175, "device_model": "iPhone 17",
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["version"] == "mobility-1" and body["ingested"] > 0
        summary = body["windows"][0]
        assert summary["bouts"] == 1 and abs(summary["cadence_spm"] - 90) < 1.5
        assert summary["walking_speed_mps"] and summary["double_support_pct"]
        assert {s["direction"] for s in summary["stairs"]} == {"up", "down"}
        rows = db.scalars(select(Observation).where(
            Observation.patient_id == "steve", Observation.source_provider == "medpull")).all()
        kinds = {str(r.metric_type) for r in rows}
        assert {"walking_speed", "step_length", "cadence", "walking_asymmetry_pct",
                "double_support_pct", "walking_steadiness", "stair_speed_up",
                "stair_speed_down", "exercise_session"} <= kinds
        session = next(r for r in rows if str(r.metric_type) == "exercise_session")
        assert session.value_json["kind"] == "guided_walk" and session.value_json["steps"] > 40
        assert all(r.source_device_id.startswith("medpull:imu:iPhone 17") for r in rows)
        # the retry lands on the same rows
        again = client.post("/api/mobile/observations/motion", headers=headers, json={
            "windows": [_payload(window)], "height_cm": 175, "device_model": "iPhone 17",
        }).json()
        assert again["ingested"] == 0 and again["updated"] == 0
        assert again["duplicates"] == body["ingested"]
        # and the clinician's dashboard lists the in-house signals
        metrics = client.get("/api/patients/steve/metrics").json()["metrics"]
        keys = {m["metric_key"] for m in metrics}
        assert {"cadence", "step_length", "double_support_pct", "walking_steadiness",
                "stair_speed_up", "stair_speed_down"} <= keys
        raw = client.get("/api/patients/steve/raw-data", params={"days": 7}).json()
        cadence_meta = next(m for m in raw["metric_types"] if m["metric_type"] == "cadence")
        assert "medpull" in cadence_meta["source_providers"]
    finally:
        _forget_medpull_rows(db)


def test_motion_upload_rejects_malformed_samples(client):
    headers, _ = _enroll(client)
    window, _ = synth_walk(duration_s=12.0)
    bad = _payload(window)
    bad["gyro"] = bad["gyro"][:-5]
    resp = client.post("/api/mobile/observations/motion", headers=headers,
                       json={"windows": [bad], "height_cm": 175})
    assert resp.status_code == 422
    bad = _payload(window)
    bad["accel"] = [[1.0, 2.0]] * len(bad["accel"])
    resp = client.post("/api/mobile/observations/motion", headers=headers,
                       json={"windows": [bad], "height_cm": 175})
    assert resp.status_code == 422
    assert client.post("/api/mobile/observations/motion", json={"windows": []}).status_code in (401, 422)


def test_six_minute_walk_and_range_of_motion_tests_store_their_rows(client, db):
    headers, _ = _enroll(client)
    start = datetime.combine(date.today(), datetime.min.time()) + timedelta(hours=11)
    try:
        resp = client.post("/api/mobile/tests/six-minute-walk", headers=headers, json={
            "started_at": start.isoformat(), "duration_s": 360, "steps": 610,
            "pedometer_distance_m": 405.5, "height_cm": 172, "device_model": "iPhone 17",
            "minute_steps": [108, 106, 104, 101, 98, 93],
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["distance_m"] == 405.5 and body["method"] == "pedometer"
        assert body["fade_pct"] == pytest.approx(-13.9, abs=0.1) and body["ingested"] == 1
        row = db.scalar(select(Observation).where(Observation.patient_id == "steve",
                                                  Observation.metric_type == "six_min_walk",
                                                  Observation.source_provider == "medpull"))
        assert row.value_num == 405.5 and row.value_json["method"] == "pedometer"
        assert str(row.granularity) == "session"

        resp = client.post("/api/mobile/tests/range-of-motion", headers=headers, json={
            "recorded_at": start.isoformat(), "protocol": "knee_flexion_supine", "side": "left",
            "reference": _gravity(2.0).round(4).tolist(), "movement": _gravity(97.0).round(4).tolist(),
        })
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["joint"] == "knee" and body["movement"] == "flexion" and body["side"] == "left"
        assert abs(body["angle_deg"] - 95.0) < 1.5 and body["steady"] and body["ingested"] == 1
        row = db.scalar(select(Observation).where(Observation.patient_id == "steve",
                                                  Observation.metric_type == "rom_flexion"))
        assert row.side == "left" and row.body_site == "knee"
        assert row.value_json["protocol"] == "knee_flexion_supine"

        resp = client.post("/api/mobile/tests/range-of-motion", headers=headers, json={
            "recorded_at": start.isoformat(), "protocol": "elbow_curl", "side": "left",
            "reference": _gravity(0.0).tolist(), "movement": _gravity(30.0).tolist(),
        })
        assert resp.status_code == 422
        resp = client.post("/api/mobile/tests/six-minute-walk", headers=headers, json={
            "started_at": start.isoformat(), "duration_s": 360,
        })
        assert resp.status_code == 422
    finally:
        _forget_medpull_rows(db)
