"""Console routes for the exercise library, under ``/api/hep``."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.hep import ensure_ready
from app.hep.models import ExerciseMedia
from app.hep.service import (
    HepError,
    clinic_id,
    create_custom,
    exercise_payload,
    get_exercise,
    list_exercises,
    patch_exercise,
    vocabulary,
)
from app.llm.insights import BANNED
from app.models.hospital import Hospital

router = APIRouter(prefix="/hep", tags=["hep"])


def _ready(db: Session = Depends(get_db)) -> Session:
    if not settings.hep_enabled:
        raise HTTPException(status_code=404, detail="Exercise plans are not enabled")
    ensure_ready(db)
    return db


def _clinic(db: Session) -> str:
    try:
        return clinic_id(db)
    except HepError as e:
        raise HTTPException(status_code=503, detail=str(e))


def _no_diagnostic(*texts: str | None) -> None:
    for text in texts:
        if text and BANNED.search(text):
            raise HTTPException(
                status_code=422, detail="Patient-facing text must not use diagnostic language"
            )


def _media_for(db: Session, media_id: int | None) -> ExerciseMedia | None:
    return db.get(ExerciseMedia, media_id) if media_id else None


class ExerciseCreate(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    body_region: str
    category: str
    instructions: str = Field(default="", max_length=2000)
    synonyms: list[str] = Field(default_factory=list, max_length=12)
    equipment: str = Field(default="", max_length=120)
    precautions: str = Field(default="", max_length=400)
    actor: str = Field(default="provider", max_length=60)


class ExercisePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=80)
    body_region: str | None = None
    category: str | None = None
    instructions: str | None = Field(default=None, max_length=2000)
    synonyms: list[str] | None = Field(default=None, max_length=12)
    equipment: str | None = Field(default=None, max_length=120)
    precautions: str | None = Field(default=None, max_length=400)
    status: str | None = None
    actor: str = Field(default="provider", max_length=60)


@router.get("/exercises")
def list_library(
    q: str | None = None,
    region: str | None = None,
    category: str | None = None,
    origin: str | None = None,
    include_archived: bool = False,
    db: Session = Depends(_ready),
) -> dict:
    clinic = _clinic(db)
    try:
        rows = list_exercises(db, clinic, q=q, region=region, category=category, origin=origin,
                              include_archived=include_archived)
    except HepError as e:
        raise HTTPException(status_code=400, detail=str(e))
    hospital = db.get(Hospital, clinic)
    return {
        "exercises": [exercise_payload(e, _media_for(db, e.media_id)) for e in rows],
        "clinic": {"id": clinic, "name": hospital.name if hospital else clinic},
        **vocabulary(),
    }


@router.get("/exercises/{exercise_id}")
def read_exercise(exercise_id: int, db: Session = Depends(_ready)) -> dict:
    e = get_exercise(db, _clinic(db), exercise_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Unknown exercise")
    return exercise_payload(e, _media_for(db, e.media_id))


@router.post("/exercises/custom")
def create_custom_exercise(body: ExerciseCreate, db: Session = Depends(_ready)) -> dict:
    _no_diagnostic(body.title, body.instructions, body.precautions)
    try:
        e = create_custom(
            db, _clinic(db), title=body.title, body_region=body.body_region,
            category=body.category, instructions=body.instructions, synonyms=body.synonyms,
            equipment=body.equipment, precautions=body.precautions, actor=body.actor,
        )
    except HepError as err:
        raise HTTPException(status_code=422, detail=str(err))
    return exercise_payload(e)


@router.patch("/exercises/{exercise_id}")
def update_exercise(exercise_id: int, body: ExercisePatch, db: Session = Depends(_ready)) -> dict:
    clinic = _clinic(db)
    e = get_exercise(db, clinic, exercise_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Unknown exercise")
    _no_diagnostic(body.title, body.instructions, body.precautions)
    patch = body.model_dump(exclude={"actor"})
    try:
        e = patch_exercise(db, clinic, e, patch, body.actor)
    except HepError as err:
        raise HTTPException(status_code=422, detail=str(err))
    return exercise_payload(e, _media_for(db, e.media_id))


# --- plans ---------------------------------------------------------------------------

from app.hep.plans import (  # noqa: E402
    HepConflict,
    PlanItemIn,
    archive_plan,
    clinic_patient,
    create_plan,
    get_plan,
    list_plans,
    options_payload,
    patient_plans_payload,
    plan_payload,
    publish_plan,
    update_plan,
)


class PlanItemBody(BaseModel):
    exercise_id: int
    sets: int | None = Field(default=None, ge=0, le=999)
    reps: int | None = Field(default=None, ge=0, le=999)
    hold_seconds: int | None = Field(default=None, ge=0, le=999)
    frequency: str = "daily"
    side: str = "not_applicable"
    clinician_instructions: str = Field(default="", max_length=400)
    precautions_override: str = Field(default="", max_length=400)

    def to_item(self) -> PlanItemIn:
        return PlanItemIn(
            exercise_id=self.exercise_id, sets=self.sets, reps=self.reps,
            hold_seconds=self.hold_seconds, frequency=self.frequency, side=self.side,
            clinician_instructions=self.clinician_instructions,
            precautions_override=self.precautions_override,
        )


class PlanCreate(BaseModel):
    patient_id: str | None = None
    title: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=600)
    items: list[PlanItemBody] = Field(default_factory=list, max_length=40)
    assigned_by: str = Field(default="provider", max_length=60)
    actor: str = Field(default="provider", max_length=60)


class PlanUpdate(BaseModel):
    version: int
    patient_id: str | None = None
    title: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=600)
    items: list[PlanItemBody] | None = Field(default=None, max_length=40)
    assigned_by: str | None = Field(default=None, max_length=60)
    actor: str = Field(default="provider", max_length=60)


class PlanPublish(BaseModel):
    version: int
    actor: str = Field(default="provider", max_length=60)


class PlanArchive(BaseModel):
    actor: str = Field(default="provider", max_length=60)


def _plan_or_404(db: Session, clinic: str, plan_id: int):
    plan = get_plan(db, clinic, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Unknown plan")
    return plan


def _items_text(items: list[PlanItemBody] | None) -> list[str]:
    out: list[str] = []
    for i in items or []:
        out.extend([i.clinician_instructions, i.precautions_override])
    return out


def _hep_error(err: HepError) -> HTTPException:
    return HTTPException(status_code=409 if isinstance(err, HepConflict) else 422, detail=str(err))


@router.get("/options")
def plan_options(db: Session = Depends(_ready)) -> dict:
    return {**options_payload(db, _clinic(db)), **vocabulary()}


@router.get("/plans")
def list_exercise_plans(
    status: str | None = None, patient_id: str | None = None, db: Session = Depends(_ready)
) -> dict:
    clinic = _clinic(db)
    try:
        rows = list_plans(db, clinic, status=status, patient_id=patient_id)
    except HepError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return {"plans": [plan_payload(db, p, with_items=False) for p in rows]}


@router.post("/plans")
def create_exercise_plan(body: PlanCreate, db: Session = Depends(_ready)) -> dict:
    _no_diagnostic(body.title, body.notes, *_items_text(body.items))
    try:
        plan = create_plan(
            db, _clinic(db), patient_id=body.patient_id, title=body.title, notes=body.notes,
            items=[i.to_item() for i in body.items], assigned_by=body.assigned_by,
            actor=body.actor,
        )
    except HepError as err:
        raise _hep_error(err)
    return plan_payload(db, plan)


@router.get("/plans/{plan_id}")
def read_exercise_plan(plan_id: int, db: Session = Depends(_ready)) -> dict:
    return plan_payload(db, _plan_or_404(db, _clinic(db), plan_id))


@router.put("/plans/{plan_id}")
def update_exercise_plan(plan_id: int, body: PlanUpdate, db: Session = Depends(_ready)) -> dict:
    clinic = _clinic(db)
    plan = _plan_or_404(db, clinic, plan_id)
    _no_diagnostic(body.title, body.notes, *_items_text(body.items))
    try:
        plan = update_plan(
            db, clinic, plan, version=body.version, patient_id=body.patient_id,
            title=body.title, notes=body.notes,
            items=[i.to_item() for i in body.items] if body.items is not None else None,
            assigned_by=body.assigned_by, actor=body.actor,
        )
    except HepError as err:
        raise _hep_error(err)
    return plan_payload(db, plan)


@router.post("/plans/{plan_id}/publish")
def publish_exercise_plan(plan_id: int, body: PlanPublish, db: Session = Depends(_ready)) -> dict:
    clinic = _clinic(db)
    plan = _plan_or_404(db, clinic, plan_id)
    try:
        return publish_plan(db, clinic, plan, version=body.version, actor=body.actor)
    except HepError as err:
        raise _hep_error(err)


@router.post("/plans/{plan_id}/archive")
def archive_exercise_plan(
    plan_id: int, body: PlanArchive | None = None, db: Session = Depends(_ready)
) -> dict:
    clinic = _clinic(db)
    plan = _plan_or_404(db, clinic, plan_id)
    return plan_payload(db, archive_plan(db, clinic, plan, actor=body.actor if body else "provider"))


@router.get("/patients/{patient_id}/plans")
def patient_exercise_plans(patient_id: str, db: Session = Depends(_ready)) -> dict:
    clinic = _clinic(db)
    try:
        clinic_patient(db, clinic, patient_id)
    except HepError as err:
        raise HTTPException(status_code=404, detail=str(err))
    return patient_plans_payload(db, clinic, patient_id)
