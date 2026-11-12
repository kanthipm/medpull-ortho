"""The calendar's wider reads: a lifter's week in review, a month at a
glance, and one exercise over time.

Each is a plain read of ``exercise_assignments`` shaped for one screen, with
the row logic (state, done against prescribed, what waits for a look,
tonnage) taken from ``schedule.py`` so the numbers here are the numbers on
the grid. Nothing in this file writes.

Everything is said in the lifter's own terms: what was done, what was
written, and the plain change between two weeks. There is no ratio, no
band and no line drawn: the therapist reads the numbers and decides.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.hep.models import CATEGORY_LABELS, REGION_LABELS, Exercise, ExerciseAssignment
from app.hep.schedule import (
    FUTURE_DAYS,
    MAX_CALENDAR_DAYS,
    WEEK,
    AssignmentView,
    UnknownRow,
    WeekStats,
    _pct,
    change_pct,
    clinic_rows,
    days_of,
    done_against_prescribed,
    done_load,
    patient_card,
    planned_load,
    planned_tonnage,
    review_reason,
    schedule_patients,
    state_of,
    tonnage,
    week_start,
    went_over,
)
from app.hep.service import HepError, clinic_care_team, clinic_payload
from app.models.mobile import Message
from app.models.patient import Patient

# How far back one exercise's history looks by default, and at most.
HISTORY_DAYS = 120
MAX_HISTORY_DAYS = 365
# Why a lifter is near the top of the week review.
ATTENTION = ("over", "review", "missed")


def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _known(rows: list[ExerciseAssignment], name: str) -> list[int]:
    return [getattr(r, name) for r in rows if getattr(r, name) is not None]


# --- the week review ----------------------------------------------------------------


def _pain(done: list[ExerciseAssignment], days: list[date]) -> dict[str, Any]:
    """Pain around the week's done exercises: the averages before and
    after, the highest after, and the same per day."""
    by_day = []
    for day in days:
        on_day = [r for r in done if r.scheduled_for == day]
        after = _known(on_day, "pain_after")
        by_day.append({
            "date": day.isoformat(),
            "done": len(on_day),
            "before_avg": _avg(_known(on_day, "pain_before")),
            "after_avg": _avg(after),
            "after_max": max(after) if after else None,
        })
    after = _known(done, "pain_after")
    return {
        "before_avg": _avg(_known(done, "pain_before")),
        "after_avg": _avg(after),
        "after_max": max(after) if after else None,
        "by_day": by_day,
    }


def _effort(done: list[ExerciseAssignment]) -> dict[str, Any]:
    """How hard the week felt against how hard it was written to feel.
    ``avg`` is over every done exercise that reported an effort. Only some
    carry a target, so the comparison is made on those alone: their
    reported effort (``avg_where_targeted``) beside their target
    (``target_avg``). ``days_over_target`` counts the days on which at
    least one exercise was reported above its target."""
    targeted = [r for r in done if r.effort is not None and r.rpe_target is not None]
    return {
        "avg": _avg(_known(done, "effort")),
        "target_avg": _avg([r.rpe_target for r in targeted]),
        "avg_where_targeted": _avg([r.effort for r in targeted]),
        "days_over_target": len({r.scheduled_for for r in targeted if r.effort > r.rpe_target}),
    }


def _week_entry(
    patient: Patient, rows: list[ExerciseAssignment], *, start: date, today: date,
    view: AssignmentView, stats: WeekStats, last_message: datetime | None, card: dict[str, Any],
) -> dict[str, Any]:
    days = days_of(start, WEEK)
    end = start + timedelta(days=WEEK)
    week = [r for r in rows if start <= r.scheduled_for < end]
    before = [r for r in rows if r.scheduled_for < start]
    coming = [r for r in rows if r.scheduled_for >= end]
    done = [r for r in week if r.status == "done"]
    missed = sum(state_of(r, today) == "missed" for r in week)
    unit = view.unit(patient.hospital_id)
    over = []
    for r in done:
        compared = done_against_prescribed(r, unit)
        if compared["over"]:
            exercise = view.exercise(r.exercise_id)
            over.append({
                "assignment_id": r.id, "exercise_id": r.exercise_id,
                "title": exercise.title if exercise else "",
                "day": r.scheduled_for.isoformat(), "line": compared["line"],
                "reviewed": r.reviewed_at is not None,
            })
    waiting = stats.awaiting_review(patient.id)
    done_week, planned_week = done_load(week), planned_load(week)
    done_before, planned_next = done_load(before), planned_load(coming)
    flags = {"over": bool(over), "review": waiting > 0, "missed": missed > 0}
    return {
        "patient": card,
        "week": {
            "assigned": len(week),
            "done": len(done),
            "skipped": sum(r.status == "skipped" for r in week),
            "missed": missed,
            # Still to do: assigned and not yet past.
            "open": sum(r.status == "assigned" for r in week) - missed,
            "pct": _pct(len(done), len(week)),
        },
        "pain": _pain(done, days),
        "effort": _effort(done),
        "load": {
            "done": done_week,
            "planned": planned_week,
            "last_week_done": done_before,
            "change_pct": change_pct(done_week, done_before),
            # The week as written against what was actually done the week before.
            "planned_vs_last_week_pct": change_pct(planned_week, done_before),
        },
        "over": over,
        "awaiting_review": waiting,
        "last_patient_message_at": last_message.isoformat() if last_message else None,
        "next_week": {
            "start": end.isoformat(),
            "assigned": len(coming),
            "planned_load": planned_next,
            "set": bool(coming),
            # Next week as written against this week as written.
            "change_pct": change_pct(planned_next, planned_week),
        },
        "attention": [name for name in ATTENTION if flags[name]],
    }


def week_review_payload(db: Session, clinic: str, *, start: date | None,
                        today: date) -> dict[str, Any]:
    """The week in review, one entry per lifter of the clinic: how the
    seven days from ``start`` went (assigned against done, pain, effort
    against target, load done and written, the days that went over the
    dose), what waits for a look, when they last wrote, and whether next
    week is set. Lifters with something to look at come first, then by
    name. ``start`` is the Monday of ``today``'s week unless given."""
    start = start or week_start(today)
    patients = schedule_patients(db, clinic)
    ids = [p.id for p in patients]
    by_patient: dict[str, list[ExerciseAssignment]] = {pid: [] for pid in ids}
    for row in clinic_rows(db, clinic, start - timedelta(days=WEEK),
                           start + timedelta(days=2 * WEEK), ids):
        by_patient[row.patient_id].append(row)
    last_messages = dict(db.execute(
        select(Message.patient_id, func.max(Message.created_at))
        .where(Message.patient_id.in_(ids), Message.sender == "patient")
        .group_by(Message.patient_id)
    ).all()) if ids else {}
    view = AssignmentView(db, today=today)
    stats = WeekStats(db, ids, today)
    entries = [
        _week_entry(p, by_patient[p.id], start=start, today=today, view=view, stats=stats,
                    last_message=last_messages.get(p.id),
                    card=patient_card(db, p, view, stats))
        for p in patients
    ]
    entries.sort(key=lambda e: (not e["attention"], e["patient"]["name"], e["patient"]["id"]))
    return {
        "start": start.isoformat(),
        "days": [d.isoformat() for d in days_of(start, WEEK)],
        "today": today.isoformat(),
        "clinic": clinic_payload(db, clinic),
        "patients": entries,
    }


