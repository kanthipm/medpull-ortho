"""Data-confidence score — the gate in front of every other output.

If the device isn't being worn, the engine must say "we can't see this
patient" instead of "this patient is fine."
"""

import pandas as pd

from app.engine.types import ConfidenceResult
from app.models.enums import ConfidenceLevel
from app.models.enums import MetricType as M

KEY_METRICS = [M.STEPS, M.RESTING_HR, M.HRV_RMSSD, M.SLEEP_DURATION, M.SKIN_TEMP, M.SPO2]
WINDOW_DAYS = 7
MIN_METRICS_PER_DAY = 3
GATE = 0.4


def coverage(series: dict[str, pd.Series], postop_day: int) -> ConfidenceResult:
    window = range(max(0, postop_day - WINDOW_DAYS + 1), postop_day + 1)
    days_with_data = 0
    for day in window:
        present = sum(
            1
            for m in KEY_METRICS
            if str(m) in series and day in series[str(m)].index
        )
        if present >= MIN_METRICS_PER_DAY:
            days_with_data += 1

    n_window = len(list(window))
    score = days_with_data / n_window if n_window else 0.0
    level = (
        ConfidenceLevel.HIGH
        if score >= 0.75
        else ConfidenceLevel.MEDIUM
        if score >= GATE
        else ConfidenceLevel.LOW
    )
    return ConfidenceResult(
        score=round(score, 2),
        level=level,
        days_with_data=days_with_data,
        window_days=n_window,
    )
