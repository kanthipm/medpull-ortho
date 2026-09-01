"""Build the 'supporting signals' metric cards from analytics results."""

from datetime import date, timedelta

import pandas as pd

from app.engine.curves import curve_mid
from app.engine.types import Baseline, ConfidenceResult, DeviationResult, MetricInsight
from app.models.enums import ConfidenceLevel, MetricStatus
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType

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

        recent_days = 5
        has_recent = len(post[post.index >= postop_day - recent_days]) > 0

        if not has_recent or baseline is None or dev is None:
            status = MetricStatus.NODATA
            status_text = "No recent data"
            finding = "Not enough recent data from the patient's device."
            next_step = None
        elif dev.flagged:
            status = MetricStatus.FLAG
            status_text = STATUS_TEXT.get((dev.direction, True), "Outside expected range")
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
            if postop_day > 10 and latest > 10.0:
                status = MetricStatus.FLAG
                status_text = "Favoring one side"
                next_step = NEXT_STEPS[metric]
            elif status is not MetricStatus.NODATA:
                status = MetricStatus.OK if latest <= 8.0 else MetricStatus.WATCH
                status_text = "Improving" if latest <= 8.0 else "Still elevated"

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


def _reference(
    metric: M, baseline: Baseline | None, procedure: ProcedureType, postop_day: int
) -> float | None:
    """Dashed reference for the sparkline: expected-today for functional
    metrics, personal baseline for vitals."""
    if baseline is None:
        return None
    if metric in (M.STEPS, M.WALKING_SPEED):
        return round(baseline.mean * float(curve_mid(procedure, postop_day)), 2)
    if metric == M.WALKING_ASYMMETRY_PCT:
        return None
    return round(baseline.mean, 2)


def _finding(metric: M, post: pd.Series, baseline: Baseline, procedure: ProcedureType) -> str:
    latest = float(post.iloc[-1])
    latest_str = _fmt(latest, metric)
    if metric in (M.STEPS, M.WALKING_SPEED):
        day = int(post.index[-1])
        expected = baseline.mean * float(curve_mid(procedure, day))
        pct = (latest / expected - 1.0) * 100 if expected > 0 else 0.0
        rel = f"{abs(pct):.0f}% {'below' if pct < 0 else 'above'} expected for day {day}"
        return f"Latest {latest_str} — {rel}."
    if metric == M.WALKING_ASYMMETRY_PCT:
        return f"Latest {latest_str}% of walking time favoring one side."
    delta = latest - baseline.mean
    sign = "+" if delta >= 0 else "−"
    return f"Latest {latest_str} vs baseline {_fmt(baseline.mean, metric)} ({sign}{_fmt(abs(delta), metric)})."
