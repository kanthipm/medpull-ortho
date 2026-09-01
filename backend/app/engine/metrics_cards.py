"""Build the 'supporting signals' metric cards from analytics results.

The cards and the risk header are read side by side, so they share their
thresholds rather than restating them: the recency window and the gait rule
below are the same ones the engine judged the patient by.
"""

from datetime import date, timedelta

import pandas as pd

from app.engine.deviation import (
    FUNCTIONAL,
    RECENCY_WINDOW_DAYS,
    REF_ANCHORED_CURVE,
    expected_functional,
    is_stale,
)
from app.engine.risk import GAIT_FLAG_AFTER_DAY, GAIT_FLAG_PCT
from app.engine.types import Baseline, ConfidenceResult, DeviationResult, MetricInsight
from app.models.enums import ConfidenceLevel, MetricStatus
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType

# Asymmetry at or under this is reported as improving rather than watched; the
# flag threshold above it lives in risk.py, which owns the rule.
GAIT_OK_PCT = 8.0

CARD_ORDER: list[tuple[M, str, str, bool]] = [
    # metric, display name, unit label, guarded
    (M.STEPS, "Daily steps", "steps", False),
    (M.RESTING_HR, "Resting heart rate", "bpm", False),
    (M.HRV_RMSSD, "HRV (RMSSD)", "ms", False),
    (M.SLEEP_DURATION, "Sleep duration", "h", False),
    (M.SKIN_TEMP, "Skin temperature", "°C", True),
    (M.SPO2, "Blood oxygen", "%", False),
    (M.RESPIRATORY_RATE, "Respiratory rate", "br/min", True),
    (M.WALKING_SPEED, "Walking speed", "m/s", False),
    (M.WALKING_ASYMMETRY_PCT, "Walking asymmetry", "%", True),
]

STATUS_TEXT = {
    ("up", True): "Rising vs baseline",
    ("down", True): "Falling vs baseline",
}

NEXT_STEPS: dict[M, str] = {
    M.RESTING_HR: "Consider contacting the patient about how they feel today.",
    M.SKIN_TEMP: "Ask about fever, chills, and the incision site.",
    M.HRV_RMSSD: "Review alongside heart rate and temperature.",
    M.STEPS: "Ask what is limiting activity — pain, fatigue, or fear of movement.",
    M.WALKING_SPEED: "Review activity progression with PT.",
    M.SLEEP_DURATION: "Ask about pain at night and sleeping position.",
    M.SPO2: "Ask about breathing comfort; verify device fit.",
    M.RESPIRATORY_RATE: "Review alongside temperature and heart rate.",
    M.WALKING_ASYMMETRY_PCT: "Consider a gait review with PT.",
}


def _fmt(value: float, metric: M) -> str:
    if metric == M.STEPS:
        return f"{value:,.0f}"
    if metric in (M.WALKING_SPEED,):
        return f"{value:.2f}"
    return f"{value:.1f}"


def build_cards(
    series: dict[str, pd.Series],
    baselines: dict[str, Baseline],
    deviations: dict[str, DeviationResult],
    confidence: ConfidenceResult,
    procedure: ProcedureType,
    postop_day: int,
    surgery_date: date,
) -> list[MetricInsight]:
    cards: list[MetricInsight] = []
    for metric, name, unit, guarded in CARD_ORDER:
        key = str(metric)
        s = series.get(key)
        if s is None:
            continue  # provider doesn't supply this metric — card omitted entirely
        post = s[s.index >= 0]
        baseline = baselines.get(key)
        dev = deviations.get(key)

        has_recent = len(post[post.index >= postop_day - RECENCY_WINDOW_DAYS]) > 0

        anchored = dev is not None and dev.reference == REF_ANCHORED_CURVE
        if not has_recent or baseline is None or dev is None or is_stale(dev, postop_day):
            status = MetricStatus.NODATA
            status_text, finding = _no_reading_text(
                metric, post, baseline, has_recent, procedure, postop_day
            )
            next_step = None
        elif dev.flagged:
            status = MetricStatus.FLAG
            # An anchored comparison never claims a level, only a pace, so the
            # card says which of the two it is measuring.
            status_text = (
                "Behind its post-op pace"
                if anchored
                else STATUS_TEXT.get((dev.direction, True), "Outside expected range")
            )
            finding = _finding(metric, post, baseline, procedure)
            next_step = NEXT_STEPS.get(metric)
        elif dev.drifting or abs(dev.latest_z) > 1.2:
            status = MetricStatus.WATCH
            status_text = "Drifting from baseline" if dev.drifting else "Nearing expected limits"
            finding = _finding(metric, post, baseline, procedure)
            next_step = NEXT_STEPS.get(metric)
        else:
            status = MetricStatus.OK
            status_text = "Stable"
            finding = _finding(metric, post, baseline, procedure)
            next_step = None

        # special-case gait asymmetry: absolute threshold, not baseline z
        if metric == M.WALKING_ASYMMETRY_PCT and has_recent and len(post) > 0:
            latest = float(post.iloc[-1])
            if postop_day > GAIT_FLAG_AFTER_DAY and latest > GAIT_FLAG_PCT:
                status = MetricStatus.FLAG
                status_text = "Favoring one side"
                next_step = NEXT_STEPS[metric]
            elif status is not MetricStatus.NODATA:
                status = MetricStatus.OK if latest <= GAIT_OK_PCT else MetricStatus.WATCH
                status_text = "Improving" if latest <= GAIT_OK_PCT else "Still elevated"

        window = confidence.window_days or 1
        covered = min(
            window, len(post[post.index > postop_day - window])
        )
        last14 = post[post.index > postop_day - 14]
        cards.append(
            MetricInsight(
                metric_key=key,
                name=name,
                status=status,
                status_text=status_text,
                finding=finding,
                confidence=confidence.level if status is not MetricStatus.NODATA else ConfidenceLevel.LOW,
                coverage_text=f"{covered} of {window} days of data",
                next_step=next_step,
                guarded=guarded,
                unit=unit,
                series=[
                    {
                        "date": (surgery_date + timedelta(days=int(d))).isoformat(),
                        "value": round(float(v), 2),
                    }
                    for d, v in last14.items()
                ],
                baseline_mean=_reference(metric, baselines.get(key), procedure, postop_day),
            )
        )
    return cards


