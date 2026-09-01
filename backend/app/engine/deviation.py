"""Deviation detection: EWMA control charts + CUSUM drift, per metric.

Two families, judged differently:
- Vitals (RHR, HRV, temp, SpO2, RR, sleep) are compared to the patient's own
  pre-op baseline — surgery shouldn't move them for long.
- Functional metrics (steps, walking speed) are compared to the EXPECTED
  recovery curve for the procedure, not the pre-op baseline — every post-op
  patient walks less than baseline, and that is not a finding.

Both feed standardized deviations into the same EWMA/CUSUM machinery, and only
the clinically adverse direction can raise a flag.

The functional comparison comes in two strengths, and which one was used
travels with the result (DeviationResult.reference) so nothing downstream
overstates it:

* With a PRE-OP baseline the curve comparison is absolute — the curves are
  fractions of pre-op capacity, so "44% below expected for day 12" means
  exactly that.
* Without one, the same curve is used for its SHAPE only. Dividing the
  expected curve by its own level on the anchor days cancels the pre-op unit
  out, which leaves a scale-free question the data can still answer: has this
  patient progressed the way the curve says a patient at their starting point
  progresses? That is weaker than a pre-op comparison and is never phrased as
  one — but it is the difference between seeing an activity collapse and
  filing it under "nothing to report", which is what leaving the series
  unscored amounted to.

Every result records the day it last saw a reading, because a metric that has
gone dark must not keep raising findings from old numbers.
"""

from math import sqrt

import pandas as pd

from app.engine.baseline import SKIP_EARLY_DAYS, compute_baseline
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
# A reading is current evidence about today while it is at most this many days
# behind the current post-op day; past that the metric is stale. One window for
# the whole engine — the risk header and the metric cards must never disagree
# about whether a signal is still reporting.
RECENCY_WINDOW_DAYS = 5
# Natural day-to-day variability of the (actual / expected) ratio for
# functional metrics, in ratio units.
FUNCTIONAL_RATIO_SD = 0.10
# The anchored comparison carries the noise of the three-day anchor mean on
# top of the day's own, so its band is wider: sqrt(0.10^2 + (0.10/sqrt(3))^2).
# Only the day-to-day part belongs here — the curve's own uncertainty about
# where the anchor sat is a systematic offset, and inflating a day-to-day SD
# with it would blind the detector to exactly the sustained shift (a plateau,
# a collapse) that this comparison exists to catch.
ANCHORED_RATIO_SD = 0.12

# DeviationResult.reference values (see types.DeviationResult).
REF_BASELINE = "baseline"
REF_PREOP_CURVE = "preop_curve"
REF_ANCHORED_CURVE = "anchored_curve"

# Direction that is clinically adverse (raises flags). Gait asymmetry and
# double-support are deliberately absent: they are HIGH after every surgery
# and improve along recovery, so baseline control charts would flag every
# patient — they get an absolute-threshold rule in risk.py instead.
ADVERSE_UP = {M.RESTING_HR, M.SKIN_TEMP, M.RESPIRATORY_RATE}
ADVERSE_DOWN = {M.HRV_RMSSD, M.STEPS, M.SLEEP_DURATION, M.SPO2, M.WALKING_SPEED}

FUNCTIONAL = {M.STEPS, M.WALKING_SPEED}


def reference_of(metric: M, baseline: Baseline) -> str:
    """Which comparison this metric's z-scores express."""
    if metric not in FUNCTIONAL:
        return REF_BASELINE
    return REF_PREOP_CURVE if baseline.is_preop else REF_ANCHORED_CURVE


def curve_anchor(baseline: Baseline, procedure: ProcedureType) -> float | None:
    """Where the expected curve says the patient already was when the baseline
    was measured — the unit `baseline.mean` is denominated in.

    A pre-op baseline is 1.0 by definition (the curves are fractions of pre-op
    capacity). A post-op anchor sits partway up the curve already, and that
    level is exactly what has to be divided out before the anchor can stand in
    for a pre-op norm. Returns None when the baseline carries no usable days,
    which is the one case that still cannot be scored.
    """
    if baseline.is_preop:
        return 1.0
    days = [d for d in baseline.window_days if d >= 0]
    if not days:
        return None
    anchor = sum(float(curve_mid(procedure, d)) for d in days) / len(days)
    return anchor if anchor > 0 else None


