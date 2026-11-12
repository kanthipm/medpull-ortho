"""The between-visits record over HTTP (``app/pt``; contract in docs/dev/pt.md).

Three routers:

* ``router`` — the console's, under ``/api/pt``, behind the console's door.
  Clinic-level routes act for the clinic the console acts for (the exercise
  calendar's rule, ``hep.api._clinic``); a chart's routes act for that
  chart's own clinic, and answer 404 for a chart the console cannot see.
* ``mobile_router`` — the person's own, under ``/api/mobile/pt``, on their
  app session. Reads only: everything a person is asked arrives as a task.
* ``public_router`` — the trainer's page, ``/api/handoff/{token}``. No
  credential: the link is the permission, and it exists only once the
  person has agreed.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import ConsoleScope, console_scope
from app.api.mobile import current_patient
from app.api.scope import require_patient
from app.database import get_db
from app.hep.api import _base_url, _clinic, _ready
from app.hep.service import clinic_care_team
from app.models.mobile import Message
from app.models.patient import Patient
from app.personal.scope import is_clinic
from app.pt import measures, regions, service, triage
from app.pt import settings as pt_settings
from app.pt.instruments import catalog as instrument_catalog
from app.pt.service import PtError
from app.pt.settings import SettingError
from app.pt.triage import RedFlagError

router = APIRouter(prefix="/pt", tags=["pt"])
mobile_router = APIRouter(prefix="/mobile/pt", tags=["pt"])
public_router = APIRouter(prefix="/handoff", tags=["pt"])


def _refuse(err: Exception) -> HTTPException:
    return HTTPException(status_code=422, detail=str(err))


def _chart(patient_id: str, db: Session = Depends(_ready),
           scope: ConsoleScope = Depends(console_scope)) -> Patient:
    """The clinic chart a route is about; 404 for one this console cannot
    see, exactly as the chart's own page answers."""
    return require_patient(db, scope, patient_id)


class By(BaseModel):
    by: str | None = Field(default=None, max_length=60)


class Ask(By):
    # Also text the person (when their number can be texted).
    text: bool = True


# --- what the pages are built from -------------------------------------------------------


@router.get("/catalog")
def catalog(db: Session = Depends(_ready), clinic: str = Depends(_clinic)) -> dict:
    """The fixed lists the pages offer: body areas, tests, outcome measures
    (with this clinic's thresholds), visit kinds, and the clinic's own
    therapists to act as."""
    overrides = pt_settings.read(db, clinic)["outcome_thresholds"]
    return {
        "clinic": clinic,
        "areas": list(regions.AREAS), "midline": sorted(regions.MIDLINE),
        "sides": list(regions.SIDES),
        "tests": measures.catalog(), "holds": list(measures.HOLDS),
        "instruments": instrument_catalog(overrides),
        "visit_kinds": [{"key": k, "label": service.VISIT_LABELS[k]} for k in service.VISIT_KINDS],
        "care_team": clinic_care_team(db, clinic),
    }


# --- the clinic's settings and rules -------------------------------------------------------


class SettingsPatch(By):
    flags: dict[str, float | None] | None = None
    exercise_guard: int | None = None
    triage_words: list[str] | None = None
    morning_check: dict[str, Any] | None = None
    week_checkin: dict[str, Any] | None = None
    outcome_thresholds: dict[str, float | None] | None = None


@router.get("/settings")
def read_settings(db: Session = Depends(_ready), clinic: str = Depends(_clinic)) -> dict:
    return {"clinic": clinic, "settings": pt_settings.read(db, clinic),
            "defaults": pt_settings.DEFAULTS}


@router.patch("/settings")
def update_settings(body: SettingsPatch, db: Session = Depends(_ready),
                    clinic: str = Depends(_clinic)) -> dict:
    patch = body.model_dump(exclude_unset=True, exclude={"by"})
    try:
        current = pt_settings.update(db, clinic, patch, by=body.by)
    except SettingError as err:
        raise _refuse(err)
    return {"clinic": clinic, "settings": current, "defaults": pt_settings.DEFAULTS}


