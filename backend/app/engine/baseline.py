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
}
SD_FLOORS_REL: dict[str, float] = {
    str(M.HRV_RMSSD): 0.06,
    str(M.STEPS): 0.05,
    str(M.WALKING_SPEED): 0.05,
}

# Days 0-1 after surgery are an expected physiological perturbation, not a
# finding: neither a fallback baseline nor deviation scoring (which imports
# this) starts before day 2.
SKIP_EARLY_DAYS = 2


def compute_baseline(metric_type: str, series: pd.Series) -> Baseline | None:
    """The patient's own normal for one metric, plus how it was established.

    is_preop is the load-bearing part: a post-op anchor is a serviceable
    reference for vitals, which surgery shouldn't move for long, but it is NOT
    a pre-op norm — and the expected-recovery curves are normalized to pre-op
    = 1.0. Consumers that compare against a curve must check it.
    """
    pre = series[series.index < 0]
    if len(pre) >= 3:
        window = f"pre-op days {int(pre.index.min())}..{int(pre.index.max())}"
        return _summarize(metric_type, pre, window, is_preop=True)

    # No pre-op data (device connected after surgery). Days 0-1 are an expected
    # physiological perturbation, so anchor on the first three days from day 2
    # — whenever those happen to fall, which for a late-connected device is not
    # days 2-4 at all.
    post = series[series.index >= SKIP_EARLY_DAYS]
    if len(post) < 3:
        return None
    values = post.iloc[:3]
    window = (
        f"post-op days {int(values.index.min())}-{int(values.index.max())} "
        "(no pre-op data)"
    )
    return _summarize(metric_type, values, window, is_preop=False)


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
    )
