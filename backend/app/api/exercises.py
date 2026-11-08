"""The patient app's half of the exercise schedule, under
``/api/mobile/exercises``: today's exercises with the therapist's clip to
follow, marking one done with a pain score and a clip of the attempt, or
skipping it with a reason.

Authorised by the app session (``mobile.current_patient``) like the rest of
the patient app; never behind the console credential. The return clip is an
ordinary patient attachment — minted at ``/api/mobile/attachments/
upload-ticket``, sent to object storage (or the direct route), confirmed
here exactly as the thread's files are — and the completion writes one
line on the thread with the clip on it, so the chart shows the score and
the clip where the conversation is.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.mobile import current_patient
from app.config import settings
from app.database import get_db
from app.hep import ensure_ready
from app.hep import media as clips
from app.hep import schedule
from app.hep.models import Exercise, ExerciseMedia
from app.hep.service import HepError
from app.models.attachment import Attachment
from app.models.mobile import Message
from app.models.patient import Patient
from app.tasks import service as tasks

router = APIRouter(prefix="/mobile/exercises", tags=["exercises"])


def _ready(db: Session = Depends(get_db)) -> Session:
    """The same gate as the console's ``/api/hep`` routes: the feature flag,
    and the catalog present."""
    if not settings.hep_enabled:
        raise HTTPException(status_code=404, detail="Exercise plans are not enabled")
    ensure_ready(db)
    return db


def _own(db: Session, patient: Patient, assignment_id: int):
    row = schedule.own_assignment(db, patient, assignment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown assignment")
    return row


def _refused(err: HepError) -> HTTPException:
    return HTTPException(status_code=409 if isinstance(err, schedule.ScheduleConflict) else 422,
                         detail=str(err))


class ReturnClip(BaseModel):
    """The clip the patient filmed, in whichever form the upload left it.

    With an object store the client put the bytes at the key its ticket
    minted and sends ``storage_key``, and the row is confirmed here as any
    thread file is. Without one the direct route has already confirmed the
    ``Attachment`` row (and never shows its key), so the client sends that
    row's ``attachment_id`` instead. One of the two is required.
    """

    storage_key: str | None = Field(default=None, min_length=8, max_length=300)
    attachment_id: int | None = None
    content_type: str | None = None
    byte_size: int = 0
    filename: str | None = None


class CompleteBody(BaseModel):
    pain_after: int | None = Field(default=None, ge=0, le=10)
    note: str = Field(default="", max_length=schedule.NOTE_LIMIT)
    video: ReturnClip | None = None


class SkipBody(BaseModel):
    reason: str = Field(default="", max_length=schedule.TEXT_LIMIT)


def _return_clip(db: Session, patient: Patient, clip: ReturnClip) -> Attachment:
    """The attachment row for a return clip: confirmed now from its key, or
    the row the direct upload already confirmed. Either way it is this
    patient's, confirmed, not withdrawn, and not yet on a message or
    another day — a clip is one attempt at one exercise."""
    from sqlalchemy import select

    from app.api.attachments import confirm_upload
    from app.hep.models import ExerciseAssignment

    if clip.attachment_id is not None:
        row = db.get(Attachment, clip.attachment_id)
        if (row is None or row.patient_id != patient.id or row.confirmed_at is None
                or row.deleted_at is not None):
            raise HTTPException(status_code=404, detail="Unknown attachment")
        if row.message_id is not None or db.scalar(select(ExerciseAssignment.id).where(
                ExerciseAssignment.video_attachment_id == row.id)):
            raise HTTPException(status_code=409, detail="That clip is already on the thread")
        return row
    if not clip.storage_key:
        raise HTTPException(status_code=422, detail="Send the clip's storage_key or attachment_id")
    if not clip.content_type:
        raise HTTPException(status_code=422, detail="Say what type of file the clip is")
    return confirm_upload(
        db, patient, storage_key=clip.storage_key, content_type=clip.content_type,
        byte_size=clip.byte_size, filename=clip.filename, uploaded_by="patient",
        uploaded_by_id=None, source="app",
    )


@router.get("")
def today_exercises(
    day: date | None = Query(default=None, alias="date"),
    patient: Patient = Depends(current_patient),
    db: Session = Depends(_ready),
) -> dict:
    """The day's exercises in order, a seven-day strip around it, and whose
    schedule it is. Clip URLs are playable as given: presigned on AWS, this
    API's own stream under the session on a laptop."""
    return schedule.today_payload(db, patient, day or date.today())


@router.post("/{assignment_id}/complete")
def complete_exercise(
    assignment_id: int,
    body: CompleteBody | None = None,
    patient: Patient = Depends(current_patient),
    db: Session = Depends(_ready),
) -> dict:
    """Mark a day done with the pain after it and, when the patient filmed
    the attempt, the clip. The clip is settled first — confirmed from its
    key as any thread file is (owned by this patient, there, within the
    cap, what its type says), or taken as the row the direct upload left —
    then one line goes on the thread with it, and the row records the rest.
    A day already done is a 409 before anything is stored."""
    body = body or CompleteBody()
    row = _own(db, patient, assignment_id)
    try:
        schedule.ensure_open(row)
    except HepError as err:
        raise _refused(err)
    attachment = _return_clip(db, patient, body.video) if body.video is not None else None
    exercise = db.get(Exercise, row.exercise_id)
    text = schedule.completion_line(exercise.title if exercise else "the exercise",
                                    body.pain_after, body.note)
    message = Message(patient_id=patient.id, sender="patient", channel="app", text=text)
    db.add(message)
    db.flush()
    if attachment is not None:
        attachment.message_id = message.id
    # The care team hears about it the way they hear about any line the
    # patient writes: the bell carries the score, not an empty message.
    tasks.notify_care_team(db, patient, f"{patient.name} sent a message", text,
                           "patient_message")
    try:
        row = schedule.complete_assignment(
            db, row, pain_after=body.pain_after, note=body.note, source="app",
            video_attachment_id=attachment.id if attachment else None,
        )
    except HepError as err:
        db.rollback()
        raise _refused(err)
    return {"assignment": schedule.AssignmentView(db, patient_app=True).render(row)}


@router.post("/{assignment_id}/skip")
def skip_exercise(
    assignment_id: int,
    body: SkipBody | None = None,
    patient: Patient = Depends(current_patient),
    db: Session = Depends(_ready),
) -> dict:
    row = _own(db, patient, assignment_id)
    try:
        row = schedule.skip_assignment(db, row, reason=(body or SkipBody()).reason)
    except HepError as err:
        raise _refused(err)
    return {"assignment": schedule.AssignmentView(db, patient_app=True).render(row)}


@router.get("/media/{media_id}/raw")
def read_clip_bytes(
    media_id: int,
    poster: bool = False,
    patient: Patient = Depends(current_patient),
    db: Session = Depends(_ready),
) -> Response:
    """A demonstration's bytes under the patient's session: their clinic's
    own clip, or a library clip. What the laptop serves in place of a
    presigned URL."""
    media = db.get(ExerciseMedia, media_id)
    if not clips.readable_by(media, patient.hospital_id):
        raise HTTPException(status_code=404, detail="Unknown clip")
    return clips.stream(media, poster=poster)
