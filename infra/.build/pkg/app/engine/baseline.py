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


def compute_baseline(metric_type: str, series: pd.Series) -> Baseline | None:
    pre = series[series.index < 0]
    if len(pre) >= 3:
        window = f"pre-op days {int(pre.index.min())}..{int(pre.index.max())}"
        values = pre
    else:
        # No pre-op data (device connected after surgery). Days 0-1 are an
        # expected physiological perturbation, so anchor on days 2+ — still a
        # weak baseline for functional metrics, but better than the acute dip.
        post = series[series.index >= 2]
        if len(post) < 3:
            return None
        values = post.iloc[:3]
        window = "post-op days 2-4 (no pre-op data)"

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
    )
