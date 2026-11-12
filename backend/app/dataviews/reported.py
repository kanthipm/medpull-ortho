"""One chart's day-by-day grid of what the person reported and what they did
on the exercise calendar: the sheet a clinic otherwise keeps by hand.

A row is a calendar day, newest first, and a day with nothing on it is still
a row: a gap is information. Three stores feed it, none of them written
here:

* **check-ins** — the answers are held as the transcript the console shows
  (``Checkin`` / ``CheckinMessage``: the question, then the person's
  sentence). ``answers_from_pairs`` reads the sentences back into the values
  that produced them, using the same question sets that wrote them
  (``app/tasks/service.py``), so a number is the number the person gave and
  a sentence nobody can read back is left out rather than guessed at.
* **training observations** — ``session_load`` (effort x minutes) and
  ``program_done`` for the day, as the engine reads them.
* **the exercise calendar** — that day's rows with what was prescribed and
  what was done, and the plain "done against prescribed" line the calendar
  itself shows (``app/hep/schedule.py``).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.dataviews import iso, window_start
from app.dataviews.readings import patient_header
from app.models.checkin import Checkin, CheckinMessage
from app.models.enums import MetricType as M
from app.models.observation import Observation
from app.models.patient import Patient
from app.tasks.service import PHRASES, QUESTION_SETS

# Every check-in question by its prompt. Two sets that ask the same question
# in the same words share its id, so the first definition stands.
_BY_PROMPT: dict[str, dict[str, Any]] = {}
for _questions in QUESTION_SETS.values():
    for _question in _questions:
        _BY_PROMPT.setdefault(_question["prompt"], _question)

_NUMBER = re.compile(r"-?\d+")

# What a column is called. A question the grid has no short name for is
# headed by its id in words.
_LABELS = {
    "pain": "Pain",
    "swelling": "New swelling",
    "new_pain": "New pain",
    "sleep": "Sleep",
    "sleep_quality": "Sleep",
    "program": "Program",
    "rpe": "Effort",
    "minutes": "Minutes",
    "note": "Note",
    "fever": "Fever",
    "redness": "Redness",
    "drainage": "Drainage",
    "exercises": "Exercises",
    "taken": "Medication",
    "fatigue": "Fatigue",
    "soreness": "Soreness",
    "stress": "Stress",
    "mood": "Mood",
    "energy": "Energy",
    "activity": "Activity",
    "done": "Done",
}


def _answer(question: dict[str, Any], text: str) -> Any:
    """The value a patient sentence stands for, or None when it cannot be
    read back with certainty. The inverse of ``tasks.service.answer_to_text``."""
    kind = question["kind"]
    qid = question["id"]
    said = (text or "").strip()
    if not said:
        return None
    if kind == "text":
        return said
    # A question with no sentence of its own is answered as the prompt
    # restated ("<prompt> <value>."); the value is what follows the prompt.
    rest = said[len(question["prompt"]):].strip() if said.startswith(question["prompt"]) else None
    if kind in ("scale", "number"):
        if said == question.get("phrase_zero"):
            return 0
        found = _NUMBER.search(rest if rest is not None else said)
        if not found:
            return None
        value = int(found.group())
        lo, hi = (0, 10) if kind == "scale" else (question.get("min", 0), question.get("max", 10_000))
        return value if lo <= value <= hi else None
    if kind in ("yes_no", "choice"):
        options = question.get("options") or ["yes", "no"]
        for value, phrase in PHRASES.get(qid, {}).items():
            if said == phrase and value in options:
                return value
        if rest is not None:
            value = rest.rstrip(".").strip().lower()
            return value if value in options else None
    return None


def answers_from_pairs(
    pairs: list[tuple[str, str]], asked: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The check-in's answers from its (question, sentence) pairs. A pair
    whose question is not one a question set asks (a free conversation with
    the assistant) contributes nothing. ``asked`` collects each answered
    question as it was put (by id, first wording seen), so a column can be
    headed by the question this person was actually asked."""
    answers: dict[str, Any] = {}
    for prompt, text in pairs:
        question = _BY_PROMPT.get(prompt)
        if question is None:
            continue
        value = _answer(question, text)
        if value is not None:
            answers[question["id"]] = value
            if asked is not None:
                asked.setdefault(question["id"], question)
    return answers


def _pairs(messages: list[CheckinMessage]) -> list[tuple[str, str]]:
    """Each question with the sentence that answered it: a line from the
    assistant followed directly by one from the patient."""
    ordered = sorted(messages, key=lambda m: m.seq)
    return [
        (asked.text, said.text)
        for asked, said in zip(ordered, ordered[1:])
        if asked.who == "copilot" and said.who == "patient"
    ]


