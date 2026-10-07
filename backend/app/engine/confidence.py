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
# The panel a patient is judged against is the key signals their own sources
# have ever reported, floored at three: a phone that gives steps alone can
# never clear the gate (one signal is not a picture of a patient), a watch
# without a temperature sensor is judged on the five it has rather than the
# six it never will, and a watch that goes quiet on half its signals is still
# marked down for every one that went dark.
MIN_PANEL = 3


def coverage(series: dict[str, pd.Series], postop_day: int) -> ConfidenceResult:
    window = range(max(0, postop_day - WINDOW_DAYS + 1), postop_day + 1)
    panel = [str(m) for m in KEY_METRICS if str(m) in series and len(series[str(m)]) > 0]
    per_day = min(MIN_METRICS_PER_DAY, max(1, len(panel)))
    days_with_data = 0
    reporting: set[str] = set()
    for day in window:
        present = [m for m in panel if day in series[m].index]
        reporting.update(present)
        if present and len(present) >= per_day:
            days_with_data += 1

    n_window = len(list(window))
    # A signal this patient's sources HAVE reported but not inside the
    # window: the device stopped syncing, or stopped measuring it.
    dark = [m for m in panel if m not in reporting]
    day_score = days_with_data / n_window if n_window else 0.0
    panel_score = (len(panel) - len(dark)) / max(len(panel), MIN_PANEL)
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
        panel=panel,
    )
