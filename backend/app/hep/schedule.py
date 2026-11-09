"""The exercise schedule: one exercise on one patient's calendar day.

A plan (``plans.py``) is a standing prescription with a frequency. This is
the therapist's week grid — Step-Ups on Monday, Wednesday and Friday, Heel
Slides every day — and what the patient's Today lists. Done, the row itself
carries what came back: the pain score, a note, the clip of the attempt (an
attachment on the patient's thread). The clip the patient follows is
resolved per clinic (``service.resolve_clip``): the therapist's own
demonstration when she has uploaded one, the library's otherwise.

The console and the patient app read the same ``Assignment`` payload
(``AssignmentView``); the patient's copy drops the clinic id and points its
media URLs at the route the patient's session can reach.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.hep.models import (
    CATEGORY_LABELS,
    REGION_LABELS,
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
from app.models.hospital import Hospital
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
TEXT_LIMIT = 400
NOTE_LIMIT = 600
COMPLETION_SOURCES = ("app", "console")
DOSE_FIELDS = ("sets", "reps", "hold_seconds", "side")
EDITABLE = DOSE_FIELDS + ("clinician_instructions", "scheduled_for", "assigned_by", "sort_order")
# Therapists who belong in a clinic's "assigned by" list before they carry a
# patient of their own: the demo clinic's two.
HOUSE_CARE_TEAM: dict[str, tuple[str, ...]] = {"hirt": ("ct_harris", "ct_gregg")}


class ScheduleConflict(HepError):
    """A write the calendar refuses as it stands — the day already carries
    that exercise, or the row is done; the router answers 409."""


class UnknownRow(HepError):
    """A patient or exercise this clinic cannot see; the router answers 404
    so that an id's existence does not leak."""


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
            hold_seconds=hold, side=side, clinician_instructions=note, assigned_by=member,
            status="assigned", created_at=now, updated_at=now,
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
    and its date — what was done is the record — but its note, author and
    position may still be tidied."""
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


def complete_assignment(
    db: Session, row: ExerciseAssignment, *, pain_after: int | None, note: str, source: str,
    video_attachment_id: int | None = None, actor: str | None = None,
) -> ExerciseAssignment:
    """Record what came back: from the app (the patient, with a clip they
    may have sent) or from the console (the therapist, in the room). The
    console's log goes to the audit trail under her id; the patient's own
    tap is its own record."""
    ensure_open(row)
    if source not in COMPLETION_SOURCES:
        raise HepError(f"Unknown completion source: {source}")
    if pain_after is not None and not 0 <= int(pain_after) <= 10:
        raise HepError("Pain is a number from 0 to 10")
    now = datetime.now()
    row.status = "done"
    row.completed_at = now
    row.pain_after = int(pain_after) if pain_after is not None else None
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


def completion_line(title: str, pain_after: int | None, note: str | None) -> str:
    """The thread line a completion from the app writes, so the chart shows
    the score (and the clip beside it) where the conversation is."""
    line = f"Did {title}"
    if pain_after is not None:
        line += f" · pain {pain_after}/10 after"
    if note:
        line += "\n" + note.strip()
    return line


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
            "dose": dose_text(row.sets, row.reps, row.hold_seconds, row.side),
            "clinician_instructions": row.clinician_instructions or "",
            "assigned_by": row.assigned_by,
            "assigned_by_name": self.member_name(row.assigned_by),
            "status": row.status,
            "video": self.video(clip),
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


def patient_card(db: Session, patient: Patient, view: AssignmentView) -> dict[str, Any]:
    from app.engine.pipeline import latest_assessment

    assessment = latest_assessment(db, patient.id)
    return {
        "id": patient.id, "name": patient.name, "initials": patient.initials,
        "pathway": pathway_of(patient),
        "assigned_provider_id": patient.assigned_provider_id,
        "assigned_provider_name": view.member_name(patient.assigned_provider_id),
        "risk_tier": str(assessment.risk_level).lower() if assessment else None,
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
    by_patient: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_patient.setdefault(row.patient_id, []).append(view.render(row))
    return {
        "start": start.isoformat(),
        "days": [d.isoformat() for d in days_of(start, days)],
        "today": today.isoformat(),
        "patients": [
            {**patient_card(db, p, view), "assignments": by_patient.get(p.id, [])}
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
        "patient": patient_card(db, patient, view),
        "start": start.isoformat(),
        "days": [d.isoformat() for d in days_of(start, days)],
        "today": today.isoformat(),
        "assignments": view.render_all(rows),
    }


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
    hospital = db.get(Hospital, patient.hospital_id) if patient.hospital_id else None
    return {
        "date": day.isoformat(),
        "items": view.render_all([r for r in rows if r.scheduled_for == day]),
        "overdue": view.render_all([r for r in rows
                                    if r.scheduled_for < day and r.status == "assigned"]),
        "week": week,
        "clinic": {"id": hospital.id, "name": hospital.name} if hospital else None,
    }