# --- a month at a glance ------------------------------------------------------------


def calendar_payload(db: Session, clinic: str, *, start: date | None, days: int, today: date,
                     patient_id: str | None = None) -> dict[str, Any]:
    """A range of the calendar for a month view: every clinic chart (or the
    one asked for) with each day's rows in their compact form and the day's
    counts. Opens on the Monday on or before the first of ``today``'s
    month unless told where."""
    if not 1 <= days <= MAX_CALENDAR_DAYS:
        raise HepError(f"Show between 1 and {MAX_CALENDAR_DAYS} days")
    start = start or week_start(today.replace(day=1))
    patients = schedule_patients(db, clinic)
    if patient_id is not None:
        patients = [p for p in patients if p.id == patient_id]
        if not patients:
            raise UnknownRow(f"Unknown patient: {patient_id}")
    ids = [p.id for p in patients]
    window = days_of(start, days)
    view = AssignmentView(db, today=today)
    stats = WeekStats(db, ids, today)
    cells: dict[tuple[str, date], list[ExerciseAssignment]] = {}
    for row in clinic_rows(db, clinic, start, start + timedelta(days=days), ids):
        cells.setdefault((row.patient_id, row.scheduled_for), []).append(row)

    def day_cell(pid: str, day: date) -> dict[str, Any]:
        rows = cells.get((pid, day), [])
        missed = sum(state_of(r, today) == "missed" for r in rows)
        return {
            "date": day.isoformat(),
            "assigned": len(rows),
            "done": sum(r.status == "done" for r in rows),
            "skipped": sum(r.status == "skipped" for r in rows),
            "missed": missed,
            "open": sum(r.status == "assigned" for r in rows) - missed,
            "over": sum(went_over(r) for r in rows),
            "awaiting_review": sum(review_reason(r) is not None for r in rows),
            "items": [view.compact(r) for r in rows],
        }

    return {
        "start": start.isoformat(),
        "days": [d.isoformat() for d in window],
        "today": today.isoformat(),
        "clinic": clinic_payload(db, clinic),
        "patients": [
            {**patient_card(db, p, view, stats), "days": [day_cell(p.id, d) for d in window]}
            for p in patients
        ],
        "care_team": clinic_care_team(db, clinic),
    }


# --- one exercise over time -----------------------------------------------------------


