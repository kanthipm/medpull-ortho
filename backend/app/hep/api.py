"""Console routes for the exercise library, the plans and the schedule,
under ``/api/hep``."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import ConsoleScope, console_scope
from app.config import settings
from app.database import get_db
from app.hep import ensure_ready
from app.hep.models import ExerciseMedia
from app.hep.service import (
    HepError,
    clinic_clip,
    clinic_clips,
    clinic_id,
    clinic_payload,
    create_custom,
    exercise_payload,
    get_exercise,
    list_exercises,
    patch_exercise,
    set_load_unit,
    vocabulary,
)
from app.llm.insights import BANNED
from app.models.patient import Patient

router = APIRouter(prefix="/hep", tags=["hep"])


def _ready(db: Session = Depends(get_db)) -> Session:
    if not settings.hep_enabled:
        raise HTTPException(status_code=404, detail="Exercise plans are not enabled")
    ensure_ready(db)
    return db


def _clinic(db: Session = Depends(_ready), scope: ConsoleScope = Depends(console_scope)) -> str:
    """The clinic this request's library and plans belong to. A hospital
    credential acts for its own hospital and no other; the staff token (or an
    open console) for ``HEP_CLINIC_ID``, else the first active hospital
    (service.clinic_id). A sports credential has no clinic to act for."""
    if scope.kind == "hospital" and scope.org_id:
        return scope.org_id
    if not scope.clinic:
        raise HTTPException(status_code=403, detail="This console has no clinic to act for")
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


def _base_url(request: Request) -> str:
    """Where a texted link points: the configured public base, else the
    host this request came in on."""
    return settings.checkin_base_url or str(request.base_url).rstrip("/")


# --- the clinic ----------------------------------------------------------------------


class ClinicPatch(BaseModel):
    """What a clinic may set about its own calendar: the unit it reads
    loads in."""

    load_unit: str = Field(max_length=8)
    actor: str = Field(default="provider", max_length=60)


@router.get("/clinic")
def read_clinic(db: Session = Depends(_ready), clinic: str = Depends(_clinic)) -> dict:
    """The clinic this console acts for and the unit it reads loads in."""
    return clinic_payload(db, clinic)


@router.patch("/clinic")
def update_clinic(
    body: ClinicPatch, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    """Pounds or kilograms for the acting clinic. A display choice: every
    load is stored, sent and received in kilograms whatever it says."""
    try:
        return set_load_unit(db, clinic, body.load_unit, actor=body.actor)
    except HepError as err:
        raise HTTPException(status_code=422, detail=str(err))


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
    db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    try:
        rows = list_exercises(db, clinic, q=q, region=region, category=category, origin=origin,
                              include_archived=include_archived)
    except HepError as e:
        raise HTTPException(status_code=400, detail=str(e))
    own = clinic_clips(db, clinic)
    return {
        "exercises": [exercise_payload(e, _media_for(db, e.media_id), own.get(e.id)) for e in rows],
        "clinic": clinic_payload(db, clinic),
        **vocabulary(),
    }


def _with_clips(db: Session, clinic: str, e) -> dict:
    """One exercise as the clinic sees it: the library clip and its own."""
    return exercise_payload(e, _media_for(db, e.media_id), clinic_clip(db, clinic, e.id))


@router.get("/exercises/{exercise_id}")
def read_exercise(
    exercise_id: int, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    e = get_exercise(db, clinic, exercise_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Unknown exercise")
    return _with_clips(db, clinic, e)


@router.post("/exercises/custom")
def create_custom_exercise(
    body: ExerciseCreate, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    _no_diagnostic(body.title, body.instructions, body.precautions)
    try:
        e = create_custom(
            db, clinic, title=body.title, body_region=body.body_region,
            category=body.category, instructions=body.instructions, synonyms=body.synonyms,
            equipment=body.equipment, precautions=body.precautions, actor=body.actor,
        )
    except HepError as err:
        raise HTTPException(status_code=422, detail=str(err))
    return exercise_payload(e)


@router.patch("/exercises/{exercise_id}")
def update_exercise(
    exercise_id: int,
    body: ExercisePatch,
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    e = get_exercise(db, clinic, exercise_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Unknown exercise")
    _no_diagnostic(body.title, body.instructions, body.precautions)
    patch = body.model_dump(exclude={"actor"})
    try:
        e = patch_exercise(db, clinic, e, patch, body.actor)
    except HepError as err:
        raise HTTPException(status_code=422, detail=str(err))
    return _with_clips(db, clinic, e)


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
def plan_options(db: Session = Depends(_ready), clinic: str = Depends(_clinic)) -> dict:
    return {**options_payload(db, clinic), **vocabulary()}


@router.get("/plans")
def list_exercise_plans(
    status: str | None = None,
    patient_id: str | None = None,
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    try:
        rows = list_plans(db, clinic, status=status, patient_id=patient_id)
    except HepError as err:
        raise HTTPException(status_code=400, detail=str(err))
    return {"plans": [plan_payload(db, p, with_items=False) for p in rows]}


@router.post("/plans")
def create_exercise_plan(
    body: PlanCreate, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    _no_diagnostic(body.title, body.notes, *_items_text(body.items))
    try:
        plan = create_plan(
            db, clinic, patient_id=body.patient_id, title=body.title, notes=body.notes,
            items=[i.to_item() for i in body.items], assigned_by=body.assigned_by,
            actor=body.actor,
        )
    except HepError as err:
        raise _hep_error(err)
    return plan_payload(db, plan)


@router.get("/plans/{plan_id}")
def read_exercise_plan(
    plan_id: int, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    return plan_payload(db, _plan_or_404(db, clinic, plan_id))


@router.put("/plans/{plan_id}")
def update_exercise_plan(
    plan_id: int, body: PlanUpdate, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
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
def publish_exercise_plan(
    plan_id: int, body: PlanPublish, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    plan = _plan_or_404(db, clinic, plan_id)
    try:
        return publish_plan(db, clinic, plan, version=body.version, actor=body.actor)
    except HepError as err:
        raise _hep_error(err)


@router.post("/plans/{plan_id}/archive")
def archive_exercise_plan(
    plan_id: int,
    body: PlanArchive | None = None,
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    plan = _plan_or_404(db, clinic, plan_id)
    return plan_payload(db, archive_plan(db, clinic, plan, actor=body.actor if body else "provider"))


@router.get("/patients/{patient_id}/plans")
def patient_exercise_plans(
    patient_id: str, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    try:
        clinic_patient(db, clinic, patient_id)
    except HepError as err:
        raise HTTPException(status_code=404, detail=str(err))
    return patient_plans_payload(db, clinic, patient_id)


# --- the schedule --------------------------------------------------------------------

from app.hep import calendar_reads  # noqa: E402
from app.hep import media as clips  # noqa: E402
from app.hep import schedule  # noqa: E402
from app.hep import texts  # noqa: E402
from app.hep.schedule import ScheduleConflict, UnknownRow  # noqa: E402


def _schedule_error(err: HepError) -> HTTPException:
    """The schedule's refusals: a row the clinic cannot see is a 404, a day
    that is taken or done a 409, anything else a 422."""
    if isinstance(err, UnknownRow):
        return HTTPException(status_code=404, detail=str(err))
    if isinstance(err, ScheduleConflict):
        return HTTPException(status_code=409, detail=str(err))
    return HTTPException(status_code=422, detail=str(err))


def _assignment_or_404(db: Session, clinic: str, assignment_id: int):
    row = schedule.get_assignment(db, clinic, assignment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown assignment")
    return row


class RepeatBody(BaseModel):
    """Repeat on these weekdays (Monday is 0) for this many weeks, counted
    in seven-day blocks from ``start``."""

    weekdays: list[int] = Field(min_length=1, max_length=7)
    weeks: int = Field(ge=1, le=schedule.MAX_REPEAT_WEEKS)
    start: date


class AssignmentCreate(BaseModel):
    patient_id: str
    exercise_id: int
    # The days, one by one, or a repeat in their place: exactly one of the two.
    dates: list[date] | None = Field(default=None, min_length=1, max_length=schedule.MAX_DATES)
    repeat: RepeatBody | None = None
    sets: int | None = Field(default=None, ge=0, le=999)
    reps: int | None = Field(default=None, ge=0, le=999)
    hold_seconds: int | None = Field(default=None, ge=0, le=999)
    side: str = "not_applicable"
    # The lifter's dose beyond counts, and what the therapist asks for with
    # the day (REQUIREMENTS: off | optional | required).
    load_kg: float | None = Field(default=None, ge=0, le=schedule.LOAD_MAX)
    rpe_target: int | None = Field(default=None, ge=0, le=schedule.SCALE_MAX)
    video_requirement: str = "optional"
    wearable_requirement: str = "optional"
    clinician_instructions: str = Field(default="", max_length=schedule.TEXT_LIMIT)
    # A care-team id; empty means the patient's assigned provider.
    assigned_by: str | None = Field(default=None, max_length=60)
    # Tell the patient by text, with a link that opens the app on the first
    # of these days.
    text_patient: bool = False
    actor: str = Field(default="provider", max_length=60)


class AssignmentPatch(BaseModel):
    """Only the fields sent are applied (``exclude_unset``), so ``"sets":
    null`` clears the sets while leaving them out leaves them alone."""

    sets: int | None = Field(default=None, ge=0, le=999)
    reps: int | None = Field(default=None, ge=0, le=999)
    hold_seconds: int | None = Field(default=None, ge=0, le=999)
    side: str | None = None
    load_kg: float | None = Field(default=None, ge=0, le=schedule.LOAD_MAX)
    rpe_target: int | None = Field(default=None, ge=0, le=schedule.SCALE_MAX)
    video_requirement: str | None = None
    wearable_requirement: str | None = None
    clinician_instructions: str | None = Field(default=None, max_length=schedule.TEXT_LIMIT)
    scheduled_for: date | None = None
    assigned_by: str | None = Field(default=None, max_length=60)
    sort_order: int | None = Field(default=None, ge=0, le=999)
    actor: str = Field(default="provider", max_length=60)


class AssignmentComplete(BaseModel):
    pain_after: int | None = Field(default=None, ge=0, le=10)
    note: str = Field(default="", max_length=schedule.NOTE_LIMIT)
    # What the patient told her in the room, when she has it.
    effort: int | None = Field(default=None, ge=0, le=schedule.SCALE_MAX)
    sets_done: int | None = Field(default=None, ge=0, le=999)
    reps_done: int | None = Field(default=None, ge=0, le=999)
    load_done_kg: float | None = Field(default=None, ge=0, le=schedule.LOAD_MAX)
    actor: str = Field(default="provider", max_length=60)


class ReviewBody(BaseModel):
    """The therapist's look at a done day. An empty note marks it reviewed
    and says nothing to the patient."""

    note: str = Field(default="", max_length=schedule.NOTE_LIMIT)
    actor: str = Field(default="provider", max_length=60)


class CopyWeekBody(BaseModel):
    patient_id: str
    from_start: date
    to_start: date
    # A care-team id; empty keeps whoever assigned each day being copied.
    assigned_by: str | None = Field(default=None, max_length=60)
    actor: str = Field(default="provider", max_length=60)


class ActorBody(BaseModel):
    actor: str = Field(default="provider", max_length=60)


class SeriesPatch(BaseModel):
    """An edit of "this and the following" days of a repeat. Only the
    fields sent are applied, as on one day; a series' days keep their own
    dates and positions."""

    sets: int | None = Field(default=None, ge=0, le=999)
    reps: int | None = Field(default=None, ge=0, le=999)
    hold_seconds: int | None = Field(default=None, ge=0, le=999)
    side: str | None = None
    load_kg: float | None = Field(default=None, ge=0, le=schedule.LOAD_MAX)
    rpe_target: int | None = Field(default=None, ge=0, le=schedule.SCALE_MAX)
    video_requirement: str | None = None
    wearable_requirement: str | None = None
    clinician_instructions: str | None = Field(default=None, max_length=schedule.TEXT_LIMIT)
    assigned_by: str | None = Field(default=None, max_length=60)
    actor: str = Field(default="provider", max_length=60)


class DuplicateBody(BaseModel):
    dates: list[date] = Field(min_length=1, max_length=schedule.MAX_DATES)
    actor: str = Field(default="provider", max_length=60)


@router.get("/schedule")
def read_schedule(
    start: date | None = None,
    days: int = Query(default=7, ge=1, le=schedule.MAX_WINDOW_DAYS),
    today: date | None = None,
    patient_id: str | None = None,
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """The week grid: the clinic's charts as rows, their assignments in the
    window, today marked. ``start`` defaults to the Monday of ``today``'s
    week; ``today`` to the server date."""
    try:
        return schedule.schedule_payload(
            db, clinic, start=start, days=days, today=today or date.today(), patient_id=patient_id,
        )
    except HepError as err:
        raise _schedule_error(err)


@router.post("/schedule", status_code=201)
def create_schedule(
    body: AssignmentCreate, request: Request, db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """One exercise, at one dose, on the days given or on a repeat.

    With ``dates`` it is all or nothing: a day that already carries the
    exercise refuses the whole request, naming the day. With ``repeat`` the
    server works the days out and lands around what is there: a day that
    already carries the exercise, or lies outside the schedule's reach, is
    left out and listed in ``skipped_days``, and the rows written share a
    ``series_id``. ``text_patient`` also texts the patient a link to the
    first of the days; what came of that is under ``text`` (null when no
    text was asked for or none could go)."""
    if (body.dates is None) == (body.repeat is None):
        raise HTTPException(status_code=422, detail="Send the days as dates, or a repeat, not both")
    _no_diagnostic(body.clinician_instructions)
    dose = {
        "sets": body.sets, "reps": body.reps, "hold_seconds": body.hold_seconds,
        "side": body.side, "clinician_instructions": body.clinician_instructions,
        "load_kg": body.load_kg, "rpe_target": body.rpe_target,
        "video_requirement": body.video_requirement,
        "wearable_requirement": body.wearable_requirement,
    }
    series_id, skips = None, []
    try:
        if body.repeat is not None:
            rows, skips, series_id = schedule.create_series(
                db, clinic, patient_id=body.patient_id, exercise_id=body.exercise_id,
                start=body.repeat.start, weekdays=body.repeat.weekdays, weeks=body.repeat.weeks,
                assigned_by=body.assigned_by, actor=body.actor, today=date.today(), **dose,
            )
        else:
            rows = schedule.create_assignments(
                db, clinic, patient_id=body.patient_id, exercise_id=body.exercise_id,
                dates=body.dates, assigned_by=body.assigned_by, actor=body.actor,
                today=date.today(), **dose,
            )
    except HepError as err:
        raise _schedule_error(err)
    text = None
    if body.text_patient and rows:
        text = texts.notify_assigned(db, db.get(Patient, body.patient_id), rows,
                                     base_url=_base_url(request), by=rows[0].assigned_by)
    return {
        "assignments": schedule.AssignmentView(db).render_all(rows),
        "series_id": series_id,
        **schedule.skipped_payload(skips),
        "text": text,
    }


@router.post("/schedule/copy-week", status_code=201)
def copy_schedule_week(
    body: CopyWeekBody, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    """Last week again: every assignment of the seven days from
    ``from_start`` on the same weekday from ``to_start``, dose, note and
    requirements with it. A day that already has the exercise, or lies
    outside the schedule's reach, is skipped: counted in ``skipped`` and
    listed with its reason in ``skipped_days``."""
    try:
        rows, skips = schedule.copy_week(
            db, clinic, patient_id=body.patient_id, from_start=body.from_start,
            to_start=body.to_start, assigned_by=body.assigned_by, actor=body.actor,
            today=date.today(),
        )
    except HepError as err:
        raise _schedule_error(err)
    return {"assignments": schedule.AssignmentView(db).render_all(rows),
            **schedule.skipped_payload(skips)}


@router.get("/review")
def review_queue(
    days: int = Query(default=schedule.REVIEW_DAYS, ge=1, le=schedule.MAX_REVIEW_DAYS),
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """What waits for the therapist: the clinic's done days nobody has
    reviewed that carry a clip of the attempt, or went over the dose,
    newest completion first. Each row says which under ``reason``."""
    try:
        return schedule.review_queue_payload(db, clinic, days=days)
    except HepError as err:
        raise _schedule_error(err)


@router.get("/review/count")
def review_count(
    days: int = Query(default=schedule.REVIEW_DAYS, ge=1, le=schedule.MAX_REVIEW_DAYS),
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """How many rows the queue holds, for the number beside Review: the
    same definition and the same window, without rendering a row."""
    try:
        return schedule.review_count_payload(db, clinic, days=days)
    except HepError as err:
        raise _schedule_error(err)


@router.get("/week")
def week_review(
    start: date | None = None,
    today: date | None = None,
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """The week in review, one entry per lifter: assigned against done,
    pain, effort against target, load done and written, the days that went
    over the dose, what waits for a look, and whether next week is set.
    Lifters with something to look at come first. ``start`` defaults to
    the Monday of ``today``'s week; ``today`` to the server date."""
    try:
        return calendar_reads.week_review_payload(db, clinic, start=start,
                                                  today=today or date.today())
    except HepError as err:
        raise _schedule_error(err)


