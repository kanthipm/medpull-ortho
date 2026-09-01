"""Multi-signal composite deviation index (complication-surveillance analogue).

Weighted sum of raw z-scores, counting only the clinically adverse direction.
The classic early-infection pattern — resting HR up, skin temp up, HRV down,
activity down together — pushes the index over the high threshold even when
single metrics look merely suspicious. "Together" is the whole claim, so a
signal that stopped reporting days ago is dropped rather than carried forward
against today's fresh ones.
"""

from app.engine.deviation import is_stale
from app.engine.types import CompositeResult, DeviationResult
from app.models.enums import MetricType as M

WEIGHTS: dict[M, tuple[float, str, str]] = {
    # metric: (weight, adverse direction, display label)
    M.RESTING_HR: (0.25, "up", "Resting heart rate"),
    M.SKIN_TEMP: (0.25, "up", "Skin temperature"),
    M.HRV_RMSSD: (0.20, "down", "HRV"),
    M.RESPIRATORY_RATE: (0.15, "up", "Respiratory rate"),
    M.STEPS: (0.15, "down", "Activity"),
}

HIGH = 2.0
ELEVATED = 1.2
Z_CLIP = 4.0


def composite_index(
    deviations: dict[str, DeviationResult], postop_day: int | None = None
) -> CompositeResult:
    """Weigh today's adverse movement across the signals that are still
    reporting. Callers that track the calendar should pass postop_day; without
    it, the most recent day any signal produced stands in for today, which is
    still enough to keep a week-old vital off the same scale as a fresh one."""
    reference_day = _reference_day(deviations, postop_day)
    total = 0.0
    contributions: list[tuple[M, str, float]] = []
    for metric, (weight, adverse_dir, label) in WEIGHTS.items():
        dev = deviations.get(str(metric))
        if dev is None:
            continue
        if reference_day is None or is_stale(dev, reference_day):
            continue
        # Raw (unsmoothed) z: the composite asks "how does the patient look
        # TODAY", and EWMA smoothing lags a fast-moving deterioration.
        z = dev.raw_z if (adverse_dir == "up") else -dev.raw_z
        z = min(max(z, 0.0), Z_CLIP)  # only adverse-direction movement counts
        part = weight * z
        total += part
        if part > 0.005:
            contributions.append((metric, label, part))

    level = "high" if total > HIGH else "elevated" if total > ELEVATED else "normal"
    contributions.sort(key=lambda c: c[2], reverse=True)
    drivers = [
        {
            "metric_type": str(m),
            "label": label,
            "contribution": round(part / total, 3) if total > 0 else 0.0,
            "direction": WEIGHTS[m][1],
        }
        for m, label, part in contributions
    ]
    return CompositeResult(index=round(total, 2), level=level, drivers=drivers)


def _reference_day(
    deviations: dict[str, DeviationResult], postop_day: int | None
) -> int | None:
    if postop_day is not None:
        return postop_day
    days = [d.last_day for d in deviations.values() if d.last_day is not None]
    return max(days) if days else None
