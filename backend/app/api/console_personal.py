"""The console's Personal version: the demo members' spaces, read-only.

Every route answers 404 unless ``DEMO_MODE`` is on, the console is staff
scope, and the row is a generated member (``app/personal/showcase.py``). A
real subscriber's space is never listed or opened here: there is no id that
unlocks one, whatever the scope.

The pages show a member's space as the member sees it, so each read is the
phone's own computation over the same rows (``compute_dashboard`` and
friends), minus anything that writes: the brief and the deep dives are read
with ``insights.peek_*`` (what is stored for today's numbers, else the
deterministic text rendered in memory), the care section from the stored
assessment. The one write is the coach, and it is a POST.

    GET  /api/console/personal/members
    GET  /api/console/personal/{id}/overview
    GET  /api/console/personal/{id}/week
    GET  /api/console/personal/{id}/signals
    GET  /api/console/personal/{id}/insights/{domain}
    GET  /api/console/personal/{id}/export
    POST /api/console/personal/{id}/coach
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import mobile
from app.api.auth import ConsoleScope, console_scope
from app.config import settings
from app.database import get_db
from app.models.mobile import Message
from app.models.patient import Device, Patient
from app.models.personal import GOAL_LABELS, PersonalLog, PersonalProfile
from app.personal import api as personal_api
from app.personal import insights, showcase, subscription
from app.personal.data import load_personal_data
from app.personal.metrics import compute_dashboard
from app.tasks import service as tasks

router = APIRouter(prefix="/console/personal", tags=["console-personal"])

UNKNOWN_MEMBER = "Unknown member"
THREAD_LINES = 40
LOG_DAYS = 30


def _staff_on_demo(scope: ConsoleScope = Depends(console_scope)) -> ConsoleScope:
    """The Personal version exists on the demo stack, for a staff console.
    Anywhere else it is not there at all: 404, not 403."""
    if not settings.demo_mode or not scope.staff:
        raise HTTPException(status_code=404, detail="Not found")
    return scope


def _member(
    member_id: str,
    _scope: ConsoleScope = Depends(_staff_on_demo),
    db: Session = Depends(get_db),
) -> Patient:
    """The generated member a route is about, or 404: a real subscriber's
    id, a clinic chart's and an athlete's all answer the same."""
    patient = db.get(Patient, member_id)
    if not showcase.is_showcase(db, patient):
        raise HTTPException(status_code=404, detail=UNKNOWN_MEMBER)
    return patient


def _profile(db: Session, patient: Patient) -> PersonalProfile:
    profile = db.get(PersonalProfile, patient.id)
    if profile is None:  # is_showcase read it a moment ago; kept for the type
        raise HTTPException(status_code=404, detail=UNKNOWN_MEMBER)
    return profile


def _board(db: Session, patient: Patient, profile: PersonalProfile) -> dict[str, Any]:
    """The member's readouts, computed in memory from what is stored."""
    return compute_dashboard(load_personal_data(db, patient), patient, profile)


def _public(board: dict[str, Any]) -> dict[str, Any]:
    """The dashboard as the phone receives it (the digest and the notes are
    the model's context, not a screen)."""
    return {k: v for k, v in board.items() if k not in ("digest", "notes")}


def _extra(board: dict[str, Any], panel: str, key: str) -> Any:
    return (((board.get("panels") or {}).get(panel) or {}).get("extra") or {}).get(key)


def _last_sync(db: Session, patient_id: str) -> str | None:
    stamp = db.scalar(
        select(Device.last_sync_at).where(Device.patient_id == patient_id)
        .order_by(Device.last_sync_at.desc()).limit(1)
    )
    return stamp.isoformat() if stamp else None


def _member_view(db: Session, patient: Patient, profile: PersonalProfile) -> dict[str, Any]:
    mark = showcase.mark_of(db, patient)
    devices = db.scalars(
        select(Device).where(Device.patient_id == patient.id).order_by(Device.connected_at)
    ).all()
    return {
        "id": patient.id,
        "name": patient.name,
        "initials": patient.initials,
        "age": patient.age,
        "goal": profile.goal,
        "goal_label": GOAL_LABELS.get(profile.goal, profile.goal),
        "sport": profile.sport,
        "tagline": mark.get("tagline") or GOAL_LABELS.get(profile.goal, profile.goal),
        "detail": mark.get("detail") or "",
        "hero": bool(mark.get("hero")),
        "joined_on": patient.created_at.date().isoformat() if patient.created_at else None,
        "devices": [
            {"provider": str(d.source_provider), "model": d.device_model,
             "connected_at": d.connected_at.isoformat() if d.connected_at else None,
             "last_sync_at": d.last_sync_at.isoformat() if d.last_sync_at else None}
            for d in devices
        ],
    }


@router.get("/members")
def members(
    _scope: ConsoleScope = Depends(_staff_on_demo), db: Session = Depends(get_db)
) -> dict:
    """Every demo member with the line a list needs: today's verdict, the
    readiness figure, last night and the debt, the week's load."""
    rows = []
    for patient in showcase.members(db):
        profile = _profile(db, patient)
        board = _board(db, patient, profile)
        week_load = ((board.get("week") or {}).get("metrics") or {}).get("load") or {}
        rows.append({
            **_member_view(db, patient, profile),
            "days_with_data": board.get("days_with_data"),
            "verdict": {k: (board.get("verdict") or {}).get(k) for k in ("kind", "title")},
            "readiness": {
                "score": _extra(board, "readiness", "score"),
                "band": _extra(board, "readiness", "band"),
            },
            "sleep": {
                "last_night_h": _extra(board, "sleep", "last_night_hours"),
                "need_h": _extra(board, "sleep", "need_hours"),
                "debt_h": _extra(board, "sleep", "debt_hours"),
            },
            "load": {
                "source": _extra(board, "load", "source"),
                "this_week": week_load.get("this"),
                "last_week": week_load.get("last"),
                "day_strain": _extra(board, "load", "day_strain"),
            },
            "last_sync": _last_sync(db, patient.id),
        })
    return {"as_of": date.today().isoformat(), "members": rows}