def _no_reading_text(
    metric: M,
    post: pd.Series,
    baseline: Baseline | None,
    has_recent: bool,
    procedure: ProcedureType,
    postop_day: int,
) -> tuple[str, str]:
    """Why this card carries no verdict — the two reasons look identical on
    screen otherwise, and 'No recent data' is a lie for a patient whose device
    reports faithfully but who cannot be measured against anything."""
    if (
        has_recent
        and baseline is not None
        and metric in FUNCTIONAL
        and expected_functional(baseline, procedure, postop_day) is None
    ):
        latest = _fmt(float(post.iloc[-1]), metric)
        return (
            "No comparison available",
            f"Latest {latest}, but this metric has no baseline days the "
            "expected curve can be anchored to.",
        )
    return "No recent data", "Not enough recent data from the patient's device."


def _reference(
    metric: M, baseline: Baseline | None, procedure: ProcedureType, postop_day: int
) -> float | None:
    """Dashed reference for the sparkline: expected-today for functional
    metrics, personal baseline for vitals.

    Functional metrics read the one shared definition of "expected", so the
    line under the chart is the number the flag was raised against — including
    for a patient with no pre-op history, whose line is the curve's shape
    projected from their own early post-op level rather than a fraction of a
    pre-op norm they never recorded."""
    if baseline is None:
        return None
    if metric in FUNCTIONAL:
        expected = expected_functional(baseline, procedure, postop_day)
        return None if expected is None else round(expected, 2)
    if metric == M.WALKING_ASYMMETRY_PCT:
        return None
    return round(baseline.mean, 2)


def _finding(metric: M, post: pd.Series, baseline: Baseline, procedure: ProcedureType) -> str:
    latest = float(post.iloc[-1])
    latest_str = _fmt(latest, metric)
    if metric in FUNCTIONAL:
        day = int(post.index[-1])
        expected = expected_functional(baseline, procedure, day)
        if expected is None:
            return f"Latest {latest_str}."
        pct = (latest / expected - 1.0) * 100 if expected > 0 else 0.0
        rel = f"{abs(pct):.0f}% {'below' if pct < 0 else 'above'} expected for day {day}"
        if baseline.is_preop:
            return f"Latest {latest_str} — {rel}."
        # Say out loud that the expectation is a projection from this
        # patient's own early post-op level: it is a claim about pace, and
        # reading it as a claim about capacity would overstate it.
        anchor_days = [d for d in baseline.window_days if d >= 0]
        span = (
            f"post-op day{'s' if len(anchor_days) > 1 else ''} "
            f"{min(anchor_days)}-{max(anchor_days)}"
            if anchor_days
            else "the early post-op days"
        )
        return (
            f"Latest {latest_str} — {rel}, projecting the recovery curve from "
            f"their own {span} level. No pre-op history, so this tracks pace, "
            "not capacity."
        )
    if metric == M.WALKING_ASYMMETRY_PCT:
        return f"Latest {latest_str}% of walking time favoring one side."
    delta = latest - baseline.mean
    sign = "+" if delta >= 0 else "−"
    return f"Latest {latest_str} vs baseline {_fmt(baseline.mean, metric)} ({sign}{_fmt(abs(delta), metric)})."