@router.get("/flags")
def flag_rules(db: Session = Depends(_ready), clinic: str = Depends(_clinic)) -> dict:
    """Each flag a chart followed by check-ins can raise: the rule in a
    sentence with this clinic's numbers in it, what it reads, its
    thresholds, and how often it has been up."""
    return {"clinic": clinic, "flags": pt_settings.flag_rules(db, clinic)}


class RedFlagBody(By):
    label: str | None = Field(default=None, max_length=120)
    phrases: list[str] | None = None
    text: str | None = Field(default=None, max_length=triage.TEXT_LIMIT)


class ApproveBody(BaseModel):
    by: str = Field(max_length=60)
    approved: bool = True


def _red_flags(db: Session, clinic: str) -> dict:
    rows = triage.ensure_entries(db, clinic)
    db.commit()
    return {"clinic": clinic, "entries": [triage.entry_view(r) for r in rows],
            "standing_reply": triage.STANDING_REPLY}


@router.get("/red-flags")
def red_flags(db: Session = Depends(_ready), clinic: str = Depends(_clinic)) -> dict:
    return _red_flags(db, clinic)


@router.post("/red-flags", status_code=201)
def create_red_flag(body: RedFlagBody, db: Session = Depends(_ready),
                    clinic: str = Depends(_clinic)) -> dict:
    try:
        triage.save_entry(db, clinic, entry_id=None, label=body.label, phrases=body.phrases,
                          text=body.text, by=body.by)
    except RedFlagError as err:
        raise _refuse(err)
    return _red_flags(db, clinic)


@router.patch("/red-flags/{entry_id}")
def update_red_flag(entry_id: int, body: RedFlagBody, db: Session = Depends(_ready),
                    clinic: str = Depends(_clinic)) -> dict:
    try:
        triage.save_entry(db, clinic, entry_id=entry_id, label=body.label, phrases=body.phrases,
                          text=body.text, by=body.by)
    except RedFlagError as err:
        raise _refuse(err)
    return _red_flags(db, clinic)


@router.post("/red-flags/{entry_id}/approve")
def approve_red_flag(entry_id: int, body: ApproveBody, db: Session = Depends(_ready),
                     clinic: str = Depends(_clinic)) -> dict:
    try:
        triage.approve_entry(db, clinic, entry_id, by=body.by, approved=body.approved)
    except RedFlagError as err:
        raise _refuse(err)
    return _red_flags(db, clinic)


@router.delete("/red-flags/{entry_id}")
def delete_red_flag(entry_id: int, db: Session = Depends(_ready),
                    clinic: str = Depends(_clinic)) -> dict:
    try:
        triage.delete_entry(db, clinic, entry_id)
    except RedFlagError as err:
        raise _refuse(err)
    return _red_flags(db, clinic)


# --- protocols -----------------------------------------------------------------------------


class ProtocolBody(By):
    name: str = Field(max_length=service.NAME_LIMIT)
    description: str = Field(default="", max_length=400)
    phases: list[dict[str, Any]]


def _protocols(db: Session, clinic: str) -> dict:
    return {"clinic": clinic,
            "protocols": [service.protocol_view(p) for p in service.protocols(db, clinic)]}


@router.get("/protocols")
def list_protocols(db: Session = Depends(_ready), clinic: str = Depends(_clinic)) -> dict:
    return _protocols(db, clinic)


@router.post("/protocols", status_code=201)
def create_protocol(body: ProtocolBody, db: Session = Depends(_ready),
                    clinic: str = Depends(_clinic)) -> dict:
    try:
        service.save_protocol(db, clinic, protocol_id=None, name=body.name,
                              description=body.description, phases=body.phases,
                              by=body.by or "provider")
    except PtError as err:
        raise _refuse(err)
    return _protocols(db, clinic)


