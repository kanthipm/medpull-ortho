"""Opening a texted link: what it points at, and (on the demo stack, for a
demo persona) the app session it may start. No console credential and no app session: the
token in the path is the credential, as with ``/api/tasks/{token}``.
Minting and the kinds a link can name are in ``app/links.py``.

Two routes, split by what they may change. ``GET`` only describes the link
and changes nothing, because Messages fetches a link to draw its preview
before the person has tapped anything. ``POST …/session`` is the redeem: it
records the open and, where sign-in by link is allowed, starts the app
session.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import links
from app.api.mobile import _issue_session, me_view
from app.database import get_db
from app.models.hospital import Hospital
from app.models.links import AppLink
from app.models.patient import Patient

router = APIRouter(prefix="/links", tags=["links"])

UNKNOWN_LINK = "This link has expired or was mistyped."
SIGN_IN_FIRST = "Open MedPull and sign in to see this."
LINK_DEVICE = "texted link"


def _live(db: Session, token: str) -> tuple[AppLink, Patient]:
    """The link and the person it was texted to, or 404 for a token that is
    unknown, expired, or whose chart is gone."""
    link = links.resolve(db, token)
    patient = db.get(Patient, link.patient_id) if link is not None else None
    if link is None or patient is None:
        raise HTTPException(status_code=404, detail=UNKNOWN_LINK)
    return link, patient


@router.get("/{token}")
def read_link(token: str, db: Session = Depends(get_db)) -> dict:
    """Where the link leads and how to follow it: the app's own URL, the
    browser's continuation, and whether redeeming it signs the phone in.
    Reads only."""
    link, patient = _live(db, token)
    hospital = db.get(Hospital, patient.hospital_id) if patient.hospital_id else None
    return {
        **links.target(link),
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "signin": links.signin_allowed(db, patient),
        "patient": {"first_name": (patient.name or "").split()[0] if patient.name else ""},
        "clinic": {"name": hospital.name} if hospital is not None else None,
        "app": {"scheme": links.app_scheme(), "url": links.app_url(token)},
        "web": links.web_path(token),
    }


class SessionBody(BaseModel):
    device_name: str | None = Field(default=None, max_length=80)


@router.post("/{token}/session")
def redeem_link(
    token: str, body: SessionBody | None = None, db: Session = Depends(get_db),
) -> dict:
    """Redeem the link: the open is recorded and, for a demo persona on the
    demo stack, an app session starts for the person it was texted to. ``me`` is what ``GET
    /api/mobile/me`` answers for that session. Where sign-in by link is not
    allowed the open is still recorded and the answer is 403: an app that
    is already signed in as that person reads the target from the GET."""
    link, patient = _live(db, token)
    links.stamp_opened(link)
    db.commit()
    if not links.signin_allowed(db, patient):
        raise HTTPException(status_code=403, detail=SIGN_IN_FIRST)
    device = (body.device_name if body else None) or LINK_DEVICE
    session_token = _issue_session(db, patient, device, None)
    return {
        "session_token": session_token,
        "me": me_view(db, patient),
        "target": links.target(link),
    }
