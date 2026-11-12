"""The exercise schedule: one exercise on one patient's calendar day.

A plan (``plans.py``) is a standing prescription with a frequency. This is
the therapist's week grid — Step-Ups on Monday, Wednesday and Friday, Heel
Slides every day — and what the patient's Today lists. Done, the row itself
carries what came back: the pain score, a note, the clip of the attempt (an
attachment on the patient's thread). The clip the patient follows is
resolved per clinic (``service.resolve_clip``): the therapist's own
demonstration when she has uploaded one, the library's otherwise.

The second pass runs the day the way a PT would: the therapist sets a load
and a target effort beside the counts and says, per exercise, whether she
wants a clip of the attempt and the wearable on (``REQUIREMENTS``); the
patient starts the exercise as a session (pain before, wearable on), finishes
it with pain after, effort and what was done, and the server fills the
duration and the heart rate from the wearable's samples inside the window;
she reviews the clip with a note that lands on the thread. A week can be
copied to the next, and a program (``templates.py``) applied from a date.

The third pass is the calendar grown for a clinic whose lifters tend to do
more than was written. Every row says where it stands today (``state_of``:
upcoming, due, in progress, done, skipped, missed); a done row says what was
done against what was prescribed (``done_against_prescribed``), and one that
went over the dose waits for the therapist's look even without a clip
(``review_reason``, the one definition of "to review"). An exercise can
repeat on weekdays for some weeks as a series that is re-dosed or cleared
from a day on; a row can be duplicated onto other days; a completion the
console logged can be undone. Loads stay in kilograms; a clinic that works
in pounds reads the server's own strings in pounds (``service.load_text``).

The console and the patient app read the same ``Assignment`` payload
(``AssignmentView``); the patient's copy drops the clinic id and points its
media URLs at the route the patient's session can reach. The wider reads —
a lifter's week in review, a month at a glance, one exercise over time —
are in ``calendar_reads.py``.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.hep.models import (
    CATEGORY_LABELS,
    REGION_LABELS,
    REQUIREMENTS,
    SIDES,
    Exercise,
    ExerciseAssignment,
    ExerciseMedia,
)
from app.hep.plans import SIDE_LABELS, _count, clinic_patient, dose_text
from app.hep.service import (
    CONSOLE_MEDIA_ROUTE,
    PATIENT_MEDIA_ROUTE,
    HepError,
    audit,
    clinic_care_team,
    clinic_clips,
    clinic_payload,
    load_text,
    load_unit_of,
    media_payload,
    resolve_clip,
    visible_to,
)
from app.models.attachment import Attachment
from app.models.enums import MetricType
from app.models.hospital import Hospital
from app.models.mobile import Message
from app.models.observation import Observation
from app.models.patient import CareTeamMember, Patient
from app.personal.scope import is_clinic

# How far from today a day may be scheduled: two months back (a therapist
# logging what was done last visit) and three months ahead (a training block).
PAST_DAYS = 60
FUTURE_DAYS = 90
# One POST puts one exercise on at most twelve weeks of days.
MAX_DATES = 84
# A repeat runs at most twelve weeks; the reach above still bounds it.
MAX_REPEAT_WEEKS = 12
# The widest grid a read may ask for.
MAX_WINDOW_DAYS = 28
# The widest month the compact calendar may ask for: six weeks of rows.
MAX_CALENDAR_DAYS = 42
# The widest calendar the patient's program may ask for.
MAX_PROGRAM_DAYS = 42
WEEK = 7
TEXT_LIMIT = 400
NOTE_LIMIT = 600
# The heaviest load a day may carry, in kilograms; RPE and pain run 0–10.
LOAD_MAX = 500.0
SCALE_MAX = 10
# How far back "to review" looks by default, and at most.
REVIEW_DAYS = 14
MAX_REVIEW_DAYS = 90
# Who logged a day done: the patient in the app, the therapist in the room,
# or the patient by text.
COMPLETION_SOURCES = ("app", "console", "sms")
# What a done day keeps: its counts, side, load and target effort.
DOSE_FIELDS = ("sets", "reps", "hold_seconds", "side", "load_kg", "rpe_target",
               # The ceilings: the load not to go past, the effort to stop at.
               "load_max_kg", "rpe_max")
REQUIREMENT_FIELDS = ("video_requirement", "wearable_requirement")
EDITABLE = DOSE_FIELDS + REQUIREMENT_FIELDS + (
    "clinician_instructions", "scheduled_for", "assigned_by", "sort_order",
)
# What an edit of a whole series may change: everything but each row's own
# day and position.
SERIES_EDITABLE = DOSE_FIELDS + REQUIREMENT_FIELDS + ("clinician_instructions", "assigned_by")
# Where a row stands on the day it is read.
STATES = ("upcoming", "due", "in_progress", "done", "skipped", "missed")
# Reported effort this far above the target counts as more than was written,
# this far below as less. One point either way is how people rate.
EFFORT_MARGIN = 2
# Why a done day waits for the therapist.
REVIEW_REASONS = ("clip", "over")
# Why a write of many days left one out.
SKIP_ALREADY_THERE = "already_there"
SKIP_OUT_OF_REACH = "out_of_reach"
SKIP_REASONS = (SKIP_ALREADY_THERE, SKIP_OUT_OF_REACH)


class ScheduleConflict(HepError):
    """A write the calendar refuses as it stands — the day already carries
    that exercise, or the row is done; the router answers 409."""


class UnknownRow(HepError):
    """A patient or exercise this clinic cannot see; the router answers 404
    so that an id's existence does not leak."""


class RequirementUnmet(HepError):
    """The therapist asked for a clip or the wearable and the completion
    came without it; the router answers 422 in the words the patient reads."""


def week_start(today: date) -> date:
    """The Monday of the week ``today`` is in: where the grid opens."""
    return today - timedelta(days=today.weekday())


def days_of(start: date, days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(days)]


def check_window(days: int) -> int:
    if not 1 <= days <= MAX_WINDOW_DAYS:
        raise HepError(f"Show between 1 and {MAX_WINDOW_DAYS} days")
    return days


def in_reach(day: date, today: date) -> bool:
    return today - timedelta(days=PAST_DAYS) <= day <= today + timedelta(days=FUTURE_DAYS)


def reach_text() -> str:
    return f"the schedule runs {PAST_DAYS} days back and {FUTURE_DAYS} days ahead of today"


def _in_reach(day: date, today: date) -> None:
    if not in_reach(day, today):
        raise HepError(f"{day.isoformat()} is out of reach: {reach_text()}")


def state_of(row: ExerciseAssignment, today: date) -> str:
    """Where a row stands on ``today``: done and skipped are what they are;
    an open row started today is in progress, one whose day has passed is
    missed, one on today is due, and the rest are upcoming. Missed is never
    stored: the same row is due again the moment its day is moved."""
    if row.status in ("done", "skipped"):
        return row.status
    if row.started_at is not None and row.started_at.date() == today:
        return "in_progress"
    if row.scheduled_for < today:
        return "missed"
    return "due" if row.scheduled_for == today else "upcoming"


# --- reads ------------------------------------------------------------------------


def get_assignment(db: Session, clinic: str, assignment_id: int) -> ExerciseAssignment | None:
    row = db.get(ExerciseAssignment, assignment_id)
    if row is None or row.hospital_id != clinic:
        return None
    return row


def own_assignment(db: Session, patient: Patient, assignment_id: int) -> ExerciseAssignment | None:
    row = db.get(ExerciseAssignment, assignment_id)
    if row is None or row.patient_id != patient.id:
        return None
    return row


def clinic_rows(db: Session, clinic: str, start: date, end: date,
                patient_ids: list[str] | None = None) -> list[ExerciseAssignment]:
    """A clinic's assignments on days ``start`` up to (not including) ``end``,
    in grid order: day, patient, position."""
    q = select(ExerciseAssignment).where(
        ExerciseAssignment.hospital_id == clinic,
        ExerciseAssignment.scheduled_for >= start,
        ExerciseAssignment.scheduled_for < end,
    )
    if patient_ids is not None:
        q = q.where(ExerciseAssignment.patient_id.in_(patient_ids))
    return db.scalars(q.order_by(
        ExerciseAssignment.scheduled_for, ExerciseAssignment.patient_id,
        ExerciseAssignment.sort_order, ExerciseAssignment.id,
    )).all()


def patient_rows(db: Session, patient_id: str, start: date, end: date) -> list[ExerciseAssignment]:
    return db.scalars(
        select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == patient_id,
            ExerciseAssignment.scheduled_for >= start,
            ExerciseAssignment.scheduled_for < end,
        ).order_by(ExerciseAssignment.scheduled_for, ExerciseAssignment.sort_order,
                   ExerciseAssignment.id)
    ).all()