@router.put("/protocols/{protocol_id}")
def update_protocol(protocol_id: int, body: ProtocolBody, db: Session = Depends(_ready),
                    clinic: str = Depends(_clinic)) -> dict:
    try:
        service.save_protocol(db, clinic, protocol_id=protocol_id, name=body.name,
                              description=body.description, phases=body.phases,
                              by=body.by or "provider")
    except PtError as err:
        raise _refuse(err)
    return _protocols(db, clinic)


@router.delete("/protocols/{protocol_id}")
def delete_protocol(protocol_id: int, db: Session = Depends(_ready),
                    clinic: str = Depends(_clinic)) -> dict:
    try:
        service.archive_protocol(db, clinic, protocol_id)
    except PtError as err:
        raise _refuse(err)
    return _protocols(db, clinic)


# --- questions -----------------------------------------------------------------------------


class QuestionMove(By):
    triage: str | None = Field(default=None, max_length=10)  # today | weekly | none
    done: bool | None = None


def _question_view(db: Session, m: Message, patients: dict[str, Patient]) -> dict:
    patient = patients[m.patient_id]
    return {
        "id": m.id, "patient_id": m.patient_id, "patient_name": patient.name,
        "initials": patient.initials, "text": m.text, "channel": m.channel,
        "created_at": m.created_at.isoformat(), "triage": m.triage,
        "sorted_by": "rule" if m.triage_by in (None, "rule") else "clinician",
        "sorted_by_name": service.member_name(db, m.triage_by),
        "red_flag": m.red_flag, "done": m.triage_done_at is not None,
        "done_at": m.triage_done_at.isoformat() if m.triage_done_at else None,
    }


@router.get("/questions")
def questions(days: int = Query(default=14, ge=1, le=60), db: Session = Depends(_ready),
              clinic: str = Depends(_clinic)) -> dict:
    """What the clinic's people asked, sorted: the ones for today, the ones
    for the weekly block, and the ones already dealt with. Sorted by rule
    (``app/pt/triage.py``) until a clinician moves one."""
    from datetime import datetime

    since = datetime.now() - timedelta(days=days)
    patients = {p.id: p for p in db.scalars(select(Patient).where(Patient.hospital_id == clinic))
                if is_clinic(p)}
    rows = db.scalars(
        select(Message).where(
            Message.patient_id.in_(list(patients) or [""]), Message.sender == "patient",
            Message.triage.is_not(None), Message.created_at >= since,
        ).order_by(Message.created_at.desc())
    ).all() if patients else []
    views = [_question_view(db, m, patients) for m in rows]
    open_views = [v for v in views if not v["done"]]
    return {
        "clinic": clinic, "days": days,
        "today": [v for v in open_views if v["triage"] == triage.TODAY],
        "weekly": [v for v in open_views if v["triage"] == triage.WEEKLY],
        "done": [v for v in views if v["done"]][:30],
        "words": pt_settings.read(db, clinic)["triage_words"],
    }


@router.post("/questions/{message_id}")
def move_question(message_id: int, body: QuestionMove, db: Session = Depends(_ready),
                  scope: ConsoleScope = Depends(console_scope)) -> dict:
    """Move a line between today and the weekly block, take it off the
    lists, or mark it dealt with. Nothing is sent to anyone."""
    from datetime import datetime

    message = db.get(Message, message_id)
    if message is None or message.sender != "patient":
        raise HTTPException(status_code=404, detail="Unknown message")
    require_patient(db, scope, message.patient_id)
    now = datetime.now()
    if body.triage is not None:
        if body.triage not in (triage.TODAY, triage.WEEKLY, "none"):
            raise HTTPException(status_code=422, detail="A line goes to today, weekly or none")
        if message.red_flag and body.triage != triage.TODAY:
            raise HTTPException(status_code=422,
                                detail="A line that matched a red flag stays on today")
        message.triage = None if body.triage == "none" else body.triage
        message.triage_by, message.triage_at = body.by or "clinician", now
    if body.done is not None:
        message.triage_done_at = now if body.done else None
    db.commit()
    return {"ok": True, "id": message.id, "triage": message.triage,
            "done": message.triage_done_at is not None}


# --- one chart -----------------------------------------------------------------------------


