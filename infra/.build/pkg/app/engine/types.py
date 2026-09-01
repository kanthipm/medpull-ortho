"""Typed results for the deterministic analytics layer.

Everything here serializes to plain JSON (via .to_dict()) into
RiskAssessment.analytics, which is the single payload the API reads for the
patient metrics view. Keep field names stable — the frontend mirrors them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.models.enums import (
    ConfidenceLevel,
    MetricStatus,
    MetricType,
    RiskLevel,
    TrajectoryState,
)


@dataclass
class Baseline:
    metric_type: str
    mean: float
    sd: float
    n_days: int
    window: str  # e.g. "pre-op days -10..-1"


@dataclass
class DeviationResult:
    """EWMA control-chart result for one metric."""

    metric_type: str
    flagged: bool                 # outside control limits >= 2 consecutive days
    direction: str                # "up" | "down" | "none"
    latest_z: float               # latest EWMA (smoothed) z-score vs baseline
    raw_z: float                  # latest single-day z-score (composite uses this)
    consecutive_out: int
    drifting: bool                # CUSUM slow-drift alarm
    series_z: list[float] = field(default_factory=list)


@dataclass
class MetricInsight:
    """One card in the 'supporting signals' section (M1..M18 analogue)."""

    metric_key: str               # e.g. "resting_hr", "gait_symmetry", "load"
    name: str                     # display name
    status: MetricStatus
    status_text: str              # <= 6 words, e.g. "Rising vs baseline"
    finding: str                  # 1-2 sentence deterministic finding
    confidence: ConfidenceLevel
    coverage_text: str            # e.g. "7 of 7 days of data"
    next_step: str | None
    guarded: bool                 # if True, phrasing must stay non-diagnostic
    unit: str
    series: list[dict[str, Any]] = field(default_factory=list)  # [{date, value}]
    baseline_mean: float | None = None


@dataclass
class TrajectoryResult:
    state: TrajectoryState
    pct: float | None                     # signed % vs expected mid-curve, last 5 days
    change_point_day: int | None          # post-op day of detected mean shift
    actual: list[dict[str, Any]] = field(default_factory=list)    # [{day, v}] functional index
    expected: list[dict[str, Any]] = field(default_factory=list)  # [{day, lo, mid, hi}]


@dataclass
class CompositeResult:
    """Multi-signal deviation index (infection/complication surveillance analogue)."""

    index: float                  # weighted directional z-composite
    level: str                    # "high" | "elevated" | "normal"
    drivers: list[dict[str, Any]] = field(default_factory=list)
    # drivers: [{metric_type, label, contribution (0..1), direction}]


@dataclass
class ConfidenceResult:
    score: float                  # 0..1 coverage across key metrics
    level: ConfidenceLevel
    days_with_data: int
    window_days: int


@dataclass
class AdherenceResult:
    rate: float                   # 0..1
    verified: int
    assigned: int
    self_attested: int
    days: list[float] = field(default_factory=list)  # last 14 days: 0 | 0.5 | 1


@dataclass
class RiskReason:
    code: str                     # e.g. "RHR_RISING", "COMPOSITE_HIGH", "LOW_COVERAGE"
    text: str                     # human sentence fragment, e.g. "Resting HR rising 4 days"
    metric_type: str | None
    severity: int                 # 1 (info) .. 3 (critical)


@dataclass
class RiskResult:
    level: RiskLevel
    score: float                  # 0..100
    reasons: list[RiskReason] = field(default_factory=list)


@dataclass
class AnalyticsBundle:
    """Complete deterministic output for one patient — the LLM's only input
    besides conversation transcripts, and the source for every chart."""

    patient_id: str
    postop_day: int
    risk: RiskResult
    confidence: ConfidenceResult
    trajectory: TrajectoryResult
    composite: CompositeResult
    adherence: AdherenceResult
    metrics: list[MetricInsight] = field(default_factory=list)
    baselines: list[Baseline] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