def series_rows(db: Session, clinic: str, series_id: str) -> list[ExerciseAssignment]:
    """Every day one repeat wrote for this clinic, oldest first."""
    return db.scalars(
        select(ExerciseAssignment).where(
            ExerciseAssignment.hospital_id == clinic,
            ExerciseAssignment.series_id == series_id,
        ).order_by(ExerciseAssignment.scheduled_for, ExerciseAssignment.id)
    ).all()


def schedule_patients(db: Session, clinic: str) -> list[Patient]:
    """The grid's rows: the clinic's clinic charts, by name."""
    rows = db.scalars(
        select(Patient).where(Patient.hospital_id == clinic).order_by(Patient.name, Patient.id)
    ).all()
    return [p for p in rows if is_clinic(p)]


# --- validation -----------------------------------------------------------------


def _exercise_for(db: Session, clinic: str, exercise_id: int) -> Exercise:
    e = db.get(Exercise, exercise_id)
    if e is None or not visible_to(e, clinic):
        raise UnknownRow(f"Unknown exercise: {exercise_id}")
    if e.status == "archived":
        raise HepError(f"{e.title} is archived and cannot be scheduled")
    return e


def _patient_for(db: Session, clinic: str, patient_id: str) -> Patient:
    try:
        return clinic_patient(db, clinic, patient_id)
    except HepError as e:
        raise UnknownRow(str(e))


def _member(db: Session, member_id: str | None, fallback: str | None) -> str:
    chosen = (member_id or "").strip() or (fallback or "")
    if not chosen or db.get(CareTeamMember, chosen) is None:
        raise HepError(f"Unknown care team member: {chosen or '(none)'}")
    return chosen


def _reviewer(db: Session, actor: str | None, fallback: str | None) -> str:
    """Who stands behind a review: the actor when the console named a care
    team member, else the patient's own therapist. The console's generic
    ``provider`` is nobody to sign a note with."""
    if actor and db.get(CareTeamMember, actor) is not None:
        return actor
    return _member(db, None, fallback)


def _side(side: str | None) -> str:
    side = side or "not_applicable"
    if side not in SIDES:
        raise HepError(f"Unknown side: {side}")
    return side


def _text(text: str | None, limit: int = TEXT_LIMIT) -> str:
    text = (text or "").strip()
    if len(text) > limit:
        raise HepError(f"Keep that under {limit} characters")
    return text


def _load(value: Any, name: str = "Load") -> float | None:
    """Kilograms, 0–500; nothing (or zero: bodyweight) reads as none."""
    if value is None or value == "":
        return None
    try:
        kg = float(value)
    except (TypeError, ValueError):
        raise HepError(f"{name} must be a number of kilograms")
    if kg < 0 or kg > LOAD_MAX:
        raise HepError(f"{name} must be between 0 and {LOAD_MAX:g} kg")
    return round(kg, 2) or None


def _scale(value: Any, name: str) -> int | None:
    """A 0–10 rating: pain, or effort (RPE)."""
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise HepError(f"{name} is a number from 0 to {SCALE_MAX}")
    if n < 0 or n > SCALE_MAX:
        raise HepError(f"{name} is a number from 0 to {SCALE_MAX}")
    return n


def _requirement(value: str | None, name: str) -> str:
    """``off``, ``optional`` or ``required``; nothing reads as optional."""
    value = (value or "optional").strip()
    if value not in REQUIREMENTS:
        raise HepError(f"{name} is one of {', '.join(REQUIREMENTS)}")
    return value


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


def _local(moment: datetime | None) -> datetime | None:
    """A phone's timestamp in the clock the rows keep: an aware instant is
    brought into the server's zone and stripped, a naive one is trusted."""
    if moment is None or moment.tzinfo is None:
        return moment
    return moment.astimezone().replace(tzinfo=None)


def _taken(db: Session, patient_id: str, exercise_id: int, days: list[date], *,
           exclude_id: int | None = None) -> list[date]:
    """The days among ``days`` that already carry this exercise for the
    patient. One row per patient, exercise and day: a second one is refused
    rather than stacked."""
    q = select(ExerciseAssignment.scheduled_for).where(
        ExerciseAssignment.patient_id == patient_id,
        ExerciseAssignment.exercise_id == exercise_id,
        ExerciseAssignment.scheduled_for.in_(days),
    )
    if exclude_id is not None:
        q = q.where(ExerciseAssignment.id != exclude_id)
    return sorted(set(db.scalars(q).all()))


def _next_positions(db: Session, patient_id: str, days: list[date]) -> dict[date, int]:
    """Where a new row lands on each day: after whatever is already there."""
    rows = db.execute(
        select(ExerciseAssignment.scheduled_for, func.max(ExerciseAssignment.sort_order))
        .where(ExerciseAssignment.patient_id == patient_id,
               ExerciseAssignment.scheduled_for.in_(days))
        .group_by(ExerciseAssignment.scheduled_for)
    ).all()
    return {day: int(top or 0) + 1 for day, top in rows}


def check_ceilings(load_kg: Any, load_max_kg: Any, rpe_target: Any, rpe_max: Any) -> None:
    """A ceiling under the dose it caps is a typo, not a prescription."""
    if load_kg is not None and load_max_kg is not None and load_max_kg < load_kg:
        raise HepError("The load ceiling cannot be under the load prescribed")
    if rpe_target is not None and rpe_max is not None and rpe_max < rpe_target:
        raise HepError("The effort to stop at cannot be under the target effort")


def dose_fields(
    *, sets: Any, reps: Any, hold_seconds: Any, side: str | None, load_kg: Any, rpe_target: Any,
    video_requirement: str | None, wearable_requirement: str | None, clinician_instructions: str,
    load_max_kg: Any = None, rpe_max: Any = None,
) -> dict[str, Any]:
    """A dose, its ceilings, its requirements and its note, checked the way
    every write checks them, in the shape a row carries (and a placement
    copies)."""
    fields = {
        "side": _side(side), "sets": _count(sets, "Sets"), "reps": _count(reps, "Reps"),
        "hold_seconds": _count(hold_seconds, "Hold"), "load_kg": _load(load_kg),
        "rpe_target": _scale(rpe_target, "Target effort"),
        "load_max_kg": _load(load_max_kg, "The load ceiling"),
        "rpe_max": _scale(rpe_max, "The effort to stop at"),
        "video_requirement": _requirement(video_requirement, "The clip requirement"),
        "wearable_requirement": _requirement(wearable_requirement, "The wearable requirement"),
        "clinician_instructions": _text(clinician_instructions),
    }
    check_ceilings(fields["load_kg"], fields["load_max_kg"], fields["rpe_target"], fields["rpe_max"])
    return fields


def _taken_text(exercise: Exercise | None, days: list[date]) -> str:
    title = exercise.title if exercise else "That exercise"
    return f"{title} is already on {', '.join(d.isoformat() for d in days)}"


# --- writes -----------------------------------------------------------------------