@router.get("/patients/{patient_id}")
def read_chart(request: Request, patient: Patient = Depends(_chart),
               db: Session = Depends(_ready)) -> dict:
    return service.chart(db, patient, date.today(), _base_url(request))


def _after(request: Request, db: Session, patient: Patient, **extra: Any) -> dict:
    return {**service.chart(db, patient, date.today(), _base_url(request)), **extra}


class PatientSettingsPatch(By):
    morning_check: dict[str, Any] | None = None
    week_checkin: dict[str, Any] | None = None


@router.patch("/patients/{patient_id}/settings")
def update_patient_settings(body: PatientSettingsPatch, request: Request,
                            patient: Patient = Depends(_chart),
                            db: Session = Depends(_ready)) -> dict:
    try:
        pt_settings.patient_update(db, patient.id, patient.hospital_id,
                                   body.model_dump(exclude_unset=True, exclude={"by"}), by=body.by)
    except SettingError as err:
        raise _refuse(err)
    return _after(request, db, patient)


class AreaBody(By):
    area: str = Field(max_length=40)
    side: str | None = Field(default=None, max_length=10)
    source: str = "evaluation"
    note: str | None = Field(default=None, max_length=300)


@router.post("/patients/{patient_id}/areas", status_code=201)
def add_area(body: AreaBody, request: Request, patient: Patient = Depends(_chart),
             db: Session = Depends(_ready)) -> dict:
    try:
        service.add_area(db, patient, area=body.area, side=body.side, source=body.source,
                         note=body.note, by=body.by, today=date.today())
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/areas/{area_id}/seen")
def area_seen(area_id: int, request: Request, patient: Patient = Depends(_chart),
              db: Session = Depends(_ready)) -> dict:
    try:
        service.mark_area_seen(db, patient, area_id, date.today())
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.delete("/patients/{patient_id}/areas/{area_id}")
def remove_area(area_id: int, request: Request, patient: Patient = Depends(_chart),
                db: Session = Depends(_ready)) -> dict:
    try:
        service.remove_area(db, patient, area_id)
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


class MorningAsk(Ask):
    session_day: date | None = None


@router.post("/patients/{patient_id}/morning/ask")
def ask_morning(body: MorningAsk, request: Request, patient: Patient = Depends(_chart),
                db: Session = Depends(_ready)) -> dict:
    today = date.today()
    try:
        _row, text = service.ask_morning(
            db, patient, session_day=body.session_day or today - timedelta(days=1), today=today,
            by=body.by, notify=body.text, base_url=_base_url(request))
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient, sent=text)


class GoalBody(By):
    text: str = Field(max_length=200)


class RateBody(By):
    scores: dict[int, int]
    on: date | None = None


@router.post("/patients/{patient_id}/goals", status_code=201)
def add_goal(body: GoalBody, request: Request, patient: Patient = Depends(_chart),
             db: Session = Depends(_ready)) -> dict:
    try:
        service.add_goal(db, patient, body.text, by=body.by or "provider")
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.delete("/patients/{patient_id}/goals/{goal_id}")
def end_goal(goal_id: int, request: Request, patient: Patient = Depends(_chart),
             db: Session = Depends(_ready)) -> dict:
    try:
        service.end_goal(db, patient, goal_id)
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/goals/rate")
def rate_goals(body: RateBody, request: Request, patient: Patient = Depends(_chart),
               db: Session = Depends(_ready)) -> dict:
    day = body.on or date.today()
    if day > date.today():
        raise HTTPException(status_code=422, detail="A rating cannot be dated in the future")
    try:
        service.rate_now(db, patient, body.scores, day)
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/goals/ask")
def ask_goals(body: Ask, request: Request, patient: Patient = Depends(_chart),
              db: Session = Depends(_ready)) -> dict:
    """Ask the person to name what they want to get back to."""
    try:
        text = service.ask_goals(db, patient, by=body.by, notify=body.text,
                                 base_url=_base_url(request))
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient, sent=text)


