"""Report objects for the care-metrics engine.

A ``CareMetric`` is one tile/card: status vs the patient's own baseline →
finding → evidence (chart) → confidence → next step. ``CareContext`` is
everything a metric function may read — the engine results ``run_patient``
already computed plus the json-bearing, intraday and patient-reported inputs
the loaders add — so a metric is a pure function of its context and unit
tests can build one by hand.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from app.engine.care.pathways import Pathway
from app.engine.types import (
    AdherenceResult,
    Baseline,
    CompositeResult,
    ConfidenceResult,
    DeviationResult,
    TrajectoryResult,
)
from app.models.enums import ConfidenceLevel, MetricStatus, ProcedureType

MAX_POINTS = 60


@dataclass
class ChartSpec:
    kind: str                      # "line" | "band" | "bars" | "scatter" | "dual" | "gauge" | "heat"
    series: list[dict[str, Any]]   # points; keys depend on kind; <= 60 points
    reference: float | None = None # dashed reference line (baseline / band centre)
    band: list[dict[str, Any]] | None = None   # [{x, lo, hi}] shaded band
    x_label: str = "Post-op day"
    y_label: str = ""
    y2_label: str = ""
    marker_x: float | None = None  # change-point / event marker
    fit: list[dict[str, Any]] | None = None     # fitted curve points [{x, y}]
    extra: dict[str, Any] = field(default_factory=dict)  # kind-specific


@dataclass
class CareMetric:
    id: str            # "M1"
    key: str           # "acute_chronic_load"
    name: str
    family: str
    template: str
    feasibility: str
    tier: int
    status: MetricStatus
    status_text: str                 # <= 6 words
    value: str | None
    value_num: float | None
    unit: str
    value_label: str
    delta_text: str | None
    finding: str
    next_step: str | None
    confidence: ConfidenceLevel
    coverage_text: str
    guarded: bool
    chart: ChartSpec | None
    method: str                    # one sentence, provider-facing, how it was computed
    inputs: list[str]              # metric types / sources used
    unlock: str | None             # only when NODATA: what data would enable it
    feeds_from_tasks: list[str]    # task kinds whose data feed this metric
    drivers: list[dict[str, Any]] = field(default_factory=list)
    domains: list[str] = field(default_factory=lambda: ["all"])
    applicable: bool = True        # domain ∈ pathway's domain or "all"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = str(self.status)
        data["confidence"] = str(self.confidence)
        return clean_json(data)


def clean_json(value: Any) -> Any:
    """Plain JSON only: numpy scalars become Python numbers, NaN/inf become
    None, enums become their string values, and chart series are capped."""
    if isinstance(value, dict):
        return {str(k): clean_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(v) for v in value]
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) or hasattr(value, "item"):
        number = value.item() if hasattr(value, "item") else value
        if isinstance(number, float) and not math.isfinite(number):
            return None
        return number
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None or isinstance(value, str):
        return str(value) if value is not None and not isinstance(value, str) else value
    return str(value)


@dataclass
class CareContext:
    """Everything a metric function may read.

    ``symptoms`` maps a pathway's symptom key ("pain", "breathlessness",
    "fatigue") to a frame with columns day, am, pm, mean (NaN where absent);
    ``pain`` is the same frame for "pain", kept as its own field because the
    ortho metrics name it directly.
    """

    patient_id: str
    first_name: str
    procedure: ProcedureType
    pathway: Pathway
    postop_day: int
    surgery_date: date
    today: date
    series: dict[str, pd.Series]
    baselines: dict[str, Baseline]
    deviations: dict[str, DeviationResult]
    confidence: ConfidenceResult
    trajectory: TrajectoryResult
    composite: CompositeResult
    adherence: AdherenceResult
    device_last_sync: datetime | None = None
    now: datetime | None = None
    pain: pd.DataFrame = field(default_factory=lambda: empty_symptom_frame())
    symptoms: dict[str, pd.DataFrame] = field(default_factory=dict)
    sleep_stages: pd.DataFrame = field(default_factory=lambda: empty_sleep_frame())
    sessions: list[dict[str, Any]] = field(default_factory=list)
    intraday: dict[str, pd.DataFrame] = field(default_factory=dict)
    checkins: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    glucose: pd.DataFrame = field(default_factory=lambda: empty_glucose_frame())
    # Deviation results computed locally for the variant statistics a real
    # device ships (hrv_sdnn, skin_temp_delta) when the canonical one is
    # absent — never stored, never fed to the risk tier.
    local_deviations: dict[str, DeviationResult] = field(default_factory=dict)

    @property
    def seed(self) -> int:
        """Deterministic per-patient seed for bootstrap resamples."""
        return sum(ord(c) * (i + 1) for i, c in enumerate(self.patient_id)) % (2**31)

    @property
    def uses_expected_curve(self) -> bool:
        return self.pathway.uses_expected_curve

    def day_phrase(self, day: int | None = None) -> str:
        d = self.postop_day if day is None else day
        if self.uses_expected_curve:
            return f"post-op day {d}"
        return f"day {d} of the program"

    def symptom(self, key: str | None = None) -> pd.DataFrame:
        key = key or self.pathway.symptom_key
        if key == "pain":
            return self.pain
        return self.symptoms.get(key, empty_symptom_frame())

    def post(self, metric: str, from_day: int = 0) -> pd.Series:
        """A metric's daily series restricted to post-op days >= from_day."""
        s = self.series.get(metric)
        if s is None:
            return pd.Series(dtype=float)
        return s[s.index >= from_day].astype(float)


def empty_symptom_frame() -> pd.DataFrame:
    return pd.DataFrame({"day": pd.Series(dtype=int), "am": pd.Series(dtype=float),
                         "pm": pd.Series(dtype=float), "mean": pd.Series(dtype=float)})


def empty_sleep_frame() -> pd.DataFrame:
    return pd.DataFrame({
        "day": pd.Series(dtype=int), "total_h": pd.Series(dtype=float),
        "awake_h": pd.Series(dtype=float), "deep_h": pd.Series(dtype=float),
        "rem_h": pd.Series(dtype=float), "light_h": pd.Series(dtype=float),
    })


def empty_glucose_frame() -> pd.DataFrame:
    return pd.DataFrame({"day": pd.Series(dtype=int), "value": pd.Series(dtype=float),
                         "granularity": pd.Series(dtype=str), "json": pd.Series(dtype=object)})


def tail(points: list[dict[str, Any]], n: int = MAX_POINTS) -> list[dict[str, Any]]:
    return points[-n:] if len(points) > n else points
