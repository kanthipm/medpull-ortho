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

The console and the patient app read the same ``Assignment`` payload
(``AssignmentView``); the patient's copy drops the clinic id and points its
media URLs at the route the patient's session can reach.
"""

from __future__ import annotations

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
    clinic_clips,
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
# One POST puts one exercise on at most a month of days.
MAX_DATES = 31
# The widest grid a read may ask for.
MAX_WINDOW_DAYS = 28
# The widest calendar the patient's program may ask for.
MAX_PROGRAM_DAYS = 35
WEEK = 7
TEXT_LIMIT = 400
NOTE_LIMIT = 600
# The heaviest load a day may carry, in kilograms; RPE and pain run 0–10.
LOAD_MAX = 500.0
SCALE_MAX = 10
# How far back the review queue looks by default, and at most.
REVIEW_DAYS = 14
MAX_REVIEW_DAYS = 90
COMPLETION_SOURCES = ("app", "console")
# What a done day keeps: its counts, side, load and target effort.
DOSE_FIELDS = ("sets", "reps", "hold_seconds", "side", "load_kg", "rpe_target")
REQUIREMENT_FIELDS = ("video_requirement", "wearable_requirement")
EDITABLE = DOSE_FIELDS + REQUIREMENT_FIELDS + (
    "clinician_instructions", "scheduled_for", "assigned_by", "sort_order",
)
# Therapists who belong in a clinic's "assigned by" list before they carry a
# patient of their own: the demo clinic's two.
HOUSE_CARE_TEAM: dict[str, tuple[str, ...]] = {"hirt": ("ct_harris", "ct_gregg")}


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


def _in_reach(day: date, today: date) -> None:
    if not today - timedelta(days=PAST_DAYS) <= day <= today + timedelta(days=FUTURE_DAYS):
        raise HepError(
            f"{day.isoformat()} is out of reach: the schedule runs {PAST_DAYS} days back "
            f"and {FUTURE_DAYS} days ahead of today"
        )


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


# --- writes -----------------------------------------------------------------------


def create_assignments(
    db: Session, clinic: str, *, patient_id: str, exercise_id: int, dates: list[date],
    sets: Any, reps: Any, hold_seconds: Any, side: str | None, clinician_instructions: str,
    assigned_by: str | None, actor: str, today: date,
    load_kg: Any = None, rpe_target: Any = None, video_requirement: str | None = None,
    wearable_requirement: str | None = None,
) -> list[ExerciseAssignment]:
    """Put one exercise, at one dose, on each of ``dates`` for a patient.
    All or nothing: a day that already has the exercise refuses the whole
    request, naming the day, so a half-written week never has to be undone
    by hand."""
    try:
        patient = clinic_patient(db, clinic, patient_id)
    except HepError as e:
        raise UnknownRow(str(e))
    exercise = _exercise_for(db, clinic, exercise_id)
    days = sorted(set(dates))
    if not days:
        raise HepError("Pick at least one day")
    if len(days) > MAX_DATES:
        raise HepError(f"One assignment covers at most {MAX_DATES} days")
    for day in days:
        _in_reach(day, today)
    side = _side(side)
    sets, reps = _count(sets, "Sets"), _count(reps, "Reps")
    hold = _count(hold_seconds, "Hold")
    load, rpe = _load(load_kg), _scale(rpe_target, "Target effort")
    video = _requirement(video_requirement, "The clip requirement")
    wearable = _requirement(wearable_requirement, "The wearable requirement")
    note = _text(clinician_instructions)
    member = _member(db, assigned_by, patient.assigned_provider_id)
    taken = _taken(db, patient.id, exercise.id, days)
    if taken:
        raise ScheduleConflict(
            f"{exercise.title} is already on {', '.join(d.isoformat() for d in taken)}"
        )
    positions = _next_positions(db, patient.id, days)
    now = datetime.now()
    rows = []
    for day in days:
        row = ExerciseAssignment(
            hospital_id=clinic, patient_id=patient.id, exercise_id=exercise.id,
            scheduled_for=day, sort_order=positions.get(day, 0), sets=sets, reps=reps,
            hold_seconds=hold, side=side, load_kg=load, rpe_target=rpe,
            clinician_instructions=note, assigned_by=member, video_requirement=video,
            wearable_requirement=wearable, status="assigned", created_at=now, updated_at=now,
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
    if "scheduled_for" in touched:
        day = patch["scheduled_for"]
        if day is None:
            raise HepError("Choose a day")
        _in_reach(day, today)
        if day != row.scheduled_for:
            if _taken(db, row.patient_id, row.exercise_id, [day], exclude_id=row.id):
                exercise = db.get(Exercise, row.exercise_id)
                raise ScheduleConflict(
                    f"{exercise.title if exercise else 'That exercise'} is already on "
                    f"{day.isoformat()}"
                )
            row.scheduled_for = day
            row.sort_order = _next_positions(db, row.patient_id, [day]).get(day, 0)
    if "sets" in touched:
        row.sets = _count(patch["sets"], "Sets")
    if "reps" in touched:
        row.reps = _count(patch["reps"], "Reps")
    if "hold_seconds" in touched:
        row.hold_seconds = _count(patch["hold_seconds"], "Hold")
    if "side" in touched:
        row.side = _side(patch["side"])
    if "load_kg" in touched:
        row.load_kg = _load(patch["load_kg"])
    if "rpe_target" in touched:
        row.rpe_target = _scale(patch["rpe_target"], "Target effort")
    if "video_requirement" in touched:
        row.video_requirement = _requirement(patch["video_requirement"], "The clip requirement")
    if "wearable_requirement" in touched:
        row.wearable_requirement = _requirement(patch["wearable_requirement"],
                                                "The wearable requirement")
    if "clinician_instructions" in touched:
        row.clinician_instructions = _text(patch["clinician_instructions"])
    if "assigned_by" in touched:
        row.assigned_by = _member(db, patch["assigned_by"], row.assigned_by)
    if "sort_order" in touched:
        order = patch["sort_order"]
        if order is None or int(order) < 0:
            raise HepError("Position must be zero or more")
        row.sort_order = int(order)
    row.updated_at = datetime.now()
    audit(db, clinic, actor, "assignment.update", "assignment", row.id,
          {"fields": sorted(touched)})
    db.commit()
    return row


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


def review_queue(db: Session, clinic: str, *, days: int,
                 now: datetime | None = None) -> list[ExerciseAssignment]:
    """What is waiting for the therapist: the clinic's done days with a
    clip and no review, finished in the last ``days``, newest first."""
    if not 1 <= days <= MAX_REVIEW_DAYS:
        raise HepError(f"Look back between 1 and {MAX_REVIEW_DAYS} days")
    since = (now or datetime.now()) - timedelta(days=days)
    return db.scalars(
        select(ExerciseAssignment).where(
            ExerciseAssignment.hospital_id == clinic,
            ExerciseAssignment.status == "done",
            ExerciseAssignment.video_attachment_id.is_not(None),
            ExerciseAssignment.reviewed_at.is_(None),
            ExerciseAssignment.completed_at >= since,
        ).order_by(ExerciseAssignment.completed_at.desc(), ExerciseAssignment.id.desc())
    ).all()


# --- placing many days at once --------------------------------------------------------


@dataclass
class Placement:
    """One row to put on a patient's day, with the fields it carries; what
    a copied week and an applied program are made of."""

    exercise: Exercise
    day: date
    assigned_by: str
    fields: dict[str, Any] = field(default_factory=dict)


def placement_fields(row: ExerciseAssignment) -> dict[str, Any]:
    """The dose, note and requirements of a row, as a copy carries them."""
    return {
        "sets": row.sets, "reps": row.reps, "hold_seconds": row.hold_seconds, "side": row.side,
        "load_kg": row.load_kg, "rpe_target": row.rpe_target,
        "clinician_instructions": row.clinician_instructions or "",
        "video_requirement": row.video_requirement or "optional",
        "wearable_requirement": row.wearable_requirement or "optional",
    }


def place_rows(
    db: Session, clinic: str, patient: Patient, placements: list[Placement], *, actor: str,
    today: date, action: str, detail: dict[str, Any],
) -> tuple[list[ExerciseAssignment], int]:
    """Write many days in one go, each after whatever its day already holds.
    A day that already carries the exercise is skipped, not refused: a copy
    or a program lands around what the therapist put there by hand. Returns
    the rows written and how many were skipped."""
    days = sorted({p.day for p in placements})
    for day in days:
        _in_reach(day, today)
    taken = set(db.execute(
        select(ExerciseAssignment.exercise_id, ExerciseAssignment.scheduled_for).where(
            ExerciseAssignment.patient_id == patient.id,
            ExerciseAssignment.scheduled_for.in_(days),
        )
    ).all())
    positions = _next_positions(db, patient.id, days)
    now = datetime.now()
    rows: list[ExerciseAssignment] = []
    skipped = 0
    for p in placements:
        if (p.exercise.id, p.day) in taken:
            skipped += 1
            continue
        taken.add((p.exercise.id, p.day))
        order = positions.get(p.day, 0)
        positions[p.day] = order + 1
        row = ExerciseAssignment(
            hospital_id=clinic, patient_id=patient.id, exercise_id=p.exercise.id,
            scheduled_for=p.day, sort_order=order, assigned_by=p.assigned_by, status="assigned",
            created_at=now, updated_at=now, **p.fields,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    if rows:
        audit(db, clinic, actor, action, "assignment", rows[0].id, {
            **detail, "patient_id": patient.id, "ids": [r.id for r in rows], "skipped": skipped,
        })
    db.commit()
    return rows, skipped


def copy_week(
    db: Session, clinic: str, *, patient_id: str, from_start: date, to_start: date,
    assigned_by: str | None, actor: str, today: date,
) -> tuple[list[ExerciseAssignment], int]:
    """Every assignment of the seven days from ``from_start`` on the same
    weekday from ``to_start``, dose, note and requirements with it; a day
    that already has the exercise is skipped. The rows are assigned by the
    member named, else by whoever assigned the day being copied."""
    try:
        patient = clinic_patient(db, clinic, patient_id)
    except HepError as e:
        raise UnknownRow(str(e))
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
    rows have in common — exercises, the clinic's clips, members, the
    patients' return clips — so a week of a clinic's grid costs a handful of
    queries rather than one per chip. ``patient_app`` drops the clinic id
    and points media at the route the patient's session can reach."""

    def __init__(self, db: Session, *, patient_app: bool = False):
        self.db = db
        self.patient_app = patient_app
        self.route = PATIENT_MEDIA_ROUTE if patient_app else CONSOLE_MEDIA_ROUTE
        self._exercises: dict[int, Exercise | None] = {}
        self._clips: dict[str, dict[int, ExerciseMedia]] = {}
        self._members: dict[str, CareTeamMember | None] = {}
        self._attachments: dict[int, Attachment | None] = {}

    def _exercise(self, exercise_id: int) -> Exercise | None:
        if exercise_id not in self._exercises:
            self._exercises[exercise_id] = self.db.get(Exercise, exercise_id)
        return self._exercises[exercise_id]

    def _clip(self, clinic: str, exercise: Exercise) -> ExerciseMedia | None:
        if clinic not in self._clips:
            self._clips[clinic] = clinic_clips(self.db, clinic)
        return resolve_clip(self.db, clinic, exercise, self._clips[clinic])

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
            # A clip nobody has looked at yet: what the review queue lists.
            "awaiting_review": attachment is not None and row.reviewed_at is None,
        }

    def render(self, row: ExerciseAssignment) -> dict[str, Any]:
        e = self._exercise(row.exercise_id)
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
            "sets": row.sets, "reps": row.reps, "hold_seconds": row.hold_seconds,
            "side": row.side, "side_label": SIDE_LABELS.get(row.side, ""),
            "load_kg": row.load_kg, "rpe_target": row.rpe_target,
            "dose": dose_text(row.sets, row.reps, row.hold_seconds, row.side, load_kg=row.load_kg),
            "clinician_instructions": row.clinician_instructions or "",
            "assigned_by": row.assigned_by,
            "assigned_by_name": self.member_name(row.assigned_by),
            "video_requirement": row.video_requirement or "optional",
            "wearable_requirement": row.wearable_requirement or "optional",
            "status": row.status,
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


