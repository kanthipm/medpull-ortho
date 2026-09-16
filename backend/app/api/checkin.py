"""Patient check-in: invite by SMS, serve the form, store the response as a
transcript so the existing history UI and digest work unchanged.

Also the one-press daily check-in a clinician fires from the console
(``/patients/{id}/actions/daily-checkin``), which puts the check-in in the
patient's app as a task plus a thread row the app draws a button on, and
texts them that it is waiting."""

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.identity import app_status
from app.models.adherence import AdherenceTask
from app.models.checkin import Checkin, CheckinInvite, CheckinMessage
from app.models.mobile import Message
from app.models.patient import Patient
from app.notifications import sendblue
from app.notifications.sendblue import send_checkin_message
from app.tasks import service as tasks_service
from app.tasks.service import CHECKIN_QUESTIONS, PHRASES

router = APIRouter(tags=["checkin"])

INVITE_TTL = timedelta(hours=72)

# One question list for every check-in surface: the tokenized web form here,
# the app's check-in task, and the texted conversation (tasks/service.py).
QUESTIONS = CHECKIN_QUESTIONS
_PHRASES = PHRASES


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _valid_invite(db: Session, token: str) -> CheckinInvite:
    invite = db.scalars(
        select(CheckinInvite).where(CheckinInvite.token_hash == _hash(token))
    ).first()
    if invite is None:
        raise HTTPException(status_code=404, detail="Unknown check-in link")
    if invite.used_at is not None:
        raise HTTPException(status_code=410, detail="This check-in was already completed")
    if invite.expires_at < datetime.now():
        raise HTTPException(status_code=410, detail="This check-in link has expired")
    return invite


class InviteRequest(BaseModel):
    phone: str


@router.post("/patients/{patient_id}/checkin-invite")
def send_invite(
    patient_id: str, body: InviteRequest, request: Request, db: Session = Depends(get_db)
) -> dict:
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Unknown patient")

    token = secrets.token_urlsafe(32)
    db.add(CheckinInvite(
        token_hash=_hash(token),
        patient_id=patient_id,
        expires_at=datetime.now() + INVITE_TTL,
    ))
    db.commit()

    base = settings.checkin_base_url or str(request.base_url).rstrip("/")
    url = f"{base}/checkin/{token}"
    result = send_checkin_message(body.phone, url)
    return {"sent": result.sent, "detail": result.detail, "url": url}


@router.get("/checkin/{token}")
def get_checkin(token: str, db: Session = Depends(get_db)) -> dict:
    invite = _valid_invite(db, token)
    patient = db.get(Patient, invite.patient_id)
    return {"patient_name": patient.name.split()[0], "questions": QUESTIONS}


class CheckinAnswers(BaseModel):
    pain: int | None = Field(default=None, ge=0, le=10)
    swelling: str | None = None
    fever: str | None = None
    sleep: str | None = None
    exercises: str | None = None
    note: str | None = Field(default=None, max_length=2000)


@router.post("/checkin/{token}")
def submit_checkin(token: str, answers: CheckinAnswers, db: Session = Depends(get_db)) -> dict:
    invite = _valid_invite(db, token)

    pairs: list[tuple[str, str]] = []
    for q in QUESTIONS:
        raw = getattr(answers, q["id"])
        if raw is None or raw == "":
            continue
        if q["id"] == "pain":
            text = f"My pain is about {raw} out of 10."
        elif q["id"] == "note":
            text = str(raw).strip()
        else:
            phrase = _PHRASES[q["id"]].get(str(raw))
            if phrase is None:
                raise HTTPException(status_code=422, detail=f"Invalid answer for {q['id']}")
            text = phrase
        pairs.append((q["prompt"], text))

    if not pairs:
        raise HTTPException(status_code=422, detail="No answers given")

    checkin = Checkin(patient_id=invite.patient_id, occurred_at=datetime.now(), channel="sms")
    db.add(checkin)
    db.flush()
    seq = 0
    for prompt, text in pairs:
        db.add(CheckinMessage(checkin_id=checkin.id, seq=seq, who="copilot", text=prompt))
        db.add(CheckinMessage(checkin_id=checkin.id, seq=seq + 1, who="patient", text=text))
        seq += 2
    invite.used_at = datetime.now()
    db.commit()
    return {"ok": True}


