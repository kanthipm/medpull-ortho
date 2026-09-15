"""Deterministic per-metric daily series generators.

Every value is drawn from numpy default_rng seeded by (patient_id, metric), so
re-seeding produces byte-identical data. Pre-op days (-10..-1) establish each
patient's personal baseline; post-op days follow the procedure's expected
recovery curve (app.engine.curves), then the patient's ScenarioSpec perturbs
the signals the intelligence engine is meant to catch.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta
from typing import Any

import numpy as np

from app.connectors.base import CanonicalObservation
from app.connectors.capabilities import CAPABILITIES
from app.connectors.mock import UNITS, daily_observation
from app.engine.curves import curve_mid, recovery_progress
from app.models.enums import Granularity
from app.models.enums import MetricType as M
from app.models.enums import SourceProvider as P
from app.seed.patients import PatientSpec, get_spec
from app.seed.scenarios import ScenarioSpec, get_scenario

PRE_OP_DAYS = 10

# --- care-metric seed extensions (engine/care reads these) -------------------
# Extra scenario pain on top of the recovery-shaped baseline: linda's night
# pain (shoulder), sofia's ankle, robert's back. aisha's is load-driven — see
# LOAD_PAIN_PER_1K below — so her symptom–load slope has something to find.
SCENARIO_PAIN: dict[str, float] = {"linda": 1.8, "sofia": 0.8, "robert": 0.3}
# aisha: extra pain per 1,000 steps walked above her plan's band ceiling the
# day before — the days she overdoes it cost her the next morning. Her daily
# steps vary only ±4 % and pain is logged in whole points, so the response
# has to be steep to be measurable at all: 5 points per 1,000 steps over a
# 3,300-step ceiling means a big day (+300) costs her about a point and a
# half, and an ordinary plateau day (~3,500) a little under one.
AISHA_BAND_HIGH = 3300.0
LOAD_PAIN_PER_1K = 5.0
AM_LOG_FRACTION = 0.6
# Stairs re-enter the routine once a patient has recovered a fifth of the
# range: after hip/knee replacement stair training is a discharge criterion,
# so waiting for 0.3 would keep a plateaued patient (aisha freezes at 0.25)
# off stairs for the whole demo.
STAIRS_FROM_PROGRESS = 0.2
GUIDED_WALK_EVERY = 3
GUIDED_WALK_FROM_DAY = 5
HOURLY_DAYS = 14
SIT_TO_STAND_PATIENTS = {"aisha", "james"}
# Two-peak diurnal step profile (mid-morning and late afternoon), hours 6-22.
_HOURS = np.arange(24)
_PROFILE = np.where(
    (_HOURS >= 6) & (_HOURS <= 22),
    np.exp(-((_HOURS - 10) ** 2) / 8.0) + 0.9 * np.exp(-((_HOURS - 17) ** 2) / 12.5),
    0.0,
)

# Metrics the generator knows how to produce (subset of MetricType).
VITALS = [M.RESTING_HR, M.HRV_RMSSD, M.SLEEP_DURATION, M.SKIN_TEMP, M.SPO2, M.RESPIRATORY_RATE]
FUNCTIONAL = [M.STEPS, M.WALKING_SPEED]
GAIT_EXTRA = [M.WALKING_ASYMMETRY_PCT, M.DOUBLE_SUPPORT_PCT]
DERIVED = [M.ACTIVE_ENERGY, M.CALORIES, M.SLEEP_STAGES]

NOISE_SD: dict[M, float] = {
    M.STEPS: 0.04,          # fraction of personal base
    M.WALKING_SPEED: 0.035,  # fraction of personal base
    M.RESTING_HR: 1.1,
    M.HRV_RMSSD: 0.05,      # fraction of personal base
    M.SLEEP_DURATION: 0.35,
    M.SKIN_TEMP: 0.10,
    M.SPO2: 0.4,
    M.RESPIRATORY_RATE: 0.5,
    M.WALKING_ASYMMETRY_PCT: 0.7,
    M.DOUBLE_SUPPORT_PCT: 0.8,
}


def _rng(patient_id: str, salt: str) -> np.random.Generator:
    digest = hashlib.sha256(f"{patient_id}:{salt}".encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def personal_baselines(spec: PatientSpec) -> dict[M, float]:
    """Stable per-patient physiological baselines (their pre-surgery normal)."""
    r = _rng(spec.id, "baseline")
    age_f = (spec.age - 20) / 60  # 0 young .. ~1 old
    return {
        M.STEPS: float(r.uniform(6500, 9500) - 2200 * age_f),
        M.WALKING_SPEED: float(r.uniform(1.15, 1.35) - 0.25 * age_f),
        M.RESTING_HR: float(r.uniform(56, 66) + 5 * age_f),
        M.HRV_RMSSD: float(r.uniform(45, 65) - 22 * age_f),
        M.SLEEP_DURATION: float(r.uniform(6.7, 7.8)),
        M.SKIN_TEMP: float(r.uniform(36.35, 36.65)),
        M.SPO2: float(r.uniform(96.5, 98.2)),
        M.RESPIRATORY_RATE: float(r.uniform(13.0, 15.5)),
        M.WALKING_ASYMMETRY_PCT: float(r.uniform(3.5, 5.0)),
        M.DOUBLE_SUPPORT_PCT: float(r.uniform(24.0, 27.0)),
    }


def _post_op_transient(metric: M, day: int) -> tuple[float, float]:
    """(additive, multiplicative) early post-surgical perturbation, decaying."""
    if day < 0:
        return (0.0, 1.0)
    decay2 = float(np.exp(-day / 2.0))
    decay3 = float(np.exp(-day / 3.0))
    match metric:
        case M.RESTING_HR:
            return (3.0 * decay2, 1.0)
        case M.SKIN_TEMP:
            return (0.15 * decay2, 1.0)
        case M.RESPIRATORY_RATE:
            return (0.8 * decay2, 1.0)
        case M.SPO2:
            return (-0.4 * decay2, 1.0)
        case M.HRV_RMSSD:
            return (0.0, 1.0 - 0.12 * decay3)
        case M.SLEEP_DURATION:
            return (0.0, 1.0 - 0.08 * decay3)
    return (0.0, 1.0)


def _scenario_effect(scenario: ScenarioSpec, metric: M, day: int) -> tuple[float, float]:
    add, mult = 0.0, 1.0
    for ramp in scenario.ramps:
        if ramp.metric is not metric:
            continue
        f = ramp.factor(day)
        add += ramp.add * f
        mult *= 1.0 + (ramp.mult_to - 1.0) * f
    return (add, mult)


def _effective_day(scenario: ScenarioSpec, day: int) -> int:
    if day >= 0 and scenario.plateau_after is not None:
        return min(day, scenario.plateau_after)
    return day


def _value(
    spec: PatientSpec,
    scenario: ScenarioSpec,
    base: dict[M, float],
    metric: M,
    day: int,
    noise: float,
) -> float:
    """One raw daily value for `metric` on post-op day `day` (negative = pre-op)."""
    eff = _effective_day(scenario, day)
    s_add, s_mult = _scenario_effect(scenario, metric, day)

    if metric in (M.STEPS, M.WALKING_SPEED):
        level = base[metric]
        if day >= 0:
            level *= float(curve_mid(spec.procedure, eff)) * scenario.track
        level *= s_mult
        level += s_add
        return max(0.0, level * (1.0 + noise * NOISE_SD[metric]))

    if metric is M.WALKING_ASYMMETRY_PCT:
        if day < 0:
            v = base[metric]
        else:
            progress = recovery_progress(spec.procedure, eff)
            v = 4.0 + 11.0 * (1.0 - progress) ** 1.5
        return max(1.0, v * s_mult + s_add + noise * NOISE_SD[metric])

    if metric is M.DOUBLE_SUPPORT_PCT:
        if day < 0:
            v = base[metric]
        else:
            progress = recovery_progress(spec.procedure, eff)
            v = base[metric] + 7.0 * (1.0 - progress)
        return max(15.0, v * s_mult + s_add + noise * NOISE_SD[metric])

    # vitals
    t_add, t_mult = _post_op_transient(metric, day)
    v = base[metric] * t_mult * s_mult + t_add + s_add
    sd = NOISE_SD[metric]
    if metric is M.HRV_RMSSD:
        v *= 1.0 + noise * sd
    else:
        v += noise * sd
    if metric is M.SPO2:
        v = min(v, 99.5)
    return max(0.0, v)


def generate_patient_observations(
    spec: PatientSpec, scenario: ScenarioSpec, today: date
) -> list[CanonicalObservation]:
    surgery = today - timedelta(days=spec.postop_day)
    supported = set(CAPABILITIES.get(spec.provider, []))

    # The mock generates the canonical series the engine analyzes. A provider
    # whose real capability is the variant statistic (Apple: SDNN, delta skin
    # temp) still measures the underlying signal — in production normalize()
    # would land it in its own metric type; the demo keeps emitting the
    # canonical series so the pinned golden tiers stay meaningful.
    equivalents: dict[M, set[M]] = {
        M.SKIN_TEMP: {M.SKIN_TEMP, M.SKIN_TEMP_DELTA},
        M.HRV_RMSSD: {M.HRV_RMSSD, M.HRV_SDNN},
    }
    metrics = [
        m for m in VITALS + FUNCTIONAL + GAIT_EXTRA
        if supported & equivalents.get(m, {m})
    ]
    days = list(range(-PRE_OP_DAYS, spec.postop_day + 1))

    # Deterministic dropout: whole days where the device wasn't worn/synced.
    drop_rng = _rng(spec.id, "dropout")
    dropped = {
        d for d in days if d >= 0 and drop_rng.random() < scenario.dropout_frac
    }
    # Never drop today for patients who have data at all — the demo needs a
    # current reading; priya stays sparse either way.
    if scenario.dropout_frac < 0.5:
        dropped.discard(spec.postop_day)

    out: list[CanonicalObservation] = []
    noise_by_metric = {m: _rng(spec.id, f"noise:{m}").standard_normal(len(days)) for m in metrics}
    base = personal_baselines(spec)
    awake_noise = _rng(spec.id, "noise:awake").standard_normal(len(days))
    values_by_day: dict[int, dict[M, float]] = {}

    for i, d in enumerate(days):
        if d in dropped:
            continue
        day_date = surgery + timedelta(days=d)
        day_values: dict[M, float] = {}
        for m in metrics:
            v = _value(spec, scenario, base, m, d, float(noise_by_metric[m][i]))
            day_values[m] = v
            out.append(daily_observation(spec.id, spec.provider, m, day_date, v))
        values_by_day[d] = day_values

        # cheap derived metrics for realism / integration counts
        if M.STEPS in day_values and M.ACTIVE_ENERGY in supported:
            active = day_values[M.STEPS] * 0.045
            out.append(daily_observation(spec.id, spec.provider, M.ACTIVE_ENERGY, day_date, active))
            if M.CALORIES in supported:
                out.append(
                    daily_observation(spec.id, spec.provider, M.CALORIES, day_date, 1450 + active)
                )
        if M.SLEEP_DURATION in day_values and M.SLEEP_STAGES in supported:
            total = day_values[M.SLEEP_DURATION]
            stages = daily_observation(spec.id, spec.provider, M.SLEEP_STAGES, day_date, total)
            # The awake fraction answers the sleep ramp: a night that the
            # scenario shortens is also a night that fragments (linda's
            # shoulder). The total is untouched, so value_num is byte-identical.
            sleep_mult = _scenario_effect(scenario, M.SLEEP_DURATION, d)[1]
            awake_frac = 0.08 + 0.12 * (1.0 - sleep_mult) + float(awake_noise[i]) * 0.01
            awake_frac = min(max(awake_frac, 0.02), 0.4)
            stages.value_json = {
                "deep": round(total * 0.20, 2),
                "rem": round(total * 0.22, 2),
                "light": round(total * (0.50 - (awake_frac - 0.08)), 2),
                "awake": round(total * awake_frac, 2),
            }
            out.append(stages)

    out.extend(_care_extensions(spec, scenario, base, supported, values_by_day, days, surgery))
    return out


def _progress(spec: PatientSpec, scenario: ScenarioSpec, day: int) -> float:
    return recovery_progress(spec.procedure, _effective_day(scenario, day))


def _observation(
    patient_id: str,
    provider: P,
    metric: M,
    start: datetime,
    end: datetime,
    value: float,
    granularity: Granularity,
    value_json: dict[str, Any] | None = None,
    patient_reported: bool = False,
    external_id: str | None = None,
) -> CanonicalObservation:
    return CanonicalObservation(
        patient_id=patient_id,
        source_provider=provider,
        metric_type=metric,
        unit=UNITS[metric],
        value_num=round(float(value), 3),
        value_json=value_json,
        start_time=start,
        end_time=end,
        granularity=granularity,
        is_patient_reported=patient_reported,
        external_id=external_id,
    )


def _care_extensions(
    spec: PatientSpec,
    scenario: ScenarioSpec,
    base: dict[M, float],
    supported: set[M],
    values_by_day: dict[int, dict[M, float]],
    days: list[int],
    surgery: date,
) -> list[CanonicalObservation]:
    """The rows the care metrics read: pain logs, flights and stair tempo,
    guided walks with per-minute detail, sit-to-stand counts, hourly step and
    heart-rate buckets, and the Withings scale/cuff. Everything is additive —
    the daily series the risk tier scores are not touched (a day with a daily
    summary keeps it; engine/dataload's additive rule ignores the hourly
    buckets on such days) — and every draw comes from its own seeded stream.
    """
    out: list[CanonicalObservation] = []
    post_days = [d for d in days if d >= 0]
    present = set(values_by_day)
    n = len(days)
    offset = -days[0]  # index of day 0 in the noise streams

    # --- pain logs: PM every day from day 1, AM on ~60% of days -------------
    pain_noise = _rng(spec.id, "noise:pain").standard_normal(n)
    am_noise = _rng(spec.id, "noise:pain_am").standard_normal(n)
    am_roll = _rng(spec.id, "pain:am_days").random(n)
    sparse = scenario.dropout_frac >= 0.5  # priya logs only on days the device reports
    for d in post_days:
        if d < 1 or (sparse and d not in present):
            continue
        i = d + offset
        progress = _progress(spec, scenario, d)
        extra = SCENARIO_PAIN.get(spec.id, 0.0)
        if spec.id == "aisha":
            prev_steps = values_by_day.get(d - 1, {}).get(M.STEPS)
            if prev_steps is not None:
                extra += LOAD_PAIN_PER_1K * max(0.0, prev_steps - AISHA_BAND_HIGH) / 1000.0
        pm = 7.5 * (1.0 - progress) ** 1.2 + extra + float(pain_noise[i]) * 0.6
        pm = min(max(pm, 0.0), 10.0)
        day_date = surgery + timedelta(days=d)
        out.append(_observation(
            spec.id, P.PATIENT_REPORTED, M.PAIN_NRS,
            datetime.combine(day_date, time(20, 0)), datetime.combine(day_date, time(20, 0)),
            round(pm), Granularity.INSTANT, {"time_of_day": "pm"}, patient_reported=True,
        ))
        if am_roll[i] < AM_LOG_FRACTION:
            am = min(max(pm - 0.8 + float(am_noise[i]) * 0.4, 0.0), 10.0)
            out.append(_observation(
                spec.id, P.PATIENT_REPORTED, M.PAIN_NRS,
                datetime.combine(day_date, time(8, 0)), datetime.combine(day_date, time(8, 0)),
                round(am), Granularity.INSTANT, {"time_of_day": "am"}, patient_reported=True,
            ))

    # --- flights climbed + ascent tempo (Apple / mock) ------------------------
    if M.FLIGHTS_CLIMBED in supported:
        flight_noise = _rng(spec.id, "noise:flights").standard_normal(n)
        tempo_noise = _rng(spec.id, "noise:stair_tempo").standard_normal(n)
        for d in post_days:
            if d not in present:
                continue
            progress = _progress(spec, scenario, d)
            if progress < STAIRS_FROM_PROGRESS:
                continue
            i = d + offset
            flights = max(0, int(1.0 + 6.0 * progress + float(flight_noise[i]) * 0.3))
            day_date = surgery + timedelta(days=d)
            out.append(daily_observation(spec.id, spec.provider, M.FLIGHTS_CLIMBED, day_date, flights))
            if flights >= 1 and M.STAIR_SPEED_UP in supported:
                tempo = max(0.1, 0.3 + 0.5 * progress + float(tempo_noise[i]) * 0.03)
                out.append(daily_observation(spec.id, spec.provider, M.STAIR_SPEED_UP, day_date, tempo))

    # --- guided walks with per-minute cadence / HR / speed --------------------
    if M.EXERCISE_SESSION in supported:
        walk_rng = _rng(spec.id, "noise:guided_walk")
        for d in post_days:
            if d < GUIDED_WALK_FROM_DAY or (d - GUIDED_WALK_FROM_DAY) % GUIDED_WALK_EVERY:
                continue
            if d not in present:
                continue
            progress = _progress(spec, scenario, d)
            minutes = 4 + int(8.0 * progress)
            c0 = 72.0 + 44.0 * progress
            fade = 0.035 * (1.0 - progress) + 0.004
            step_len = 0.55 + 0.2 * progress
            rhr = values_by_day[d].get(M.RESTING_HR, base[M.RESTING_HR])
            hr_noise = walk_rng.standard_normal(minutes)
            cadence = [round(c0 * (1.0 - fade * m), 1) for m in range(minutes)]
            hr = [round(rhr + 22.0 + 28.0 * (1.0 - progress) + 4.0 * m / minutes
                        + float(hr_noise[m]) * 2.0, 1) for m in range(minutes)]
            speed = [round(c * step_len / 60.0, 3) for c in cadence]
            day_date = surgery + timedelta(days=d)
            start = datetime.combine(day_date, time(10, 0))
            out.append(_observation(
                spec.id, spec.provider, M.EXERCISE_SESSION, start,
                start + timedelta(minutes=minutes), minutes, Granularity.SESSION,
                {"kind": "guided_walk", "minutes": minutes, "cadence_spm": cadence,
                 "hr_bpm": hr, "speed_mps": speed, "steps": int(round(sum(cadence)))},
            ))

    # --- sit-to-stand self-reports ----------------------------------------------
    if spec.id in SIT_TO_STAND_PATIENTS:
        sts_noise = _rng(spec.id, "noise:sit_to_stand").standard_normal(n)
        for d in post_days:
            if d < 1:
                continue
            progress = _progress(spec, scenario, d)
            count = max(0, int(round(6.0 + 8.0 * progress + float(sts_noise[d + offset]))))
            row = daily_observation(
                spec.id, P.PATIENT_REPORTED, M.SIT_TO_STAND, surgery + timedelta(days=d), count,
            )
            row.value_json = {"source": "self_report"}
            row.is_patient_reported = True
            out.append(row)

    # --- hourly steps + heart-rate samples, last 14 days (Apple / mock) ----------
    if spec.provider in (P.APPLE, P.MOCK) and M.HR_SAMPLE in supported:
        hourly_rng = _rng(spec.id, "noise:hourly")
        last_days = [d for d in post_days if d > spec.postop_day - HOURLY_DAYS and d in present]
        for d in last_days:
            total = values_by_day[d].get(M.STEPS)
            if total is None:
                continue
            weights = _PROFILE * np.clip(1.0 + 0.25 * hourly_rng.standard_normal(24), 0.05, None)
            weights = np.where(_PROFILE > 0, weights, 0.0)
            weights /= weights.sum()
            target = int(round(total))
            raw = weights * target
            buckets = np.floor(raw).astype(int)
            remainder = target - int(buckets.sum())
            for h in np.argsort(-(raw - buckets))[:remainder]:
                buckets[h] += 1
            peak = max(int(buckets.max()), 1)
            rhr = values_by_day[d].get(M.RESTING_HR, base[M.RESTING_HR])
            hr_noise = hourly_rng.standard_normal(24)
            day_date = surgery + timedelta(days=d)
            for h in range(24):
                start = datetime.combine(day_date, time(h, 0))
                end = start + timedelta(hours=1)
                ext = f"seed:hourly:{day_date.isoformat()}:{h}"
                out.append(_observation(
                    spec.id, spec.provider, M.STEPS, start, end, int(buckets[h]),
                    Granularity.INTERVAL, external_id=ext,
                ))
                hr = rhr + 8.0 + 18.0 * (buckets[h] / peak) + float(hr_noise[h]) * 3.0
                out.append(_observation(
                    spec.id, spec.provider, M.HR_SAMPLE, start, end, round(hr, 1),
                    Granularity.INTERVAL, external_id=ext,
                ))

    # --- Withings scale + cuff (priya) --------------------------------------------
    if spec.provider is P.WITHINGS and M.BODY_WEIGHT in supported:
        weight_rng = _rng(spec.id, "baseline:weight")
        weight_base = float(weight_rng.uniform(60.0, 90.0))
        weight_noise = _rng(spec.id, "noise:weight").standard_normal(n)
        bp_noise = _rng(spec.id, "noise:bp").standard_normal((n, 2))
        for d in days:
            i = d + offset
            day_date = surgery + timedelta(days=d)
            out.append(daily_observation(
                spec.id, spec.provider, M.BODY_WEIGHT, day_date,
                weight_base + float(weight_noise[i]) * 0.4,
            ))
            if d % 2 == 0:
                out.append(daily_observation(
                    spec.id, spec.provider, M.BLOOD_PRESSURE_SYSTOLIC, day_date,
                    128.0 + float(bp_noise[i, 0]) * 6.0,
                ))
                out.append(daily_observation(
                    spec.id, spec.provider, M.BLOOD_PRESSURE_DIASTOLIC, day_date,
                    82.0 + float(bp_noise[i, 1]) * 4.0,
                ))
    return out


def generate_range(
    patient_id: str,
    start: date,
    end: date,
    metric_types: list[M] | None = None,
) -> list[CanonicalObservation]:
    """MockConnector.fetch_historical: regenerate this patient's series for a
    date window (used for back-fill demos). Unknown patients get nothing."""
    spec = get_spec(patient_id)
    if spec is None:
        return []
    today = date.today()
    all_obs = generate_patient_observations(spec, get_scenario(patient_id), today)
    return [
        o
        for o in all_obs
        if start <= o.start_time.date() <= end
        and (metric_types is None or o.metric_type in metric_types)
    ]