def _pct(part: int, whole: int) -> int | None:
    return round(100 * part / whole) if whole else None


class WeekStats:
    """The numbers under a patient's name on the grid and the worklist: how
    the seven days ending today went, what they lifted against the week
    before, and how many clips wait for a look. Two queries for a whole
    clinic, however many rows it has."""

    def __init__(self, db: Session, patient_ids: list[str], today: date):
        self.today = today
        self.rows: dict[str, list[ExerciseAssignment]] = {pid: [] for pid in patient_ids}
        self.waiting: dict[str, int] = {}
        if not patient_ids:
            return
        for row in db.scalars(select(ExerciseAssignment).where(
                ExerciseAssignment.patient_id.in_(patient_ids),
                ExerciseAssignment.scheduled_for >= today - timedelta(days=2 * WEEK - 1),
                ExerciseAssignment.scheduled_for <= today)):
            self.rows.setdefault(row.patient_id, []).append(row)
        self.waiting = dict(db.execute(
            select(ExerciseAssignment.patient_id, func.count(ExerciseAssignment.id)).where(
                ExerciseAssignment.patient_id.in_(patient_ids),
                ExerciseAssignment.status == "done",
                ExerciseAssignment.video_attachment_id.is_not(None),
                ExerciseAssignment.reviewed_at.is_(None),
            ).group_by(ExerciseAssignment.patient_id)
        ).all())

    def _week(self, patient_id: str, weeks_back: int) -> list[ExerciseAssignment]:
        end = self.today - timedelta(days=WEEK * weeks_back)
        start = end - timedelta(days=WEEK - 1)
        return [r for r in self.rows.get(patient_id, []) if start <= r.scheduled_for <= end]

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

    def load_week(self, patient_id: str) -> dict[str, Any]:
        this = round(sum(tonnage(r) for r in self._week(patient_id, 0) if r.status == "done"), 1)
        last = round(sum(tonnage(r) for r in self._week(patient_id, 1) if r.status == "done"), 1)
        return {
            "this": this, "last": last,
            "change_pct": round(100 * (this - last) / last) if last else None,
        }

    def awaiting_review(self, patient_id: str) -> int:
        return int(self.waiting.get(patient_id, 0))

    def worklist(self, patient_id: str) -> dict[str, Any] | None:
        """The worklist card's line, or nothing for a chart with no exercise
        on the seven days ending today."""
        week = self._week(patient_id, 0)
        if not week:
            return None
        done = sum(r.status == "done" for r in week)
        return {
            "assigned": len(week), "done": done, "pct": _pct(done, len(week)),
            "awaiting_review": sum(r.status == "done" and r.video_attachment_id is not None
                                   and r.reviewed_at is None for r in week),
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
    }


