"""Programs: the exercises a clinic puts on a kind of patient's week.

A template ("Patellar tendinopathy · phase 2") is a clinic's own list of
exercises with their weekdays, doses and requirements, kept as JSON on one
row (``models.ExerciseTemplate``). Applying it to a patient from a start
date for a number of weeks writes ordinary schedule rows through
``schedule.place_rows``, so what lands on the grid is indistinguishable from
days the therapist put there one at a time, and a day that already carries
the exercise is left as it is. Deleting a template archives it: the days it
produced stay.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.hep import schedule
from app.hep.models import Exercise, ExerciseTemplate
from app.hep.plans import SIDE_LABELS, _count, clinic_patient, dose_text
from app.hep.service import HepError, audit, visible_to
from app.hep.schedule import Placement, UnknownRow, _load, _member, _requirement, _scale, _side

NAME_LIMIT = 80
DESCRIPTION_LIMIT = 600
MAX_WEEKS = 12
MAX_ITEMS = 40
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
# What one item carries, in the order the payload lists it.
ITEM_FIELDS = (
    "exercise_id", "exercise_key", "weekdays", "sets", "reps", "hold_seconds", "side",
    "load_kg", "rpe_target", "clinician_instructions", "video_requirement", "wearable_requirement",
)


# --- reads ------------------------------------------------------------------------


def list_templates(db: Session, clinic: str) -> list[ExerciseTemplate]:
    """The clinic's programs still in use, by name."""
    return db.scalars(
        select(ExerciseTemplate).where(
            ExerciseTemplate.hospital_id == clinic, ExerciseTemplate.archived_at.is_(None),
        ).order_by(ExerciseTemplate.name, ExerciseTemplate.id)
    ).all()


def get_template(db: Session, clinic: str, template_id: int) -> ExerciseTemplate | None:
    """One of the clinic's programs; another clinic's, or an archived one,
    is not there."""
    row = db.get(ExerciseTemplate, template_id)
    if row is None or row.hospital_id != clinic or row.archived_at is not None:
        return None
    return row


def find_template(db: Session, clinic: str, name: str) -> ExerciseTemplate | None:
    """The clinic's program of that name, if one is in use (the seed asks)."""
    return db.scalar(
        select(ExerciseTemplate).where(
            ExerciseTemplate.hospital_id == clinic, ExerciseTemplate.name == name,
            ExerciseTemplate.archived_at.is_(None),
        ).order_by(ExerciseTemplate.id)
    )


# --- validation -----------------------------------------------------------------


def _name(name: str | None) -> str:
    name = " ".join((name or "").split())
    if len(name) < 2:
        raise HepError("Give the program a name")
    if len(name) > NAME_LIMIT:
        raise HepError(f"Keep the name under {NAME_LIMIT} characters")
    return name


def _weeks(weeks: Any, fallback: int | None = None) -> int:
    if weeks is None or weeks == "":
        if fallback is None:
            raise HepError("Say how many weeks the program runs")
        return fallback
    try:
        n = int(weeks)
    except (TypeError, ValueError):
        raise HepError("Weeks must be a whole number")
    if not 1 <= n <= MAX_WEEKS:
        raise HepError(f"A program runs between 1 and {MAX_WEEKS} weeks")
    return n


def _weekdays(value: Any) -> list[int] | None:
    """``[0..6]`` with Monday 0, in order and once each, or None for every
    day."""
    if value is None:
        return None
    try:
        days = sorted({int(d) for d in value})
    except (TypeError, ValueError):
        raise HepError("Weekdays are numbers from 0 (Monday) to 6 (Sunday)")
    if not days:
        raise HepError("Pick at least one weekday, or leave weekdays empty for every day")
    if any(d < 0 or d > 6 for d in days):
        raise HepError("Weekdays are numbers from 0 (Monday) to 6 (Sunday)")
    return days


