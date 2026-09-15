"""Care metrics (the M1–M18 / C1–C6 report objects) and the raw observation
view behind them.

Both are read paths: ``care-metrics`` is the stored bundle slice behind
``ensure_fresh_assessment`` (no recompute beyond the staleness check) and
``raw-data`` is one grouped query over the observation table.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.worklist import ensure_fresh_assessment
from app.database import get_db
from app.engine.care.catalog import families_payload
from app.engine.care.pathways import pathway_by_key, pathway_for
from app.models.adherence import AdherenceTask
from app.models.checkin import Checkin
from app.models.observation import Observation
from app.models.patient import Patient

router = APIRouter(prefix="/patients", tags=["care"])

RAW_ROW_CAP = 400


def _get_patient(db: Session, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
    return patient


@router.get("/{patient_id}/care-metrics")
def care_metrics(patient_id: str, db: Session = Depends(get_db)) -> dict:
    patient = _get_patient(db, patient_id)
    assessment = ensure_fresh_assessment(db, patient_id)
    care = (assessment.analytics or {}).get("care_metrics") or {}
    pathway = pathway_by_key(care.get("pathway")) if care.get("pathway") else pathway_for(patient)
    return {
        "version": care.get("version", "care-1"),
        "pathway": {"key": pathway.key, "name": pathway.name, "domain": pathway.domain},
        "headline": care.get("headline", []),
        "metrics": care.get("metrics", []),
        "families": families_payload(),
        "computed_at": assessment.computed_at.isoformat(),
    }


@router.get("/{patient_id}/raw-data")
def raw_data(
    patient_id: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
) -> dict:
    """Every non-deleted observation in the window, grouped by metric type,
    newest first, capped per type. The window is on ``local_date`` — the
    product's one day definition — not on ``start_time``."""
    _get_patient(db, patient_id)
    since = date.today() - timedelta(days=days)
    rows = db.scalars(
        select(Observation)
        .where(
            Observation.patient_id == patient_id,
            Observation.deleted_at.is_(None),
            Observation.local_date >= since,
        )
        .order_by(Observation.metric_type, Observation.local_date.desc(),
                  Observation.start_time.desc(), Observation.id.desc())
    ).all()

    grouped: dict[str, list[dict]] = {}
    summary: dict[str, dict] = {}
    for row in rows:
        key = str(row.metric_type)
        meta = summary.setdefault(key, {
            "metric_type": key, "unit": row.unit, "count": 0, "first": None, "last": None,
            "source_providers": [], "truncated": False,
        })
        meta["count"] += 1
        day = row.local_date.isoformat()
        meta["first"] = day if meta["first"] is None or day < meta["first"] else meta["first"]
        meta["last"] = day if meta["last"] is None or day > meta["last"] else meta["last"]
        provider = str(row.source_provider)
        if provider not in meta["source_providers"]:
            meta["source_providers"].append(provider)
        bucket = grouped.setdefault(key, [])
        if len(bucket) >= RAW_ROW_CAP:
            meta["truncated"] = True
            continue
        bucket.append({
            "date": day,
            "start_time": row.start_time.isoformat(),
            "value": row.value_num,
            "unit": row.unit,
            "source": provider,
            "granularity": str(row.granularity),
            "patient_reported": bool(row.is_patient_reported),
            "json": row.value_json,
        })

    checkins_count = db.scalar(
        select(func.count(Checkin.id)).where(Checkin.patient_id == patient_id)
    )
    tasks_count = db.scalar(
        select(func.count(AdherenceTask.id)).where(AdherenceTask.patient_id == patient_id)
    )
    return {
        "days": days,
        "since": since.isoformat(),
        "metric_types": sorted(summary.values(), key=lambda m: m["metric_type"]),
        "rows": grouped,
        "checkins_count": int(checkins_count or 0),
        "tasks_count": int(tasks_count or 0),
    }