def care_team_payload(db: Session, clinic: str, patients: list[Patient],
                      rows: list[ExerciseAssignment]) -> list[dict[str, Any]]:
    """Who can be named as having assigned a day: the therapists carrying
    these patients, anyone already named on a row in view, and the house
    list for a clinic that has one. In practice, the clinic's therapists."""
    ids = {p.assigned_provider_id for p in patients if p.assigned_provider_id}
    ids |= {r.assigned_by for r in rows if r.assigned_by}
    ids |= set(HOUSE_CARE_TEAM.get(clinic, ()))
    if not ids:
        return []
    members = db.scalars(
        select(CareTeamMember).where(CareTeamMember.id.in_(ids)).order_by(CareTeamMember.name)
    ).all()
    return [{"id": m.id, "name": m.name, "role": str(m.role)} for m in members]


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
    view = AssignmentView(db)
    stats = WeekStats(db, [p.id for p in patients], today)
    by_patient: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_patient.setdefault(row.patient_id, []).append(view.render(row))
    return {
        "start": start.isoformat(),
        "days": [d.isoformat() for d in days_of(start, days)],
        "today": today.isoformat(),
        "patients": [
            {**patient_card(db, p, view, stats), "assignments": by_patient.get(p.id, [])}
            for p in patients
        ],
        "care_team": care_team_payload(db, clinic, patients, rows),
    }