@router.post("/patients/{patient_id}/goals/ask-rating")
def ask_function(body: Ask, request: Request, patient: Patient = Depends(_chart),
                 db: Session = Depends(_ready)) -> dict:
    try:
        text = service.ask_function(db, patient, by=body.by, notify=body.text,
                                    base_url=_base_url(request))
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient, sent=text)


@router.post("/patients/{patient_id}/week/ask")
def ask_week(body: Ask, request: Request, patient: Patient = Depends(_chart),
             db: Session = Depends(_ready)) -> dict:
    try:
        _row, text = service.ask_week(db, patient, today=date.today(), by=body.by,
                                      notify=body.text, base_url=_base_url(request))
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient, sent=text)


class PhasesBody(By):
    protocol_id: int | None = None
    name: str | None = Field(default=None, max_length=service.NAME_LIMIT)
    phases: list[dict[str, Any]] | None = None


class CriterionBody(BaseModel):
    by: str = Field(max_length=60)
    met: bool = True


class AdvanceBody(BaseModel):
    by: str = Field(max_length=60)
    with_unmet: bool = False


@router.put("/patients/{patient_id}/phases")
def set_phases(body: PhasesBody, request: Request, patient: Patient = Depends(_chart),
               db: Session = Depends(_ready)) -> dict:
    if (body.protocol_id is None) == (body.phases is None):
        raise HTTPException(status_code=422, detail="Send a protocol, or phases, not both")
    try:
        service.set_phases(db, patient, protocol_id=body.protocol_id, phases=body.phases,
                           name=body.name, by=body.by or "provider", today=date.today())
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/phases/{phase_id}/criteria/{index}")
def tick_criterion(phase_id: int, index: int, body: CriterionBody, request: Request,
                   patient: Patient = Depends(_chart), db: Session = Depends(_ready)) -> dict:
    try:
        service.set_criterion(db, patient, phase_id, index, met=body.met, by=body.by)
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/phases/advance")
def advance_phase(body: AdvanceBody, request: Request, patient: Patient = Depends(_chart),
                  db: Session = Depends(_ready)) -> dict:
    """The clinician moves the person to the next phase. With criteria still
    unticked the answer is 409 naming them, until ``with_unmet`` is sent."""
    try:
        service.advance_phase(db, patient, by=body.by, today=date.today(),
                              with_unmet=body.with_unmet)
    except PtError as err:
        text = str(err)
        raise HTTPException(status_code=409 if "not ticked" in text else 422, detail=text)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/phases/back")
def step_back(body: ApproveBody, request: Request, patient: Patient = Depends(_chart),
              db: Session = Depends(_ready)) -> dict:
    try:
        service.step_back_phase(db, patient, by=body.by, today=date.today())
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


class TestBody(By):
    tested_on: date | None = None
    kind: str = Field(max_length=40)
    label: str | None = Field(default=None, max_length=80)
    side: str | None = Field(default=None, max_length=10)
    value: float
    unit: str | None = Field(default=None, max_length=12)
    note: str | None = Field(default=None, max_length=300)


class HoldAsk(Ask):
    kind: str = Field(max_length=40)


@router.post("/patients/{patient_id}/tests", status_code=201)
def add_test(body: TestBody, request: Request, patient: Patient = Depends(_chart),
             db: Session = Depends(_ready)) -> dict:
    today = date.today()
    try:
        service.add_measurement(
            db, patient, tested_on=body.tested_on or today, kind=body.kind, label=body.label,
            side=body.side, value=body.value, unit=body.unit, note=body.note, by=body.by,
            today=today)
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.delete("/patients/{patient_id}/tests/{measurement_id}")
def remove_test(measurement_id: int, request: Request, patient: Patient = Depends(_chart),
                db: Session = Depends(_ready)) -> dict:
    try:
        service.remove_measurement(db, patient, measurement_id)
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/tests/ask-hold")
def ask_hold(body: HoldAsk, request: Request, patient: Patient = Depends(_chart),
             db: Session = Depends(_ready)) -> dict:
    try:
        text = service.ask_hold(db, patient, body.kind, by=body.by, notify=body.text,
                                base_url=_base_url(request))
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient, sent=text)