def create_assignments(
    db: Session, clinic: str, *, patient_id: str, exercise_id: int, dates: list[date],
    sets: Any, reps: Any, hold_seconds: Any, side: str | None, clinician_instructions: str,
    assigned_by: str | None, actor: str, today: date,
    load_kg: Any = None, rpe_target: Any = None, video_requirement: str | None = None,
    wearable_requirement: str | None = None, load_max_kg: Any = None, rpe_max: Any = None,
) -> list[ExerciseAssignment]:
    """Put one exercise, at one dose, on each of ``dates`` for a patient.
    All or nothing: a day that already has the exercise refuses the whole
    request, naming the day, so a half-written week never has to be undone
    by hand."""
    patient = _patient_for(db, clinic, patient_id)
    exercise = _exercise_for(db, clinic, exercise_id)
    days = sorted(set(dates))
    if not days:
        raise HepError("Pick at least one day")
    if len(days) > MAX_DATES:
        raise HepError(f"One assignment covers at most {MAX_DATES} days")
    for day in days:
        _in_reach(day, today)
    fields = dose_fields(
        sets=sets, reps=reps, hold_seconds=hold_seconds, side=side, load_kg=load_kg,
        rpe_target=rpe_target, video_requirement=video_requirement,
        wearable_requirement=wearable_requirement, clinician_instructions=clinician_instructions,
        load_max_kg=load_max_kg, rpe_max=rpe_max,
    )
    member = _member(db, assigned_by, patient.assigned_provider_id)
    taken = _taken(db, patient.id, exercise.id, days)
    if taken:
        raise ScheduleConflict(_taken_text(exercise, taken))
    positions = _next_positions(db, patient.id, days)
    now = datetime.now()
    rows = []
    for day in days:
        row = ExerciseAssignment(
            hospital_id=clinic, patient_id=patient.id, exercise_id=exercise.id,
            scheduled_for=day, sort_order=positions.get(day, 0), assigned_by=member,
            status="assigned", created_at=now, updated_at=now, **fields,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    audit(db, clinic, actor, "assignment.create", "assignment", rows[0].id, {
        "ids": [r.id for r in rows], "patient_id": patient.id, "exercise_id": exercise.id,
        "dates": [d.isoformat() for d in days],
    })
    db.commit()
    return rows


def repeat_days(start: date, weekdays: list[int], weeks: int) -> list[date]:
    """The days a repeat lands on: each of ``weekdays`` (Monday 0) in the
    ``weeks`` seven-day blocks from ``start``, which need not be a Monday."""
    return [d for d in days_of(start, WEEK * weeks) if d.weekday() in weekdays]


def create_series(
    db: Session, clinic: str, *, patient_id: str, exercise_id: int, start: date,
    weekdays: Any, weeks: Any, sets: Any, reps: Any, hold_seconds: Any, side: str | None,
    clinician_instructions: str, assigned_by: str | None, actor: str, today: date,
    load_kg: Any = None, rpe_target: Any = None, video_requirement: str | None = None,
    wearable_requirement: str | None = None, load_max_kg: Any = None, rpe_max: Any = None,
) -> tuple[list[ExerciseAssignment], list["Skip"], str | None]:
    """One exercise, at one dose, on its weekdays for some weeks from
    ``start``: Step-Ups on Monday, Wednesday and Friday for four weeks.
    The rows share a ``series_id`` so the run can be re-dosed or cleared
    from a day on. Unlike a list of dates this lands around what is there:
    a day that already carries the exercise, or lies outside the schedule's
    reach, is left out and reported. Returns the rows, what was left out,
    and the series id (none when nothing was written)."""
    patient = _patient_for(db, clinic, patient_id)
    exercise = _exercise_for(db, clinic, exercise_id)
    on = _weekdays(weekdays)
    if on is None:
        raise HepError("Pick at least one weekday to repeat on")
    try:
        weeks = int(weeks)
    except (TypeError, ValueError):
        raise HepError("Weeks must be a whole number")
    if not 1 <= weeks <= MAX_REPEAT_WEEKS:
        raise HepError(f"A repeat runs between 1 and {MAX_REPEAT_WEEKS} weeks")
    fields = dose_fields(
        sets=sets, reps=reps, hold_seconds=hold_seconds, side=side, load_kg=load_kg,
        rpe_target=rpe_target, video_requirement=video_requirement,
        wearable_requirement=wearable_requirement, clinician_instructions=clinician_instructions,
        load_max_kg=load_max_kg, rpe_max=rpe_max,
    )
    member = _member(db, assigned_by, patient.assigned_provider_id)
    series_id = secrets.token_hex(8)
    placements = [Placement(exercise=exercise, day=day, assigned_by=member, fields=fields)
                  for day in repeat_days(start, on, weeks)]
    rows, skips = place_rows(
        db, clinic, patient, placements, actor=actor, today=today, action="assignment.repeat",
        detail={"series_id": series_id, "exercise_id": exercise.id, "start": start.isoformat(),
                "weekdays": on, "weeks": weeks},
        series_id=series_id,
    )
    return rows, skips, series_id if rows else None


def _clean_patch(db: Session, patch: dict[str, Any], touched: set[str]) -> dict[str, Any]:
    """The dose, requirement, note and author fields a patch touches, each
    checked, as a row is then set to them. Everything is checked before
    anything is written, so one bad field leaves a row (or a whole series)
    as it was. An empty ``assigned_by`` keeps whoever each row already
    names."""
    clean: dict[str, Any] = {}
    if "sets" in touched:
        clean["sets"] = _count(patch["sets"], "Sets")
    if "reps" in touched:
        clean["reps"] = _count(patch["reps"], "Reps")
    if "hold_seconds" in touched:
        clean["hold_seconds"] = _count(patch["hold_seconds"], "Hold")
    if "side" in touched:
        clean["side"] = _side(patch["side"])
    if "load_kg" in touched:
        clean["load_kg"] = _load(patch["load_kg"])
    if "rpe_target" in touched:
        clean["rpe_target"] = _scale(patch["rpe_target"], "Target effort")
    if "load_max_kg" in touched:
        clean["load_max_kg"] = _load(patch["load_max_kg"], "The load ceiling")
    if "rpe_max" in touched:
        clean["rpe_max"] = _scale(patch["rpe_max"], "The effort to stop at")
    if "video_requirement" in touched:
        clean["video_requirement"] = _requirement(patch["video_requirement"],
                                                  "The clip requirement")
    if "wearable_requirement" in touched:
        clean["wearable_requirement"] = _requirement(patch["wearable_requirement"],
                                                     "The wearable requirement")
    if "clinician_instructions" in touched:
        clean["clinician_instructions"] = _text(patch["clinician_instructions"])
    if "assigned_by" in touched and (patch["assigned_by"] or "").strip():
        clean["assigned_by"] = _member(db, patch["assigned_by"], None)
    return clean


def update_assignment(
    db: Session, clinic: str, row: ExerciseAssignment, patch: dict[str, Any], *,
    actor: str, today: date,
) -> ExerciseAssignment:
    """Re-dose, move, re-word or re-assign one day. A done day keeps its dose
    and its date — what was done is the record — but its note, author,
    requirements and position may still be tidied."""
    touched = {k for k in patch if k in EDITABLE}
    if not touched:
        raise HepError("Nothing to change")
    if row.status == "done" and touched & (set(DOSE_FIELDS) | {"scheduled_for"}):
        raise ScheduleConflict("That day is done; its dose and date stay as they were. "
                               "Add a new day instead")
    clean = _clean_patch(db, patch, touched)
    order = None
    if "sort_order" in touched:
        order = patch["sort_order"]
        if order is None or int(order) < 0:
            raise HepError("Position must be zero or more")
    if "scheduled_for" in touched:
        day = patch["scheduled_for"]
        if day is None:
            raise HepError("Choose a day")
        _in_reach(day, today)
        if day != row.scheduled_for:
            if _taken(db, row.patient_id, row.exercise_id, [day], exclude_id=row.id):
                raise ScheduleConflict(_taken_text(db.get(Exercise, row.exercise_id), [day]))
            row.scheduled_for = day
            row.sort_order = _next_positions(db, row.patient_id, [day]).get(day, 0)
    check_ceilings(clean.get("load_kg", row.load_kg), clean.get("load_max_kg", row.load_max_kg),
                   clean.get("rpe_target", row.rpe_target), clean.get("rpe_max", row.rpe_max))
    for name, value in clean.items():
        setattr(row, name, value)
    if order is not None:
        row.sort_order = int(order)
    row.updated_at = datetime.now()
    audit(db, clinic, actor, "assignment.update", "assignment", row.id,
          {"fields": sorted(touched)})
    db.commit()
    return row


def _open_from(rows: list[ExerciseAssignment], from_day: date) -> list[ExerciseAssignment]:
    """A series' rows an edit may still touch: assigned, on ``from_day`` or
    later. Done and skipped days are the record and stay."""
    return [r for r in rows if r.status == "assigned" and r.scheduled_for >= from_day]


def update_series(
    db: Session, clinic: str, series_id: str, patch: dict[str, Any], *, from_day: date,
    actor: str,
) -> list[ExerciseAssignment]:
    """Re-dose or re-word "this and the following": the patch goes onto
    every still-open row of the series from ``from_day`` on. Days already
    done or skipped, and open days before it, keep what they had. Returns
    the rows changed."""
    rows = series_rows(db, clinic, series_id)
    if not rows:
        raise UnknownRow(f"Unknown series: {series_id}")
    touched = {k for k in patch if k in SERIES_EDITABLE}
    if not touched:
        raise HepError("Nothing to change")
    clean = _clean_patch(db, patch, touched)
    changed = _open_from(rows, from_day)
    if not changed:
        return []
    for row in changed:
        check_ceilings(clean.get("load_kg", row.load_kg), clean.get("load_max_kg", row.load_max_kg),
                       clean.get("rpe_target", row.rpe_target), clean.get("rpe_max", row.rpe_max))
    now = datetime.now()
    for row in changed:
        for name, value in clean.items():
            setattr(row, name, value)
        row.updated_at = now
    audit(db, clinic, actor, "series.update", "series", series_id, {
        "ids": [r.id for r in changed], "from": from_day.isoformat(), "fields": sorted(touched),
    })
    db.commit()
    return changed


def delete_series(db: Session, clinic: str, series_id: str, *, from_day: date,
                  actor: str) -> tuple[int, int]:
    """Clear "this and the following": remove the series' still-open rows
    from ``from_day`` on. Returns how many went and how many of the series
    remain (the done, the skipped, the earlier)."""
    rows = series_rows(db, clinic, series_id)
    if not rows:
        raise UnknownRow(f"Unknown series: {series_id}")
    gone = _open_from(rows, from_day)
    if not gone:
        return 0, len(rows)
    audit(db, clinic, actor, "series.delete", "series", series_id, {
        "ids": [r.id for r in gone], "from": from_day.isoformat(),
        "patient_id": gone[0].patient_id, "exercise_id": gone[0].exercise_id,
    })
    for row in gone:
        db.delete(row)
    db.commit()
    return len(gone), len(rows) - len(gone)


def duplicate_assignment(
    db: Session, clinic: str, row: ExerciseAssignment, dates: list[date], *, actor: str,
    today: date,
) -> list[ExerciseAssignment]:
    """The same exercise at the same dose, note and requirements on other
    days: what dragging a chip with the copy key does. The copies are open
    days of their own, signed by whoever assigned the one copied, and not
    part of its series. All or nothing, like an assignment made by hand: a
    day that already carries the exercise refuses the request, naming it."""
    exercise = _exercise_for(db, clinic, row.exercise_id)
    days = sorted(set(dates))
    if not days:
        raise HepError("Pick at least one day")
    if len(days) > MAX_DATES:
        raise HepError(f"One copy covers at most {MAX_DATES} days")
    for day in days:
        _in_reach(day, today)
    taken = _taken(db, row.patient_id, row.exercise_id, days)
    if taken:
        raise ScheduleConflict(_taken_text(exercise, taken))
    positions = _next_positions(db, row.patient_id, days)
    now = datetime.now()
    copies = []
    for day in days:
        copy = ExerciseAssignment(
            hospital_id=clinic, patient_id=row.patient_id, exercise_id=row.exercise_id,
            scheduled_for=day, sort_order=positions.get(day, 0), assigned_by=row.assigned_by,
            status="assigned", created_at=now, updated_at=now, **placement_fields(row),
        )
        db.add(copy)
        copies.append(copy)
    db.flush()
    audit(db, clinic, actor, "assignment.duplicate", "assignment", row.id, {
        "ids": [c.id for c in copies], "patient_id": row.patient_id,
        "exercise_id": row.exercise_id, "dates": [d.isoformat() for d in days],
    })
    db.commit()
    return copies


def delete_assignment(db: Session, clinic: str, row: ExerciseAssignment, *, actor: str) -> None:
    if row.status == "done":
        raise ScheduleConflict("That day is done; the record stays")
    audit(db, clinic, actor, "assignment.delete", "assignment", row.id, {
        "patient_id": row.patient_id, "exercise_id": row.exercise_id,
        "scheduled_for": row.scheduled_for.isoformat(),
    })
    db.delete(row)
    db.commit()


def ensure_open(row: ExerciseAssignment) -> None:
    """A day is marked done once. The second tap (or the therapist logging
    what the patient already sent) is a conflict, never a quiet overwrite."""
    if row.status == "done":
        raise ScheduleConflict("That day is already marked done")


def check_requirements(row: ExerciseAssignment, *, has_clip: bool,
                       wearable_worn: bool | None) -> None:
    """What the therapist asked for has to be there before the day is
    done, in the words the patient reads on the sheet."""
    if row.video_requirement == "required" and not has_clip:
        raise RequirementUnmet("This exercise needs a clip of your attempt")
    if row.wearable_requirement == "required" and wearable_worn is not True:
        raise RequirementUnmet("This exercise is done with your wearable on")


def start_assignment(
    db: Session, row: ExerciseAssignment, *, pain_before: int | None, wearable_worn: bool | None,
) -> ExerciseAssignment:
    """The patient starts the exercise from the phone: the session opens
    now, with the pain they are in and whether the wearable is on. Starting
    again moves the start (the first attempt did not count); a day skipped
    earlier is back on; a done day is a conflict."""
    ensure_open(row)
    now = datetime.now()
    if row.status == "skipped":
        row.status, row.skip_reason = "assigned", None
    row.started_at = now
    row.ended_at = row.duration_s = row.hr_avg = row.hr_max = None
    row.pain_before = _scale(pain_before, "Pain")
    row.wearable_worn = wearable_worn
    row.updated_at = now
    db.commit()
    return row


def heart_rate_window(db: Session, patient_id: str, start: datetime,
                      end: datetime) -> tuple[int | None, int | None]:
    """The average and peak of the wearable's heart-rate samples inside the
    session, in bpm, or nothing when none arrived."""
    avg, top = db.execute(
        select(func.avg(Observation.value_num), func.max(Observation.value_num)).where(
            Observation.patient_id == patient_id,
            Observation.metric_type == MetricType.HR_SAMPLE,
            Observation.deleted_at.is_(None),
            Observation.value_num.is_not(None),
            Observation.start_time >= start,
            Observation.start_time <= end,
        )
    ).one()
    if avg is None:
        return None, None
    return int(round(avg)), int(round(top))


def complete_assignment(
    db: Session, row: ExerciseAssignment, *, pain_after: int | None, note: str, source: str,
    video_attachment_id: int | None = None, actor: str | None = None,
    effort: int | None = None, sets_done: Any = None, reps_done: Any = None,
    load_done_kg: Any = None, wearable_worn: bool | None = None,
    started_at: datetime | None = None, ended_at: datetime | None = None,
) -> ExerciseAssignment:
    """Record what came back: from the app (the patient, with a clip they
    may have sent) or from the console (the therapist, in the room). The
    console's log goes to the audit trail under her id; the patient's own
    tap is its own record. The session closes here: the phone's own
    ``started_at``/``ended_at`` when it sent them, else the start the server
    kept and now, and the heart rate inside that window when the wearable
    sent any."""
    ensure_open(row)
    if source not in COMPLETION_SOURCES:
        raise HepError(f"Unknown completion source: {source}")
    now = datetime.now()
    started = _local(started_at) or row.started_at
    ended = _local(ended_at) or (now if started else None)
    if started and ended and ended < started:
        raise HepError("The session ends after it starts")
    row.status = "done"
    row.completed_at = now
    row.pain_after = _scale(pain_after, "Pain")
    row.effort = _scale(effort, "Effort")
    row.sets_done = _count(sets_done, "Sets done")
    row.reps_done = _count(reps_done, "Reps done")
    row.load_done_kg = _load(load_done_kg, "Load done")
    row.started_at, row.ended_at = started, ended
    row.duration_s = int((ended - started).total_seconds()) if started and ended else None
    if wearable_worn is not None:
        row.wearable_worn = wearable_worn
    row.hr_avg, row.hr_max = (heart_rate_window(db, row.patient_id, started, ended)
                              if started and ended else (None, None))
    row.note = _text(note, NOTE_LIMIT) or None
    row.completion_source = source
    row.video_attachment_id = video_attachment_id
    row.skip_reason = None
    row.updated_at = now
    if actor:
        audit(db, row.hospital_id, actor, "assignment.complete", "assignment", row.id,
              {"pain_after": row.pain_after, "source": source})
    db.commit()
    return row


def reopen_assignment(db: Session, clinic: str, row: ExerciseAssignment, *,
                      actor: str) -> ExerciseAssignment:
    """Undo a day the console logged done: the row is open again, as if she
    had not logged it, and a review of it goes with it. A day the patient
    logged from the app (or by text) is their record and is not undone
    here. A session the patient had started on the phone keeps its start."""
    if row.status != "done":
        raise ScheduleConflict("That day is not marked done; there is nothing to undo")
    if row.completion_source != "console":
        raise ScheduleConflict("That day was logged by the patient; their record stays "
                               "as they sent it")
    row.status = "assigned"
    row.completed_at = row.pain_after = row.effort = None
    row.sets_done = row.reps_done = row.load_done_kg = None
    row.note = row.completion_source = None
    row.ended_at = row.duration_s = row.hr_avg = row.hr_max = None
    row.reviewed_at = row.reviewed_by = row.review_note = None
    row.updated_at = datetime.now()
    audit(db, clinic, actor, "assignment.reopen", "assignment", row.id,
          {"patient_id": row.patient_id})
    db.commit()
    return row


def skip_assignment(db: Session, row: ExerciseAssignment, *, reason: str) -> ExerciseAssignment:
    ensure_open(row)
    row.status = "skipped"
    row.skip_reason = _text(reason) or None
    row.updated_at = datetime.now()
    db.commit()
    return row


def completion_line(title: str, pain_after: int | None, note: str | None,
                    effort: int | None = None) -> str:
    """The thread line a completion from the app writes, so the chart shows
    the score (and the clip beside it) where the conversation is."""
    line = f"Did {title}"
    if pain_after is not None:
        line += f" · pain {pain_after}/10 after"
    if effort is not None:
        line += f" · effort {effort}/10"
    if note:
        line += "\n" + note.strip()
    return line


def review_line(title: str, note: str, *, has_clip: bool = True) -> str:
    """The thread line a review with a note writes, so the patient reads it
    in Care under the therapist's name."""
    what = f"{title} clip" if has_clip else title
    return f"About your {what}: {note.strip()}"


def review_assignment(
    db: Session, row: ExerciseAssignment, *, note: str, actor: str,
) -> tuple[ExerciseAssignment, Message | None]:
    """The therapist has looked at a done day. The review is recorded on
    the row under her id; a note also goes to the patient as one line on
    the thread. A day not done yet has nothing to look at."""
    if row.status != "done":
        raise ScheduleConflict("That day is not done yet; there is nothing to review")
    note = _text(note, NOTE_LIMIT)
    patient = db.get(Patient, row.patient_id)
    reviewer = _reviewer(db, actor, patient.assigned_provider_id if patient else None)
    now = datetime.now()
    row.reviewed_at, row.reviewed_by = now, reviewer
    row.review_note = note or None
    row.updated_at = now
    message = None
    if note:
        exercise = db.get(Exercise, row.exercise_id)
        message = Message(
            patient_id=row.patient_id, sender="care_team", sender_id=reviewer, channel="app",
            text=review_line(exercise.title if exercise else "the exercise", note,
                             has_clip=row.video_attachment_id is not None),
            authored_by="care_team", read_by_care_team_at=now,
        )
        db.add(message)
    audit(db, row.hospital_id, actor, "assignment.review", "assignment", row.id,
          {"reviewed_by": reviewer, "note": bool(note)})
    db.commit()
    return row, message


# --- done against prescribed --------------------------------------------------------


def _against(done: Any, prescribed: Any) -> dict[str, Any]:
    """One part of a dose as it was done and as it was written. ``delta``
    is done minus prescribed, and nothing when either is unknown."""
    delta = None
    if done is not None and prescribed is not None:
        delta = round(done - prescribed, 2)
        delta = int(delta) if delta == int(delta) else delta
    return {"done": done, "prescribed": prescribed, "delta": delta}


def _counted(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def done_against_prescribed(row: ExerciseAssignment, unit: str = "kg") -> dict[str, Any]:
    """What a done day did against what was written, with no opinion on it.

    ``performed`` sets each of sets, reps, load and effort beside its dose
    (effort beside the target RPE). ``over`` is true when the lifter did
    more than was written: more sets, more reps, a heavier load, or an
    effort ``EFFORT_MARGIN`` or more above the target. ``under`` is the same
    the other way. A load reported where none was written counts as heavier;
    a part nobody reported is not compared. ``line`` says the differences in
    a sentence ("16 kg done, 10 kg prescribed"), "Done as prescribed" when
    what was reported matches, and nothing when nothing was reported.
    """
    sets = _against(row.sets_done, row.sets)
    reps = _against(row.reps_done, row.reps)
    load = _against(row.load_done_kg, row.load_kg)
    if row.load_done_kg is not None and row.load_kg is None:
        load["delta"] = _against(row.load_done_kg, 0)["delta"]
    effort = _against(row.effort, row.rpe_target)
    counted = [p["delta"] for p in (sets, reps, load) if p["delta"] is not None]
    felt = effort["delta"]
    parts: list[str] = []
    if sets["delta"]:
        parts.append(f"{_counted(row.sets_done, 'set')} done, {row.sets} prescribed")
    if reps["delta"]:
        parts.append(f"{_counted(row.reps_done, 'rep')} done, {row.reps} prescribed")
    if load["delta"]:
        written = (f"{load_text(row.load_kg, unit)} prescribed" if row.load_kg is not None
                   else "no load prescribed")
        parts.append(f"{load_text(row.load_done_kg, unit)} done, {written}")
    if felt:
        parts.append(f"effort {row.effort}, target {row.rpe_target}")
    # The ceilings are a different thing from the target: a lifter told to
    # stop at RPE 7 who reports an 8 went past it, whatever the target was.
    past: list[str] = []
    if row.load_max_kg is not None and row.load_done_kg is not None \
            and row.load_done_kg > row.load_max_kg:
        past.append(f"{load_text(row.load_done_kg, unit)} done, ceiling "
                    f"{load_text(row.load_max_kg, unit)}")
    if row.rpe_max is not None and row.effort is not None and row.effort > row.rpe_max:
        past.append(f"effort {row.effort}, told to stop at {row.rpe_max}")
    if past:
        parts.append("past the ceiling: " + ", ".join(past))
    if parts:
        line = " · ".join(parts)
    elif counted or felt is not None:
        line = "Done as prescribed"
    else:
        line = None
    return {
        "performed": {"sets": sets, "reps": reps, "load_kg": load, "effort": effort},
        "over": (any(d > 0 for d in counted) or (felt is not None and felt >= EFFORT_MARGIN)
                 or bool(past)),
        "under": any(d < 0 for d in counted) or (felt is not None and felt <= -EFFORT_MARGIN),
        "past_ceiling": bool(past),
        "line": line,
    }


def went_over(row: ExerciseAssignment) -> bool:
    """A done day on which the lifter did more than was written."""
    return row.status == "done" and done_against_prescribed(row)["over"]


# --- to review ----------------------------------------------------------------------


def review_reason(row: ExerciseAssignment) -> str | None:
    """Why a row waits for the therapist, or nothing when it does not. The
    one definition of "to review", used by the queue, its count, the grid's
    and the worklist's numbers and each row's own flag: a done day nobody
    has reviewed that carries a clip of the attempt (``clip``) or, without
    one, went over the dose (``over``)."""
    if row.status != "done" or row.reviewed_at is not None:
        return None
    if row.video_attachment_id is not None:
        return "clip"
    return "over" if went_over(row) else None


def to_review(
    db: Session, *, clinic: str | None = None, patient_ids: list[str] | None = None,
    days: int = REVIEW_DAYS, now: datetime | None = None,
) -> list[ExerciseAssignment]:
    """The rows waiting for the therapist (``review_reason``) among those
    finished in the last ``days``, newest first: a clinic's, or the given
    patients'. One query, however many rows."""
    if not 1 <= days <= MAX_REVIEW_DAYS:
        raise HepError(f"Look back between 1 and {MAX_REVIEW_DAYS} days")
    if patient_ids is not None and not patient_ids:
        return []
    q = select(ExerciseAssignment).where(
        ExerciseAssignment.status == "done",
        ExerciseAssignment.reviewed_at.is_(None),
        ExerciseAssignment.completed_at >= (now or datetime.now()) - timedelta(days=days),
    )
    if clinic is not None:
        q = q.where(ExerciseAssignment.hospital_id == clinic)
    if patient_ids is not None:
        q = q.where(ExerciseAssignment.patient_id.in_(patient_ids))
    rows = db.scalars(q.order_by(ExerciseAssignment.completed_at.desc(),
                                 ExerciseAssignment.id.desc())).all()
    return [r for r in rows if review_reason(r) is not None]


def review_queue(db: Session, clinic: str, *, days: int,
                 now: datetime | None = None) -> list[ExerciseAssignment]:
    """What is waiting for the therapist at this clinic, newest first."""
    return to_review(db, clinic=clinic, days=days, now=now)


# --- placing many days at once --------------------------------------------------------


@dataclass
class Placement:
    """One row to put on a patient's day, with the fields it carries; what
    a copied week, a repeat and an applied program are made of."""

    exercise: Exercise
    day: date
    assigned_by: str
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Skip:
    """A day a write of many days left out, and why (``SKIP_REASONS``)."""

    exercise: Exercise
    day: date
    reason: str


def placement_fields(row: ExerciseAssignment) -> dict[str, Any]:
    """The dose, note and requirements of a row, as a copy carries them."""
    return {
        "sets": row.sets, "reps": row.reps, "hold_seconds": row.hold_seconds, "side": row.side,
        "load_kg": row.load_kg, "rpe_target": row.rpe_target,
        "load_max_kg": row.load_max_kg, "rpe_max": row.rpe_max,
        "clinician_instructions": row.clinician_instructions or "",
        "video_requirement": row.video_requirement or "optional",
        "wearable_requirement": row.wearable_requirement or "optional",
    }


def place_rows(
    db: Session, clinic: str, patient: Patient, placements: list[Placement], *, actor: str,
    today: date, action: str, detail: dict[str, Any], series_id: str | None = None,
) -> tuple[list[ExerciseAssignment], list[Skip]]:
    """Write many days in one go, each after whatever its day already holds.
    A day that already carries the exercise is skipped, not refused: a copy
    or a program lands around what the therapist put there by hand. A day
    outside the schedule's reach is skipped too, so a twelve-week program
    started next month places what fits. Only a request with no day in
    reach at all is refused. Returns the rows written and what was left
    out, in the order asked."""
    reachable = sorted({p.day for p in placements if in_reach(p.day, today)})
    if placements and not reachable:
        raise HepError(f"None of those days is in reach: {reach_text()}")
    taken = set(db.execute(
        select(ExerciseAssignment.exercise_id, ExerciseAssignment.scheduled_for).where(
            ExerciseAssignment.patient_id == patient.id,
            ExerciseAssignment.scheduled_for.in_(reachable),
        )
    ).all())
    positions = _next_positions(db, patient.id, reachable)
    now = datetime.now()
    rows: list[ExerciseAssignment] = []
    skips: list[Skip] = []
    for p in placements:
        if not in_reach(p.day, today):
            skips.append(Skip(p.exercise, p.day, SKIP_OUT_OF_REACH))
            continue
        if (p.exercise.id, p.day) in taken:
            skips.append(Skip(p.exercise, p.day, SKIP_ALREADY_THERE))
            continue
        taken.add((p.exercise.id, p.day))
        order = positions.get(p.day, 0)
        positions[p.day] = order + 1
        row = ExerciseAssignment(
            hospital_id=clinic, patient_id=patient.id, exercise_id=p.exercise.id,
            scheduled_for=p.day, sort_order=order, assigned_by=p.assigned_by, status="assigned",
            series_id=series_id, created_at=now, updated_at=now, **p.fields,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    if rows:
        audit(db, clinic, actor, action, "assignment", rows[0].id, {
            **detail, "patient_id": patient.id, "ids": [r.id for r in rows],
            "skipped": len(skips),
        })
    db.commit()
    return rows, skips


def skipped_payload(skips: list[Skip]) -> dict[str, Any]:
    """What a write of many days left out, as its response says it: how
    many, how many for each reason, and each day with a sentence."""
    def sentence(skip: Skip) -> str:
        if skip.reason == SKIP_OUT_OF_REACH:
            return f"{skip.day.isoformat()} is out of reach: {reach_text()}"
        return _taken_text(skip.exercise, [skip.day])

    return {
        "skipped": len(skips),
        "skipped_reasons": {reason: sum(s.reason == reason for s in skips)
                            for reason in SKIP_REASONS},
        "skipped_days": [
            {"date": s.day.isoformat(), "exercise_id": s.exercise.id, "title": s.exercise.title,
             "reason": s.reason, "detail": sentence(s)}
            for s in skips
        ],
    }


def copy_week(
    db: Session, clinic: str, *, patient_id: str, from_start: date, to_start: date,
    assigned_by: str | None, actor: str, today: date,
) -> tuple[list[ExerciseAssignment], list[Skip]]:
    """Every assignment of the seven days from ``from_start`` on the same
    weekday from ``to_start``, dose, note and requirements with it; a day
    that already has the exercise, or lies out of reach, is skipped. The
    rows are assigned by the member named, else by whoever assigned the day
    being copied."""
    patient = _patient_for(db, clinic, patient_id)
    if from_start == to_start:
        raise HepError("Pick a different week to copy to")
    source = [r for r in patient_rows(db, patient.id, from_start, from_start + timedelta(days=WEEK))
              if r.hospital_id == clinic]
    if not source:
        raise HepError(f"Nothing to copy: the week of {from_start.isoformat()} is empty")
    member = _member(db, assigned_by, None) if (assigned_by or "").strip() else None
    exercises = {e.id: e for e in db.scalars(select(Exercise).where(
        Exercise.id.in_({r.exercise_id for r in source})))}
    placements = [
        Placement(exercise=exercises[r.exercise_id],
                  day=to_start + (r.scheduled_for - from_start),
                  assigned_by=member or r.assigned_by, fields=placement_fields(r))
        for r in source if r.exercise_id in exercises
    ]
    return place_rows(db, clinic, patient, placements, actor=actor, today=today,
                      action="assignment.copy_week",
                      detail={"from_start": from_start.isoformat(), "to_start": to_start.isoformat()})


# --- payloads -----------------------------------------------------------------------


class AssignmentView:
    """Renders assignment payloads for one request, sharing the lookups the
    rows have in common — exercises, the clinic's clips and unit, members,
    the patients' return clips — so a week of a clinic's grid costs a
    handful of queries rather than one per chip. ``today`` is the day each
    row's ``state`` is read on (the server's unless the request said).
    ``patient_app`` drops the clinic id and points media at the route the
    patient's session can reach."""

    def __init__(self, db: Session, *, patient_app: bool = False, today: date | None = None):
        self.db = db
        self.patient_app = patient_app
        self.today = today or date.today()
        self.route = PATIENT_MEDIA_ROUTE if patient_app else CONSOLE_MEDIA_ROUTE
        self._exercises: dict[int, Exercise | None] = {}
        self._clips: dict[str, dict[int, ExerciseMedia]] = {}
        self._members: dict[str, CareTeamMember | None] = {}
        self._attachments: dict[int, Attachment | None] = {}
        self._units: dict[str, str] = {}

    def exercise(self, exercise_id: int) -> Exercise | None:
        if exercise_id not in self._exercises:
            self._exercises[exercise_id] = self.db.get(Exercise, exercise_id)
        return self._exercises[exercise_id]

    def _clip(self, clinic: str, exercise: Exercise) -> ExerciseMedia | None:
        if clinic not in self._clips:
            self._clips[clinic] = clinic_clips(self.db, clinic)
        return resolve_clip(self.db, clinic, exercise, self._clips[clinic])

    def unit(self, clinic: str) -> str:
        """The unit this clinic reads loads in, for the strings built here."""
        if clinic not in self._units:
            self._units[clinic] = load_unit_of(self.db.get(Hospital, clinic))
        return self._units[clinic]

    def member_name(self, member_id: str | None) -> str | None:
        if not member_id:
            return None
        if member_id not in self._members:
            self._members[member_id] = self.db.get(CareTeamMember, member_id)
        member = self._members[member_id]
        return member.name if member else None

    def _attachment(self, attachment_id: int) -> Attachment | None:
        if attachment_id not in self._attachments:
            self._attachments[attachment_id] = self.db.get(Attachment, attachment_id)
        return self._attachments[attachment_id]

    def video(self, clip: ExerciseMedia | None) -> dict[str, Any] | None:
        if clip is None:
            return None
        return media_payload(clip, route=self.route,
                             uploaded_by_name=self.member_name(clip.uploaded_by))

    def dose(self, row: ExerciseAssignment) -> str:
        return dose_text(row.sets, row.reps, row.hold_seconds, row.side, load_kg=row.load_kg,
                         load_unit=self.unit(row.hospital_id))

    def ceiling(self, row: ExerciseAssignment) -> str:
        parts = []
        if row.rpe_max is not None:
            parts.append(f"stop at RPE {row.rpe_max}")
        if row.load_max_kg is not None:
            parts.append(f"do not exceed {load_text(row.load_max_kg, self.unit(row.hospital_id))}")
        text = " · ".join(parts)
        return text[:1].upper() + text[1:] if text else ""

    @staticmethod
    def session(row: ExerciseAssignment) -> dict[str, Any] | None:
        """What the phone recorded around the attempt; nothing until the
        patient has started it (or the completion said something about it)."""
        if all(v is None for v in (row.started_at, row.ended_at, row.pain_before,
                                   row.wearable_worn, row.hr_avg, row.hr_max)):
            return None
        return {
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "ended_at": row.ended_at.isoformat() if row.ended_at else None,
            "duration_s": row.duration_s,
            "pain_before": row.pain_before,
            "wearable_worn": row.wearable_worn,
            "hr_avg": row.hr_avg,
            "hr_max": row.hr_max,
        }

    def review(self, row: ExerciseAssignment) -> dict[str, Any] | None:
        if row.reviewed_at is None:
            return None
        return {
            "at": row.reviewed_at.isoformat(),
            "by": row.reviewed_by,
            "by_name": self.member_name(row.reviewed_by),
            "note": row.review_note or "",
        }

    def completion(self, row: ExerciseAssignment) -> dict[str, Any] | None:
        if row.status != "done":
            return None
        from app.api.attachments import attachment_view

        attachment = self._attachment(row.video_attachment_id) if row.video_attachment_id else None
        reason = review_reason(row)
        return {
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            "pain_after": row.pain_after,
            "note": row.note or "",
            "source": row.completion_source,
            "video": attachment_view(attachment, with_url=True) if attachment else None,
            "effort": row.effort,
            "sets_done": row.sets_done,
            "reps_done": row.reps_done,
            "load_done_kg": row.load_done_kg,
            "review": self.review(row),
            # Waiting for the therapist's look, and why: a clip nobody has
            # looked at yet, or a day that went over the dose.
            "awaiting_review": reason is not None,
            "review_reason": reason,
            **done_against_prescribed(row, self.unit(row.hospital_id)),
        }

    def render(self, row: ExerciseAssignment) -> dict[str, Any]:
        e = self.exercise(row.exercise_id)
        clip = self._clip(row.hospital_id, e) if e else None
        payload = {
            "id": row.id,
            "clinic_id": row.hospital_id,
            "patient_id": row.patient_id,
            "exercise_id": row.exercise_id,
            "exercise_key": e.key if e else None,
            "title": e.title if e else "",
            "body_region": e.body_region if e else None,
            "body_region_label": REGION_LABELS.get(e.body_region, e.body_region) if e else None,
            "category": e.category if e else None,
            "category_label": CATEGORY_LABELS.get(e.category, e.category) if e else None,
            "steps": [s for s in (e.instructions or "").splitlines() if s.strip()] if e else [],
            "equipment": (e.equipment or "") if e else "",
            "precautions": (e.precautions or "") if e else "",
            "scheduled_for": row.scheduled_for.isoformat(),
            "sort_order": row.sort_order,
            "series_id": row.series_id,
            "sets": row.sets, "reps": row.reps, "hold_seconds": row.hold_seconds,
            "side": row.side, "side_label": SIDE_LABELS.get(row.side, ""),
            "load_kg": row.load_kg, "rpe_target": row.rpe_target,
            "load_max_kg": row.load_max_kg, "rpe_max": row.rpe_max,
            "dose": self.dose(row),
            # "Stop at RPE 7 · do not exceed 65 lb", or "" with no ceiling.
            "ceiling": self.ceiling(row),
            "clinician_instructions": row.clinician_instructions or "",
            "assigned_by": row.assigned_by,
            "assigned_by_name": self.member_name(row.assigned_by),
            "video_requirement": row.video_requirement or "optional",
            "wearable_requirement": row.wearable_requirement or "optional",
            "status": row.status,
            "state": state_of(row, self.today),
            "video": self.video(clip),
            "session": self.session(row),
            "completion": self.completion(row),
            "skip_reason": row.skip_reason,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        if self.patient_app:
            payload.pop("clinic_id")
        return payload

    def render_all(self, rows: list[ExerciseAssignment]) -> list[dict[str, Any]]:
        return [self.render(r) for r in rows]

    def compact(self, row: ExerciseAssignment) -> dict[str, Any]:
        """A row as a month view draws it: what it is, where it stands and
        how it went, with no steps, no clip URLs and nothing to presign."""
        e = self.exercise(row.exercise_id)
        reason = review_reason(row)
        compared = (done_against_prescribed(row, self.unit(row.hospital_id))
                    if row.status == "done" else None)
        return {
            "id": row.id,
            "patient_id": row.patient_id,
            "exercise_id": row.exercise_id,
            "title": e.title if e else "",
            "scheduled_for": row.scheduled_for.isoformat(),
            "sort_order": row.sort_order,
            "series_id": row.series_id,
            "status": row.status,
            "state": state_of(row, self.today),
            "dose": self.dose(row),
            "load_kg": row.load_kg,
            "rpe_target": row.rpe_target,
            "ceiling": self.ceiling(row),
            "video_requirement": row.video_requirement or "optional",
            "pain_after": row.pain_after,
            "effort": row.effort,
            "over": bool(compared and compared["over"]),
            "under": bool(compared and compared["under"]),
            "line": compared["line"] if compared else None,
            "awaiting_review": reason is not None,
            "review_reason": reason,
            # The lifter's own clip of the attempt, not her demonstration.
            "has_clip": row.video_attachment_id is not None,
            "reviewed": row.reviewed_at is not None,
        }


def pathway_of(patient: Patient) -> str:
    """The clinic's words for what the patient is here for: ``care_pathway``
    when it reads as one ("Patellar tendinopathy · progressive loading"),
    else the procedure line. A pathway code the engine keys on
    ("ortho_tka") is not something to print."""
    pathway = (patient.care_pathway or "").strip()
    if pathway and " " in pathway:
        return pathway
    return patient.procedure_display or pathway


# --- the week's numbers ------------------------------------------------------------------


def tonnage(row: ExerciseAssignment) -> float:
    """What a done day moved, in kilograms: load × reps × sets, each as it
    was done when the patient said, else as it was prescribed. Bodyweight
    work and holds count nothing here."""
    load = row.load_done_kg if row.load_done_kg is not None else row.load_kg
    reps = row.reps_done if row.reps_done is not None else row.reps
    sets = row.sets_done if row.sets_done is not None else row.sets
    if not load or not reps:
        return 0.0
    return float(load) * int(reps) * int(sets or 1)


def planned_tonnage(row: ExerciseAssignment) -> float:
    """What a day was written to move, in kilograms: the prescribed load ×
    reps × sets, whatever came of the day."""
    if not row.load_kg or not row.reps:
        return 0.0
    return float(row.load_kg) * int(row.reps) * int(row.sets or 1)


def done_load(rows: list[ExerciseAssignment]) -> float:
    return round(sum(tonnage(r) for r in rows if r.status == "done"), 1)


def planned_load(rows: list[ExerciseAssignment]) -> float:
    return round(sum(planned_tonnage(r) for r in rows), 1)


def _pct(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


def change_pct(now: float, before: float) -> int | None:
    """How far ``now`` is from ``before``, as a whole percentage of
    ``before``; nothing when there is no ``before`` to stand on."""
    return round(100 * (now - before) / before) if before else None


class WeekStats:
    """The numbers under a patient's name on the grid and the worklist: how
    the seven days ending today went, what they lifted against the week
    before, what is written for this calendar week and the next, and how
    many done days wait for a look. Two queries for a whole clinic, however
    many rows it has."""

    def __init__(self, db: Session, patient_ids: list[str], today: date):
        self.today = today
        self.monday = week_start(today)
        self.rows: dict[str, list[ExerciseAssignment]] = {pid: [] for pid in patient_ids}
        self.waiting: dict[str, int] = {}
        if not patient_ids:
            return
        # From the start of the seven days before the seven ending today
        # (never later than last week's Monday) through next week's Sunday.
        for row in db.scalars(select(ExerciseAssignment).where(
                ExerciseAssignment.patient_id.in_(patient_ids),
                ExerciseAssignment.scheduled_for >= today - timedelta(days=2 * WEEK - 1),
                ExerciseAssignment.scheduled_for < self.monday + timedelta(days=2 * WEEK))):
            self.rows.setdefault(row.patient_id, []).append(row)
        for row in to_review(db, patient_ids=patient_ids):
            self.waiting[row.patient_id] = self.waiting.get(row.patient_id, 0) + 1

    def _week(self, patient_id: str, weeks_back: int) -> list[ExerciseAssignment]:
        end = self.today - timedelta(days=WEEK * weeks_back)
        start = end - timedelta(days=WEEK - 1)
        return [r for r in self.rows.get(patient_id, []) if start <= r.scheduled_for <= end]

    def _calendar_week(self, patient_id: str, offset: int) -> list[ExerciseAssignment]:
        """The rows of a Monday-to-Sunday week: this one (0), the one before
        (−1) or the one after (1)."""
        start = self.monday + timedelta(days=WEEK * offset)
        end = start + timedelta(days=WEEK)
        return [r for r in self.rows.get(patient_id, []) if start <= r.scheduled_for < end]

    def adherence(self, patient_id: str) -> dict[str, Any]:
        week = self._week(patient_id, 0)
        done = sum(r.status == "done" for r in week)
        return {
            "assigned": len(week),
            "done": done,
            "skipped": sum(r.status == "skipped" for r in week),
            "missed": sum(r.status == "assigned" and r.scheduled_for < self.today for r in week),
            "pct": _pct(done, len(week)),
        }

    def over_week(self, patient_id: str) -> int:
        """How many of the seven days' done rows went over the dose."""
        return sum(went_over(r) for r in self._week(patient_id, 0))

    def load_week(self, patient_id: str) -> dict[str, Any]:
        """Tonnage in the lifter's own terms. ``this``/``last`` are the seven
        days ending today and the seven before, as done. The rest is by
        calendar week: what was done this week and last, what is written
        (every row at its prescribed dose, whatever came of it) for last
        week, this week and next, and plain changes between them. No ratio
        and no line drawn: the therapist reads the numbers."""
        this = done_load(self._week(patient_id, 0))
        last = done_load(self._week(patient_id, 1))
        before, current, coming = (self._calendar_week(patient_id, n) for n in (-1, 0, 1))
        done_this, done_last = done_load(current), done_load(before)
        planned_this, planned_next = planned_load(current), planned_load(coming)
        return {
            "this": this, "last": last, "change_pct": change_pct(this, last),
            "week_start": self.monday.isoformat(),
            "done_this_week": done_this,
            "done_last_week": done_last,
            "done_change_pct": change_pct(done_this, done_last),
            "planned_last_week": planned_load(before),
            "planned_this_week": planned_this,
            "planned_next_week": planned_next,
            # Next week as written against this week as written.
            "planned_change_pct": change_pct(planned_next, planned_this),
            # This week as written against what was actually done last week.
            "planned_vs_last_done_pct": change_pct(planned_this, done_last),
        }

    def awaiting_review(self, patient_id: str) -> int:
        return int(self.waiting.get(patient_id, 0))

    def worklist(self, patient_id: str) -> dict[str, Any] | None:
        """The worklist card's line, or nothing for a chart with no exercise
        on the seven days ending today and nothing waiting for a look."""
        week = self._week(patient_id, 0)
        waiting = self.awaiting_review(patient_id)
        if not week and not waiting:
            return None
        done = sum(r.status == "done" for r in week)
        return {
            "assigned": len(week), "done": done, "pct": _pct(done, len(week)),
            "awaiting_review": waiting,
            "over": sum(went_over(r) for r in week),
            "missed": sum(r.status == "assigned" and r.scheduled_for < self.today for r in week),
        }


def week_summaries(db: Session, patient_ids: list[str], today: date) -> dict[str, dict | None]:
    """The worklist's ``exercises`` field for every chart in one go."""
    stats = WeekStats(db, patient_ids, today)
    return {pid: stats.worklist(pid) for pid in patient_ids}


def patient_card(db: Session, patient: Patient, view: AssignmentView,
                 stats: WeekStats | None = None) -> dict[str, Any]:
    from app.engine.pipeline import latest_assessment

    assessment = latest_assessment(db, patient.id)
    stats = stats or WeekStats(db, [patient.id], date.today())
    return {
        "id": patient.id, "name": patient.name, "initials": patient.initials,
        "pathway": pathway_of(patient),
        "assigned_provider_id": patient.assigned_provider_id,
        "assigned_provider_name": view.member_name(patient.assigned_provider_id),
        "risk_tier": str(assessment.risk_level).lower() if assessment else None,
        "adherence": stats.adherence(patient.id),
        "load_week": stats.load_week(patient.id),
        "awaiting_review": stats.awaiting_review(patient.id),
        "over_week": stats.over_week(patient.id),
    }


def to_review_payload(count: int) -> dict[str, Any]:
    return {"count": count, "days": REVIEW_DAYS}


def schedule_payload(db: Session, clinic: str, *, start: date | None, days: int, today: date,
                     patient_id: str | None = None) -> dict[str, Any]:
    """The grid: every clinic chart as a row, the assignments in the window
    under each, and the therapists to pick from."""
    days = check_window(days)
    start = start or week_start(today)
    patients = schedule_patients(db, clinic)
    if patient_id is not None:
        patients = [p for p in patients if p.id == patient_id]
        if not patients:
            raise UnknownRow(f"Unknown patient: {patient_id}")
    end = start + timedelta(days=days)
    rows = clinic_rows(db, clinic, start, end,
                       [p.id for p in patients] if patient_id is not None else None)
    view = AssignmentView(db, today=today)
    stats = WeekStats(db, [p.id for p in patients], today)
    by_patient: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_patient.setdefault(row.patient_id, []).append(view.render(row))
    return {
        "start": start.isoformat(),
        "days": [d.isoformat() for d in days_of(start, days)],
        "today": today.isoformat(),
        "clinic": clinic_payload(db, clinic),
        "patients": [
            {**patient_card(db, p, view, stats), "assignments": by_patient.get(p.id, [])}
            for p in patients
        ],
        "care_team": clinic_care_team(db, clinic),
        # The same count the review queue lists, for the charts in view.
        "to_review": to_review_payload(sum(stats.awaiting_review(p.id) for p in patients)),
    }


def patient_schedule_payload(db: Session, clinic: str, patient: Patient, *, start: date | None,
                             days: int, today: date) -> dict[str, Any]:
    """One chart's strip for the patient page."""
    days = check_window(days)
    start = start or week_start(today)
    rows = [r for r in patient_rows(db, patient.id, start, start + timedelta(days=days))
            if r.hospital_id == clinic]
    view = AssignmentView(db, today=today)
    return {
        "patient": patient_card(db, patient, view, WeekStats(db, [patient.id], today)),
        "start": start.isoformat(),
        "days": [d.isoformat() for d in days_of(start, days)],
        "today": today.isoformat(),
        "clinic": clinic_payload(db, clinic),
        "assignments": view.render_all(rows),
    }


def review_queue_payload(db: Session, clinic: str, *, days: int) -> dict[str, Any]:
    """What waits for a look, newest first, each row saying whose it is and
    why it is here (``reason``: a clip, or over the dose)."""
    rows = review_queue(db, clinic, days=days)
    names = dict(db.execute(select(Patient.id, Patient.name).where(
        Patient.id.in_({r.patient_id for r in rows}))).all()) if rows else {}
    view = AssignmentView(db)
    return {
        "items": [{**view.render(r), "patient_name": names.get(r.patient_id),
                   "reason": review_reason(r)} for r in rows],
        "count": len(rows),
        "days": days,
    }


def review_count_payload(db: Session, clinic: str, *, days: int) -> dict[str, Any]:
    """How many rows wait for a look, and for which reason: the number
    beside Review in the navigation. One query."""
    reasons = [review_reason(r) for r in review_queue(db, clinic, days=days)]
    return {
        "count": len(reasons),
        "days": days,
        "by_reason": {reason: reasons.count(reason) for reason in REVIEW_REASONS},
    }


def _clinic_of(db: Session, patient: Patient) -> dict[str, Any] | None:
    return clinic_payload(db, patient.hospital_id)


def assignment_payload(db: Session, patient: Patient, row: ExerciseAssignment,
                       today: date) -> dict[str, Any]:
    """One of the patient's own days by id, however old: what a texted
    link opens."""
    return {
        "assignment": AssignmentView(db, patient_app=True, today=today).render(row),
        "today": today.isoformat(),
        "clinic": _clinic_of(db, patient),
    }


def today_payload(db: Session, patient: Patient, day: date,
                  today: date | None = None) -> dict[str, Any]:
    """What the patient's Today shows: the day's exercises in order, a
    seven-day strip around it (how many were on each day, how many done),
    and whose schedule it is. ``day`` is the day asked for; ``today`` (the
    server's unless given) is the day each row's state is read on."""
    today = today or date.today()
    week_days = days_of(day - timedelta(days=3), 7)
    # A week back, not three days: the strip is three each side, but an
    # exercise put on an earlier day and never done still has to reach the
    # phone, as "still to do from earlier this week".
    rows = patient_rows(db, patient.id, day - timedelta(days=7), week_days[-1] + timedelta(days=1))
    view = AssignmentView(db, patient_app=True, today=today)
    week = []
    for d in week_days:
        on_day = [r for r in rows if r.scheduled_for == d]
        week.append({
            "date": d.isoformat(),
            "assigned": len(on_day),
            "done": sum(r.status == "done" for r in on_day),
            "skipped": sum(r.status == "skipped" for r in on_day),
        })
    return {
        "date": day.isoformat(),
        "today": today.isoformat(),
        "items": view.render_all([r for r in rows if r.scheduled_for == day]),
        "overdue": view.render_all([r for r in rows
                                    if r.scheduled_for < day and r.status == "assigned"]),
        "week": week,
        "clinic": _clinic_of(db, patient),
    }


def program_payload(db: Session, patient: Patient, *, start: date | None, days: int,
                    today: date) -> dict[str, Any]:
    """The patient's calendar: each day of the window with its exercises
    and how it went. A past day's open row is ``missed``; today's is still
    to do. Opens a week back by default."""
    if not 1 <= days <= MAX_PROGRAM_DAYS:
        raise HepError(f"Show between 1 and {MAX_PROGRAM_DAYS} days")
    start = start or today - timedelta(days=WEEK)
    rows = patient_rows(db, patient.id, start, start + timedelta(days=days))
    view = AssignmentView(db, patient_app=True, today=today)
    out = []
    for d in days_of(start, days):
        on_day = [r for r in rows if r.scheduled_for == d]
        out.append({
            "date": d.isoformat(),
            "items": view.render_all(on_day),
            "assigned": len(on_day),
            "done": sum(r.status == "done" for r in on_day),
            "skipped": sum(r.status == "skipped" for r in on_day),
            "missed": sum(r.status == "assigned" for r in on_day) if d < today else 0,
        })
    return {
        "start": start.isoformat(),
        "today": today.isoformat(),
        "days": out,
        "clinic": _clinic_of(db, patient),
    }
