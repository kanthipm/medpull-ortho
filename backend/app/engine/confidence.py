"""Data-confidence score — the gate in front of every other output.

If the device isn't being worn, the engine must say "we can't see this
patient" instead of "this patient is fine."

Coverage has two dimensions and confidence is the weaker of them: how many
recent days reported at all, and how much of the key panel is still reporting.
Counting days alone would call a patient fully seen while half their signals
sat dark, because three faithful metrics clear the per-day threshold on their
own.
"""

import pandas as pd

from app.engine.types import ConfidenceResult
from app.models.enums import ConfidenceLevel
from app.models.enums import MetricType as M

KEY_METRICS = [M.STEPS, M.RESTING_HR, M.HRV_RMSSD, M.SLEEP_DURATION, M.SKIN_TEMP, M.SPO2]
WINDOW_DAYS = 7
MIN_METRICS_PER_DAY = 3
GATE = 0.4
HIGH_GATE = 0.75


def coverage(series: dict[str, pd.Series], postop_day: int) -> ConfidenceResult:
    window = range(max(0, postop_day - WINDOW_DAYS + 1), postop_day + 1)
    days_with_data = 0
    reporting: set[str] = set()
    for day in window:
        present = [
            str(m)
            for m in KEY_METRICS
            if str(m) in series and day in series[str(m)].index
        ]
        reporting.update(present)
        if len(present) >= MIN_METRICS_PER_DAY:
            days_with_data += 1

    n_window = len(list(window))
    dark = [str(m) for m in KEY_METRICS if str(m) not in reporting]
    day_score = days_with_data / n_window if n_window else 0.0
    # A signal that never appeared in the window is one we cannot speak to,
    # whether the device stopped syncing or never measured it.
    panel_score = (len(KEY_METRICS) - len(dark)) / len(KEY_METRICS)
    score = min(day_score, panel_score)
    level = (
        ConfidenceLevel.HIGH
        if score >= HIGH_GATE
        else ConfidenceLevel.MEDIUM
        if score >= GATE
        else ConfidenceLevel.LOW
    )
    return ConfidenceResult(
        score=round(score, 2),
        level=level,
        days_with_data=days_with_data,
        window_days=n_window,
        dark_metrics=dark,
    )