def _checkins(
    db: Session, patient_id: str, since: date, today: date,
) -> tuple[dict[date, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    """The window's check-ins by day, oldest first within a day, and the
    questions they answered (by id, in the order they were first asked)."""
    rows = db.scalars(
        select(Checkin)
        .where(
            Checkin.patient_id == patient_id,
            Checkin.occurred_at >= datetime.combine(since, time.min),
            Checkin.occurred_at < datetime.combine(today + timedelta(days=1), time.min),
        )
        .order_by(Checkin.occurred_at)
    ).all()
    asked: dict[str, dict[str, Any]] = {}
    if not rows:
        return {}, asked
    messages: dict[int, list[CheckinMessage]] = {}
    for message in db.scalars(
        select(CheckinMessage).where(CheckinMessage.checkin_id.in_([c.id for c in rows]))
    ).all():
        messages.setdefault(message.checkin_id, []).append(message)
    by_day: dict[date, list[dict[str, Any]]] = {}
    for checkin in rows:
        by_day.setdefault(checkin.occurred_at.date(), []).append({
            "id": checkin.id,
            "at": iso(checkin.occurred_at),
            "channel": checkin.channel,
            "answers": answers_from_pairs(_pairs(messages.get(checkin.id, [])), asked),
        })
    return by_day, asked


def _training(db: Session, patient_id: str, since: date, today: date) -> dict[date, dict[str, Any]]:
    """The day's training load (sessions add up) and program answer (the
    last one of the day stands), as the engine reads them."""
    rows = db.execute(
        select(Observation.local_date, Observation.metric_type, Observation.value_num,
               Observation.start_time)
        .where(
            Observation.patient_id == patient_id,
            Observation.deleted_at.is_(None),
            Observation.value_num.is_not(None),
            Observation.metric_type.in_([str(M.SESSION_LOAD), str(M.PROGRAM_DONE)]),
            Observation.local_date >= since,
            Observation.local_date <= today,
        )
        .order_by(Observation.start_time)
    ).all()
    by_day: dict[date, dict[str, Any]] = {}
    for day, metric_type, value, _ in rows:
        cell = by_day.setdefault(day, {"load": None, "program": None})
        if str(metric_type) == str(M.SESSION_LOAD):
            cell["load"] = round((cell["load"] or 0.0) + float(value), 1)
        else:
            cell["program"] = float(value)
    return by_day


def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _exercise_days(db: Session, patient: Patient, since: date, today: date) -> tuple[dict[date, dict[str, Any]], str]:
    """Each day's exercise rows with what was prescribed and what was done,
    and the unit the clinic reads loads in."""
    if not settings.hep_enabled:
        return {}, "kg"
    from app.hep import schedule
    from app.hep.models import Exercise, ExerciseAssignment
    from app.hep.service import load_unit_of
    from app.models.hospital import Hospital

    hospital = db.get(Hospital, patient.hospital_id) if patient.hospital_id else None
    unit = load_unit_of(hospital)
    rows = db.scalars(
        select(ExerciseAssignment)
        .where(
            ExerciseAssignment.patient_id == patient.id,
            ExerciseAssignment.scheduled_for >= since,
            ExerciseAssignment.scheduled_for <= today,
        )
        .order_by(ExerciseAssignment.scheduled_for, ExerciseAssignment.sort_order,
                  ExerciseAssignment.id)
    ).all()
    if not rows:
        return {}, unit
    titles = dict(db.execute(
        select(Exercise.id, Exercise.title).where(Exercise.id.in_({r.exercise_id for r in rows}))
    ).all())
    by_day: dict[date, list[ExerciseAssignment]] = {}
    for row in rows:
        by_day.setdefault(row.scheduled_for, []).append(row)

    out: dict[date, dict[str, Any]] = {}
    for day, day_rows in by_day.items():
        done = [r for r in day_rows if r.status == "done"]
        items = []
        for row in day_rows:
            against = (schedule.done_against_prescribed(row, unit) if row.status == "done"
                       else {"over": False, "under": False, "line": None})
            items.append({
                "id": row.id,
                "exercise_id": row.exercise_id,
                "title": titles.get(row.exercise_id) or "Exercise",
                "state": schedule.state_of(row, today),
                "sets": row.sets, "reps": row.reps, "hold_seconds": row.hold_seconds,
                "load_kg": row.load_kg, "rpe_target": row.rpe_target,
                "sets_done": row.sets_done, "reps_done": row.reps_done,
                "load_done_kg": row.load_done_kg, "effort": row.effort,
                "pain_before": row.pain_before, "pain_after": row.pain_after,
                "duration_s": row.duration_s,
                "note": row.note or None,
                "skip_reason": row.skip_reason or None,
                "has_clip": row.video_attachment_id is not None,
                "reviewed": row.reviewed_at is not None,
                "over": bool(against["over"]),
                "under": bool(against["under"]),
                "line": against["line"],
            })
        states = [item["state"] for item in items]
        seconds = [r.duration_s for r in done if r.duration_s]
        out[day] = {
            "assigned": len(day_rows),
            "done": len(done),
            "skipped": states.count("skipped"),
            "missed": states.count("missed"),
            "pain_before": _avg([r.pain_before for r in done if r.pain_before is not None]),
            "pain_after": max((r.pain_after for r in done if r.pain_after is not None), default=None),
            "effort": max((r.effort for r in done if r.effort is not None), default=None),
            "effort_target": max((r.rpe_target for r in done if r.rpe_target is not None), default=None),
            "minutes": round(sum(seconds) / 60) if seconds else None,
            # kilograms moved: load x reps x sets, as done where the lifter said
            "load_done": round(sum(schedule.tonnage(r) for r in done), 1),
            "over": sum(1 for item in items if item["over"]),
            "clips": sum(1 for item in items if item["has_clip"]),
            "items": items,
        }
    return out, unit


def _questions(asked: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The check-in columns this window needs: every question that was
    answered at least once, worded as it was asked, in the order the
    check-in asks them (the note last, where a sheet keeps it)."""
    ordered = sorted(asked.values(), key=lambda q: q["kind"] == "text")
    return [
        {
            "id": question["id"],
            "label": _LABELS.get(question["id"], question["id"].replace("_", " ").capitalize()),
            "kind": question["kind"],
            "prompt": question["prompt"],
            "options": question.get("options") or (
                ["yes", "no"] if question["kind"] == "yes_no" else None),
        }
        for question in ordered
    ]


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _pain_summary(rows: list[dict[str, Any]], today: date) -> dict[str, Any] | None:
    """Reported pain this week against the week before, as plain averages."""
    recent: list[float] = []
    prior: list[float] = []
    latest = None
    for row in rows:  # newest first
        pain = row["answers"].get("pain")
        if not isinstance(pain, int):
            continue
        if latest is None:
            latest = {"value": pain, "date": row["date"]}
        age = (today - date.fromisoformat(row["date"])).days
        if age < 7:
            recent.append(float(pain))
        elif age < 14:
            prior.append(float(pain))
    if latest is None:
        return None
    return {"latest": latest, "mean_7": _mean(recent), "mean_prior_7": _mean(prior)}


def reported(db: Session, patient: Patient, days: int, today: date) -> dict[str, Any]:
    since = window_start(today, days)
    checkins, asked = _checkins(db, patient.id, since, today)
    training = _training(db, patient.id, since, today)
    exercises, unit = _exercise_days(db, patient, since, today)

    rows: list[dict[str, Any]] = []
    for offset in range(days):
        day = today - timedelta(days=offset)
        day_checkins = checkins.get(day, [])
        # The day's answers: a later check-in the same day restates an earlier one.
        answers: dict[str, Any] = {}
        for checkin in day_checkins:
            answers.update(checkin["answers"])
        trained = training.get(day, {})
        rows.append({
            "date": day.isoformat(),
            "day": (day - patient.surgery_date).days,
            "checkins": day_checkins,
            "answers": answers,
            "load": trained.get("load"),
            "program": trained.get("program"),
            "exercises": exercises.get(day),
        })

    with_checkin = sum(1 for row in rows if row["checkins"])
    with_exercises = [row["exercises"] for row in rows if row["exercises"]]
    return {
        "patient": patient_header(db, patient, today),
        "as_of": today.isoformat(),
        "days": days,
        "since": since.isoformat(),
        "load_unit": unit,
        "questions": _questions(asked),
        "rows": rows,
        "summary": {
            "checkin_days": with_checkin,
            "pain": _pain_summary(rows, today),
            "exercises": {
                "assigned": sum(day["assigned"] for day in with_exercises),
                "done": sum(day["done"] for day in with_exercises),
                "over": sum(day["over"] for day in with_exercises),
                "clips": sum(day["clips"] for day in with_exercises),
            },
        },
    }
