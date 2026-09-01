"""RTM endpoints: readiness card, treatment-management actions with automatic
time logging, documentation review/approve, and the practice overview strip.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.enums import (
    DocumentKind,
    DocumentStatus,
    InteractionKind,
    NotificationChannel,
    TimeLogActivity,
)
from app.models.notification import Notification
from app.models.patient import Patient
from app.models.rtm import ProviderTimeLog, RtmDocument, RtmInteraction

logger = logging.getLogger(__name__)

router = APIRouter(tags=["rtm"])


def _get_patient(db: Session, patient_id: str) -> Patient:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
    return patient


def _log(
    db: Session,
    patient: Patient,
    kind: InteractionKind,
    detail: str,
    activity: TimeLogActivity,
    seconds: int,
    interactive: bool = False,
) -> None:
    """Every treatment-management action leaves both an interaction row (the
    audit trail) and a time-log row (the billing clock) — commit is the
    caller's job so an action stays one transaction."""
    now = datetime.now()
    db.add(
        RtmInteraction(
            patient_id=patient.id,
            provider_id=patient.assigned_provider_id,
            kind=kind,
            detail=detail[:200],
            occurred_at=now,
        )
    )
    db.add(
        ProviderTimeLog(
            patient_id=patient.id,
            provider_id=patient.assigned_provider_id,
            activity=activity,
            seconds=seconds,
            interactive=interactive,
            note=detail[:200] or None,
            occurred_at=now,
            month=f"{now.year:04d}-{now.month:02d}",
        )
    )


@router.get("/patients/{patient_id}/rtm")
def rtm_readiness(patient_id: str, db: Session = Depends(get_db)) -> dict:
    from app.rtm.readiness import compute_readiness

    patient = _get_patient(db, patient_id)
    readiness = compute_readiness(db, patient)
    interactions = db.scalars(
        select(RtmInteraction)
        .where(RtmInteraction.patient_id == patient_id)
        .order_by(RtmInteraction.occurred_at.desc())
        .limit(6)
    ).all()
    readiness["recent_interactions"] = [
        {
            "kind": str(i.kind),
            "detail": i.detail,
            "occurred_at": i.occurred_at.isoformat(),
        }
        for i in interactions
    ]
    return readiness


class CallBody(BaseModel):
    minutes: int = 5
    note: str = ""


@router.post("/patients/{patient_id}/actions/call")
def log_call(patient_id: str, body: CallBody, db: Session = Depends(get_db)) -> dict:
    """A completed patient call — the live interactive communication the
    treatment-management codes require."""
    patient = _get_patient(db, patient_id)
    minutes = max(1, min(body.minutes, 60))
    _log(
        db,
        patient,
        InteractionKind.CALL,
        body.note.strip() or f"Patient call ({minutes} min)",
        TimeLogActivity.CALL,
        seconds=minutes * 60,
        interactive=True,
    )
    db.commit()
    return {"ok": True, "logged_minutes": minutes, "interactive": True}


class FollowupBody(BaseModel):
    when: str  # free text for v1, e.g. "Tomorrow 2:30 PM"
    note: str = ""


@router.post("/patients/{patient_id}/actions/schedule-followup")
def schedule_followup(patient_id: str, body: FollowupBody, db: Session = Depends(get_db)) -> dict:
    patient = _get_patient(db, patient_id)
    when = body.when.strip()
    if not when:
        raise HTTPException(status_code=422, detail="Follow-up time is required")
    detail = f"Follow-up scheduled: {when}" + (f" — {body.note.strip()}" if body.note.strip() else "")
    _log(
        db,
        patient,
        InteractionKind.SCHEDULE_FOLLOWUP,
        detail,
        TimeLogActivity.CARE_COORDINATION,
        seconds=120,
    )
    notification = Notification(
        patient_id=patient_id,
        recipient_id=patient.assigned_provider_id,
        kind="followup",
        title=f"{patient.name} — follow-up scheduled",
        body=detail,
        channel=NotificationChannel.IN_APP,
    )
    db.add(notification)
    db.commit()
    return {"ok": True, "detail": detail}


