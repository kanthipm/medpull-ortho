"""Routes that exist on the demo stack only.

The demo screen shows the console and the patient's phone side by side:
the therapist assigns a day on the left, it appears on the phone on the
right. The phone frame is the patient web app in an iframe, and it needs
to be signed in as the lifter without anyone typing a code on camera — so
the console, already authorised for that chart, asks for a patient session
here and hands it to the frame. Off the demo stack (``DEMO_MODE`` unset)
the route does not exist: it is a way to act as a patient, and nothing on
the real app may offer that.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.auth import ConsoleScope, console_scope
from app.api.mobile import _issue_session
from app.api.scope import UNKNOWN_PATIENT, require_patient
from app.config import settings
from app.database import get_db
from app.personal.scope import is_clinic

router = APIRouter(prefix="/demo", tags=["demo"])

DEVICE_NAME = "demo screen"


class PatientSessionBody(BaseModel):
    patient_id: str


@router.post("/patient-session")
def demo_patient_session(
    body: PatientSessionBody,
    scope: ConsoleScope = Depends(console_scope),
    db: Session = Depends(get_db),
) -> dict:
    """A patient-app session for a chart in this console's scope, for the
    demo screen's phone frame. 404 off the demo stack, and for any chart the
    console could not open itself."""
    if not settings.demo_mode:
        raise HTTPException(status_code=404, detail="Not found")
    patient = require_patient(db, scope, body.patient_id)
    if not is_clinic(patient):
        raise HTTPException(status_code=404, detail=UNKNOWN_PATIENT)
    token = _issue_session(db, patient, DEVICE_NAME, None)
    return {"token": token, "patient": {"id": patient.id, "name": patient.name}}
