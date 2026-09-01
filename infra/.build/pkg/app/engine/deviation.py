"""Deviation detection: EWMA control charts + CUSUM drift, per metric.

Two families, judged differently:
- Vitals (RHR, HRV, temp, SpO2, RR, sleep) are compared to the patient's own
  pre-op baseline — surgery shouldn't move them for long.
- Functional metrics (steps, walking speed) are compared to the EXPECTED
  recovery curve for the procedure, not the pre-op baseline — every post-op
  patient walks less than baseline, and that is not a finding.

Both feed standardized deviations into the same EWMA/CUSUM machinery, and only
the clinically adverse direction can raise a flag.
"""

from math import sqrt

import pandas as pd

from app.engine.baseline import compute_baseline
from app.engine.curves import curve_mid
from app.engine.types import Baseline, DeviationResult
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType

EWMA_LAMBDA = 0.3
EWMA_L = 2.66
CUSUM_K = 0.5
CUSUM_H = 5.0
# CUSUM looks at recent drift only — accumulating since surgery would latch on
# noise over long recoveries.
CUSUM_WINDOW = 14
# Days 0-1 after surgery are an expected physiological perturbation, not a
# finding — deviation scoring starts at day 2.
SKIP_EARLY_DAYS = 2
# Natural day-to-day variability of the (actual / expected) ratio for
# functional metrics, in ratio units.
FUNCTIONAL_RATIO_SD = 0.10

# Direction that is clinically adverse (raises flags). Gait asymmetry and
# double-support are deliberately absent: they are HIGH after every surgery
# and improve along recovery, so baseline control charts would flag every
# patient — they get an absolute-threshold rule in risk.py instead.
ADVERSE_UP = {M.RESTING_HR, M.SKIN_TEMP, M.RESPIRATORY_RATE}
ADVERSE_DOWN = {M.HRV_RMSSD, M.STEPS, M.SLEEP_DURATION, M.SPO2, M.WALKING_SPEED}

FUNCTIONAL = {M.STEPS, M.WALKING_SPEED}


def standardized_deviations(
    metric: M,
    series: pd.Series,
    baseline: Baseline,
    procedure: ProcedureType,
) -> pd.Series:
    """Per-day z-scores for the post-op window (skipping the expected
    immediate post-surgical perturbation)."""
    post = series[series.index >= SKIP_EARLY_DAYS]
    if metric in FUNCTIONAL:
        expected = pd.Series(
            [float(curve_mid(procedure, int(d))) for d in post.index], index=post.index
        )
        ratio = (post / max(baseline.mean, 1e-6)) / expected
        return (ratio - 1.0) / FUNCTIONAL_RATIO_SD
    return (post - baseline.mean) / baseline.sd


def _adverse(metric: M, direction: str) -> bool:
    return (direction == "up" and metric in ADVERSE_UP) or (
        direction == "down" and metric in ADVERSE_DOWN
    )


def ewma_cusum(metric: M, z: pd.Series) -> DeviationResult:
    """Run both detectors over a standardized post-op series."""
    if len(z) == 0:
        return DeviationResult(
            metric_type=str(metric), flagged=False, direction="none",
            latest_z=0.0, raw_z=0.0, consecutive_out=0, drifting=False,
        )

    # EWMA of z-scores; control limit scales by sqrt(lambda / (2 - lambda)).
    limit = EWMA_L * sqrt(EWMA_LAMBDA / (2 - EWMA_LAMBDA))
    ewma_vals: list[float] = []
    e = 0.0
    for value in z:
        e = EWMA_LAMBDA * float(value) + (1 - EWMA_LAMBDA) * e
        ewma_vals.append(e)
    ewma = pd.Series(ewma_vals, index=z.index)

    out_of_control = ewma.abs() > limit
    # consecutive out-of-control days ending at the latest day
    consecutive = 0
    for flag in reversed(out_of_control.tolist()):
        if not flag:
            break
        consecutive += 1

    latest = float(ewma.iloc[-1])
    direction = "up" if latest > 0 else "down" if latest < 0 else "none"
    recent_out = int(out_of_control.iloc[-5:].sum())
    flagged = consecutive >= 2 and recent_out >= 2 and _adverse(metric, direction)

    # One-sided CUSUM in the adverse direction, over the recent window only;
    # the alarm reflects the CURRENT accumulated drift, not a latched past one.
    drift_sign = 1.0 if metric in ADVERSE_UP else -1.0
    c = 0.0
    for value in z.iloc[-CUSUM_WINDOW:]:
        c = max(0.0, c + drift_sign * float(value) - CUSUM_K)
    drifting = c >= CUSUM_H and _adverse(metric, "up" if drift_sign > 0 else "down")

    return DeviationResult(
        metric_type=str(metric),
        flagged=bool(flagged),
        direction=direction,
        latest_z=round(latest, 2),
        raw_z=round(float(z.iloc[-1]), 2),
        consecutive_out=int(consecutive),
        drifting=bool(drifting),
        series_z=[round(float(v), 2) for v in ewma_vals[-14:]],
    )


def analyze_metric(
    metric: M,
    series: pd.Series,
    procedure: ProcedureType,
) -> tuple[Baseline, DeviationResult] | None:
    baseline = compute_baseline(str(metric), series)
    if baseline is None:
        return None
    z = standardized_deviations(metric, series, baseline, procedure)
    return baseline, ewma_cusum(metric, z)