def _load_used(row: ExerciseAssignment) -> float | None:
    """The load a done day was done at: what the lifter reported, else
    what was written; nothing for bodyweight work."""
    return row.load_done_kg if row.load_done_kg is not None else row.load_kg


def _history_point(row: ExerciseAssignment, view: AssignmentView) -> dict[str, Any]:
    done = row.status == "done"
    compared = done_against_prescribed(row, view.unit(row.hospital_id)) if done else None
    return {
        "id": row.id,
        "date": row.scheduled_for.isoformat(),
        "status": row.status,
        "state": state_of(row, view.today),
        "dose": view.dose(row),
        "sets": row.sets, "reps": row.reps, "hold_seconds": row.hold_seconds,
        "load_kg": row.load_kg,
        "sets_done": row.sets_done, "reps_done": row.reps_done,
        "load_done_kg": row.load_done_kg,
        # What the day moved as done; nothing until it is done.
        "tonnage": round(tonnage(row), 1) if done else None,
        "planned_tonnage": round(planned_tonnage(row), 1),
        "pain_before": row.pain_before, "pain_after": row.pain_after,
        "effort": row.effort, "rpe_target": row.rpe_target,
        "duration_s": row.duration_s,
        "has_clip": row.video_attachment_id is not None,
        "reviewed": row.reviewed_at is not None,
        "over": bool(compared and compared["over"]),
        "under": bool(compared and compared["under"]),
        "line": compared["line"] if compared else None,
    }


def _history_summary(rows: list[ExerciseAssignment], today: date) -> dict[str, Any]:
    """The run in a few numbers: how many sessions were done, the load at
    the first, the latest and the heaviest of them, and the change from the
    first to the latest."""
    done = [r for r in rows if r.status == "done"]
    loaded = [(r, _load_used(r)) for r in done if _load_used(r)]
    first, latest = (loaded[0], loaded[-1]) if loaded else (None, None)
    best = max(loaded, key=lambda pair: (pair[1], pair[0].scheduled_for)) if loaded else None

    def kg(pair: Any) -> float | None:
        return pair[1] if pair else None

    def on(pair: Any) -> str | None:
        return pair[0].scheduled_for.isoformat() if pair else None

    return {
        "sessions": len(rows),
        "sessions_done": len(done),
        "skipped": sum(r.status == "skipped" for r in rows),
        "missed": sum(state_of(r, today) == "missed" for r in rows),
        "over": sum(went_over(r) for r in done),
        "first_load_kg": kg(first), "first_load_on": on(first),
        "latest_load_kg": kg(latest), "latest_load_on": on(latest),
        "best_load_kg": kg(best), "best_load_on": on(best),
        "load_change_pct": change_pct(kg(latest), kg(first)) if loaded else None,
        "total_tonnage": round(sum(tonnage(r) for r in done), 1),
        "pain_after_avg": _avg(_known(done, "pain_after")),
        "effort_avg": _avg(_known(done, "effort")),
        "last_done_on": done[-1].scheduled_for.isoformat() if done else None,
    }


def history_payload(
    db: Session, patient: Patient, exercise: Exercise, *, days: int, ahead: int, today: date,
    patient_app: bool = False,
) -> dict[str, Any]:
    """One exercise on one patient's calendar over time, oldest first: each
    day it was on, as written and as done, and a summary of the run. Looks
    ``days`` back from ``today`` and, when asked, ``ahead`` days forward to
    what is written next."""
    if not 1 <= days <= MAX_HISTORY_DAYS:
        raise HepError(f"Look back between 1 and {MAX_HISTORY_DAYS} days")
    if not 0 <= ahead <= FUTURE_DAYS:
        raise HepError(f"Look ahead between 0 and {FUTURE_DAYS} days")
    start, end = today - timedelta(days=days), today + timedelta(days=ahead)
    rows = db.scalars(
        select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == patient.id,
            ExerciseAssignment.exercise_id == exercise.id,
            ExerciseAssignment.scheduled_for >= start,
            ExerciseAssignment.scheduled_for <= end,
        ).order_by(ExerciseAssignment.scheduled_for, ExerciseAssignment.id)
    ).all()
    view = AssignmentView(db, patient_app=patient_app, today=today)
    return {
        "patient": {"id": patient.id, "name": patient.name},
        "exercise": {
            "id": exercise.id, "key": exercise.key, "title": exercise.title,
            "body_region": exercise.body_region,
            "body_region_label": REGION_LABELS.get(exercise.body_region, exercise.body_region),
            "category": exercise.category,
            "category_label": CATEGORY_LABELS.get(exercise.category, exercise.category),
        },
        "from": start.isoformat(),
        "to": end.isoformat(),
        "today": today.isoformat(),
        "clinic": clinic_payload(db, patient.hospital_id),
        "points": [_history_point(r, view) for r in rows],
        "summary": _history_summary([r for r in rows if r.scheduled_for <= today], today),
    }
