"""Library reads and writes, clinic scope, payloads and the audit log."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.hep.models import (
    BODY_REGIONS,
    CATEGORIES,
    CATEGORY_LABELS,
    EXERCISE_STATUSES,
    REGION_LABELS,
    AuditEvent,
    Exercise,
    ExerciseMedia,
)
from app.models.hospital import Hospital
from app.models.patient import Patient
from app.personal.scope import clinic_filter


class HepError(ValueError):
    """A request the library refuses; the router turns it into a 422."""


# --- clinic scope ---------------------------------------------------------------


def clinic_id(db: Session) -> str:
    """The clinic the staff console (the global token, or an open console) acts
    for: ``HEP_CLINIC_ID`` names it, else the active hospital with the most
    clinic charts, ties by id, so a new, empty hospital row never moves the
    library. A hospital credential never asks: its clinic is its own
    (app/hep/api.py). Every HEP query is scoped by the answer."""
    if settings.hep_clinic_id:
        if db.get(Hospital, settings.hep_clinic_id) is None:
            raise HepError(f"HEP_CLINIC_ID names an unknown hospital: {settings.hep_clinic_id}")
        return settings.hep_clinic_id
    charts = clinic_filter(
        select(Patient.hospital_id, func.count(Patient.id).label("n")).group_by(Patient.hospital_id)
    ).subquery()
    row = db.scalar(
        select(Hospital)
        .outerjoin(charts, charts.c.hospital_id == Hospital.id)
        .where(Hospital.active.is_(True))
        .order_by(func.coalesce(charts.c.n, 0).desc(), Hospital.id)
    )
    if row is None:
        raise HepError("No hospital to act for")
    return row.id


def visible_to(exercise: Exercise, clinic: str) -> bool:
    return exercise.origin == "standard" or exercise.hospital_id == clinic


# --- audit ----------------------------------------------------------------------


def audit(db: Session, clinic: str | None, actor: str, action: str, subject_type: str,
          subject_id: int | str, detail: dict[str, Any] | None = None) -> None:
    db.add(AuditEvent(hospital_id=clinic, actor=actor or "provider", action=action,
                      subject_type=subject_type, subject_id=str(subject_id), detail=detail))


# --- the library ----------------------------------------------------------------


def search_terms(exercise: Exercise) -> str:
    return " ".join([exercise.title, *(exercise.synonyms or []), exercise.key or ""]).lower()


def list_exercises(
    db: Session, clinic: str, *, q: str | None = None, region: str | None = None,
    category: str | None = None, origin: str | None = None, include_archived: bool = False,
) -> list[Exercise]:
    if region is not None and region not in BODY_REGIONS:
        raise HepError(f"Unknown body region: {region}")
    if category is not None and category not in CATEGORIES:
        raise HepError(f"Unknown category: {category}")
    if origin is not None and origin not in ("standard", "custom"):
        raise HepError(f"Unknown origin: {origin}")
    needle = (q or "").strip().lower()
    rows = db.scalars(select(Exercise).order_by(Exercise.title, Exercise.id)).all()
    out = []
    for e in rows:
        if not visible_to(e, clinic):
            continue
        if e.status == "archived" and not include_archived:
            continue
        if origin is not None and e.origin != origin:
            continue
        if region is not None and e.body_region != region:
            continue
        if category is not None and e.category != category:
            continue
        if needle and needle not in search_terms(e):
            continue
        out.append(e)
    return out


def get_exercise(db: Session, clinic: str, exercise_id: int) -> Exercise | None:
    e = db.get(Exercise, exercise_id)
    if e is None or not visible_to(e, clinic):
        return None
    return e


def _clean_lines(text: str) -> str:
    return "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())


def _clean_synonyms(values: list[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        s = " ".join(str(v).split())[:60]
        if s and s.lower() not in {x.lower() for x in seen}:
            seen.append(s)
    return seen[:12]


def create_custom(
    db: Session, clinic: str, *, title: str, body_region: str, category: str,
    instructions: str, synonyms: list[str], equipment: str, precautions: str, actor: str,
) -> Exercise:
    if body_region not in BODY_REGIONS:
        raise HepError(f"Unknown body region: {body_region}")
    if category not in CATEGORIES:
        raise HepError(f"Unknown category: {category}")
    title = " ".join(title.split())
    if len(title) < 3:
        raise HepError("Give the exercise a name")
    exercise = Exercise(
        key=None, origin="custom", hospital_id=clinic, title=title,
        synonyms=_clean_synonyms(synonyms), body_region=body_region, category=category,
        instructions=_clean_lines(instructions), equipment=equipment.strip()[:120],
        precautions=precautions.strip()[:400], status="draft", created_by=actor or "provider",
    )
    db.add(exercise)
    db.flush()
    audit(db, clinic, actor, "exercise.create", "exercise", exercise.id, {"title": title})
    db.commit()
    return exercise


def patch_exercise(db: Session, clinic: str, exercise: Exercise, patch: dict[str, Any],
                   actor: str) -> Exercise:
    """Text fields change only on a custom exercise (standard wording follows
    the catalog). ``status`` may move on either, except that a standard
    exercise cannot be archived away from a clinic's library — the spec keeps
    the standard set shared."""
    text_keys = {"title", "synonyms", "body_region", "category", "instructions", "equipment",
                 "precautions"}
    touched = {k for k, v in patch.items() if v is not None}
    if exercise.origin == "standard" and touched & text_keys:
        raise HepError("Standard exercises cannot be edited; create a custom copy instead")
    changed = False
    if "title" in touched:
        title = " ".join(str(patch["title"]).split())
        if len(title) < 3:
            raise HepError("Give the exercise a name")
        exercise.title, changed = title, True
    if "synonyms" in touched:
        exercise.synonyms, changed = _clean_synonyms(list(patch["synonyms"])), True
    if "body_region" in touched:
        if patch["body_region"] not in BODY_REGIONS:
            raise HepError(f"Unknown body region: {patch['body_region']}")
        exercise.body_region, changed = patch["body_region"], True
    if "category" in touched:
        if patch["category"] not in CATEGORIES:
            raise HepError(f"Unknown category: {patch['category']}")
        exercise.category, changed = patch["category"], True
    if "instructions" in touched:
        exercise.instructions, changed = _clean_lines(str(patch["instructions"])), True
    if "equipment" in touched:
        exercise.equipment, changed = str(patch["equipment"]).strip()[:120], True
    if "precautions" in touched:
        exercise.precautions, changed = str(patch["precautions"]).strip()[:400], True
    if "status" in touched:
        status = patch["status"]
        if status not in EXERCISE_STATUSES:
            raise HepError(f"Unknown status: {status}")
        if exercise.origin == "standard" and status == "archived":
            raise HepError("Standard exercises cannot be archived")
        exercise.status = status
    if changed:
        exercise.version = (exercise.version or 1) + 1
    exercise.updated_at = datetime.now()
    audit(db, clinic, actor, "exercise.update", "exercise", exercise.id,
          {"fields": sorted(touched)})
    db.commit()
    return exercise


# --- payloads -------------------------------------------------------------------


# Where a client fetches a clip's bytes when there is no object store to
# presign against (a laptop, the tests): the console's route and the patient
# app's, each behind its own credential.
CONSOLE_MEDIA_ROUTE = "/api/hep/media"
PATIENT_MEDIA_ROUTE = "/api/mobile/exercises/media"


def media_source(media: ExerciseMedia) -> str:
    """``clinic`` for a clinic's own demonstration, ``library`` for the
    shared clip a standard exercise ships with."""
    return "clinic" if media.hospital_id else "library"


def media_payload(
    media: ExerciseMedia | None, *, route: str = CONSOLE_MEDIA_ROUTE,
    uploaded_by_name: str | None = None,
) -> dict[str, Any] | None:
    """What a client may play. The URL is present only once a reviewer has
    approved the clip; until then the UI shows a placeholder and the text.
    ``route`` is where the bytes stream from on a laptop (the console's
    route or the patient app's); on AWS both are a presigned URL."""
    if media is None:
        return None
    approved = media.approval_status == "approved"
    return {
        "id": media.id, "kind": media.kind, "source": media_source(media),
        "exercise_id": media.exercise_id, "clinic_id": media.hospital_id,
        "approval_status": media.approval_status,
        "playable": approved,
        "url": media_url(media.storage_key, media.content_type, media.id, route=route)
        if approved else None,
        "poster_url": media_url(media.poster_key, "image/jpeg", media.id, poster=True, route=route)
        if approved and media.poster_key else None,
        "content_type": media.content_type,
        "width": media.width, "height": media.height, "duration_ms": media.duration_ms,
        "uploaded_by": media.uploaded_by, "uploaded_by_name": uploaded_by_name,
        "reviewed_by": media.reviewed_by,
        "reviewed_at": media.reviewed_at.isoformat() if media.reviewed_at else None,
        "version": media.version,
        "created_at": media.created_at.isoformat() if media.created_at else None,
    }


def media_url(
    key: str | None, content_type: str, media_id: int | None = None, *,
    poster: bool = False, route: str = CONSOLE_MEDIA_ROUTE,
) -> str | None:
    """``public:<path>`` is a non-PHI file served by the SPA bucket at
    ``/hep/<path>``; anything else is an attachments blob behind a
    presigned URL or, with no object store, the API's own stream of that
    media row (``GET <route>/<id>/raw``, ``?poster=1`` for the still)."""
    if not key:
        return None
    if key.startswith("public:"):
        return "/hep/" + key.removeprefix("public:").lstrip("/")
    from app.storage import blobs

    url = blobs.download_url(key, content_type)
    if url or media_id is None:
        return url
    return f"{route}/{media_id}/raw" + ("?poster=1" if poster else "")


def clinic_clips(db: Session, clinic: str) -> dict[int, ExerciseMedia]:
    """The clinic's own approved demonstrations, newest per exercise. One
    query for a whole library list or a week of the schedule."""
    rows = db.scalars(
        select(ExerciseMedia).where(
            ExerciseMedia.hospital_id == clinic,
            ExerciseMedia.exercise_id.is_not(None),
            ExerciseMedia.approval_status == "approved",
        ).order_by(ExerciseMedia.created_at, ExerciseMedia.id)
    ).all()
    # Ascending, so the latest upload for an exercise is the one kept.
    return {row.exercise_id: row for row in rows}


def clinic_clip(db: Session, clinic: str, exercise_id: int) -> ExerciseMedia | None:
    return db.scalar(
        select(ExerciseMedia).where(
            ExerciseMedia.hospital_id == clinic,
            ExerciseMedia.exercise_id == exercise_id,
            ExerciseMedia.approval_status == "approved",
        ).order_by(ExerciseMedia.created_at.desc(), ExerciseMedia.id.desc())
    )


def resolve_clip(
    db: Session, clinic: str | None, exercise: Exercise,
    clips: dict[int, ExerciseMedia] | None = None,
) -> ExerciseMedia | None:
    """The demonstration a clinic and its patients see for an exercise: the
    clinic's latest approved clip, else the library clip, else none.
    ``clips`` is a ``clinic_clips`` map when the caller already has one."""
    own = None
    if clinic:
        own = clips.get(exercise.id) if clips is not None else clinic_clip(db, clinic, exercise.id)
    if own is not None:
        return own
    if exercise.media_id:
        media = db.get(ExerciseMedia, exercise.media_id)
        if media is not None and media.approval_status == "approved":
            return media
    return None


def exercise_payload(
    e: Exercise, media: ExerciseMedia | None = None, clinic_media: ExerciseMedia | None = None,
) -> dict[str, Any]:
    """``media`` is the library clip; ``clinic_media`` the clinic's own
    demonstration of this exercise, which wins wherever the exercise is
    shown to that clinic or its patients (``resolve_clip``)."""
    return {
        "id": e.id, "key": e.key, "origin": e.origin, "clinic_id": e.hospital_id,
        "title": e.title, "synonyms": list(e.synonyms or []),
        "body_region": e.body_region, "body_region_label": REGION_LABELS.get(e.body_region, e.body_region),
        "category": e.category, "category_label": CATEGORY_LABELS.get(e.category, e.category),
        "instructions": e.instructions or "",
        "steps": [s for s in (e.instructions or "").splitlines() if s.strip()],
        "equipment": e.equipment or "", "precautions": e.precautions or "",
        "status": e.status, "version": int(e.version or 1),
        "usage_count": int(e.usage_count or 0),
        "media": media_payload(media),
        "clinic_media": media_payload(clinic_media),
        "created_by": e.created_by,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def vocabulary() -> dict[str, Any]:
    return {
        "regions": [{"key": k, "label": REGION_LABELS[k]} for k in BODY_REGIONS],
        "categories": [{"key": k, "label": CATEGORY_LABELS[k]} for k in CATEGORIES],
        "statuses": list(EXERCISE_STATUSES),
    }
