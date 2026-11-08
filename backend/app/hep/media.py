"""A clinic's own demonstration clips.

The library ships a clip per standard exercise (or none yet); a clinic can
put its own therapist's video of the exercise over it, and from then on
that clinic and its patients see hers (``service.resolve_clip``). The
bytes go where patient attachments go, under a clinic key
(``blobs.new_clinic_key``), so the bucket policy, CORS rule and lifecycle
apply unchanged; the row is ``ExerciseMedia`` with ``exercise_id`` set and
``hospital_id`` the clinic's, approved on creation because the therapist
who uploaded it is the reviewer.

The upload follows ``app/api/attachments.py`` step for step — a ticket, the
bytes straight to object storage (or to this API on a laptop), a confirm
that checks the object is there, within the cap and what its type claims —
and, like that module, the helpers here answer with the HTTP refusal
rather than a HepError, because every refusal is one the uploader must see
in those words.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.hep.models import Exercise, ExerciseMedia
from app.hep.service import audit
from app.storage import blobs

# A demonstration is a clip, or a still of the position. Nothing else.
CLIP_KINDS = ("video", "image")


def check_clip_type(content_type: str) -> str:
    """The stored type for a demonstration, or a 422: one of the types we
    accept at all, and a video or a picture."""
    try:
        checked = blobs.check_type(content_type)
    except blobs.BlobError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if blobs.kind_of(checked) not in CLIP_KINDS:
        raise HTTPException(status_code=422, detail="A demonstration is a video or a picture")
    return checked


def clip_ticket(clinic: str, content_type: str, byte_size: int) -> dict[str, Any]:
    """Where to put the therapist's clip: the attachments ticket shape for a
    fresh clinic key."""
    from app.api.attachments import ticket_for

    checked = check_clip_type(content_type)
    try:
        blobs.check_size(byte_size, checked)
    except blobs.BlobError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return ticket_for(blobs.new_clinic_key(clinic, checked), checked)


def _row(clinic: str, exercise: Exercise, *, key: str, content_type: str, size: int,
         actor: str) -> ExerciseMedia:
    now = datetime.now()
    actor = actor or "provider"
    return ExerciseMedia(
        hospital_id=clinic, exercise_id=exercise.id, kind=blobs.kind_of(content_type),
        storage_key=key, content_type=content_type, size_bytes=size,
        approval_status="approved", reviewed_by=actor, reviewed_at=now, uploaded_by=actor,
    )


def confirm_clip(
    db: Session, clinic: str, exercise: Exercise, *, storage_key: str, content_type: str,
    byte_size: int, filename: str | None, actor: str,
) -> ExerciseMedia:
    """The clip arrived at its ticket's key; write the row once the object
    checks out. The key must be one minted for this clinic, or a caller
    could confirm a row against any object in the bucket; a failed check
    deletes the object rather than leaving a file nobody can reach."""
    checked = check_clip_type(content_type)
    if not blobs.owned_by_clinic(storage_key, clinic):
        raise HTTPException(status_code=403, detail="That upload does not belong to this clinic")
    if db.scalar(select(ExerciseMedia.id).where(ExerciseMedia.storage_key == storage_key)):
        raise HTTPException(status_code=409, detail="That upload was already confirmed")
    stored = blobs.stat(storage_key)
    if stored is None:
        raise HTTPException(status_code=409, detail="The file has not arrived yet — try again")
    try:
        blobs.check_size(stored, checked)
        if byte_size and stored != byte_size:
            raise blobs.BlobError("The file that arrived is not the size that was declared")
        blobs.sniff(blobs.head_bytes(storage_key), checked)
    except blobs.BlobError as e:
        blobs.delete(storage_key)
        raise HTTPException(status_code=422, detail=str(e))
    row = _row(clinic, exercise, key=storage_key, content_type=checked, size=stored, actor=actor)
    return _record(db, clinic, exercise, row, filename, actor)


def store_clip(
    db: Session, clinic: str, exercise: Exercise, data: bytes, content_type: str,
    filename: str | None, actor: str,
) -> ExerciseMedia:
    """The body upload: the laptop path, and the fallback when a presigned
    POST is refused. The same checks as a confirm, in the same order."""
    checked = check_clip_type(content_type)
    cap = blobs.max_bytes_for(checked)
    if len(data) > cap:
        raise HTTPException(
            status_code=413, detail=f"That file is larger than {cap // (1024 * 1024)} MB"
        )
    try:
        blobs.check_size(len(data), checked)
        blobs.sniff(data[:1024], checked)
        stored = blobs.put(blobs.new_clinic_key(clinic, checked), data, checked)
    except blobs.BlobError as e:
        raise HTTPException(status_code=422, detail=str(e))
    row = _row(clinic, exercise, key=stored.key, content_type=checked, size=stored.byte_size,
               actor=actor)
    return _record(db, clinic, exercise, row, filename, actor)


def _record(db: Session, clinic: str, exercise: Exercise, row: ExerciseMedia,
            filename: str | None, actor: str) -> ExerciseMedia:
    db.add(row)
    db.flush()
    audit(db, clinic, actor, "media.create", "media", row.id,
          {"exercise_id": exercise.id, "kind": row.kind, "filename": (filename or "")[:80]})
    db.commit()
    return row


def clinic_media(db: Session, clinic: str, exercise_id: int,
                 media_id: int) -> ExerciseMedia | None:
    """The clinic's own clip for that exercise, or None — another clinic's
    is unknown to this one, which the router turns into a 404."""
    media = db.get(ExerciseMedia, media_id)
    if media is None or media.hospital_id != clinic or media.exercise_id != exercise_id:
        return None
    return media


def delete_clip(db: Session, clinic: str, media: ExerciseMedia, *, actor: str) -> None:
    """Blob and row both go: a demonstration the therapist took back must
    stop playing on every day it was assigned to, which resolution handles
    the moment the row is gone."""
    blobs.delete(media.storage_key)
    if media.poster_key and not media.poster_key.startswith("public:"):
        blobs.delete(media.poster_key)
    for e in db.scalars(select(Exercise).where(Exercise.media_id == media.id)).all():
        e.media_id = None
    audit(db, clinic, actor, "media.delete", "media", media.id,
          {"exercise_id": media.exercise_id})
    db.delete(media)
    db.commit()


def readable_by(media: ExerciseMedia | None, clinic: str | None) -> bool:
    """Whether a clinic, or one of its patients, may stream this clip: the
    clinic's own, or an approved library clip. Anyone else gets the same
    404 an unknown id gets."""
    if media is None:
        return False
    if media.hospital_id is not None:
        return clinic is not None and media.hospital_id == clinic
    return media.approval_status == "approved"


def stream(media: ExerciseMedia, *, poster: bool = False) -> Response:
    """The bytes, from this API: what a laptop serves in place of a presigned
    URL. A ``public:`` key is the SPA bucket's to serve, not ours."""
    from app.api.attachments import bytes_response

    key = media.poster_key if poster else media.storage_key
    if not key or key.startswith("public:"):
        raise HTTPException(status_code=404, detail="Unknown clip")
    return bytes_response(key, "image/jpeg" if poster else media.content_type, None, inline=True)