def _thread(db: Session, patient_id: str) -> list[dict[str, Any]]:
    rows = list(db.scalars(
        select(Message).where(Message.patient_id == patient_id)
        .order_by(Message.created_at.desc(), Message.id.desc()).limit(THREAD_LINES)
    ).all())
    rows.reverse()
    return [mobile._message_view(m) for m in rows]


def _logs(db: Session, patient_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The member's own entries over the last month, newest first: the
    numbers by day, and the notes."""
    since = date.today() - timedelta(days=LOG_DAYS - 1)
    rows = db.scalars(
        select(PersonalLog)
        .where(PersonalLog.patient_id == patient_id, PersonalLog.date >= since)
        .order_by(PersonalLog.date.desc(), PersonalLog.id.desc())
    ).all()
    days: dict[date, dict[str, Any]] = {}
    notes: list[dict[str, Any]] = []
    for row in rows:
        if row.key == "note":
            if row.text:
                notes.append({"date": row.date.isoformat(), "text": row.text, "source": row.source})
            continue
        if row.value_num is None:
            continue
        # newest first, so the first value seen for a day and key is the one that stands
        days.setdefault(row.date, {}).setdefault(row.key, row.value_num)
    logs = [{"date": day.isoformat(), **values} for day, values in sorted(days.items(), reverse=True)]
    return logs, notes


def _care(db: Session, patient: Patient, profile: PersonalProfile) -> dict[str, Any] | None:
    """The care section a recovery goal adds, from the assessment on file."""
    if profile.goal != "recovery":
        return None
    from app.engine.pipeline import latest_assessment

    assessment = latest_assessment(db, patient.id)
    return personal_api.care_view(assessment) if assessment is not None else None


@router.get("/{member_id}/overview")
def overview(patient: Patient = Depends(_member), db: Session = Depends(get_db)) -> dict:
    """One member's space in a single read: who they are, today's readouts
    exactly as their phone computes them, the brief, the plan, the thread
    with the coach, and what they logged."""
    profile = _profile(db, patient)
    board = _board(db, patient, profile)
    logs, notes = _logs(db, patient.id)
    return {
        "member": _member_view(db, patient, profile),
        "profile": personal_api._profile_view(profile),
        "subscription": subscription.status(db, patient),
        "dashboard": _public(board),
        "brief": insights.peek_brief(db, patient, board),
        "care": _care(db, patient, profile),
        "plan": {
            "open": [mobile._task_view(t) for t in tasks.open_tasks(db, patient.id)],
            "recent": [mobile._task_view(t) for t in tasks.recent_tasks(db, patient.id, limit=12)],
        },
        "thread": _thread(db, patient.id),
        "logs": logs,
        "notes": notes,
    }


@router.get("/{member_id}/week")
def week(patient: Patient = Depends(_member), db: Session = Depends(get_db)) -> dict:
    """This week against last, thirteen weeks of trends, and the review."""
    profile = _profile(db, patient)
    board = _board(db, patient, profile)
    return {
        "week": board.get("week"),
        "trends": board.get("trends"),
        "review": insights.peek_deep_dive(db, patient, board, "weekly"),
    }


@router.get("/{member_id}/signals")
def signals(
    days: int = Query(default=90, ge=3, le=90),
    patient: Patient = Depends(_member),
    db: Session = Depends(get_db),
) -> dict:
    """The raw daily signals behind the readouts, as the member's own
    "all metrics" screen lists them."""
    return mobile.portfolio_for(db, patient.observations_from or patient.id, days)


@router.get("/{member_id}/insights/{domain}")
def insight(domain: str, patient: Patient = Depends(_member), db: Session = Depends(get_db)) -> dict:
    if domain not in insights.DOMAINS:
        raise HTTPException(status_code=404, detail="Unknown insight")
    profile = _profile(db, patient)
    return insights.peek_deep_dive(db, patient, _board(db, patient, profile), domain)


@router.get("/{member_id}/export")
def export(patient: Patient = Depends(_member), db: Session = Depends(get_db)) -> dict:
    """Everything the member's account holds, as the one document their own
    "Export my data" produces."""
    return personal_api.export_bundle(db, patient, _profile(db, patient))


class CoachBody(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


@router.post("/{member_id}/coach")
def coach(body: CoachBody, patient: Patient = Depends(_member), db: Session = Depends(get_db)) -> dict:
    """One turn with the member's coach, as the member: the same function
    their phone calls, with today's readouts in context. Both lines land on
    the member's thread. With no model configured the reply is the
    deterministic one, and ``provider`` says so."""
    from app.personal import coach as personal_coach

    profile = _profile(db, patient)
    result = personal_coach.respond(db, patient, profile, _board(db, patient, profile),
                                    body.text.strip(), channel="app")
    return {
        "reply": result.get("reply"),
        "provider": result.get("provider"),
        "flagged": bool(result.get("flagged")),
        "thread": _thread(db, patient.id),
    }