def expected_functional(
    baseline: Baseline, procedure: ProcedureType, day: int
) -> float | None:
    """The value a functional metric is expected to reach on `day`, in the
    patient's own units. The single definition of "expected" — the z-scores,
    the metric card's finding and the chart's dashed line all read it, so the
    number under the chart can never disagree with the one behind the flag."""
    anchor = curve_anchor(baseline, procedure)
    if anchor is None or baseline.mean <= 0:
        return None
    return baseline.mean * float(curve_mid(procedure, day)) / anchor


def standardized_deviations(
    metric: M,
    series: pd.Series,
    baseline: Baseline,
    procedure: ProcedureType,
) -> pd.Series:
    """Per-day z-scores for the post-op window (skipping the expected
    immediate post-surgical perturbation).

    Functional metrics are scored against the expected curve. With a pre-op
    baseline that comparison is absolute. Without one the curve is divided by
    its own level on the anchor days, which cancels the pre-op unit and asks
    the scale-free question instead — is this patient progressing the way the
    curve says a patient starting where they started progresses?

    Scoring the anchor against the raw curve (rather than the curve relative
    to the anchor) is the mistake this guards: it reads an ordinary recovery
    as several hundred percent AHEAD, because it silently treats "36% of
    pre-op capacity on day 3" as if it were 100%.
    """
    post = series[series.index >= SKIP_EARLY_DAYS]
    if metric in FUNCTIONAL:
        anchor = curve_anchor(baseline, procedure)
        if anchor is None or baseline.mean <= 0:
            return pd.Series(dtype=float)
        expected = pd.Series(
            [float(curve_mid(procedure, int(d))) / anchor for d in post.index],
            index=post.index,
        )
        ratio = (post / baseline.mean) / expected
        sd = FUNCTIONAL_RATIO_SD if baseline.is_preop else ANCHORED_RATIO_SD
        return (ratio - 1.0) / sd
    return (post - baseline.mean) / baseline.sd


def _adverse(metric: M, direction: str) -> bool:
    return (direction == "up" and metric in ADVERSE_UP) or (
        direction == "down" and metric in ADVERSE_DOWN
    )


def _adverse_sign(metric: M) -> float | None:
    """+1 if rising is adverse, -1 if falling is, None if neither — gait
    asymmetry and double-support move in both directions during a normal
    recovery, so drift in either one is not a finding."""
    if metric in ADVERSE_UP:
        return 1.0
    if metric in ADVERSE_DOWN:
        return -1.0
    return None


def is_stale(deviation: DeviationResult, postop_day: int) -> bool:
    """True when the metric last reported too long ago to say anything about
    today. Stale metrics keep their numbers — they are still the truth about
    the day they came from — but may not raise a flag, weigh into the
    composite, or move a risk tier."""
    if deviation.last_day is None:
        return True
    return postop_day - deviation.last_day > RECENCY_WINDOW_DAYS


def ewma_cusum(metric: M, z: pd.Series) -> DeviationResult:
    """Run both detectors over a standardized post-op series."""
    if len(z) == 0:
        return DeviationResult(
            metric_type=str(metric), flagged=False, direction="none",
            latest_z=0.0, raw_z=0.0, consecutive_out=0, drifting=False,
            last_day=None,
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
    flagged = consecutive >= 2 and _adverse(metric, direction)

    # One-sided CUSUM in the adverse direction, over the recent window only;
    # the alarm reflects the CURRENT accumulated drift, not a latched past one.
    drift_sign = _adverse_sign(metric)
    drifting = False
    if drift_sign is not None:
        c = 0.0
        for value in z.iloc[-CUSUM_WINDOW:]:
            c = max(0.0, c + drift_sign * float(value) - CUSUM_K)
        drifting = c >= CUSUM_H

    return DeviationResult(
        metric_type=str(metric),
        flagged=bool(flagged),
        direction=direction,
        latest_z=round(latest, 2),
        raw_z=round(float(z.iloc[-1]), 2),
        consecutive_out=int(consecutive),
        drifting=bool(drifting),
        last_day=int(z.index[-1]),
        series_z=[round(float(v), 2) for v in ewma_vals[-14:]],
    )


def analyze_metric(
    metric: M,
    series: pd.Series,
    procedure: ProcedureType,
    baseline: Baseline | None = None,
) -> tuple[Baseline, DeviationResult] | None:
    """Score one metric. `baseline` overrides the one this series would
    produce — the pipeline passes the patient's ESTABLISHED baseline so that
    data arriving later cannot silently redefine the reference (see
    engine/baseline_store.py)."""
    if baseline is None:
        baseline = compute_baseline(str(metric), series)
    if baseline is None:
        return None
    z = standardized_deviations(metric, series, baseline, procedure)
    result = ewma_cusum(metric, z)
    result.reference = reference_of(metric, baseline)
    return baseline, result