# --- one press: send today's check-in ------------------------------------------
#
# The console already had a way to assign a check-in: open the task builder,
# add a row, confirm. That is the right shape for building a care plan and the
# wrong shape for the single most routine thing a clinician does, which is ask
# this patient how today went. This is that one press.
#
# It deliberately does NOT go through ``tasks.dispatch``. A generic task text
# ("A new task is ready — ...  Or reply 1 to do it right here by text") always
# carries the tokenized web link, and for a patient who already has the app
# that link is a worse copy of something they can already reach behind their
# own session. So the send is composed here: the link goes only to somebody
# who has never enrolled, and everybody else gets a thread row carrying an
# action the app draws as a button.


def _open_checkin(db: Session, patient_id: str) -> AdherenceTask | None:
    """Today's check-in if the patient already has one waiting.

    The button gets pressed twice — a take is reshot, a clinician is not sure
    it registered — and a patient opening the app to four identical check-ins
    is the kind of detail that is very hard to explain on camera.
    """
    return next((t for t in tasks_service.open_tasks(db, patient_id) if t.kind == "checkin"), None)


@router.post("/patients/{patient_id}/actions/daily-checkin")
def send_daily_checkin(patient_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Put today's check-in in the patient's app and text them that it's there.

    The text is best effort and never fails the request: the check-in itself
    is a row in their plan and a button on their thread the moment this
    returns, whether or not a carrier ever carries anything. That matters
    beyond robustness — most demo patients carry placeholder numbers that
    Sendblue will refuse, and the feature still has to work in front of
    an audience.
    """
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail="Unknown patient")

    task = _open_checkin(db, patient_id)
    reused = task is not None
    if task is None:
        task, _ = tasks_service.create_task(
            db,
            patient,
            title="Daily check-in",
            why="Your care team is following how each day goes.",
            kind="checkin",
            notify=False,
            created_by=patient.assigned_provider_id,
        )

    member = tasks_service.assigning_clinician(db, task)

    # A patient who has ever signed in holds the check-in behind their own
    # session, so their text carries no link at all. One who has not needs
    # the tokenized page, because for them the text is the only way in.
    link: str | None = None
    if not app_status(db, patient)["ever_enrolled"]:
        base = settings.checkin_base_url or str(request.base_url).rstrip("/")
        link = tasks_service.task_url(base, tasks_service.mint_token(task))

    text = sendblue.daily_checkin_text(link, member)
    if patient.phone:
        result = sendblue.send_daily_checkin_message(patient.phone, link=link, member=member)
    else:
        result = sendblue.CheckinSendResult(sent=False, detail="no phone number on file")

    db.add(Message(
        patient_id=patient.id,
        sender="care_team" if member is not None else "copilot",
        sender_id=member.id if member is not None else None,
        channel="sms" if patient.phone else "app",
        text=text,
        authored_by="care_team" if member is not None else "ai",
        # No phone means nothing was sent out of band, which is not a failure
        # and must not draw the thread's red "not delivered" badge.
        delivery_status=("sent" if result.sent else "failed") if patient.phone else None,
        delivery_detail=None if result.sent else result.detail,
        external_handle=result.message_handle,
        action_kind="open_task",
        action_task_id=task.id,
        action_label="Start check-in",
    ))
    if result.sent:
        task.status = "sent"
        task.sent_at = datetime.now()
    db.commit()

    return {
        "ok": True,
        "reused": reused,
        "task_id": task.id,
        "in_app": True,
        "sms": {
            "attempted": bool(patient.phone),
            "sent": result.sent,
            "detail": result.detail,
            "linked": link is not None,
        },
    }
