"""Care-metrics engine: the M1–M18 (ortho) and C1–C6 (chronic) report
objects that join the analytics bundle as ``care_metrics``.

``build_context`` gathers what ``run_patient`` already computed plus the
json-bearing, intraday and patient-reported inputs the loaders add;
``compute_care_metrics`` runs every metric in catalog order inside its own
try/except — an engine failure in one metric is logged and replaced by the
catalog's NODATA object, never allowed to fail the assessment — then picks
the pathway's headline.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.engine.care import chronic, engagement, function, load, recovery_quality, surveillance
from app.engine.care import trajectory as trajectory_metrics
from app.engine.care._common import unavailable
from app.engine.care.catalog import CATALOG_ORDER
from app.engine.care.headline import select_headline
from app.engine.care.loaders import (
    device_last_sync,
    load_checkins,
    load_glucose,
    load_intraday,
    load_sessions,
    load_sleep_stages,
    load_symptom,
    load_tasks_with_records,
)
from app.engine.care.pathways import Pathway, pathway_for
from app.engine.care.types import CareContext, CareMetric
from app.engine.deviation import analyze_metric
from app.engine.types import (
    AdherenceResult,
    Baseline,
    CompositeResult,
    ConfidenceResult,
    DeviationResult,
    TrajectoryResult,
)
from app.models.enums import MetricType as M
from app.models.enums import ProcedureType

logger = logging.getLogger(__name__)

CARE_VERSION = "care-1"

REGISTRY: dict[str, Callable[[CareContext], CareMetric]] = {
    "M1": load.m1, "M2": load.m2, "M3": load.m3,
    "M4": function.m4, "M5": function.m5, "M6": function.m6, "M7": function.m7, "M8": function.m8,
    "M9": recovery_quality.m9, "M10": recovery_quality.m10, "M11": recovery_quality.m11,
    "M12": surveillance.m12, "M13": surveillance.m13,
    "M14": engagement.m14, "M15": engagement.m15, "M16": engagement.m16,
    "M17": trajectory_metrics.m17, "M18": trajectory_metrics.m18,
    "C1": chronic.c1, "C2": chronic.c2, "C3": chronic.c3, "C4": chronic.c4,
    "C5": chronic.c5, "C6": chronic.c6,
}

# Variant statistics a real device ships instead of the canonical one the
# risk engine scores (§9.4): scored locally, read only by the care metrics.
VARIANTS: dict[M, M] = {M.HRV_RMSSD: M.HRV_SDNN, M.SKIN_TEMP: M.SKIN_TEMP_DELTA}


def build_context(
    db: Session,
    patient,
    today: date,
    postop_day: int,
    series: dict[str, pd.Series],
    baselines: dict[str, Baseline],
    deviations: dict[str, DeviationResult],
    confidence: ConfidenceResult,
    trajectory: TrajectoryResult,
    composite: CompositeResult,
    adherence: AdherenceResult,
    now: datetime | None = None,
) -> CareContext:
    pathway = pathway_for(patient)
    surgery_date = patient.surgery_date
    procedure = ProcedureType(patient.procedure_type)
    symptoms = {
        key: load_symptom(db, patient.id, surgery_date, key)
        for key in ("pain", "breathlessness", "fatigue")
    }
    local: dict[str, DeviationResult] = {}
    for canonical, variant in VARIANTS.items():
        if str(canonical) in deviations or str(variant) not in series:
            continue
        scored = analyze_metric(variant, series[str(variant)], procedure)
        if scored is not None:
            local[str(variant)] = scored[1]
    return CareContext(
        patient_id=patient.id,
        first_name=(patient.name or patient.id).split()[0],
        procedure=procedure,
        pathway=pathway,
        postop_day=postop_day,
        surgery_date=surgery_date,
        today=today,
        series=series,
        baselines=baselines,
        deviations=deviations,
        confidence=confidence,
        trajectory=trajectory,
        composite=composite,
        adherence=adherence,
        device_last_sync=device_last_sync(patient),
        now=now or datetime.now(),
        pain=symptoms["pain"],
        symptoms=symptoms,
        sleep_stages=load_sleep_stages(db, patient.id, surgery_date),
        sessions=load_sessions(db, patient.id, surgery_date, today),
        intraday={
            str(M.STEPS): load_intraday(db, patient.id, surgery_date, today, M.STEPS),
            str(M.HR_SAMPLE): load_intraday(db, patient.id, surgery_date, today, M.HR_SAMPLE),
        },
        checkins=load_checkins(db, patient.id),
        tasks=load_tasks_with_records(db, patient.id, today),
        glucose=load_glucose(db, patient.id, surgery_date, today),
        local_deviations=local,
    )


def compute_care_metrics(ctx: CareContext) -> dict[str, Any]:
    metrics: list[CareMetric] = []
    for metric_id in CATALOG_ORDER:
        try:
            metric = REGISTRY[metric_id](ctx)
        except Exception:  # noqa: BLE001 — one metric must never fail the assessment
            logger.exception("care metric %s failed for %s", metric_id, ctx.patient_id)
            metric = unavailable(metric_id, ctx)
        metrics.append(metric)
    return {
        "version": CARE_VERSION,
        "pathway": ctx.pathway.key,
        "headline": select_headline(ctx.pathway, metrics),
        "metrics": [m.to_dict() for m in metrics],
    }


def unavailable_bundle(pathway: Pathway) -> dict[str, Any]:
    """What the bundle carries when the context itself could not be built."""
    metrics = [unavailable(metric_id) for metric_id in CATALOG_ORDER]
    return {
        "version": CARE_VERSION,
        "pathway": pathway.key,
        "headline": select_headline(pathway, metrics),
        "metrics": [m.to_dict() for m in metrics],
    }


__all__ = [
    "CARE_VERSION", "REGISTRY", "build_context", "compute_care_metrics", "unavailable_bundle",
    "select_headline", "pathway_for",
]
