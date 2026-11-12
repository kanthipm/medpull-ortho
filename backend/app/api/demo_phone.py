"""Binding a real phone number to a demo persona, so the texts the demo
sends reach the presenter's own phone. Demo stack only (404 elsewhere);
authorised by the persona's app session, not the console credential.

    GET    /api/demo/phone     what is bound, and whether it can be texted yet
    POST   /api/demo/phone     {"phone": "+1..."}: bind it (and send the welcome)
    DELETE /api/demo/phone     unbind

Every answer has the same shape: ``{"phone", "reachable", "text_to",
"text_body", "sent", "detail"}``.

The number may already be on the presenter's real chart; that chart keeps
it. While the number is bound here, a text from it is the persona's
(``tasks.service.patient_for_phone``), and unbinding gives it back. One
number is bound to one persona at a time: binding it to a second takes it
off the first.

On Sendblue's free plan a number can only be texted after it has texted the
line once. Then ``reachable`` is false, the app shows "text us first" with
``text_to`` and ``text_body``, and polls ``GET``; the welcome text (with its
link into the app) is owed and goes out the moment that first text arrives
(``tasks.service.handle_inbound_sms``). ``GET`` only reads.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.mobile import current_patient
from app.config import settings
from app.database import get_db
from app.hep import texts
from app.models.patient import Patient
from app.notifications import reachability, sendblue
from app.seed import showcase

router = APIRouter(prefix="/demo", tags=["demo"])


def _persona(patient: Patient = Depends(current_patient), db: Session = Depends(get_db)) -> Patient:
    """The signed-in demo persona. Not the demo stack, or a session that is
    a real person's: there is nothing here."""
    if not settings.demo_mode or showcase.resolve(db, patient.id) is None:
        raise HTTPException(status_code=404, detail="Not found")
    return patient


def _bound(patient: Patient) -> str | None:
    """The real number bound to this persona, or None (the 555 placeholder
    the roster ships with is nobody's phone)."""
    if patient.demo_phone_bound_at is None or reachability.is_placeholder(patient.phone):
        return None
    return patient.phone


def _reachable(db: Session, phone: str, *, fresh: bool = False) -> bool:
    """Whether a text to ``phone`` would be accepted as far as is known. A
    number the provider has not ruled on counts as reachable: the send is
    tried, and a refusal is learned from."""
    if reachability.known_verified(db, phone):
        return True
    return reachability.lookup(db, phone, fresh=fresh) != "unverified"


def _state(db: Session, patient: Patient, *, detail: str | None = None,
           fresh: bool = False) -> dict:
    phone = _bound(patient)
    return {
        "phone": phone,
        "reachable": _reachable(db, phone, fresh=fresh) if phone else False,
        "text_to": reachability.line_number(phone),
        "text_body": reachability.text_first_body(),
        # the welcome has gone out (nothing is still owed to this number)
        "sent": phone is not None and patient.sms_welcome_owed_at is None,
        "detail": detail,
    }


@router.get("/phone")
def read_phone(patient: Patient = Depends(_persona), db: Session = Depends(get_db)) -> dict:
    """What is bound to this persona and whether it can be texted yet."""
    return _state(db, patient)


class PhoneBody(BaseModel):
    phone: str = Field(min_length=7, max_length=32)


def _base_url(request: Request) -> str | None:
    return settings.checkin_base_url or str(request.base_url).rstrip("/") or None


@router.post("/phone")
def bind_phone(
    body: PhoneBody,
    request: Request,
    patient: Patient = Depends(_persona),
    db: Session = Depends(get_db),
) -> dict:
    """Bind a real number to this persona and text it the welcome, or leave
    the welcome owed until the number has texted the line."""
    phone = sendblue.normalize_phone(body.phone)
    if phone is None:
        raise HTTPException(status_code=422, detail="That does not look like a phone number")
    if reachability.is_placeholder(phone):
        raise HTTPException(status_code=422, detail="A 555 number is nobody's phone")
    if settings.sendblue_from_number and phone == sendblue.normalize_phone(settings.sendblue_from_number):
        raise HTTPException(status_code=422, detail="That is the number MedPull texts from")

    now = datetime.now()
    holders = db.scalars(select(Patient).where(Patient.phone == phone, Patient.id != patient.id)).all()
    for other in holders:
        # Another persona this phone was bound to gives it up; a real chart
        # that carries the number keeps it.
        if other.demo_phone_bound_at is not None:
            other.phone = None
            other.demo_phone_bound_at = None
            other.sms_welcome_owed_at = None
    patient.phone = phone
    patient.demo_phone_bound_at = now
    # A number that replied STOP stays stopped whoever it is bound to.
    stopped = next((o.sms_opt_out_at for o in holders if o.sms_opt_out_at is not None), None)
    patient.sms_opt_out_at = stopped
    patient.sms_welcome_owed_at = now
    db.commit()

    blocked = texts.cannot_text(patient)
    if blocked is not None:
        return _state(db, patient, detail=blocked[1])
    if not _reachable(db, phone, fresh=True):
        return _state(db, patient)
    sent = texts.welcome(db, patient, base_url=_base_url(request))
    if sent is not None and sent["sent"]:
        patient.sms_welcome_owed_at = None
        db.commit()
        return _state(db, patient)
    # Refused for not having texted the line yet is the ordinary first-time
    # case: the welcome stays owed and the app shows "text us first".
    detail = None if sent is None or sent["unreachable"] else sent["detail"]
    return {**_state(db, patient, detail=detail),
            "reachable": not (sent is not None and sent["unreachable"]) and _reachable(db, phone)}


@router.delete("/phone")
def unbind_phone(patient: Patient = Depends(_persona), db: Session = Depends(get_db)) -> dict:
    """Take the bound number off this persona. The next fill gives the
    persona its placeholder back."""
    if patient.demo_phone_bound_at is not None:
        patient.phone = None
        patient.demo_phone_bound_at = None
        patient.sms_welcome_owed_at = None
        db.commit()
    return _state(db, patient)
