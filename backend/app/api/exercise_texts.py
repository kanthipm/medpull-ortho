"""Console actions that text a lifter about their exercises
(``app/hep/texts.py`` writes and sends them)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.hep import schedule, texts
from app.hep.api import _clinic, _ready
from app.hep.service import HepError

router = APIRouter(prefix="/hep", tags=["hep-texts"])


class TextTodayBody(BaseModel):
    # The care-team member the text is signed with; none, and it is the app's own.
    by: str | None = None
    day: date | None = None


@router.post("/patients/{patient_id}/text-today")
def text_today(
    patient_id: str,
    request: Request,
    body: TextTodayBody | None = None,
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """Text one lifter their plan for the day (today unless ``day`` says),
    with a link that opens the app on it. 409 with the reason when the chart
    cannot be texted at all: no number, a placeholder, a STOP, or texting not
    set up."""
    try:
        patient = schedule.clinic_patient(db, clinic, patient_id)
    except HepError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    blocked = texts.cannot_text(patient)
    if blocked is not None:
        raise HTTPException(status_code=409, detail=blocked[1])
    body = body or TextTodayBody()
    base = settings.checkin_base_url or str(request.base_url).rstrip("/")
    sent = texts.text_today(db, patient, base_url=base, day=body.day, by=body.by)
    if sent is None:
        raise HTTPException(status_code=409, detail="The text could not be written; nothing was sent.")
    return sent
