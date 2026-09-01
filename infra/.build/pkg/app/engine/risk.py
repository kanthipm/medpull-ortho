"""Risk scoring — ordered rules over the analytics results.

The output is a tier plus TYPED reason codes. Reasons are the contract between
the deterministic engine, the LLM prompts, and the UI: everything narrative is
derived from them, so they must stay short, human, and concrete.
"""

from app.engine.types import (
    AdherenceResult,
    CompositeResult,
    ConfidenceResult,
    DeviationResult,
    RiskReason,
    RiskResult,
    TrajectoryResult,
)
from app.models.enums import ConfidenceLevel
from app.models.enums import MetricType as M
from app.models.enums import RiskLevel, TrajectoryState

GAIT_FLAG_PCT = 10.0
GAIT_FLAG_AFTER_DAY = 10
ADHERENCE_LOW = 0.5

_FLAG_REASONS: dict[str, tuple[str, str, int]] = {
    str(M.RESTING_HR): ("RHR_RISING", "Resting HR rising vs baseline", 3),
    str(M.SKIN_TEMP): ("TEMP_RISING", "Skin temperature elevated vs baseline", 3),
    str(M.HRV_RMSSD): ("HRV_FALLING", "HRV falling vs baseline", 2),
    str(M.STEPS): ("STEPS_FALLING", "Activity below expected range", 2),
    str(M.WALKING_SPEED): ("WALKING_SLOWING", "Walking speed below expected range", 2),
    str(M.SLEEP_DURATION): ("SLEEP_DISRUPTED", "Sleep well below baseline", 2),
    str(M.SPO2): ("SPO2_LOW", "Blood oxygen below baseline", 3),
    str(M.RESPIRATORY_RATE): ("RR_RISING", "Respiratory rate elevated", 3),
}

VITAL_KEYS = {str(M.RESTING_HR), str(M.SKIN_TEMP)}


def score_risk(
    postop_day: int,
    deviations: dict[str, DeviationResult],
    trajectory: TrajectoryResult,
    composite: CompositeResult,
    confidence: ConfidenceResult,
    adherence: AdherenceResult,
    gait_asymmetry_latest: float | None,
) -> RiskResult:
    reasons: list[RiskReason] = []

    # Gate: we can't assess what we can't see.
    if confidence.level == ConfidenceLevel.LOW:
        pct = int(round(confidence.score * 100))
        reasons.append(
            RiskReason(
                code="LOW_COVERAGE",
                text=f"Only {pct}% of recent days reporting data",
                metric_type=None,
                severity=2,
            )
        )
        return RiskResult(level=RiskLevel.MISSING_DATA, score=0.0, reasons=reasons)

    flagged = {m: d for m, d in deviations.items() if d.flagged}
    drifting = [m for m, d in deviations.items() if d.drifting and not d.flagged]

    for metric, dev in flagged.items():
        if metric in _FLAG_REASONS:
            code, text, severity = _FLAG_REASONS[metric]
            reasons.append(RiskReason(code=code, text=text, metric_type=metric, severity=severity))

    gait_flagged = (
        gait_asymmetry_latest is not None
        and postop_day > GAIT_FLAG_AFTER_DAY
        and gait_asymmetry_latest > GAIT_FLAG_PCT
    )
    if gait_flagged:
        reasons.append(
            RiskReason(
                code="GAIT_ASYMMETRY_HIGH",
                text=f"Walking asymmetry {gait_asymmetry_latest:.0f}% — favoring one side",
                metric_type=str(M.WALKING_ASYMMETRY_PCT),
                severity=2,
            )
        )

    if composite.level == "high":
        reasons.append(
            RiskReason(
                code="COMPOSITE_HIGH",
                text="Multiple signals deviating from baseline together",
                metric_type=None,
                severity=3,
            )
        )

    if trajectory.state == TrajectoryState.BEHIND and trajectory.pct is not None:
        reasons.append(
            RiskReason(
                code="TRAJECTORY_BEHIND",
                text=f"Behind expected recovery curve ({trajectory.pct:+.0f}%)",
                metric_type=None,
                severity=2,
            )
        )

    drift_labels = {
        str(M.STEPS): "Activity",
        str(M.HRV_RMSSD): "HRV",
        str(M.RESTING_HR): "Resting HR",
        str(M.SLEEP_DURATION): "Sleep",
        str(M.SKIN_TEMP): "Skin temperature",
        str(M.WALKING_SPEED): "Walking speed",
        str(M.SPO2): "Blood oxygen",
        str(M.RESPIRATORY_RATE): "Respiratory rate",
    }
    for metric in drifting:
        label = drift_labels.get(metric, "A signal")
        reasons.append(
            RiskReason(
                code="DRIFT_DETECTED",
                text=f"{label} sliding gradually day over day",
                metric_type=metric,
                severity=2,
            )
        )

    if adherence.assigned > 0 and adherence.rate < ADHERENCE_LOW:
        reasons.append(
            RiskReason(
                code="ADHERENCE_LOW",
                text=f"Task adherence {int(round(adherence.rate * 100))}% over 14 days",
                metric_type=None,
                severity=1,
            )
        )

    reasons.sort(key=lambda r: -r.severity)

    # HIGH: coupled multi-signal deterioration, or >=2 flags involving RHR/temp.
    if composite.level == "high" or (
        len(flagged) >= 2 and any(m in VITAL_KEYS for m in flagged)
    ):
        score = min(95.0, 75.0 + composite.index * 5.0)
        return RiskResult(level=RiskLevel.HIGH, score=round(score, 1), reasons=reasons)

    # MEDIUM: anything worth a look this week.
    if (
        flagged
        or drifting
        or gait_flagged
        or trajectory.state == TrajectoryState.BEHIND
        or (adherence.assigned > 0 and adherence.rate < ADHERENCE_LOW)
    ):
        score = min(
            70.0,
            40.0
            + 5.0 * len(flagged)
            + (10.0 if trajectory.state == TrajectoryState.BEHIND else 0.0)
            + (5.0 if drifting else 0.0),
        )
        return RiskResult(level=RiskLevel.MEDIUM, score=round(score, 1), reasons=reasons)

    if not reasons:
        text = (
            "Recovery tracking as expected"
            if trajectory.state != TrajectoryState.AHEAD
            else "Recovery ahead of the expected curve"
        )
        reasons.append(RiskReason(code="ON_TRACK", text=text, metric_type=None, severity=1))
    score = 10.0 + (5.0 if trajectory.state == TrajectoryState.AHEAD else 0.0)
    return RiskResult(level=RiskLevel.LOW, score=score, reasons=reasons)
