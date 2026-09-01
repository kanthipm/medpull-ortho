"""Deterministic per-metric daily series generators.

Every value is drawn from numpy default_rng seeded by (patient_id, metric), so
re-seeding produces byte-identical data. Pre-op days (-10..-1) establish each
patient's personal baseline; post-op days follow the procedure's expected
recovery curve (app.engine.curves), then the patient's ScenarioSpec perturbs
the signals the intelligence engine is meant to catch.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

import numpy as np

from app.connectors.base import CanonicalObservation
from app.connectors.capabilities import CAPABILITIES
from app.connectors.mock import daily_observation
from app.engine.curves import curve_mid, recovery_progress
from app.models.enums import MetricType as M
from app.seed.patients import PatientSpec, get_spec
from app.seed.scenarios import ScenarioSpec, get_scenario

PRE_OP_DAYS = 10

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

    for i, d in enumerate(days):
        if d in dropped:
            continue
        day_date = surgery + timedelta(days=d)
        day_values: dict[M, float] = {}
        for m in metrics:
            v = _value(spec, scenario, base, m, d, float(noise_by_metric[m][i]))
            day_values[m] = v
            out.append(daily_observation(spec.id, spec.provider, m, day_date, v))

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
            stages.value_json = {
                "deep": round(total * 0.20, 2),
                "rem": round(total * 0.22, 2),
                "light": round(total * 0.50, 2),
                "awake": round(total * 0.08, 2),
            }
            out.append(stages)

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
