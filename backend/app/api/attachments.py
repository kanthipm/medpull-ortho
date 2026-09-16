"""Files on the thread: a photo of an incision, a sheet of exercises.

Three steps, and the shape of them is forced by where this runs.

1. **Ask where to put it** — ``GET .../attachments/upload-ticket``. A GET on
   purpose: every mutating request takes the cross-instance SQLite write lock
   and re-uploads the whole database (``app/aws/middleware.py``), and picking
   a photo must not cost that. Nothing is written here; the ticket is a
   signed form and the key inside it is the only state.
2. **Send the bytes** — the client posts them straight to object storage with
   that form, so a twelve-megabyte photo never passes through a function
   whose payload ceiling is six. The form's policy carries the size range and
   the content type, so S3 refuses an oversized or mistyped body itself.
3. **Confirm** — ``POST .../attachments``. The server checks the object is
   really there, is within the cap, and begins with the bytes its declared
   type begins with, and only then writes the row. A confirm that fails
   deletes what was uploaded rather than leaving a file nobody can reach.

With no object store (a laptop, the test suite) there is nothing to presign
against, so step 1 says so and step 2 becomes a plain upload to this API.

Reading is a mint too: a short-lived link per request, after the row has been
checked against the caller. Patients are identified by their app session and
may only ever reach their own; the console is identified by its hospital
token and may only reach that hospital's patients — which is stricter than
the rest of the console, whose routes have no caller identity at all, and
deliberately so, because the payload here is a photograph of a wound.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.mobile import current_patient
from app.api.patients import require_hospital_auth
from app.database import get_db
from app.models.attachment import Attachment
from app.models.mobile import Message
from app.models.patient import Patient
from app.storage import blobs

logger = logging.getLogger(__name__)

# The patient app's half: authorised by the app session.
router = APIRouter(prefix="/mobile/attachments", tags=["attachments"])
# The console's half: authorised by the hospital token, and scoped to it.
console_router = APIRouter(prefix="/patients/{patient_id}/attachments", tags=["attachments"])

# A ticket is minted without a row, so an upload nobody confirms leaves an
# object with nothing pointing at it. Anything older than this is fair game
# for the sweep that runs when a chart is removed.
ORPHAN_AFTER = timedelta(hours=6)


def _view(a: Attachment, *, with_url: bool = False) -> dict[str, Any]:
    """One attachment, as both clients read it.

    ``url`` is filled only where the caller has just been authorised for it:
    a link that outlives its request is a link that outlives its check.
    """
    view: dict[str, Any] = {
        "id": a.id,
        "content_type": a.content_type,
        "byte_size": a.byte_size,
        "filename": a.filename,
        "kind": "image" if a.is_image else "file",
        # Content-addressed, so a client can cache the bytes across the
        # rotating short-lived URLs that serve them.
        "sha256": a.sha256,
        "uploaded_by": a.uploaded_by,
        "source": a.source,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "withdrawn": a.deleted_at is not None,
    }
    if with_url and a.available:
        view["url"] = blobs.download_url(a.storage_key, a.content_type, a.filename)
    return view


def attachments_for(db: Session, messages: list[Message]) -> dict[int, list[dict[str, Any]]]:
    """Every message's attachments in one query, keyed by message id.

    Both threads render up to a few hundred lines, so this is a batch loader
    beside the one that resolves clinician names rather than a query per row.
    """
    ids = [m.id for m in messages if m.id is not None]
    if not ids:
        return {}
    # Withdrawn files are listed too, carrying withdrawn=true and no url. A
    # file that silently disappears from a thread leaves a reply to nothing;
    # saying it was taken back is the honest version, and the bytes are gone
    # either way.
    rows = db.scalars(
        select(Attachment)
        .where(Attachment.message_id.in_(ids), Attachment.confirmed_at.is_not(None))
        .order_by(Attachment.id)
    ).all()
    out: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        out.setdefault(row.message_id, []).append(_view(row))
    return out


def claim(db: Session, patient: Patient, attachment_ids: list[int], message: Message) -> int:
    """Attach uploaded files to the message that was just written.

    Only this patient's own confirmed, unattached files: an id belonging to
    another chart, or already on another line, is ignored rather than
    honoured, so a message cannot be used to reach into someone else's
    thread.
    """
    if not attachment_ids:
        return 0
    rows = db.scalars(
        select(Attachment).where(
            Attachment.id.in_(attachment_ids[:8]),
            Attachment.patient_id == patient.id,
            Attachment.message_id.is_(None),
            Attachment.confirmed_at.is_not(None),
            Attachment.deleted_at.is_(None),
        )
    ).all()
    for row in rows:
        row.message_id = message.id
    if len(rows) != len(set(attachment_ids)):
        logger.info(
            "Message %s claimed %d of %d attachment ids for %s",
            message.id, len(rows), len(set(attachment_ids)), patient.id,
        )
    return len(rows)


# --- minting, confirming, reading: shared by both callers -------------------------


def _ticket(patient: Patient, content_type: str, byte_size: int) -> dict[str, Any]:
    try:
        content_type = blobs.check_type(content_type)
        blobs.check_size(byte_size)
    except blobs.BlobError as e:
        raise HTTPException(status_code=422, detail=str(e))
    key = blobs.new_key(patient.id, content_type)
    ticket = blobs.upload_ticket(key, content_type)
    if ticket is None:
        # No object store to send the bytes to: this deployment takes them.
        return {"storage_key": key, "direct": True, "max_bytes": blobs.MAX_BYTES,
                "upload": None}
    return {
        "storage_key": key,
        "direct": False,
        "max_bytes": ticket.max_bytes,
        "upload": {"url": ticket.url, "fields": ticket.fields,
                   "expires_in": ticket.expires_in},
    }


def _confirm(
    db: Session,
    patient: Patient,
    *,
    storage_key: str,
    content_type: str,
    byte_size: int,
    filename: str | None,
    uploaded_by: str,
    uploaded_by_id: str | None,
    source: str,
) -> Attachment:
    try:
        content_type = blobs.check_type(content_type)
    except blobs.BlobError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # The key must be one we minted for this patient. Without this check a
    # caller could confirm a row against any object in the bucket.
    if not storage_key.startswith(f"{blobs.PREFIX}/{patient.id}/"):
        raise HTTPException(status_code=403, detail="That upload does not belong to this patient")
    if db.scalar(select(Attachment.id).where(Attachment.storage_key == storage_key)):
        raise HTTPException(status_code=409, detail="That upload was already confirmed")

    stored = blobs.stat(storage_key)
    if stored is None:
        raise HTTPException(status_code=409, detail="The file has not arrived yet — try again")
    try:
        blobs.check_size(stored)
        if byte_size and stored != byte_size:
            raise blobs.BlobError("The file that arrived is not the size that was declared")
        blobs.sniff(blobs.head_bytes(storage_key), content_type)
    except blobs.BlobError as e:
        # Refuse loudly and leave nothing behind: a stored object with no row
        # is unreachable, and this one failed its checks.
        blobs.delete(storage_key)
        raise HTTPException(status_code=422, detail=str(e))

    safe_name = None
    if filename:
        safe_name = "".join(c for c in filename if c.isalnum() or c in " ._-").strip()[:80] or None
    row = Attachment(
        patient_id=patient.id,
        uploaded_by=uploaded_by,
        uploaded_by_id=uploaded_by_id,
        source=source,
        content_type=content_type,
        byte_size=stored,
        storage_key=storage_key,
        filename=safe_name,
        confirmed_at=datetime.now(),
    )
    db.add(row)
    db.commit()
    return row


def _store_body(
    db: Session, patient: Patient, data: bytes, content_type: str, filename: str | None,
    *, uploaded_by: str, uploaded_by_id: str | None, source: str,
) -> Attachment:
    """Take the bytes off a request and store them, confirmed in one step.

    The same checks a presigned upload gets on confirm, in the same order:
    the declared type must be allowed, the length must be under the cap
    before anything is read as a file, and the magic bytes must agree with
    the declaration.
    """
    try:
        checked = blobs.check_type(content_type)
    except blobs.BlobError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if len(data) > blobs.MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"That file is larger than {blobs.MAX_BYTES // (1024 * 1024)} MB",
        )
    try:
        blobs.check_size(len(data))
        blobs.sniff(data[:1024], checked)
        stored = blobs.put(blobs.new_key(patient.id, checked), data, checked)
    except blobs.BlobError as e:
        raise HTTPException(status_code=422, detail=str(e))

    safe_name = None
    if filename:
        safe_name = "".join(c for c in filename if c.isalnum() or c in " ._-").strip()[:80] or None
    row = Attachment(
        patient_id=patient.id, uploaded_by=uploaded_by, uploaded_by_id=uploaded_by_id,
        source=source, content_type=checked, byte_size=stored.byte_size,
        sha256=stored.sha256, storage_key=stored.key, filename=safe_name,
        confirmed_at=datetime.now(),
    )
    db.add(row)
    db.commit()
    return row


def _own(db: Session, attachment_id: int, patient_id: str) -> Attachment:
    row = db.get(Attachment, attachment_id)
    # Ownership is resolved through the row, never by reading the key: a
    # record merge moves the row to another chart and leaves the key naming
    # the one it was minted under.
    if row is None or row.patient_id != patient_id or row.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Unknown attachment")
    return row


def _bytes_response(row: Attachment) -> Response:
    """Serve the bytes from this API. The laptop path, and the fallback for a
    client that cannot follow a redirect."""
    try:
        data = blobs.read(row.storage_key)
    except blobs.BlobError as e:
        raise HTTPException(status_code=410, detail=str(e))
    disposition = "inline" if row.is_image else "attachment"
    if row.filename:
        disposition = f'{disposition}; filename="{row.filename}"'
    return Response(
        content=data,
        media_type=row.content_type,
        headers={
            "Content-Disposition": disposition,
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


# --- the patient app ---------------------------------------------------------------


@router.get("/upload-ticket")
def upload_ticket(
    content_type: str = Query(...),
    byte_size: int = Query(..., ge=1),
    patient: Patient = Depends(current_patient),
) -> dict:
    """Where to put a file. A GET: this writes nothing, and a mutating
    request would take the database write lock for every photo picked."""
    return _ticket(patient, content_type, byte_size)


class ConfirmBody(BaseModel):
    storage_key: str = Field(min_length=8, max_length=300)
    content_type: str
    byte_size: int = 0
    filename: str | None = None


@router.post("")
def confirm(
    body: ConfirmBody,
    patient: Patient = Depends(current_patient),
    db: Session = Depends(get_db),
) -> dict:
    row = _confirm(
        db, patient, storage_key=body.storage_key, content_type=body.content_type,
        byte_size=body.byte_size, filename=body.filename,
        uploaded_by="patient", uploaded_by_id=None, source="app",
    )
    return {"attachment": _view(row, with_url=True)}


@router.post("/direct")
def upload_direct(
    data: bytes = Body(..., media_type="application/octet-stream"),
    content_type: str = Header(..., alias="Content-Type"),
    filename: str | None = Query(default=None),
    patient: Patient = Depends(current_patient),
    db: Session = Depends(get_db),
) -> dict:
    """Send the bytes through the API, as the raw request body.

    The body is the file itself rather than a multipart form: a form would
    add a dependency to the Lambda artifact for one route, and base64 inside
    JSON would inflate a photo by a third against a six-megabyte ceiling.
    What a deployment without object storage uses, and the fallback when a
    presigned upload is refused.

    A plain ``def``, like every other route here: the engine and SQLAlchemy
    are synchronous, so FastAPI must keep this on the threadpool rather than
    the event loop (see test_every_api_route_runs_on_the_threadpool).
    """
    return {"attachment": _view(
        _store_body(db, patient, data, content_type, filename,
                    uploaded_by="patient", uploaded_by_id=None, source="app"),
        with_url=True,
    )}


@router.get("/{attachment_id}")
def read_one(
    attachment_id: int,
    patient: Patient = Depends(current_patient),
    db: Session = Depends(get_db),
) -> dict:
    """A fresh short-lived link for one file the caller is allowed to see."""
    row = _own(db, attachment_id, patient.id)
    return {"attachment": _view(row, with_url=True)}


@router.get("/{attachment_id}/raw")
def read_bytes(
    attachment_id: int,
    patient: Patient = Depends(current_patient),
    db: Session = Depends(get_db),
) -> Response:
    return _bytes_response(_own(db, attachment_id, patient.id))


@router.delete("/{attachment_id}")
def withdraw(
    attachment_id: int,
    patient: Patient = Depends(current_patient),
    db: Session = Depends(get_db),
) -> dict:
    """Take a file back. The object is deleted for real; the row stays so the
    thread can say a file was withdrawn rather than losing the line."""
    row = _own(db, attachment_id, patient.id)
    blobs.delete(row.storage_key)
    row.deleted_at = datetime.now()
    db.commit()
    return {"ok": True, "attachment": _view(row)}


# --- the console --------------------------------------------------------------------


def console_patient(
    patient_id: str,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Patient:
    """The chart a console request is about.

    The console has no sign-in in this deployment: every other route on this
    surface answers on CloudFront origin verification alone. Demanding a
    hospital token here alone would make the feature unreachable without
    making the thread these files hang on any more private — the message
    text beside a wound photo is already served without one.

    So a token is honoured rather than required. Sent, it is checked (a
    wrong one is refused, not ignored) and it pins the lookup to that
    hospital, which is the guarantee a multi-tenant console will need.
    Absent, this behaves like the rest of the console.
    """
    if authorization is not None:
        hospital = require_hospital_auth(authorization, db)
        patient = db.get(Patient, patient_id)
        if patient is None or patient.hospital_id != hospital.id:
            raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
        return patient
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_id}")
    return patient


@console_router.get("/upload-ticket")
def console_upload_ticket(
    content_type: str = Query(...),
    byte_size: int = Query(..., ge=1),
    patient: Patient = Depends(console_patient),
) -> dict:
    return _ticket(patient, content_type, byte_size)


class ConsoleConfirmBody(ConfirmBody):
    # Which clinician is attaching it. Defaults to the assigned provider, the
    # same rule the console's message route follows.
    sender_id: str | None = None


@console_router.post("")
def console_confirm(
    body: ConsoleConfirmBody,
    patient: Patient = Depends(console_patient),
    db: Session = Depends(get_db),
) -> dict:
    from app.models.patient import CareTeamMember

    sender_id = body.sender_id or patient.assigned_provider_id
    if db.get(CareTeamMember, sender_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown sender: {sender_id}")
    row = _confirm(
        db, patient, storage_key=body.storage_key, content_type=body.content_type,
        byte_size=body.byte_size, filename=body.filename,
        uploaded_by="care_team", uploaded_by_id=sender_id, source="console",
    )
    return {"attachment": _view(row, with_url=True)}


@console_router.post("/direct")
def console_upload_direct(
    data: bytes = Body(..., media_type="application/octet-stream"),
    content_type: str = Header(..., alias="Content-Type"),
    filename: str | None = Query(default=None),
    sender_id: str | None = Query(default=None),
    patient: Patient = Depends(console_patient),
    db: Session = Depends(get_db),
) -> dict:
    """The console's body upload, for a deployment with no object store to
    presign against — the laptop, and the fallback when a presigned POST is
    refused."""
    from app.models.patient import CareTeamMember

    member_id = sender_id or patient.assigned_provider_id
    if db.get(CareTeamMember, member_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown sender: {member_id}")
    return {"attachment": _view(
        _store_body(db, patient, data, content_type, filename,
                    uploaded_by="care_team", uploaded_by_id=member_id, source="console"),
        with_url=True,
    )}


@console_router.get("/{attachment_id}")
def console_read_one(
    attachment_id: int,
    patient: Patient = Depends(console_patient),
    db: Session = Depends(get_db),
) -> dict:
    return {"attachment": _view(_own(db, attachment_id, patient.id), with_url=True)}


@console_router.delete("/{attachment_id}")
def console_withdraw(
    attachment_id: int,
    patient: Patient = Depends(console_patient),
    db: Session = Depends(get_db),
) -> dict:
    """Take back a file the clinic sent.

    The wrong scan on the wrong chart has to be removable by the person who
    put it there, and the patient's app is already showing it. The object is
    deleted for real; the row stays so the thread says a file was withdrawn
    rather than losing the line a reply refers to.
    """
    row = _own(db, attachment_id, patient.id)
    blobs.delete(row.storage_key)
    row.deleted_at = datetime.now()
    db.commit()
    return {"ok": True, "attachment": _view(row)}


@console_router.get("/{attachment_id}/raw")
def console_read_bytes(
    attachment_id: int,
    patient: Patient = Depends(console_patient),
    db: Session = Depends(get_db),
) -> Response:
    return _bytes_response(_own(db, attachment_id, patient.id))
