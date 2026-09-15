"""Helpers shared by the metric modules: building a CareMetric from its
catalog entry, the NODATA/stale paths, confidence downgrades, coverage
strings, and the activity-load source selection M1/M2/M15 share.

Nothing here touches the database.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.engine.care.catalog import CATALOG, FAMILY_NAME, MetricDef
from app.engine.care.types import CareContext, CareMetric, ChartSpec
from app.engine.deviation import RECENCY_WINDOW_DAYS
from app.models.enums import ConfidenceLevel, MetricStatus
from app.models.enums import MetricType as M

UNAVAILABLE_FINDING = "This metric could not be computed from the current data."
UNAVAILABLE_TEXT = "Unavailable"
NO_RECENT_TEXT = "No recent data"
NOT_USED_TEXT = "Not used on this pathway"

STATUS_RANK = {
    MetricStatus.NODATA: 0, MetricStatus.OK: 0, MetricStatus.WATCH: 1, MetricStatus.FLAG: 2,
}
_DOWNGRADE = {
    ConfidenceLevel.HIGH: ConfidenceLevel.MEDIUM,
    ConfidenceLevel.MEDIUM: ConfidenceLevel.LOW,
    ConfidenceLevel.LOW: ConfidenceLevel.LOW,
}


def definition(metric_id: str) -> MetricDef:
    return CATALOG[metric_id]


def applicable(metric_id: str, ctx: CareContext) -> bool:
    domains = CATALOG[metric_id].domains
    return "all" in domains or ctx.pathway.domain in domains


def build(
    metric_id: str,
    ctx: CareContext | None,
    *,
    status: MetricStatus,
    status_text: str,
    finding: str,
    value: str | None = None,
    value_num: float | None = None,
    unit: str = "",
    value_label: str = "",
    delta_text: str | None = None,
    next_step: str | None = None,
    confidence: ConfidenceLevel | None = None,
    coverage_text: str = "",
    chart: ChartSpec | None = None,
    method: str | None = None,
    inputs: list[str] | None = None,
    unlock: str | None = None,
    drivers: list[dict[str, Any]] | None = None,
    name: str | None = None,
) -> CareMetric:
    d = CATALOG[metric_id]
    if confidence is None:
        confidence = ctx.confidence.level if ctx is not None else ConfidenceLevel.LOW
    if status is MetricStatus.NODATA:
        confidence = ConfidenceLevel.LOW
    return CareMetric(
        id=d.id, key=d.key, name=name or d.name, family=FAMILY_NAME[d.family],
        template=d.template, feasibility=d.feasibility, tier=d.tier,
        status=status, status_text=status_text[:60],
        value=value, value_num=None if value_num is None else round(float(value_num), 3),
        unit=unit, value_label=value_label, delta_text=delta_text,
        finding=finding, next_step=next_step, confidence=confidence,
        coverage_text=coverage_text, guarded=d.guarded, chart=chart,
        method=method or d.method_short, inputs=list(inputs or d.inputs),
        unlock=unlock if status is MetricStatus.NODATA else None,
        feeds_from_tasks=list(d.feeds_from_tasks), drivers=list(drivers or []),
        domains=list(d.domains),
        applicable=applicable(metric_id, ctx) if ctx is not None else True,
    )


def nodata(
    metric_id: str,
    ctx: CareContext | None,
    status_text: str = "No data yet",
    finding: str | None = None,
    unlock: str | None = None,
    coverage_text: str = "",
    name: str | None = None,
) -> CareMetric:
    d = CATALOG[metric_id]
    if ctx is not None and not applicable(metric_id, ctx) and status_text == "No data yet":
        status_text = NOT_USED_TEXT
    return build(
        metric_id, ctx, status=MetricStatus.NODATA, status_text=status_text,
        finding=finding or f"{d.name} needs data this patient's sources are not reporting yet.",
        unlock=unlock or d.unlock, coverage_text=coverage_text, name=name,
    )


def unavailable(metric_id: str, ctx: CareContext | None = None) -> CareMetric:
    """The object a metric that raised is replaced by — never an exception."""
    return build(
        metric_id, ctx, status=MetricStatus.NODATA, status_text=UNAVAILABLE_TEXT,
        finding=UNAVAILABLE_FINDING, unlock=CATALOG[metric_id].unlock,
    )


def stale(latest_day: int | None, postop_day: int) -> bool:
    return latest_day is None or postop_day - latest_day > RECENCY_WINDOW_DAYS


def confidence_for(ctx: CareContext, present: int, wanted: int) -> ConfidenceLevel:
    """The engine's confidence, one step lower when this metric's own
    coverage is thinner than half of what it asked for."""
    level = ctx.confidence.level
    if wanted > 0 and present < 0.5 * wanted:
        return _DOWNGRADE[level]
    return level


def days_text(present: int, wanted: int, label: str) -> str:
    return f"{present} of {wanted} days of {label}"


def last_n_days(series: pd.Series, postop_day: int, n: int) -> pd.Series:
    """The values on the last n calendar post-op days (gaps stay absent)."""
    if len(series) == 0:
        return series
    return series[(series.index > postop_day - n) & (series.index <= postop_day)]


def grid(series: pd.Series, start: int, end: int) -> pd.Series:
    """Complete daily grid start..end with NaN gaps."""
    return series.reindex(range(start, end + 1)).astype(float)


def load_source(ctx: CareContext) -> tuple[pd.Series | None, str, str]:
    """(series, metric key, label) for the activity load: steps, else active
    energy, else exercise-session minutes — whichever this patient's sources
    report. The label travels into every finding so a provider knows which."""
    for metric, label in (
        (M.STEPS, "steps"), (M.ACTIVE_ENERGY, "energy load"),
        (M.EXERCISE_SESSION, "exercise minutes"),
    ):
        s = ctx.series.get(str(metric))
        if s is not None and len(s[s.index >= 0]) >= 3:
            return s.astype(float), str(metric), label
    return None, "", ""


def signed_pct(value: float) -> str:
    return f"{'−' if value < 0 else '+'}{abs(value):.0f}%"


def fmt_num(value: float, digits: int = 0) -> str:
    return f"{value:,.{digits}f}"


def as_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def points(series: pd.Series, key: str = "x", value: str = "y", digits: int = 2) -> list[dict]:
    return [
        {key: int(d), value: round(float(v), digits)}
        for d, v in series.items() if v == v
    ]