def patient_schedule_payload(db: Session, clinic: str, patient: Patient, *, start: date | None,
                             days: int, today: date) -> dict[str, Any]:
    """One chart's strip for the patient page."""
    days = check_window(days)
    start = start or week_start(today)
    rows = [r for r in patient_rows(db, patient.id, start, start + timedelta(days=days))
            if r.hospital_id == clinic]
    view = AssignmentView(db)
    return {
        "patient": patient_card(db, patient, view, WeekStats(db, [patient.id], today)),
        "start": start.isoformat(),
        "days": [d.isoformat() for d in days_of(start, days)],
        "today": today.isoformat(),
        "assignments": view.render_all(rows),
    }


def review_queue_payload(db: Session, clinic: str, *, days: int) -> dict[str, Any]:
    """The clips waiting for a look, newest first, each saying whose it is."""
    rows = review_queue(db, clinic, days=days)
    names = dict(db.execute(select(Patient.id, Patient.name).where(
        Patient.id.in_({r.patient_id for r in rows}))).all()) if rows else {}
    view = AssignmentView(db)
    return {"items": [{**view.render(r), "patient_name": names.get(r.patient_id)} for r in rows]}


def _clinic_of(db: Session, patient: Patient) -> dict[str, Any] | None:
    hospital = db.get(Hospital, patient.hospital_id) if patient.hospital_id else None
    return {"id": hospital.id, "name": hospital.name} if hospital else None


def today_payload(db: Session, patient: Patient, day: date) -> dict[str, Any]:
    """What the patient's Today shows: the day's exercises in order, a
    seven-day strip around it (how many were on each day, how many done),
    and whose schedule it is."""
    week_days = days_of(day - timedelta(days=3), 7)
    # A week back, not three days: the strip is three each side, but an
    # exercise put on an earlier day and never done still has to reach the
    # phone, as "still to do from earlier this week".
    rows = patient_rows(db, patient.id, day - timedelta(days=7), week_days[-1] + timedelta(days=1))
    view = AssignmentView(db, patient_app=True)
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
    view = AssignmentView(db, patient_app=True)
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