def _resolve_exercise(db: Session, clinic: str, item: dict[str, Any]) -> Exercise:
    exercise = None
    if item.get("exercise_id") is not None:
        exercise = db.get(Exercise, int(item["exercise_id"]))
    elif item.get("exercise_key"):
        exercise = db.scalar(select(Exercise).where(Exercise.key == str(item["exercise_key"])))
    else:
        raise HepError("Each item names an exercise, by id or by key")
    if exercise is None or not visible_to(exercise, clinic):
        raise HepError(f"Unknown exercise: {item.get('exercise_id') or item.get('exercise_key')}")
    if exercise.status == "archived":
        raise HepError(f"{exercise.title} is archived and cannot be in a program")
    return exercise


def normalize_items(db: Session, clinic: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The items as stored: each exercise resolved to a row the clinic can
    see, the dose and requirements checked as the schedule checks them, and
    no exercise twice on the same weekday (it could only ever land once)."""
    if not items:
        raise HepError("Add at least one exercise")
    if len(items) > MAX_ITEMS:
        raise HepError(f"A program holds at most {MAX_ITEMS} exercises")
    seen: dict[tuple[int, int], str] = {}
    out = []
    for item in items:
        exercise = _resolve_exercise(db, clinic, item)
        weekdays = _weekdays(item.get("weekdays"))
        for d in weekdays if weekdays is not None else range(7):
            if (exercise.id, d) in seen:
                raise HepError(f"{exercise.title} is listed twice on {WEEKDAY_NAMES[d]}")
            seen[(exercise.id, d)] = exercise.title
        out.append({
            "exercise_id": exercise.id,
            "exercise_key": exercise.key,
            "weekdays": weekdays,
            "sets": _count(item.get("sets"), "Sets"),
            "reps": _count(item.get("reps"), "Reps"),
            "hold_seconds": _count(item.get("hold_seconds"), "Hold"),
            "side": _side(item.get("side")),
            "load_kg": _load(item.get("load_kg")),
            "rpe_target": _scale(item.get("rpe_target"), "Target effort"),
            "clinician_instructions": schedule._text(item.get("clinician_instructions")),
            "video_requirement": _requirement(item.get("video_requirement"),
                                              "The clip requirement"),
            "wearable_requirement": _requirement(item.get("wearable_requirement"),
                                                 "The wearable requirement"),
        })
    return out


# --- writes -----------------------------------------------------------------------


def create_template(
    db: Session, clinic: str, *, name: str, description: str, weeks: Any,
    items: list[dict[str, Any]], actor: str,
) -> ExerciseTemplate:
    now = datetime.now()
    row = ExerciseTemplate(
        hospital_id=clinic, name=_name(name),
        description=schedule._text(description, DESCRIPTION_LIMIT), weeks=_weeks(weeks),
        items=normalize_items(db, clinic, items), created_by=actor or "provider",
        created_at=now, updated_at=now,
    )
    db.add(row)
    db.flush()
    audit(db, clinic, actor, "template.create", "template", row.id,
          {"name": row.name, "items": len(row.items)})
    db.commit()
    return row


def update_template(
    db: Session, clinic: str, row: ExerciseTemplate, *, name: str | None,
    description: str | None, weeks: Any, items: list[dict[str, Any]] | None, actor: str,
) -> ExerciseTemplate:
    """Replace what was sent; what was left out stays."""
    if name is not None:
        row.name = _name(name)
    if description is not None:
        row.description = schedule._text(description, DESCRIPTION_LIMIT)
    if weeks is not None:
        row.weeks = _weeks(weeks)
    if items is not None:
        row.items = normalize_items(db, clinic, items)
    row.updated_at = datetime.now()
    audit(db, clinic, actor, "template.update", "template", row.id,
          {"name": row.name, "items": len(row.items)})
    db.commit()
    return row


def archive_template(db: Session, clinic: str, row: ExerciseTemplate, *, actor: str) -> None:
    now = datetime.now()
    row.archived_at = now
    row.updated_at = now
    audit(db, clinic, actor, "template.archive", "template", row.id, {"name": row.name})
    db.commit()


def apply_template(
    db: Session, clinic: str, row: ExerciseTemplate, *, patient_id: str, start: date,
    weeks: Any, assigned_by: str | None, actor: str, today: date,
):
    """Every item on its weekdays from ``start`` for ``weeks`` weeks (the
    program's own count unless told otherwise), skipping days that already
    carry the exercise. Returns the rows written and how many were skipped."""
    try:
        patient = clinic_patient(db, clinic, patient_id)
    except HepError as e:
        raise UnknownRow(str(e))
    weeks = _weeks(weeks, fallback=row.weeks)
    member = _member(db, assigned_by, patient.assigned_provider_id)
    exercises = {e.id: e for e in db.scalars(select(Exercise).where(
        Exercise.id.in_({int(item["exercise_id"]) for item in row.items})))}
    placements: list[Placement] = []
    for offset in range(7 * weeks):
        day = start + timedelta(days=offset)
        for item in row.items:
            weekdays = item.get("weekdays")
            if weekdays is not None and day.weekday() not in weekdays:
                continue
            exercise = exercises.get(int(item["exercise_id"]))
            if exercise is None or exercise.status == "archived":
                continue
            placements.append(Placement(
                exercise=exercise, day=day, assigned_by=member,
                fields={k: item.get(k) for k in ITEM_FIELDS[3:]},
            ))
    if not placements:
        raise HepError("That program has nothing left to put on the calendar")
    return schedule.place_rows(
        db, clinic, patient, placements, actor=actor, today=today, action="assignment.apply",
        detail={"template_id": row.id, "start": start.isoformat(), "weeks": weeks},
    )


# --- payloads -----------------------------------------------------------------------


def item_payload(item: dict[str, Any], exercise: Exercise | None) -> dict[str, Any]:
    side = item.get("side") or "not_applicable"
    return {
        "exercise_id": item.get("exercise_id"),
        "exercise_key": exercise.key if exercise else item.get("exercise_key"),
        "title": exercise.title if exercise else "",
        "weekdays": item.get("weekdays"),
        "sets": item.get("sets"), "reps": item.get("reps"), "hold_seconds": item.get("hold_seconds"),
        "side": side, "side_label": SIDE_LABELS.get(side, ""),
        "load_kg": item.get("load_kg"), "rpe_target": item.get("rpe_target"),
        "dose": dose_text(item.get("sets"), item.get("reps"), item.get("hold_seconds"), side,
                          load_kg=item.get("load_kg")),
        "clinician_instructions": item.get("clinician_instructions") or "",
        "video_requirement": item.get("video_requirement") or "optional",
        "wearable_requirement": item.get("wearable_requirement") or "optional",
    }


def template_payload(db: Session, row: ExerciseTemplate,
                     exercises: dict[int, Exercise] | None = None) -> dict[str, Any]:
    ids = {int(item["exercise_id"]) for item in row.items if item.get("exercise_id") is not None}
    if exercises is None:
        exercises = {e.id: e for e in db.scalars(select(Exercise).where(Exercise.id.in_(ids)))}
    return {
        "id": row.id, "clinic_id": row.hospital_id, "name": row.name,
        "description": row.description or "", "weeks": row.weeks,
        "items": [item_payload(item, exercises.get(int(item["exercise_id"])))
                  for item in row.items],
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def templates_payload(db: Session, clinic: str) -> dict[str, Any]:
    rows = list_templates(db, clinic)
    ids = {int(item["exercise_id"]) for row in rows for item in row.items
           if item.get("exercise_id") is not None}
    exercises = ({e.id: e for e in db.scalars(select(Exercise).where(Exercise.id.in_(ids)))}
                 if ids else {})
    return {"templates": [template_payload(db, row, exercises) for row in rows]}
