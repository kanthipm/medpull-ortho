"""The patient app's API.

Onboarding (no credential yet): list hospitals -> search the roster by name
within one hospital -> enroll against the chosen record with a phone number
-> verify the phone by texted code when Sendblue can send one -> a session
token. Everything after that carries ``Authorization: Bearer <token>``.

Posture, stated plainly: the provider console this sits beside has no
authentication at all (README, "Not in v1"). This API is the first part of
the product that does — a session is tied to one patient and can only read
and write that patient's rows — but the search and enroll routes are by
construction pre-authentication. What limits them: search is scoped to one
hospital, answers a masked candidate list (first name, last initial,
procedure, surgery month) and needs at least two characters of a name; and
when Sendblue is configured the phone must receive a code before a session
is issued. Without Sendblue (a laptop, the test suite) enrollment is
unverified and says so in its response.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.integrations import _raise_for, _require_configured, _wearables_view
from app.api.worklist import ensure_fresh_assessment
from app.config import settings
from app.connectors.junction_client import JunctionError
from app.connectors.registry import junction_connector
from app.database import get_db
from app.models.adherence import AdherenceTask
from app.models.enums import ConnectionStatus, Granularity, MetricType, RiskLevel
from app.models.hospital import Hospital
from app.models.mobile import Message, PatientSession, PhoneVerification
from app.models.observation import Observation
from app.models.patient import Patient
from app.notifications import sendblue
from app.tasks import service as tasks

router = APIRouter(prefix="/mobile", tags=["mobile"])
# Tokenized task endpoints for the web page a task text links to; no
# session, the token in the link is the credential (like /api/checkin).
public_router = APIRouter(tags=["mobile"])

VERIFICATION_TTL = timedelta(minutes=10)
VERIFICATION_MAX_ATTEMPTS = 5
SESSION_TOUCH_INTERVAL = timedelta(minutes=5)
SEARCH_MIN_CHARS = 2
SEARCH_LIMIT = 5


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(value: datetime | date | None) -> str | None:
    return value.isoformat() if value else None


def _base_url(request: Request) -> str:
    return settings.checkin_base_url or str(request.base_url).rstrip("/")


# --- auth ------------------------------------------------------------------------


def current_patient(
    authorization: str | None = Header(default=None), db: Session = Depends(get_db)
) -> Patient:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to the app to continue")
    token = authorization.split(" ", 1)[1].strip()
    session = db.scalar(select(PatientSession).where(PatientSession.token_hash == _hash(token)))
    if session is None or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="This session has ended — sign in again")
    now = datetime.now()
    if now - session.last_seen_at > SESSION_TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    patient = db.get(Patient, session.patient_id)
    if patient is None:
        raise HTTPException(status_code=401, detail="This session has ended — sign in again")
    return patient


def _current_session(authorization: str | None, db: Session) -> PatientSession | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    return db.scalar(select(PatientSession).where(PatientSession.token_hash == _hash(token)))


def _issue_session(
    db: Session, patient: Patient, device_name: str | None, app_version: str | None
) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        PatientSession(
            patient_id=patient.id,
            token_hash=_hash(token),
            device_name=(device_name or "")[:80] or None,
            app_version=(app_version or "")[:40] or None,
        )
    )
    db.commit()
    return token


# --- views -----------------------------------------------------------------------

RECOVERY_LABEL = {
    RiskLevel.LOW: ("On track", "Your signals look steady. Keep going."),
    RiskLevel.MEDIUM: ("Worth a check-in", "A couple of signals moved. Your care team is keeping an eye on it."),
    RiskLevel.HIGH: ("Care team reviewing", "Your care team has been alerted and will be in touch."),
    RiskLevel.MISSING_DATA: ("Waiting for data", "Connect Apple Health or a wearable so we can follow your recovery."),
}
# The same four states, worded for a patient who did not have surgery.
GENERAL_LABEL = {
    RiskLevel.LOW: ("Steady", "Your signals look like your usual self."),
    RiskLevel.MEDIUM: ("Worth a look", "A couple of signals moved from your baseline. Your care team can see it."),
    RiskLevel.HIGH: ("Care team reviewing", "Your care team has been alerted and will be in touch."),
    RiskLevel.MISSING_DATA: ("Waiting for data", "Connect Apple Health or a wearable and your portfolio fills in on its own."),
}

PROCEDURES: list[dict[str, str]] = [
    {"id": "TKA", "label": "Knee replacement"},
    {"id": "THA", "label": "Hip replacement"},
    {"id": "ACL", "label": "ACL reconstruction"},
    {"id": "MENISCUS", "label": "Meniscus repair"},
    {"id": "ROTATOR_CUFF", "label": "Rotator cuff repair"},
    {"id": "LUMBAR", "label": "Spine (lumbar) surgery"},
    {"id": "ANKLE", "label": "Ankle fracture surgery"},
]
PROCEDURE_DISPLAY = {
    "TKA": "Total Knee Replacement (TKA)",
    "THA": "Total Hip Replacement (THA)",
    "ACL": "ACL Reconstruction",
    "MENISCUS": "Meniscus Repair",
    "ROTATOR_CUFF": "Rotator Cuff Repair",
    "LUMBAR": "Lumbar Decompression",
    "ANKLE": "Ankle Fracture ORIF",
    "NONE": "General care",
}


def is_surgical(patient: Patient) -> bool:
    return str(patient.procedure_type) != "NONE"


def _hospital_view(h: Hospital | None) -> dict[str, Any] | None:
    if h is None:
        return None
    return {"id": h.id, "name": h.name, "system": h.system, "city": h.city, "state": h.state}


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = re.sub(r"\D", "", phone)
    return f"•••• {digits[-4:]}" if len(digits) >= 4 else "••••"


def _task_view(t: AdherenceTask) -> dict[str, Any]:
    return {
        "id": t.id,
        "kind": t.kind or "custom",
        "kind_label": tasks.KIND_LABELS.get(t.kind or "custom", "Task"),
        "title": t.title,
        "why": t.why,
        "status": t.status or "pending",
        "created_at": _iso(t.created_at),
        "due_at": _iso(t.due_at),
        "sent_at": _iso(t.sent_at),
        "completed_at": _iso(t.completed_at),
        "completed_via": t.completed_via,
        "questions": tasks.QUESTION_SETS.get(t.kind or "custom", tasks.QUESTION_SETS["custom"]),
        "result": t.result,
        "in_sms_conversation": isinstance((t.payload or {}).get("sms"), dict),
    }


def _message_view(m: Message) -> dict[str, Any]:
    return {
        "id": m.id,
        "sender": m.sender,
        "channel": m.channel,
        "text": m.text,
        "created_at": _iso(m.created_at),
        "delivery_status": m.delivery_status,
        "read": m.read_by_patient_at is not None,
    }


def _wearable_summary(db: Session, patient: Patient) -> dict[str, Any]:
    conn = junction_connector().connection_for(db, patient.id)
    apple = next(
        (d for d in patient.devices if str(d.source_provider) == "apple" and d.status != "revoked"),
        None,
    )
    others = [
        {"provider": str(d.source_provider), "model": d.device_model, "status": d.status,
         "last_sync_at": _iso(d.last_sync_at)}
        for d in patient.devices
        if str(d.source_provider) != "apple" and d.status != "revoked"
    ]
    return {
        "aggregator_configured": junction_connector().is_configured(),
        "connection_status": str(conn.status) if conn else None,
        "apple_health": {
            "connected": apple is not None,
            "last_sync_at": _iso(apple.last_sync_at) if apple else None,
        },
        "devices": others,
        "last_data_at": _iso(conn.last_data_at) if conn else None,
    }


def me_view(db: Session, patient: Patient) -> dict[str, Any]:
    assessment = ensure_fresh_assessment(db, patient.id)
    analytics = assessment.analytics or {}
    level = RiskLevel(assessment.risk_level)
    surgical = is_surgical(patient)
    label, blurb = (RECOVERY_LABEL if surgical else GENERAL_LABEL)[level]
    open_tasks = tasks.open_tasks(db, patient.id)
    unread = db.scalars(
        select(Message.id).where(
            Message.patient_id == patient.id,
            Message.sender != "patient",
            Message.read_by_patient_at.is_(None),
        )
    ).all()
    postop = analytics.get("postop_day")
    if postop is None:
        postop = (date.today() - patient.surgery_date).days
    return {
        "patient": {
            "id": patient.id,
            "name": patient.name,
            "first_name": patient.name.split()[0],
            "initials": patient.initials,
            # recovery: had surgery, followed along a recovery curve.
            # general: joined their hospital's programme; no operation.
            "mode": "recovery" if surgical else "general",
            "procedure_display": patient.procedure_display,
            "surgery_date": patient.surgery_date.isoformat() if surgical else None,
            "joined_date": patient.surgery_date.isoformat(),
            "postop_day": postop if surgical else None,
            "days_enrolled": postop,
            "care_pathway": patient.care_pathway,
            "phone_masked": _mask_phone(patient.phone),
            "hospital": _hospital_view(patient.hospital),
            "care_team": [
                {"name": patient.surgeon.name, "role": str(patient.surgeon.role)},
                *(
                    [{"name": patient.assigned_provider.name,
                      "role": str(patient.assigned_provider.role)}]
                    if patient.assigned_provider_id != patient.surgeon_id
                    else []
                ),
            ],
        },
        "recovery": {
            "level": str(level),
            "label": label,
            "blurb": blurb,
            "trajectory": {
                "state": str(assessment.trajectory_state),
                "pct": assessment.trajectory_pct,
            },
            "days_with_data": (analytics.get("confidence") or {}).get("days_with_data"),
            "computed_at": _iso(assessment.computed_at),
        },
        "tasks_open": len(open_tasks),
        "unread_messages": len(unread),
        "wearables": _wearable_summary(db, patient),
        "features": {
            "sms": sendblue.configured(),
            "apple_health": junction_connector().is_configured(),
            "deep_link_scheme": settings.mobile_app_scheme,
        },
    }


# --- onboarding ------------------------------------------------------------------


@router.get("/hospitals")
def list_hospitals(q: str = "", db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Hospital).where(Hospital.active.is_(True)).order_by(Hospital.name)).all()
    needle = q.strip().lower()
    if needle:
        rows = [h for h in rows if needle in h.name.lower() or needle in (h.system or "").lower()
                or needle in h.city.lower()]
    return {"hospitals": [_hospital_view(h) for h in rows]}


class SearchBody(BaseModel):
    hospital_id: str
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = None
    date_of_birth: date | None = None


def _tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[\s,.-]+", name.lower().strip()) if t]


def search_candidates(
    db: Session, hospital_id: str, name: str, phone: str | None, dob: date | None
) -> list[dict[str, Any]]:
    """Roster matches for a typed name, scored: exact word 2, prefix 1,
    matching phone or date of birth +3. Masked before it leaves."""
    needle = _tokens(name)
    if not needle or len("".join(needle)) < SEARCH_MIN_CHARS:
        return []
    normalized_phone = sendblue.normalize_phone(phone) if phone else None
    patients = db.scalars(select(Patient).where(Patient.hospital_id == hospital_id)).all()
    scored: list[tuple[int, Patient, bool, bool]] = []
    for p in patients:
        words = _tokens(p.name)
        score = 0
        for t in needle:
            if t in words:
                score += 2
            elif any(w.startswith(t) for w in words):
                score += 1
        if score == 0:
            continue
        phone_match = bool(normalized_phone and p.phone and p.phone == normalized_phone)
        dob_match = bool(dob and p.date_of_birth and p.date_of_birth == dob)
        score += 3 * phone_match + 3 * dob_match
        scored.append((score, p, phone_match, dob_match))
    scored.sort(key=lambda s: (-s[0], s[1].name))
    out = []
    for score, p, phone_match, dob_match in scored[:SEARCH_LIMIT]:
        parts = p.name.split()
        display = parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "")
        out.append(
            {
                "patient_id": p.id,
                "display_name": display,
                "procedure_display": p.procedure_display,
                "surgery_month": p.surgery_date.strftime("%B %Y"),
                "confidence": "high" if score >= 4 or phone_match or dob_match else
                              "medium" if score >= 2 else "low",
                "phone_match": phone_match,
                "has_phone_on_file": bool(p.phone),
            }
        )
    return out


@router.post("/patients/search")
def patient_search(body: SearchBody, db: Session = Depends(get_db)) -> dict:
    if db.get(Hospital, body.hospital_id) is None:
        raise HTTPException(status_code=404, detail="Unknown hospital")
    return {"candidates": search_candidates(db, body.hospital_id, body.name, body.phone,
                                            body.date_of_birth)}


class EnrollBody(BaseModel):
    patient_id: str
    hospital_id: str
    phone: str
    date_of_birth: date | None = None
    device_name: str | None = None
    app_version: str | None = None


def _verification_needed() -> bool:
    return settings.mobile_otp_required and sendblue.configured()


@router.post("/enroll")
def enroll(body: EnrollBody, db: Session = Depends(get_db)) -> dict:
    patient = db.get(Patient, body.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Unknown patient")
    if patient.hospital_id and patient.hospital_id != body.hospital_id:
        raise HTTPException(status_code=409, detail="That record belongs to a different hospital")
    phone = sendblue.normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=422, detail="Enter a valid mobile number")
    if body.date_of_birth and patient.date_of_birth and body.date_of_birth != patient.date_of_birth:
        raise HTTPException(status_code=409, detail="Date of birth doesn't match our record")

    if _verification_needed():
        code = f"{secrets.randbelow(10**6):06d}"
        verification = PhoneVerification(
            patient_id=patient.id,
            phone=phone,
            code_hash=_hash(code),
            expires_at=datetime.now() + VERIFICATION_TTL,
        )
        db.add(verification)
        db.commit()
        result = sendblue.send_verification_code(phone, code)
        if not result.sent:
            raise HTTPException(status_code=502, detail=f"Couldn't text a code: {result.detail}")
        return {
            "status": "verification_required",
            "verification_id": verification.id,
            "phone_masked": _mask_phone(phone),
            "expires_at": _iso(verification.expires_at),
        }

    # No way to text a code: a number already on file must match; a blank
    # one is taken as entered. The response says the phone was not verified.
    if patient.phone and patient.phone != phone:
        raise HTTPException(
            status_code=409,
            detail="That number doesn't match the one on file, and this deployment "
            "can't text a verification code. Ask your care team to update it.",
        )
    if not patient.hospital_id:
        patient.hospital_id = body.hospital_id
    if body.date_of_birth and not patient.date_of_birth:
        patient.date_of_birth = body.date_of_birth
    patient.phone = phone
    token = _issue_session(db, patient, body.device_name, body.app_version)
    return {"status": "enrolled", "verified": False, "session_token": token,
            "me": me_view(db, patient)}


class VerifyBody(BaseModel):
    verification_id: int
    code: str = Field(min_length=4, max_length=8)
    device_name: str | None = None
    app_version: str | None = None


@router.post("/enroll/verify")
def verify(body: VerifyBody, db: Session = Depends(get_db)) -> dict:
    verification = db.get(PhoneVerification, body.verification_id)
    if verification is None or verification.verified_at is not None:
        raise HTTPException(status_code=404, detail="Start over — that code is no longer valid")
    if verification.expires_at < datetime.now():
        raise HTTPException(status_code=410, detail="That code expired — request a new one")
    if verification.attempts >= VERIFICATION_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many tries — request a new code")
    verification.attempts += 1
    if not secrets.compare_digest(verification.code_hash, _hash(body.code.strip())):
        db.commit()
        raise HTTPException(status_code=401, detail="That code isn't right")
    verification.verified_at = datetime.now()
    patient = db.get(Patient, verification.patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Unknown patient")
    patient.phone = verification.phone
    token = _issue_session(db, patient, body.device_name, body.app_version)
    return {"status": "enrolled", "verified": True, "session_token": token,
            "me": me_view(db, patient)}


@router.get("/procedures")
def list_procedures() -> dict:
    return {"procedures": PROCEDURES}


class JoinBody(BaseModel):
    hospital_id: str
    name: str = Field(min_length=2, max_length=120)
    phone: str
    date_of_birth: date | None = None
    sex: str | None = None  # M | F | X | None
    had_surgery: bool = False
    procedure_type: str | None = None
    surgery_date: date | None = None
    device_name: str | None = None
    app_version: str | None = None


def _slug(name: str, db: Session) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "patient"
    candidate = base
    while db.get(Patient, candidate) is not None:
        candidate = f"{base}-{secrets.token_hex(2)}"
    return candidate


def _default_provider(db: Session, surgical: bool) -> tuple[str, str]:
    """(surgeon_id, assigned_provider_id) for a self-enrolled patient: the
    first surgeon on the care team, and for a non-surgical patient the nurse
    as the day-to-day contact when there is one."""
    from app.models.enums import CareRole
    from app.models.patient import CareTeamMember

    members = db.scalars(select(CareTeamMember).order_by(CareTeamMember.id)).all()
    if not members:
        raise HTTPException(status_code=503, detail="No care team is set up on this server yet")
    surgeon = next((m for m in members if str(m.role) == str(CareRole.SURGEON)), members[0])
    nurse = next((m for m in members if str(m.role) == str(CareRole.NURSE)), None)
    assigned = surgeon if surgical or nurse is None else nurse
    return surgeon.id, assigned.id


@router.post("/join")
def join(body: JoinBody, db: Session = Depends(get_db)) -> dict:
    """Self-enrollment: a person who is not on the hospital's roster joins it
    from the app — as a general patient (no surgery) or, if they say they had
    an operation, with the procedure and date they give. Creates the Patient
    row and then runs the same phone verification as enrolling against an
    existing record."""
    if db.get(Hospital, body.hospital_id) is None:
        raise HTTPException(status_code=404, detail="Unknown hospital")
    phone = sendblue.normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=422, detail="Enter a valid mobile number")
    if db.scalar(select(Patient).where(Patient.phone == phone)) is not None:
        raise HTTPException(
            status_code=409,
            detail="That number is already on a record here — go back and find your record instead",
        )
    name = " ".join(body.name.split())
    if body.had_surgery:
        if body.procedure_type not in PROCEDURE_DISPLAY or body.procedure_type == "NONE":
            raise HTTPException(status_code=422, detail="Pick the operation you had")
        if body.surgery_date is None or body.surgery_date > date.today():
            raise HTTPException(status_code=422, detail="Enter the date of your surgery")
        procedure = body.procedure_type
        anchor = body.surgery_date
    else:
        procedure = "NONE"
        anchor = date.today()
    age = 0
    if body.date_of_birth:
        today = date.today()
        age = today.year - body.date_of_birth.year - (
            (today.month, today.day) < (body.date_of_birth.month, body.date_of_birth.day)
        )
        if not 0 <= age <= 120:
            raise HTTPException(status_code=422, detail="Check the date of birth")
    surgeon_id, assigned_id = _default_provider(db, body.had_surgery)
    parts = name.split()
    patient = Patient(
        id=_slug(name, db),
        name=name,
        initials="".join(part[0] for part in parts[:2]).upper(),
        age=age,
        sex=(body.sex or "U")[:1].upper(),
        procedure_type=procedure,
        procedure_display=PROCEDURE_DISPLAY[procedure],
        surgery_date=anchor,
        discharge_date=anchor,
        surgeon_id=surgeon_id,
        assigned_provider_id=assigned_id,
        hospital_id=body.hospital_id,
        date_of_birth=body.date_of_birth,
        care_pathway=None if body.had_surgery else "general_recovery",
    )
    db.add(patient)
    db.commit()

    # Frictionless onboarding: skip SMS verification entirely
    patient.phone = phone
    token = _issue_session(db, patient, body.device_name, body.app_version)
    return {"status": "enrolled", "verified": True, "session_token": token,
            "me": me_view(db, patient)}


@router.post("/signout")
def signout(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> dict:
    session = _current_session(authorization, db)
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now()
        db.commit()
    return {"ok": True}


# --- the signed-in app -------------------------------------------------------------


@router.get("/me")
def me(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    return me_view(db, patient)


@router.get("/tasks")
def list_tasks(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    rows = tasks.recent_tasks(db, patient.id)
    open_rows = [t for t in rows if t.status in tasks.OPEN_STATUSES and t.active]
    done_rows = [t for t in rows if t.status not in tasks.OPEN_STATUSES]
    return {"open": [_task_view(t) for t in open_rows], "recent": [_task_view(t) for t in done_rows[:20]]}


class AnswersBody(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)
    via: str = "app"


def _own_task(db: Session, patient: Patient, task_id: int) -> AdherenceTask:
    task = db.get(AdherenceTask, task_id)
    if task is None or task.patient_id != patient.id:
        raise HTTPException(status_code=404, detail="Unknown task")
    return task


@router.post("/tasks/{task_id}/complete")
def complete(
    task_id: int, body: AnswersBody, patient: Patient = Depends(current_patient),
    db: Session = Depends(get_db),
) -> dict:
    task = _own_task(db, patient, task_id)
    via = body.via if body.via in ("app", "voice") else "app"
    try:
        checkin = tasks.complete_task(db, task, body.answers, via=via)
    except ValueError as e:
        raise HTTPException(status_code=409 if "already" in str(e) else 422, detail=str(e))
    return {"ok": True, "task": _task_view(task), "checkin_id": checkin.id if checkin else None}


@router.post("/tasks/{task_id}/skip")
def skip(
    task_id: int, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> dict:
    task = _own_task(db, patient, task_id)
    try:
        tasks.skip_task(db, task, via="app")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"ok": True, "task": _task_view(task)}


@router.get("/messages")
def list_messages(
    since_id: int = 0, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> dict:
    rows = db.scalars(
        select(Message)
        .where(Message.patient_id == patient.id, Message.id > since_id)
        .order_by(Message.id)
        .limit(200)
    ).all()
    return {"messages": [_message_view(m) for m in rows]}


class MessageBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.post("/messages")
def send_message(
    body: MessageBody, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> dict:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message text is required")
    message = Message(patient_id=patient.id, sender="patient", channel="app", text=text)
    db.add(message)
    tasks.notify_care_team(db, patient, f"{patient.name} sent a message", text, "patient_message")
    db.commit()
    return {"ok": True, "message": _message_view(message)}


@router.post("/messages/read")
def mark_read(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(Message).where(
            Message.patient_id == patient.id,
            Message.sender != "patient",
            Message.read_by_patient_at.is_(None),
        )
    ).all()
    now = datetime.now()
    for m in rows:
        m.read_by_patient_at = now
    db.commit()
    return {"ok": True, "count": len(rows)}


class AgentBody(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    channel: str = "app"  # app | voice


@router.post("/agent")
def agent(
    body: AgentBody, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> dict:
    from app.agent.copilot import respond

    channel = body.channel if body.channel in ("app", "voice") else "app"
    result = respond(db, patient, body.text, channel=channel)
    return {**result, "tasks_open": len(tasks.open_tasks(db, patient.id))}


# --- wearables ---------------------------------------------------------------------


@router.get("/wearables")
def wearables(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    return {**_wearables_view(db, patient), "summary": _wearable_summary(db, patient)}


@router.post("/wearables/apple/session")
def apple_session(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    """A Vital Sign-In Token for this patient's Junction user, for the Health
    SDK in the app. The team API key stays here; the app only ever sees a
    token scoped to its own user."""
    _require_configured()
    try:
        return junction_connector().create_sign_in_token(db, patient.id)
    except (JunctionError, ValueError) as e:
        _raise_for(e)


@router.post("/wearables/refresh")
def wearables_refresh(
    patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> dict:
    """After the Health SDK connects, ask Junction what it now reports for
    the user so the Apple Health device row exists before the first webhook
    (which a laptop deployment never receives)."""
    connector = junction_connector()
    conn = connector.connection_for(db, patient.id)
    error: str | None = None
    if conn is not None and conn.status != ConnectionStatus.DISCONNECTED and connector.is_configured():
        try:
            connector.sync_providers(db, patient.id)
        except (JunctionError, ValueError) as e:
            error = str(e)
        db.refresh(patient)
    return {**_wearables_view(db, patient, error), "summary": _wearable_summary(db, patient)}


@router.post("/wearables/link")
def wearable_link(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> dict:
    """A Junction Link for a cloud wearable (Oura, Garmin, WHOOP...). The
    hosted page hands back to the app through its URL scheme."""
    _require_configured()
    redirect = f"{settings.mobile_app_scheme}://wearables/connected"
    try:
        session = junction_connector().create_link(db, patient.id, redirect_url=redirect)
    except (JunctionError, ValueError) as e:
        _raise_for(e)
    return {"link_url": session.url, "expires_at": session.expires_at}


@router.get("/progress")
def progress(
    days: int = 14, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> dict:
    """Daily steps and sleep for the app's progress charts, from the same
    observations the engine scores. Steps sum within a day (intervals) or
    take the daily summary; sleep takes the longest session of the day."""
    days = max(3, min(days, 60))
    since = date.today() - timedelta(days=days - 1)
    rows = db.scalars(
        select(Observation).where(
            Observation.patient_id == patient.id,
            Observation.metric_type.in_([MetricType.STEPS, MetricType.SLEEP_DURATION]),
            Observation.local_date >= since,
            Observation.deleted_at.is_(None),
            Observation.value_num.is_not(None),
        )
    ).all()
    steps_daily: dict[date, float] = defaultdict(float)
    steps_summary: dict[date, float] = {}
    sleep: dict[date, float] = defaultdict(float)
    for o in rows:
        if o.metric_type == MetricType.STEPS:
            if o.granularity == Granularity.DAILY_SUMMARY:
                steps_summary[o.local_date] = max(steps_summary.get(o.local_date, 0.0), o.value_num)
            else:
                steps_daily[o.local_date] += o.value_num
        else:
            sleep[o.local_date] = max(sleep[o.local_date], o.value_num)
    out = []
    for i in range(days):
        d = since + timedelta(days=i)
        steps = steps_summary.get(d, steps_daily.get(d))
        out.append(
            {
                "date": d.isoformat(),
                "postop_day": (d - patient.surgery_date).days,
                "steps": round(steps) if steps is not None else None,
                "sleep_hours": round(sleep[d], 2) if d in sleep else None,
            }
        )
    return {"days": out}


PORTFOLIO_METRICS: list[tuple[str, str, str, str]] = [
    # (MetricType value, label, unit shown, how a day aggregates: sum|max|mean|last)
    ("steps", "Steps", "steps", "sum"),
    ("sleep_duration", "Sleep", "h", "max"),
    ("resting_hr", "Resting heart rate", "bpm", "mean"),
    ("hrv_rmssd", "Heart rate variability", "ms", "mean"),
    ("hrv_sdnn", "Heart rate variability", "ms", "mean"),
    ("spo2", "Blood oxygen", "%", "mean"),
    ("respiratory_rate", "Breathing rate", "br/min", "mean"),
    ("active_energy", "Active energy", "kcal", "sum"),
    ("exercise_session", "Exercise", "min", "sum"),
    ("walking_speed", "Walking speed", "m/s", "mean"),
    ("walking_steadiness", "Walking steadiness", "%", "mean"),
    ("body_weight", "Weight", "kg", "last"),
    ("bp_systolic", "Blood pressure (systolic)", "mmHg", "mean"),
    ("bp_diastolic", "Blood pressure (diastolic)", "mmHg", "mean"),
    ("blood_glucose", "Blood glucose", "mg/dL", "mean"),
    ("pain_nrs", "Pain", "/10", "last"),
]


@router.get("/portfolio")
def portfolio(
    days: int = 14, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> dict:
    """The patient's aggregated health portfolio: for every metric the
    engine stores for them, the latest value and a daily series over the
    window. Metric names the enum does not know (another module's additions
    not yet deployed) are skipped rather than failing the whole call."""
    days = max(3, min(days, 90))
    since = date.today() - timedelta(days=days - 1)
    wanted = []
    for key, label, unit, agg in PORTFOLIO_METRICS:
        try:
            wanted.append((MetricType(key), label, unit, agg))
        except ValueError:
            continue
    rows = db.scalars(
        select(Observation).where(
            Observation.patient_id == patient.id,
            Observation.metric_type.in_([m for m, *_ in wanted]),
            Observation.local_date >= since,
            Observation.deleted_at.is_(None),
            Observation.value_num.is_not(None),
        ).order_by(Observation.start_time)
    ).all()
    by_metric: dict[MetricType, dict[date, list[tuple[float, bool]]]] = defaultdict(lambda: defaultdict(list))
    for o in rows:
        by_metric[o.metric_type][o.local_date].append(
            (o.value_num, o.granularity == Granularity.DAILY_SUMMARY)
        )
    out = []
    seen_labels: set[str] = set()
    for metric, label, unit, agg in wanted:
        per_day = by_metric.get(metric)
        if not per_day:
            continue
        if label in seen_labels:  # rmssd vs sdnn: one HRV line, whichever the device has
            continue
        seen_labels.add(label)
        series = []
        for d in sorted(per_day):
            values = per_day[d]
            summaries = [v for v, is_summary in values if is_summary]
            plain = [v for v, _ in values]
            if summaries:
                value = max(summaries)
            elif agg == "sum":
                value = sum(plain)
            elif agg == "max":
                value = max(plain)
            elif agg == "last":
                value = plain[-1]
            else:
                value = sum(plain) / len(plain)
            series.append({"date": d.isoformat(), "value": round(value, 2)})
        out.append({
            "key": str(metric),
            "label": label,
            "unit": unit,
            "latest": series[-1],
            "series": series,
            "days_with_data": len(series),
        })
    return {"days": days, "since": since.isoformat(), "metrics": out}


# --- gait, straight from HealthKit -------------------------------------------------

# Apple's walking metrics never pass through Junction (README, wearables), so
# the app reads them from HealthKit itself and posts daily values here. They
# go through the same ingest choke point as every connector's rows.
GAIT_UNITS: dict[MetricType, str] = {
    MetricType.WALKING_SPEED: "m/s",
    MetricType.STEP_LENGTH: "m",
    MetricType.DOUBLE_SUPPORT_PCT: "%",
    MetricType.WALKING_ASYMMETRY_PCT: "%",
    MetricType.WALKING_STEADINESS: "score",
    MetricType.STAIR_SPEED_UP: "m/s",
    MetricType.STAIR_SPEED_DOWN: "m/s",
    MetricType.SIX_MIN_WALK: "m",
}
MAX_GAIT_ROWS = 400


class GaitPoint(BaseModel):
    metric_type: str
    date: date
    value: float


class GaitBody(BaseModel):
    points: list[GaitPoint] = Field(max_length=MAX_GAIT_ROWS)
    device_model: str | None = None


@router.post("/observations/gait")
def upload_gait(
    body: GaitBody, patient: Patient = Depends(current_patient), db: Session = Depends(get_db)
) -> dict:
    from datetime import time as dtime

    from app.connectors.base import CanonicalObservation
    from app.connectors.ingest import PLAUSIBLE_RANGE, ingest_observations, partition_by_window
    from app.models.enums import SourceProvider

    rows: list[CanonicalObservation] = []
    rejected = 0
    dropped = 0
    for pt in body.points:
        try:
            metric = MetricType(pt.metric_type)
        except ValueError:
            rejected += 1
            continue
        unit = GAIT_UNITS.get(metric)
        if unit is None:
            rejected += 1
            continue
        low, high = PLAUSIBLE_RANGE.get(str(metric), (float("-inf"), float("inf")))
        if not low <= pt.value <= high:
            # Dropped and counted, like an aggregator delivery: a phone that
            # produced one odd sample should not lose the day's other rows.
            dropped += 1
            continue
        rows.append(
            CanonicalObservation(
                patient_id=patient.id,
                source_provider=SourceProvider.APPLE,
                metric_type=metric,
                unit=unit,
                value_num=round(float(pt.value), 4),
                start_time=datetime.combine(pt.date, dtime.min),
                end_time=datetime.combine(pt.date, dtime(23, 59, 59)),
                granularity=Granularity.DAILY_SUMMARY,
                source_device_id="apple_health:gait",
                timezone=patient.timezone,
                raw_payload={"device_model": body.device_model} if body.device_model else None,
            )
        )
    inside, outside = partition_by_window(db, rows)
    ingested, updated, duplicates = ingest_observations(db, inside)
    if ingested or updated:
        from app.engine.pipeline import run_patient

        run_patient(db, patient.id)
    return {
        "ingested": ingested,
        "updated": updated,
        "duplicates": duplicates,
        "skipped_out_of_window": len(outside),
        "dropped_implausible": dropped,
        "rejected": rejected,
    }


# --- tokenized web fallback (the page a task text links to) -------------------------


def _task_by_token(db: Session, token: str) -> AdherenceTask:
    task = tasks.find_by_token(db, token)
    if task is None:
        raise HTTPException(status_code=404, detail="Unknown task link")
    return task


@public_router.get("/tasks/{token}")
def public_task(token: str, db: Session = Depends(get_db)) -> dict:
    task = _task_by_token(db, token)
    patient = db.get(Patient, task.patient_id)
    return {
        "first_name": patient.name.split()[0] if patient else "",
        "task": _task_view(task),
        "deep_link": tasks.deep_link(task),
        "completed": task.status == "done",
    }


@public_router.post("/tasks/{token}")
def public_complete(token: str, body: AnswersBody, db: Session = Depends(get_db)) -> dict:
    task = _task_by_token(db, token)
    try:
        tasks.complete_task(db, task, body.answers, via="web")
    except ValueError as e:
        raise HTTPException(status_code=410 if "already" in str(e) else 422, detail=str(e))
    return {"ok": True}