class PlanUpdateBody(BaseModel):
    summary: str


@router.post("/patients/{patient_id}/actions/update-plan")
def update_plan(patient_id: str, body: PlanUpdateBody, db: Session = Depends(get_db)) -> dict:
    patient = _get_patient(db, patient_id)
    summary = body.summary.strip()
    if not summary:
        raise HTTPException(status_code=422, detail="Plan update summary is required")
    _log(
        db,
        patient,
        InteractionKind.UPDATE_PLAN,
        summary,
        TimeLogActivity.CHART_REVIEW,
        seconds=180,
    )
    db.commit()
    return {"ok": True}


class ReviewTimeBody(BaseModel):
    seconds: int


@router.post("/patients/{patient_id}/rtm/review-time")
def log_review_time(patient_id: str, body: ReviewTimeBody, db: Session = Depends(get_db)) -> dict:
    """Background chart-review time from the UI timer — batched, capped, quiet."""
    patient = _get_patient(db, patient_id)
    seconds = max(0, min(body.seconds, 30 * 60))
    if seconds < 15:
        return {"ok": True, "logged_seconds": 0}
    now = datetime.now()
    db.add(
        ProviderTimeLog(
            patient_id=patient.id,
            provider_id=patient.assigned_provider_id,
            activity=TimeLogActivity.CHART_REVIEW,
            seconds=seconds,
            interactive=False,
            note="Chart review (auto-tracked)",
            occurred_at=now,
            month=f"{now.year:04d}-{now.month:02d}",
        )
    )
    db.commit()
    return {"ok": True, "logged_seconds": seconds}


@router.get("/patients/{patient_id}/rtm/documents")
def rtm_documents(patient_id: str, db: Session = Depends(get_db)) -> dict:
    """This month's documentation, generating drafts on demand."""
    from app.llm.documentation import get_document

    patient = _get_patient(db, patient_id)
    documents = [
        get_document(db, patient, DocumentKind.ENCOUNTER_NOTE),
        get_document(db, patient, DocumentKind.MONTHLY_SUMMARY),
    ]
    return {
        "documents": [
            {
                "id": d.id,
                "kind": str(d.kind),
                "title": d.content.get("title", ""),
                "body": d.content.get("body", ""),
                "status": str(d.status),
                "provider": d.llm_provider,
                "created_at": d.created_at.isoformat(),
                "approved_at": d.approved_at.isoformat() if d.approved_at else None,
            }
            for d in documents
        ]
    }


@router.post("/patients/{patient_id}/rtm/documents/{document_id}/approve")
def approve_document(patient_id: str, document_id: int, db: Session = Depends(get_db)) -> dict:
    patient = _get_patient(db, patient_id)
    document = db.get(RtmDocument, document_id)
    if document is None or document.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Unknown document")
    if document.status != DocumentStatus.APPROVED:
        document.status = DocumentStatus.APPROVED
        document.approved_at = datetime.now()
        document.approved_by = patient.assigned_provider_id
        db.commit()
    return {"ok": True, "status": str(document.status)}


@router.post("/patients/{patient_id}/rtm/documents/{document_id}/regenerate")
def regenerate_document(patient_id: str, document_id: int, db: Session = Depends(get_db)) -> dict:
    from app.llm.documentation import get_document

    patient = _get_patient(db, patient_id)
    document = db.get(RtmDocument, document_id)
    if document is None or document.patient_id != patient_id:
        raise HTTPException(status_code=404, detail="Unknown document")
    if document.status == DocumentStatus.APPROVED:
        raise HTTPException(status_code=409, detail="Approved documentation is signed")
    fresh = get_document(db, patient, DocumentKind(document.kind), force=True)
    return {
        "ok": True,
        "document": {
            "id": fresh.id,
            "kind": str(fresh.kind),
            "title": fresh.content.get("title", ""),
            "body": fresh.content.get("body", ""),
            "status": str(fresh.status),
            "provider": fresh.llm_provider,
        },
    }


@router.get("/practice/overview")
def get_practice_overview(db: Session = Depends(get_db)) -> dict:
    from app.rtm.readiness import practice_overview

    return practice_overview(db)
