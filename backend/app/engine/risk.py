"""Risk scoring — ordered rules over the analytics results.

The output is a tier plus TYPED reason codes. Reasons are the contract between
the deterministic engine, the LLM prompts, and the UI: everything narrative is
derived from them, so they must stay short, human, and concrete.

Every rule here judges the patient TODAY, so a metric that stopped reporting
days ago is excluded before any of them run: an eight-day-old temperature is a
fact about the day it was measured, never grounds for paging the care team
tonight. What it does earn is a coverage reason — the signal is dark, and the
clinician should be told that rather than told nothing.
"""

from app.engine.deviation import RECENCY_WINDOW_DAYS, REF_ANCHORED_CURVE, is_stale
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

# Same finding, honest about a weaker comparison. A patient with no pre-op
# history is scored against the SHAPE of the expected curve projected from
# their own early post-op level (engine/deviation.py), which supports a claim
# about progress and not one about how far below normal they are.
_ANCHORED_FLAG_TEXT: dict[str, str] = {
    str(M.STEPS): "Activity not progressing from its post-op start",
    str(M.WALKING_SPEED): "Walking speed not progressing from its post-op start",
}

VITAL_KEYS = {str(M.RESTING_HR), str(M.SKIN_TEMP)}

METRIC_LABELS: dict[str, str] = {
    str(M.STEPS): "Activity",
    str(M.HRV_RMSSD): "HRV",
    str(M.RESTING_HR): "Resting HR",
    str(M.SLEEP_DURATION): "Sleep",
    str(M.SKIN_TEMP): "Skin temperature",
    str(M.WALKING_SPEED): "Walking speed",
    str(M.SPO2): "Blood oxygen",
    str(M.RESPIRATORY_RATE): "Respiratory rate",
    str(M.WALKING_ASYMMETRY_PCT): "Walking asymmetry",
}


def score_risk(
    postop_day: int,
    deviations: dict[str, DeviationResult],
    trajectory: TrajectoryResult,
    composite: CompositeResult,
    confidence: ConfidenceResult,
    adherence: AdherenceResult,
    gait_asymmetry_latest: float | None,
    gait_asymmetry_day: int | None = None,
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

    stale = {m for m, d in deviations.items() if is_stale(d, postop_day)}
    flagged = {m: d for m, d in deviations.items() if d.flagged and m not in stale}
    drifting = [
        m for m, d in deviations.items()
        if d.drifting and not d.flagged and m not in stale
    ]

    for metric, dev in flagged.items():
        if metric in _FLAG_REASONS:
            code, text, severity = _FLAG_REASONS[metric]
            if dev.reference == REF_ANCHORED_CURVE:
                text = _ANCHORED_FLAG_TEXT.get(metric, text)
            reasons.append(RiskReason(code=code, text=text, metric_type=metric, severity=severity))

    # Gait is the one rule fed a bare number rather than a DeviationResult, so
    # it carries its own day: asking `not in stale` alone would wave through a
    # patient whose asymmetry never earned a baseline at all (fewer than three
    # readings), since a metric with no deviation entry is in neither dict. The
    # day is checked against the engine-wide recency window, so this rule and
    # the metric card agree about when a limp stopped being news.
    gait_current = (
        gait_asymmetry_latest is not None
        and gait_asymmetry_day is not None
        and postop_day - gait_asymmetry_day <= RECENCY_WINDOW_DAYS
        and str(M.WALKING_ASYMMETRY_PCT) not in stale
    )
    gait_flagged = (
        gait_current
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

    for metric in drifting:
        label = METRIC_LABELS.get(metric, "A signal")
        reasons.append(
            RiskReason(
                code="DRIFT_DETECTED",
                text=f"{label} sliding gradually day over day",
                metric_type=metric,
                severity=2,
            )
        )

    # Signals that could have raised a flag but have gone quiet. LOW_COVERAGE
    # is the right code even above the confidence gate: the suggested action it
    # renders is to check the device, which is exactly the ask. Only metrics
    # with a known last reading qualify — we say a signal went quiet when we
    # know when it last spoke, never when it was simply never scored.
    dark = [
        m for m, d in deviations.items()
        if m in stale and m in _FLAG_REASONS and d.last_day is not None
    ]
    if dark:
        labels = ", ".join(METRIC_LABELS.get(m, "A signal") for m in dark)
        reasons.append(
            RiskReason(
                code="LOW_COVERAGE",
                text=f"{labels} no longer reporting",
                metric_type=None,
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

    # MEDIUM: anything worth a look this week — including a vital that has gone
    # dark, since "we stopped being able to see the two signals that decide the
    # HIGH tier" is a finding, not a quiet week.
    if (
        flagged
        or drifting
        or gait_flagged
        or any(m in VITAL_KEYS for m in dark)
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
        # Never claim more than was measured. UNKNOWN means no functional index
        # could be compared to the curve at all (too little history, or no
        # pre-op norm to express it in), and "tracking as expected" printed
        # above a card that says the pace could not be compared is the header
        # contradicting its own evidence.
        if trajectory.state == TrajectoryState.AHEAD:
            text = "Recovery ahead of the expected curve"
        elif trajectory.state == TrajectoryState.UNKNOWN:
            text = "No concerning signals — recovery pace not compared"
        else:
            text = "Recovery tracking as expected"
        reasons.append(RiskReason(code="ON_TRACK", text=text, metric_type=None, severity=1))
    score = 10.0 + (5.0 if trajectory.state == TrajectoryState.AHEAD else 0.0)
    return RiskResult(level=RiskLevel.LOW, score=score, reasons=reasons)
