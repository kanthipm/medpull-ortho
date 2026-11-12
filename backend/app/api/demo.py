"""Routes that exist on the demo stack only.

The demo screen shows the console and the patient's phone side by side:
the therapist assigns a day on the left, it appears on the phone on the
right. The phone frame is the patient web app in an iframe, and it needs
to be signed in as the lifter without anyone typing a code on camera — so
the console, already authorised for that chart, asks for a patient session
here and hands it to the frame. Off the demo stack (``DEMO_MODE`` unset)
the route does not exist: it is a way to act as a patient, and nothing on
the real app may offer that.

The demo iPhone app has no console to ask, so it has routes of its own on
``public_router``, with no credential at all: the list of fictional people
it can become (``app/seed/showcase.py``), a session as one of them, and a
way to put that person's exercise day back between walkthroughs. They too
exist on the demo stack only, and they sign a phone in as nobody the
showcase did not write.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.auth import ConsoleScope, console_scope
from app.api.mobile import _issue_session, me_view
from app.api.scope import UNKNOWN_PATIENT, require_patient
from app.config import settings
from app.database import get_db
from app.models.mobile import PatientSession
from app.models.patient import Patient
from app.personal.scope import is_clinic
from app.seed import showcase

router = APIRouter(prefix="/demo", tags=["demo"])
# The routes the demo iPhone app calls before it has any credential: the
# persona list and the session for one of them. Mounted without the console's
# door; each answers 404 off the demo stack.
public_router = APIRouter(prefix="/demo", tags=["demo"])

DEVICE_NAME = "demo screen"
# The device a persona session is filed under when the caller names none.
PERSONA_DEVICE_NAME = "demo phone"
UNKNOWN_PERSONA = "Unknown persona"


class PatientSessionBody(BaseModel):
    patient_id: str


@router.post("/patient-session")
def demo_patient_session(
    body: PatientSessionBody,
    scope: ConsoleScope = Depends(console_scope),
    db: Session = Depends(get_db),
) -> dict:
    """A patient-app session for a demo persona in this console's scope, for
    the demo screen's phone frame. 404 off the demo stack, for any chart the
    console could not open itself, and for a chart the showcase did not
    write."""
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not found")
    patient = require_patient(db, scope, body.patient_id)
    # Only a person the showcase wrote. The demo stack can hold real charts
    # beside the fictional ones, and an open console must not be a way to
    # act as a real patient in their own app.
    if not is_clinic(patient) or showcase.resolve(db, patient.id) is None:
        raise HTTPException(status_code=404, detail=UNKNOWN_PATIENT)
    token = _issue_session(db, patient, DEVICE_NAME, None)
    return {"token": token, "patient": {"id": patient.id, "name": patient.name}}


# --- the persona routes: no credential, demo stack only ----------------------------------


def _demo_only() -> None:
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not found")


def _persona(db: Session, persona_id: str) -> tuple[showcase.Persona, Patient]:
    """The persona and its row, or 404: only people the showcase knows."""
    found = showcase.resolve(db, persona_id)
    if found is None:
        raise HTTPException(status_code=404, detail=UNKNOWN_PERSONA)
    return found


class PersonaBody(BaseModel):
    persona_id: str = Field(min_length=1, max_length=120)


class PersonaSessionBody(PersonaBody):
    device_name: str | None = Field(default=None, max_length=200)


@public_router.get("/personas")
def demo_personas(db: Session = Depends(get_db)) -> dict:
    """Everyone the showcase can show and the phone can become, by version
    and org, with the line the demo texts from. Reads only."""
    _demo_only()
    return showcase.personas(db)


@public_router.post("/session")
def demo_session(body: PersonaSessionBody, db: Session = Depends(get_db)) -> dict:
    """An app session as one persona, of any version, with the same ``me``
    the app would read next. One session per persona and device name: asking
    again from the same device replaces the earlier one (its token stops
    working), so a phone that switches people all afternoon leaves one row
    per person behind, not one per tap."""
    _demo_only()
    entry, patient = _persona(db, body.persona_id)
    device = (body.device_name or "").strip()[:80] or PERSONA_DEVICE_NAME
    db.execute(delete(PatientSession).where(
        PatientSession.patient_id == patient.id, PatientSession.device_name == device,
    ))
    token = _issue_session(db, patient, device, None)
    return {
        "session_token": token,
        "me": me_view(db, patient),
        "persona": {"id": patient.id, "name": patient.name, "version": entry.version},
    }


@public_router.post("/reset-day")
def demo_reset_day(body: PersonaBody, db: Session = Depends(get_db)) -> dict:
    """Put a persona's exercise day back so a walkthrough can be run again:
    today's rows reopened, the lines today's completions and reviews wrote
    taken off the thread. A Personal or Sports persona has no exercise
    calendar and reports zeros."""
    _demo_only()
    _, patient = _persona(db, body.persona_id)
    return showcase.reset_day(db, patient)
