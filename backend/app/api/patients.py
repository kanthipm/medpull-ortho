import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.worklist import ensure_fresh_assessment
from app.database import get_db
from app.models.adherence import AdherenceTask
from app.models.checkin import Checkin
from app.models.enums import InsightKind, MetricType, NotificationChannel
from app.models.notification import Notification
from app.models.observation import Observation
from app.models.patient import Patient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patients", tags=["patients"])


def _get_patient(db: Session, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
    return patient


@router.get("/{patient_id}")
def patient_detail(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.llm.insights import get_patient_insight
    from app.models.rtm import EnrollmentStatus
    from app.rtm.coverage import get_current

    patient = _get_patient(db, patient_id)
    assessment = ensure_fresh_assessment(db, patient_id)
    analytics = assessment.analytics

    summary = get_patient_insight(db, InsightKind.PATIENT_SUMMARY, patient_id)
    actions = get_patient_insight(db, InsightKind.SUGGESTED_ACTIONS, patient_id)

    last_checkin = db.scalar(
        select(Checkin.occurred_at)
        .where(Checkin.patient_id == patient_id)
        .order_by(Checkin.occurred_at.desc())
        .limit(1)
    )
    # Patient.devices is ordered newest-connected-first, so an upgraded watch
    # wins over the row that happened to be written first.
    device = patient.devices[0] if patient.devices else None
    rtm = get_current(db, patient_id)
    enrollment = db.get(EnrollmentStatus, patient_id)

    return {
        "id": patient.id,
        "name": patient.name,
        "initials": patient.initials,
        "age": patient.age,
        "sex": patient.sex,
        "procedure_display": patient.procedure_display,
        "postop_day": analytics.get("postop_day"),
        "surgery_date": patient.surgery_date.isoformat(),
        "discharge_date": patient.discharge_date.isoformat(),
        "surgeon": patient.surgeon.name,
        "assigned_provider": patient.assigned_provider.name,
        "device": {
            "provider": str(device.source_provider),
            "model": device.device_model,
            "last_sync_at": device.last_sync_at.isoformat() if device.last_sync_at else None,
        }
        if device
        else None,
        "risk": {
            "level": assessment.risk_level,
            "score": assessment.risk_score,
            "reasons": assessment.reasons,
            "computed_at": assessment.computed_at.isoformat(),
        },
        "data_confidence": {
            "score": analytics["confidence"]["score"],
            "level": analytics["confidence"]["level"],
            "days_with_data": analytics["confidence"]["days_with_data"],
        },
        "trajectory": {
            "state": analytics["trajectory"]["state"],
            "pct": analytics["trajectory"]["pct"],
        },
        "summary": {
            "text": summary.content.get("summary", ""),
            "generated_at": summary.generated_at.isoformat(),
            "provider": summary.llm_provider,
        },
        "actions": actions.content.get("actions", []),
        "rtm": {
            "days_with_data": rtm.days_with_data if rtm else 0,
            "window_days": 30,
            "target": 16,
            "qualifies": bool(rtm.qualifies_16_of_30) if rtm else False,
            "enrolled": bool(enrollment and enrollment.complete),
        },
        "last_checkin_at": last_checkin.isoformat() if last_checkin else None,
    }


@router.get("/{patient_id}/metrics")
def patient_metrics(patient_id: str, db: Session = Depends(get_db)) -> dict:
    _get_patient(db, patient_id)
    assessment = ensure_fresh_assessment(db, patient_id)
    analytics = assessment.analytics
    return {
        "data_confidence": analytics["confidence"],
        "trajectory": analytics["trajectory"],
        "composite": analytics["composite"],
        "metrics": analytics["metrics"],
        "adherence": analytics["adherence"],
    }


@router.get("/{patient_id}/timeline")
def patient_timeline(patient_id: str, db: Session = Depends(get_db)) -> dict:
    patient = _get_patient(db, patient_id)
    assessment = ensure_fresh_assessment(db, patient_id)
    analytics = assessment.analytics

    events: list[dict] = [
        {"date": patient.surgery_date.isoformat(), "kind": "surgery", "label": "Surgery"},
        {"date": patient.discharge_date.isoformat(), "kind": "discharge", "label": "Discharged"},
    ]

    checkin_dates = db.scalars(
        select(Checkin.occurred_at).where(Checkin.patient_id == patient_id)
    ).all()
    for occurred in checkin_dates:
        events.append(
            {"date": occurred.date().isoformat(), "kind": "checkin", "label": "Daily check-in"}
        )

    change_day = analytics["trajectory"].get("change_point_day")
    if change_day is not None:
        change_date = patient.surgery_date + timedelta(days=int(change_day))
        events.append(
            {
                "date": change_date.isoformat(),
                "kind": "change_point",
                "label": "Trajectory shift",
            }
        )

    severe = [r for r in assessment.reasons if r.get("severity", 0) >= 3][:2]
    for reason in severe:
        events.append(
            {
                "date": assessment.computed_at.date().isoformat(),
                "kind": "flag",
                "label": reason["text"],
            }
        )

    events.append({"date": datetime.now().date().isoformat(), "kind": "today", "label": "Today"})
    events.sort(key=lambda e: (e["date"], e["kind"] == "today"))
    return {"events": events}


@router.get("/{patient_id}/checkins")
def patient_checkins(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.engine.checkin_digest import digest

    _get_patient(db, patient_id)
    checkins = db.scalars(
        select(Checkin)
        .where(Checkin.patient_id == patient_id)
        .order_by(Checkin.occurred_at.desc())
    ).all()
    return {
        "checkins": [
            {
                "id": c.id,
                "occurred_at": c.occurred_at.isoformat(),
                "channel": c.channel,
                "messages": [{"who": m.who, "text": m.text} for m in c.messages],
                "digest": digest([{"who": m.who, "text": m.text} for m in c.messages]),
            }
            for c in checkins
        ]
    }


@router.get("/{patient_id}/observations")
def patient_observations(
    patient_id: str, metric_type: str, days: int = 30, db: Session = Depends(get_db)
) -> dict:
    _get_patient(db, patient_id)
    try:
        metric = MetricType(metric_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid metric_type: {metric_type}")

    since = datetime.now() - timedelta(days=days)
    rows = db.scalars(
        select(Observation)
        .where(
            Observation.patient_id == patient_id,
            Observation.metric_type == metric,
            Observation.start_time >= since,
            # A provider tombstone is a retraction: connectors/ingest soft-deletes
            # so the deletion survives redelivery, and every reader owes it the
            # filter or the chart keeps plotting a value the source withdrew.
            Observation.deleted_at.is_(None),
        )
        .order_by(Observation.start_time)
    ).all()
    unit = rows[0].unit if rows else ""
    return {
        "metric_type": metric_type,
        "unit": unit,
        "points": [
            {"t": r.start_time.isoformat(), "v": r.value_num}
            for r in rows
            if r.value_num is not None
        ],
    }


@router.post("/{patient_id}/recompute")
def recompute(patient_id: str, db: Session = Depends(get_db)) -> dict:
    """Full refresh: rerun the deterministic engine AND bust the narrative
    caches, so the next reads trigger fresh LLM generations — this patient's
    insights plus the roster briefing (which embeds this patient's reason).

    It runs to completion and returns the fresh assessment, so it answers 200
    rather than the 202 it used to declare for work it never deferred.

    Not every roster-level row is the briefing: `/api/ask` answers are stored
    with a NULL patient_id too, keyed on questions this patient's numbers need
    not appear in. Deleting by "patient_id IS NULL" emptied that cache as well,
    at one LLM call per cached question to refill."""
    from sqlalchemy import and_, delete, or_

    from app.engine.pipeline import run_patient
    from app.models.insight import Insight

    _get_patient(db, patient_id)
    db.execute(
        delete(Insight).where(
            or_(
                Insight.patient_id == patient_id,
                and_(
                    Insight.patient_id.is_(None),
                    Insight.kind == InsightKind.DAILY_BRIEFING,
                ),
            )
        )
    )
    db.commit()
    assessment = run_patient(db, patient_id, force=True)
    return {
        "risk_level": assessment.risk_level,
        "recomputed_at": assessment.computed_at.isoformat(),
    }


class AssignTaskBody(BaseModel):
    title: str
    why: str = ""


class MessageBody(BaseModel):
    text: str


@router.post("/{patient_id}/actions/assign-task")
def assign_task(patient_id: str, body: AssignTaskBody, db: Session = Depends(get_db)) -> dict:
    """Records the assignment and the coordination time. Completion is NOT
    tracked: `engine.adherence.compute_adherence` scores `AdherenceRecord` rows
    only, and nothing in the product writes one — there is no patient app and no
    completion endpoint — so this task cannot move the adherence rate. The
    status says so rather than letting the caller infer follow-through."""
    from app.api.rtm import _log
    from app.models.enums import InteractionKind, TimeLogActivity

    patient = _get_patient(db, patient_id)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Task title is required")
    task = AdherenceTask(
        patient_id=patient_id,
        title=title[:120],
        why=body.why.strip()[:200] or "Assigned by care team",
        verified_by="self-report",
    )
    db.add(task)
    _log(
        db, patient, InteractionKind.ASSIGN_TASK, f"Task assigned: {title}",
        TimeLogActivity.CARE_COORDINATION, seconds=60,
    )
    db.commit()
    return {
        "ok": True,
        "status": "assigned_untracked",
        "task": {"id": task.id, "title": task.title},
    }


@router.post("/{patient_id}/actions/message")
def message_patient(patient_id: str, body: MessageBody, db: Session = Depends(get_db)) -> dict:
    """Stub channel — queues intent only. Real delivery arrives with the SMS
    integration; the UI is honest about that."""
    from app.api.rtm import _log
    from app.models.enums import InteractionKind, TimeLogActivity

    patient = _get_patient(db, patient_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message text is required")
    logger.info("Message stub -> %s: %s", patient.id, text[:120])
    _log(
        db, patient, InteractionKind.MESSAGE, f"Message queued: {text[:120]}",
        TimeLogActivity.MESSAGING, seconds=120,
    )
    db.commit()
    return {"status": "queued_stub"}


@router.post("/{patient_id}/actions/draft-message")
def draft_message(patient_id: str, db: Session = Depends(get_db)) -> dict:
    """AI-drafted patient message — for the clinician to edit before queueing."""
    from app.engine.pipeline import latest_assessment
    from app.llm.draft import draft_message as draft

    patient = _get_patient(db, patient_id)
    assessment = latest_assessment(db, patient_id)
    if assessment is None:
        raise HTTPException(status_code=409, detail="No analysis available yet for this patient")
    return draft(db, patient, assessment)


@router.post("/{patient_id}/actions/escalate")
def escalate(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.api.rtm import _log
    from app.engine.pipeline import latest_assessment
    from app.models.enums import InteractionKind, TimeLogActivity

    patient = _get_patient(db, patient_id)
    assessment = latest_assessment(db, patient_id)
    top_reason = (
        assessment.reasons[0]["text"]
        if assessment is not None and assessment.reasons
        else "Provider requested review"
    )
    notification = Notification(
        patient_id=patient_id,
        recipient_id=patient.assigned_provider_id,
        kind="escalation",
        title=f"{patient.name} — escalated by provider",
        body=top_reason,
        channel=NotificationChannel.IN_APP,
    )
    db.add(notification)
    _log(
        db, patient, InteractionKind.ESCALATE, f"Escalated: {top_reason}",
        TimeLogActivity.CARE_COORDINATION, seconds=120,
    )
    db.commit()
    return {"ok": True}
