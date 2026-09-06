"""Patient check-in: invite by SMS, serve the form, store the response as a
transcript so the existing history UI and digest work unchanged."""

import hashlib
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.checkin import Checkin, CheckinInvite, CheckinMessage
from app.models.patient import Patient
from app.notifications.sendblue import send_checkin_message

router = APIRouter(tags=["checkin"])

INVITE_TTL = timedelta(hours=72)

QUESTIONS = [
    {"id": "pain", "prompt": "How's your pain today, 0 to 10?", "kind": "scale"},
    {"id": "swelling", "prompt": "Any new swelling around the incision?", "kind": "yes_no"},
    {"id": "fever", "prompt": "Any fever or chills?", "kind": "yes_no"},
    {"id": "sleep", "prompt": "How did you sleep?", "kind": "choice",
     "options": ["well", "rough"]},
    {"id": "exercises", "prompt": "Did you get your exercises in?", "kind": "choice",
     "options": ["all", "some", "none"]},
    {"id": "note", "prompt": "Anything else you want the care team to know?", "kind": "text"},
]

# Answers become the patient's own words so checkin_digest picks up topics
# and reported trend exactly as it does for seeded transcripts.
_PHRASES = {
    "swelling": {"yes": "It looks more swollen than yesterday.", "no": "No new swelling."},
    "fever": {"yes": "I've felt feverish with some chills.", "no": "No fever or chills."},
    "sleep": {"well": "I slept fine.", "rough": "It was a rough night, I kept waking up."},
    "exercises": {
        "all": "I did all my exercises.",
        "some": "I did some of my exercises.",
        "none": "I couldn't do my exercises today.",
    },
}


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
