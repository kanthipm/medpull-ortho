"""Personal baselines from the pre-op window."""

import pandas as pd

from app.engine.types import Baseline
from app.models.enums import MetricType as M

# Physiological floors for the standard deviation used in z-scores. Sample SD
# from a quiet 10-day window understates real day-to-day variability, which
# would make trivial changes look like findings (and, for temperature, a
# fraction-of-mean floor would be absurdly wide — 2% of 36.5 °C is 0.7 °C).
SD_FLOORS_ABS: dict[str, float] = {
    str(M.RESTING_HR): 1.5,
    str(M.SKIN_TEMP): 0.12,
    str(M.SLEEP_DURATION): 0.4,
    str(M.SPO2): 0.5,
    str(M.RESPIRATORY_RATE): 0.6,
    str(M.WALKING_ASYMMETRY_PCT): 1.0,
    str(M.DOUBLE_SUPPORT_PCT): 1.2,
    # in-house set: the steadiness index moves in whole points; a joint angle
    # by the phone inclinometer has an MDC95 of ~3 deg (extension) to ~9 deg
    # (flexion); the stress index is a z-composite scaled 25 per SD.
    str(M.WALKING_STEADINESS): 5.0,
    str(M.ROM_FLEXION): 4.0,
    str(M.ROM_EXTENSION): 3.0,
    str(M.ROM_ABDUCTION): 4.0,
    str(M.STRESS_INDEX): 8.0,
    str(M.EXERCISE_SESSION): 3.0,
}
SD_FLOORS_REL: dict[str, float] = {
    str(M.HRV_RMSSD): 0.06,
    str(M.STEPS): 0.05,
    str(M.WALKING_SPEED): 0.05,
    str(M.STEP_LENGTH): 0.05,
    str(M.CADENCE): 0.05,
    str(M.STAIR_SPEED_UP): 0.10,
    str(M.STAIR_SPEED_DOWN): 0.10,
    str(M.SIX_MIN_WALK): 0.06,
    str(M.EXERCISE_SESSION): 0.15,
    str(M.ACTIVE_ENERGY): 0.10,
}

# Days 0-1 after surgery are an expected physiological perturbation, not a
# finding: neither a fallback baseline nor deviation scoring (which imports
# this) starts before day 2.
SKIP_EARLY_DAYS = 2
# Days a reference needs. Two is enough to start comparing against — the SD
# floors above carry the day-to-day spread a two-point sample cannot — so a
# patient who starts wearing a watch sees their cards on the third day of
# wear rather than the fourth. Three is where the reference is trusted: a
# pre-op norm is frozen then (engine/baseline_store.py), and until then every
# consumer is told the baseline is provisional.
MIN_BASELINE_DAYS = 2
FIRM_BASELINE_DAYS = 3
# How many post-op days a no-pre-op anchor is taken from, at most.
ANCHOR_DAYS = 3


def compute_baseline(metric_type: str, series: pd.Series) -> Baseline | None:
    """The patient's own normal for one metric, plus how it was established.

    is_preop is the load-bearing part: a post-op anchor is a serviceable
    reference for vitals, which surgery shouldn't move for long, but it is NOT
    a pre-op norm — and the expected-recovery curves are normalized to pre-op
    = 1.0. Consumers that compare against a curve must check it.
    """
    pre = series[series.index < 0]
    if len(pre) >= MIN_BASELINE_DAYS:
        window = f"pre-op days {int(pre.index.min())}..{int(pre.index.max())}"
        return _summarize(metric_type, pre, window, is_preop=True)

    # No pre-op data (device connected after surgery). Days 0-1 are an expected
    # physiological perturbation, so anchor on the first days from day 2 —
    # whenever those happen to fall, which for a late-connected device is not
    # days 2-4 at all.
    post = series[series.index >= SKIP_EARLY_DAYS]
    if len(post) < MIN_BASELINE_DAYS:
        return None
    values = post.iloc[:ANCHOR_DAYS]
    window = (
        f"post-op days {int(values.index.min())}-{int(values.index.max())} "
        "(no pre-op data)"
    )
    return _summarize(metric_type, values, window, is_preop=False)


def baseline_readiness(series: pd.Series | None, postop_day: int) -> dict:
    """How far one metric is from having a reference at all: the days in
    hand that could anchor it, the two it needs, and the three that settle
    it — counting from post-op day 2, so a day-0 patient is told three days,
    not one."""
    from app.engine.readiness import readiness

    if series is None or len(series) == 0:
        return readiness(0, MIN_BASELINE_DAYS, FIRM_BASELINE_DAYS,
                         note="days of readings from post-op day 2",
                         extra_wait=max(0, SKIP_EARLY_DAYS - postop_day)).to_dict()
    pre = series[series.index < 0]
    if len(pre) >= MIN_BASELINE_DAYS:
        return readiness(int(len(pre)), MIN_BASELINE_DAYS, FIRM_BASELINE_DAYS,
                         note="pre-op days").to_dict()
    post = series[series.index >= SKIP_EARLY_DAYS]
    return readiness(int(len(post)), MIN_BASELINE_DAYS, FIRM_BASELINE_DAYS,
                     note="days of readings from post-op day 2",
                     extra_wait=max(0, SKIP_EARLY_DAYS - postop_day)).to_dict()


def _summarize(
    metric_type: str, values: pd.Series, window: str, is_preop: bool
) -> Baseline:
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    floor = SD_FLOORS_ABS.get(metric_type, 0.0)
    rel = SD_FLOORS_REL.get(metric_type, 0.0) * abs(mean)
    sd = max(sd, floor, rel, 1e-6)
    return Baseline(
        metric_type=metric_type,
        mean=round(mean, 3),
        sd=round(sd, 3),
        n_days=int(len(values)),
        window=window,
        is_preop=is_preop,
        # The days themselves, not just their prose label: a post-op anchor is
        # only usable as a reference once you know where on the recovery curve
        # it was taken, and deviation.py reads them back to work that out.
        window_days=[int(d) for d in values.index],
        provisional=int(len(values)) < FIRM_BASELINE_DAYS,
    )