class ScheduleBody(By):
    every_days: int = Field(ge=service.OUTCOME_MIN_DAYS, le=service.OUTCOME_MAX_DAYS)
    start: date | None = None


class ScoreBody(By):
    total: float
    on: date | None = None


@router.put("/patients/{patient_id}/outcomes/{instrument}/schedule")
def set_outcome_schedule(instrument: str, body: ScheduleBody, request: Request,
                         patient: Patient = Depends(_chart), db: Session = Depends(_ready)) -> dict:
    try:
        service.set_outcome_schedule(db, patient, instrument, every_days=body.every_days,
                                     start=body.start or date.today(), by=body.by or "provider")
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.delete("/patients/{patient_id}/outcomes/{instrument}/schedule")
def stop_outcome_schedule(instrument: str, request: Request, patient: Patient = Depends(_chart),
                          db: Session = Depends(_ready)) -> dict:
    try:
        service.stop_outcome_schedule(db, patient, instrument)
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/outcomes/{instrument}/scores", status_code=201)
def add_score(instrument: str, body: ScoreBody, request: Request,
              patient: Patient = Depends(_chart), db: Session = Depends(_ready)) -> dict:
    today = date.today()
    try:
        service.add_score(db, patient, instrument, body.total, body.on or today, by=body.by,
                          today=today)
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/outcomes/{instrument}/ask")
def ask_outcome(instrument: str, body: Ask, request: Request,
                patient: Patient = Depends(_chart), db: Session = Depends(_ready)) -> dict:
    try:
        text = service.ask_outcome(db, patient, instrument, by=body.by, notify=body.text,
                                   base_url=_base_url(request))
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient, sent=text)


class HandoffBody(By):
    trainer_name: str = Field(default="", max_length=service.NAME_LIMIT)
    limits: list[str] = Field(default_factory=list)
    report_back: str = Field(default="", max_length=400)
    include_week: bool = True


@router.put("/patients/{patient_id}/handoff")
def save_handoff(body: HandoffBody, request: Request, patient: Patient = Depends(_chart),
                 db: Session = Depends(_ready)) -> dict:
    try:
        service.save_handoff(db, patient, trainer_name=body.trainer_name, limits=body.limits,
                             report_back=body.report_back, include_week=body.include_week,
                             by=body.by or "provider")
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


@router.post("/patients/{patient_id}/handoff/request")
def request_handoff(body: Ask, request: Request, patient: Patient = Depends(_chart),
                    db: Session = Depends(_ready)) -> dict:
    """Ask the person whether the page may be shared. No link until yes."""
    try:
        _row, text = service.request_handoff(db, patient, by=body.by, notify=body.text,
                                             base_url=_base_url(request))
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient, sent=text)


@router.post("/patients/{patient_id}/handoff/revoke")
def revoke_handoff(request: Request, patient: Patient = Depends(_chart),
                   db: Session = Depends(_ready)) -> dict:
    try:
        service.revoke_handoff(db, patient)
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient)


class VisitBody(By):
    on: date
    at: str | None = Field(default=None, max_length=5)
    kind: str = "visit"
    note: str | None = Field(default=None, max_length=300)


class MarkBody(By):
    day: date
    kind: str = "rest"
    note: str | None = Field(default=None, max_length=200)


@router.post("/patients/{patient_id}/visits", status_code=201)
def add_visit(body: VisitBody, request: Request, patient: Patient = Depends(_chart),
              db: Session = Depends(_ready)) -> dict:
    try:
        visit = service.add_visit(db, patient.hospital_id, patient, visit_on=body.on, at=body.at,
                                  kind=body.kind, note=body.note, by=body.by or "provider",
                                  today=date.today())
    except PtError as err:
        raise _refuse(err)
    return _after(request, db, patient, visit=service.visit_view(db, visit))