@router.get("/calendar")
def read_calendar(
    start: date | None = None,
    days: int = Query(default=schedule.MAX_CALENDAR_DAYS, ge=1, le=schedule.MAX_CALENDAR_DAYS),
    today: date | None = None,
    patient_id: str | None = None,
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """A month of the calendar in compact rows: per chart and per day, what
    is on it, where each row stands and how it went, with the day's counts.
    No steps and no clip URLs; open a row through ``/schedule`` for those.
    ``start`` defaults to the Monday on or before the first of ``today``'s
    month."""
    try:
        return calendar_reads.calendar_payload(
            db, clinic, start=start, days=days, today=today or date.today(),
            patient_id=patient_id,
        )
    except HepError as err:
        raise _schedule_error(err)


@router.patch("/schedule/{assignment_id}")
def update_schedule(
    assignment_id: int, body: AssignmentPatch, db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    row = _assignment_or_404(db, clinic, assignment_id)
    patch = body.model_dump(exclude_unset=True, exclude={"actor"})
    _no_diagnostic(patch.get("clinician_instructions"))
    try:
        row = schedule.update_assignment(db, clinic, row, patch, actor=body.actor,
                                         today=date.today())
    except HepError as err:
        raise _schedule_error(err)
    return schedule.AssignmentView(db).render(row)


@router.delete("/schedule/{assignment_id}")
def delete_schedule(
    assignment_id: int, actor: str = Query(default="provider", max_length=60),
    db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    row = _assignment_or_404(db, clinic, assignment_id)
    try:
        schedule.delete_assignment(db, clinic, row, actor=actor)
    except HepError as err:
        raise _schedule_error(err)
    return {"ok": True}


@router.post("/schedule/{assignment_id}/complete")
def complete_schedule(
    assignment_id: int, body: AssignmentComplete | None = None, db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """The therapist logging a day done from the room, with what the
    patient told her: the pain after, the effort, and the sets, reps and
    load actually done. ``completion_source`` reads ``console``."""
    body = body or AssignmentComplete()
    row = _assignment_or_404(db, clinic, assignment_id)
    try:
        row = schedule.complete_assignment(
            db, row, pain_after=body.pain_after, note=body.note, source="console",
            actor=body.actor, effort=body.effort, sets_done=body.sets_done,
            reps_done=body.reps_done, load_done_kg=body.load_done_kg,
        )
    except HepError as err:
        raise _schedule_error(err)
    return schedule.AssignmentView(db).render(row)


@router.post("/schedule/{assignment_id}/reopen")
def reopen_schedule(
    assignment_id: int, body: ActorBody | None = None, db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """Undo a day the console logged done: the row is open again. A day the
    patient logged themselves is their record and answers 409, as does a
    day that is not done."""
    row = _assignment_or_404(db, clinic, assignment_id)
    try:
        row = schedule.reopen_assignment(db, clinic, row, actor=(body or ActorBody()).actor)
    except HepError as err:
        raise _schedule_error(err)
    return schedule.AssignmentView(db).render(row)


@router.post("/schedule/{assignment_id}/duplicate", status_code=201)
def duplicate_schedule(
    assignment_id: int, body: DuplicateBody, db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """The same exercise at the same dose, note and requirements on other
    days, as open days of their own: drag to copy. All or nothing, like an
    assignment made by hand: a day that already carries the exercise is a
    409 naming it."""
    row = _assignment_or_404(db, clinic, assignment_id)
    try:
        rows = schedule.duplicate_assignment(db, clinic, row, body.dates, actor=body.actor,
                                             today=date.today())
    except HepError as err:
        raise _schedule_error(err)
    return {"assignments": schedule.AssignmentView(db).render_all(rows)}


@router.post("/schedule/{assignment_id}/review")
def review_schedule(
    assignment_id: int, request: Request, body: ReviewBody | None = None,
    db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    """The therapist has looked at a done day. The row records who and
    when; a note also goes to the patient as one line on the thread, under
    her name, so they read it in Care, and as a text with a link to the
    exercise (``text``: what came of that, null when there was no note or
    no text could go). An open day → 409."""
    body = body or ReviewBody()
    row = _assignment_or_404(db, clinic, assignment_id)
    _no_diagnostic(body.note)
    try:
        row, message = schedule.review_assignment(db, row, note=body.note, actor=body.actor)
    except HepError as err:
        raise _schedule_error(err)
    text = None
    if message is not None:
        text = texts.notify_review(db, row, base_url=_base_url(request))
    return {**schedule.AssignmentView(db).render(row), "text": text}


# --- a repeat, as one thing -----------------------------------------------------------


@router.patch("/series/{series_id}")
def update_series(
    series_id: str, body: SeriesPatch,
    from_day: date | None = Query(default=None, alias="from"),
    db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    """Re-dose or re-word "this and the following": the fields sent go onto
    every still-open day of the repeat from ``from`` on (today when left
    out). Done and skipped days, and open days before it, keep what they
    had."""
    patch = body.model_dump(exclude_unset=True, exclude={"actor"})
    _no_diagnostic(patch.get("clinician_instructions"))
    since = from_day or date.today()
    try:
        rows = schedule.update_series(db, clinic, series_id, patch, from_day=since,
                                      actor=body.actor)
    except HepError as err:
        raise _schedule_error(err)
    return {
        "series_id": series_id,
        "from": since.isoformat(),
        "updated": len(rows),
        "assignments": schedule.AssignmentView(db).render_all(rows),
    }


@router.delete("/series/{series_id}")
def delete_series(
    series_id: str,
    from_day: date | None = Query(default=None, alias="from"),
    actor: str = Query(default="provider", max_length=60),
    db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    """Clear "this and the following": remove the repeat's still-open days
    from ``from`` on (today when left out). ``kept`` counts the days of the
    repeat that stay: the done, the skipped and the earlier."""
    since = from_day or date.today()
    try:
        deleted, kept = schedule.delete_series(db, clinic, series_id, from_day=since, actor=actor)
    except HepError as err:
        raise _schedule_error(err)
    return {"ok": True, "series_id": series_id, "from": since.isoformat(),
            "deleted": deleted, "kept": kept}


@router.get("/patients/{patient_id}/schedule")
def patient_schedule(
    patient_id: str,
    start: date | None = None,
    days: int = Query(default=7, ge=1, le=schedule.MAX_WINDOW_DAYS),
    today: date | None = None,
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """One chart's strip, for the patient page."""
    try:
        patient = clinic_patient(db, clinic, patient_id)
    except HepError as err:
        raise HTTPException(status_code=404, detail=str(err))
    try:
        return schedule.patient_schedule_payload(
            db, clinic, patient, start=start, days=days, today=today or date.today(),
        )
    except HepError as err:
        raise _schedule_error(err)


@router.get("/patients/{patient_id}/exercises/{exercise_id}/history")
def exercise_history(
    patient_id: str,
    exercise_id: int,
    days: int = Query(default=calendar_reads.HISTORY_DAYS, ge=1,
                      le=calendar_reads.MAX_HISTORY_DAYS),
    ahead: int = Query(default=0, ge=0, le=schedule.FUTURE_DAYS),
    today: date | None = None,
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """One exercise on one chart over time, oldest first: each day it was
    on, as written and as done (load, sets, reps, pain, effort against the
    target), and the run in a few numbers. ``ahead`` adds the days already
    written after today."""
    try:
        patient = clinic_patient(db, clinic, patient_id)
    except HepError as err:
        raise HTTPException(status_code=404, detail=str(err))
    exercise = _exercise_or_404(db, clinic, exercise_id)
    try:
        return calendar_reads.history_payload(db, patient, exercise, days=days, ahead=ahead,
                                              today=today or date.today())
    except HepError as err:
        raise _schedule_error(err)


# --- the therapist's clip ----------------------------------------------------------


def _exercise_or_404(db: Session, clinic: str, exercise_id: int):
    e = get_exercise(db, clinic, exercise_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Unknown exercise")
    return e


class ClipConfirm(BaseModel):
    storage_key: str = Field(min_length=8, max_length=300)
    content_type: str
    byte_size: int = 0
    filename: str | None = None
    actor: str = Field(default="provider", max_length=60)


@router.get("/exercises/{exercise_id}/media/upload-ticket")
def clip_upload_ticket(
    exercise_id: int,
    content_type: str = Query(...),
    byte_size: int = Query(..., ge=1),
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """Where to put the therapist's own demonstration: the attachments
    ticket shape, for a clinic key. A GET, like the patient's ticket, so
    picking a clip never takes the database write lock."""
    _exercise_or_404(db, clinic, exercise_id)
    return clips.clip_ticket(clinic, content_type, byte_size)


@router.post("/exercises/{exercise_id}/media", status_code=201)
def confirm_clip(
    exercise_id: int, body: ClipConfirm, db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """The clip is at its key; check it and write the row, approved. From
    here the exercise plays her clip wherever this clinic assigns it."""
    e = _exercise_or_404(db, clinic, exercise_id)
    clips.confirm_clip(
        db, clinic, e, storage_key=body.storage_key, content_type=body.content_type,
        byte_size=body.byte_size, filename=body.filename, actor=body.actor,
    )
    return {"exercise": _with_clips(db, clinic, e)}


@router.post("/exercises/{exercise_id}/media/direct", status_code=201)
def upload_clip_direct(
    exercise_id: int,
    data: bytes = Body(..., media_type="application/octet-stream"),
    content_type: str = Header(..., alias="Content-Type"),
    filename: str | None = Query(default=None),
    actor: str = Query(default="provider", max_length=60),
    db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """The clip as the raw request body: the laptop and test path, and the
    fallback when a presigned POST is refused (see
    ``attachments.console_upload_direct`` for why not multipart)."""
    e = _exercise_or_404(db, clinic, exercise_id)
    clips.store_clip(db, clinic, e, data, content_type, filename, actor)
    return {"exercise": _with_clips(db, clinic, e)}


@router.delete("/exercises/{exercise_id}/media/{media_id}")
def delete_clip(
    exercise_id: int, media_id: int, actor: str = Query(default="provider", max_length=60),
    db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    _exercise_or_404(db, clinic, exercise_id)
    media = clips.clinic_media(db, clinic, exercise_id, media_id)
    if media is None:
        raise HTTPException(status_code=404, detail="Unknown clip")
    clips.delete_clip(db, clinic, media, actor=actor)
    return {"ok": True}


@router.get("/media/{media_id}/raw")
def read_clip_bytes(
    media_id: int, poster: bool = False, db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> Response:
    """A clip's bytes from this API, where there is no object store to
    presign against. ``service.media_url`` points here on a laptop."""
    media = db.get(ExerciseMedia, media_id)
    if not clips.readable_by(media, clinic):
        raise HTTPException(status_code=404, detail="Unknown clip")
    return clips.stream(media, poster=poster)


# --- programs ------------------------------------------------------------------------

from app.hep import templates as programs  # noqa: E402


class TemplateItemBody(BaseModel):
    """One exercise of a program: named by id or by catalog key, on its
    weekdays (Monday is 0; empty means every day), with the dose and the
    requirements an assignment carries."""

    exercise_id: int | None = None
    exercise_key: str | None = Field(default=None, max_length=80)
    weekdays: list[int] | None = Field(default=None, max_length=7)
    sets: int | None = Field(default=None, ge=0, le=999)
    reps: int | None = Field(default=None, ge=0, le=999)
    hold_seconds: int | None = Field(default=None, ge=0, le=999)
    side: str = "not_applicable"
    load_kg: float | None = Field(default=None, ge=0, le=schedule.LOAD_MAX)
    rpe_target: int | None = Field(default=None, ge=0, le=schedule.SCALE_MAX)
    clinician_instructions: str = Field(default="", max_length=schedule.TEXT_LIMIT)
    video_requirement: str = "optional"
    wearable_requirement: str = "optional"


class TemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=programs.NAME_LIMIT)
    description: str = Field(default="", max_length=programs.DESCRIPTION_LIMIT)
    weeks: int = Field(default=2, ge=1, le=programs.MAX_WEEKS)
    items: list[TemplateItemBody] = Field(min_length=1, max_length=programs.MAX_ITEMS)
    actor: str = Field(default="provider", max_length=60)


class TemplateUpdate(BaseModel):
    """What is sent is replaced; what is left out stays."""

    name: str | None = Field(default=None, min_length=2, max_length=programs.NAME_LIMIT)
    description: str | None = Field(default=None, max_length=programs.DESCRIPTION_LIMIT)
    weeks: int | None = Field(default=None, ge=1, le=programs.MAX_WEEKS)
    items: list[TemplateItemBody] | None = Field(default=None, min_length=1,
                                                 max_length=programs.MAX_ITEMS)
    actor: str = Field(default="provider", max_length=60)


class TemplateApply(BaseModel):
    patient_id: str
    start: date
    # Defaults to the program's own length.
    weeks: int | None = Field(default=None, ge=1, le=programs.MAX_WEEKS)
    # A care-team id; empty means the patient's assigned provider.
    assigned_by: str | None = Field(default=None, max_length=60)
    actor: str = Field(default="provider", max_length=60)


def _template_or_404(db: Session, clinic: str, template_id: int):
    row = programs.get_template(db, clinic, template_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown program")
    return row


def _template_items(items: list[TemplateItemBody] | None) -> list[dict] | None:
    if items is None:
        return None
    _no_diagnostic(*(i.clinician_instructions for i in items))
    return [i.model_dump() for i in items]


@router.get("/templates")
def list_templates(db: Session = Depends(_ready), clinic: str = Depends(_clinic)) -> dict:
    """The clinic's programs still in use, by name."""
    return programs.templates_payload(db, clinic)


@router.post("/templates", status_code=201)
def create_template(
    body: TemplateCreate, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    try:
        row = programs.create_template(
            db, clinic, name=body.name, description=body.description, weeks=body.weeks,
            items=_template_items(body.items), actor=body.actor,
        )
    except HepError as err:
        raise _schedule_error(err)
    return programs.template_payload(db, row)


@router.get("/templates/{template_id}")
def read_template(
    template_id: int, db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    return programs.template_payload(db, _template_or_404(db, clinic, template_id))


@router.put("/templates/{template_id}")
def update_template(
    template_id: int, body: TemplateUpdate, db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    row = _template_or_404(db, clinic, template_id)
    try:
        row = programs.update_template(
            db, clinic, row, name=body.name, description=body.description, weeks=body.weeks,
            items=_template_items(body.items), actor=body.actor,
        )
    except HepError as err:
        raise _schedule_error(err)
    return programs.template_payload(db, row)


@router.delete("/templates/{template_id}")
def delete_template(
    template_id: int, actor: str = Query(default="provider", max_length=60),
    db: Session = Depends(_ready), clinic: str = Depends(_clinic),
) -> dict:
    """Archives the program; the days it put on calendars stay."""
    programs.archive_template(db, clinic, _template_or_404(db, clinic, template_id), actor=actor)
    return {"ok": True}


@router.post("/templates/{template_id}/apply", status_code=201)
def apply_template(
    template_id: int, body: TemplateApply, db: Session = Depends(_ready),
    clinic: str = Depends(_clinic),
) -> dict:
    """Every item on its weekdays from ``start`` for ``weeks`` weeks, around
    whatever the patient's calendar already holds and inside the schedule's
    reach: a day that already has the exercise, or lies past the reach, is
    skipped, counted in ``skipped`` and listed with its reason in
    ``skipped_days``."""
    row = _template_or_404(db, clinic, template_id)
    try:
        rows, skips = programs.apply_template(
            db, clinic, row, patient_id=body.patient_id, start=body.start, weeks=body.weeks,
            assigned_by=body.assigned_by, actor=body.actor, today=date.today(),
        )
    except HepError as err:
        raise _schedule_error(err)
    return {"assignments": schedule.AssignmentView(db).render_all(rows),
            **schedule.skipped_payload(skips)}