@router.delete("/visits/{visit_id}")
def remove_visit(visit_id: int, db: Session = Depends(_ready),
                 clinic: str = Depends(_clinic)) -> dict:
    try:
        service.remove_visit(db, clinic, visit_id)
    except PtError as err:
        raise HTTPException(status_code=404, detail=str(err))
    return {"ok": True}


@router.post("/patients/{patient_id}/marks", status_code=201)
def set_mark(body: MarkBody, patient: Patient = Depends(_chart),
             db: Session = Depends(_ready)) -> dict:
    try:
        mark = service.set_mark(db, patient.hospital_id, patient, day=body.day, kind=body.kind,
                                note=body.note, by=body.by or "provider")
    except PtError as err:
        raise _refuse(err)
    return {"mark": service.mark_view(mark)}


@router.delete("/marks/{mark_id}")
def clear_mark(mark_id: int, db: Session = Depends(_ready),
               clinic: str = Depends(_clinic)) -> dict:
    try:
        service.clear_mark(db, clinic, mark_id)
    except PtError as err:
        raise HTTPException(status_code=404, detail=str(err))
    return {"ok": True}


# --- a clip, looked at closely -------------------------------------------------------------


class CommentBody(BaseModel):
    by: str = Field(max_length=60)
    at_ms: int | None = Field(default=None, ge=0)
    text: str | None = Field(default=None, max_length=400)
    voice_attachment_id: int | None = None


def _assignment_clinic(assignment_id: int, db: Session, scope: ConsoleScope) -> str:
    from app.hep.models import ExerciseAssignment

    row = db.get(ExerciseAssignment, assignment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown exercise day")
    require_patient(db, scope, row.patient_id)
    return row.hospital_id


@router.get("/assignments/{assignment_id}/clip")
def clip_detail(assignment_id: int, db: Session = Depends(_ready),
                scope: ConsoleScope = Depends(console_scope)) -> dict:
    """What a close look at one clip needs: the comments on it, and the same
    person's earlier clips of the same exercise to set beside it."""
    clinic = _assignment_clinic(assignment_id, db, scope)
    return {"comments": service.comments(db, clinic, assignment_id),
            "earlier": service.earlier_clips(db, clinic, assignment_id)}


@router.post("/assignments/{assignment_id}/comments", status_code=201)
def add_comment(assignment_id: int, body: CommentBody, db: Session = Depends(_ready),
                scope: ConsoleScope = Depends(console_scope)) -> dict:
    clinic = _assignment_clinic(assignment_id, db, scope)
    try:
        comment = service.add_comment(db, clinic, assignment_id, at_ms=body.at_ms, text=body.text,
                                      voice_attachment_id=body.voice_attachment_id, by=body.by)
        service.voice_to_thread(db, comment)
    except PtError as err:
        raise _refuse(err)
    return {"comments": service.comments(db, clinic, assignment_id)}


@router.delete("/comments/{comment_id}")
def remove_comment(comment_id: int, db: Session = Depends(_ready),
                   scope: ConsoleScope = Depends(console_scope)) -> dict:
    from app.pt.models import ClipComment

    row = db.get(ClipComment, comment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown comment")
    clinic = _assignment_clinic(row.assignment_id, db, scope)
    assignment_id = row.assignment_id
    service.remove_comment(db, clinic, comment_id)
    return {"comments": service.comments(db, clinic, assignment_id)}


# --- the person's own side -----------------------------------------------------------------


@mobile_router.get("")
def mine(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    """What a person's own app shows of the between-visits record: the next
    visit, a rest day, the phase they are in, their goals and their own
    ratings, and whether a trainer page is shared."""
    if not is_clinic(patient):
        return {"next_visit": None, "rest_day": None, "phase": None, "goals": [], "handoff": None}
    return service.patient_side(db, patient, date.today())


# --- the trainer's page --------------------------------------------------------------------


@public_router.get("/{token}")
def handoff_page(token: str, db: Session = Depends(get_db)) -> dict:
    page = service.handoff_page(db, token, date.today())
    if page is None:
        raise HTTPException(status_code=404, detail="This link is not active")
    return page
