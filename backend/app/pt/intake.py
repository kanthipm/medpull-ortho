"""Where the answers to the clinic's asks are filed.

``record_task_answers`` is called by ``tasks.complete_task`` for a task
whose question set is one of ``app/pt/asks.py``'s, with the answers already
checked against the questions. It writes the row the chart reads and raises
the care team's notice when the answer is one they would want today. The
caller commits.

``after_checkin`` is the other door: a daily check-in that says "yes, a new
pain" is followed by the ask that finds out where.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.adherence import AdherenceTask
from app.models.patient import Patient
from app.pt import asks, measures, regions
from app.pt.instruments import INSTRUMENTS
from app.pt.models import (
    FunctionGoal,
    FunctionRating,
    Handoff,
    Measurement,
    MorningCheck,
    OutcomeSchedule,
    OutcomeScore,
    PainArea,
    WeekCheckin,
)

logger = logging.getLogger(__name__)


def _notify(db: Session, patient: Patient, title: str, body: str) -> None:
    from app.tasks.service import notify_care_team

    notify_care_team(db, patient, f"{patient.name} — {title}", body, "patient_report")


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _day(value: Any, fallback: date) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return fallback


# --- one filing per ask ------------------------------------------------------------------


def _morning(db: Session, task: AdherenceTask, patient: Patient, answers: dict, ref: dict,
             now: datetime) -> None:
    session_day = _day(ref.get("session_day"), now.date() - timedelta(days=1))
    row = db.scalar(select(MorningCheck).where(
        MorningCheck.patient_id == patient.id, MorningCheck.session_day == session_day))
    if row is None:
        row = MorningCheck(patient_id=patient.id, session_day=session_day,
                           ceiling=int(ref.get("ceiling", 3)), asked_at=task.created_at)
        db.add(row)
    row.task_id = task.id
    row.answered_at = now
    row.pain = _int(answers.get("pain"))
    stiffer = answers.get("stiffer")
    row.stiffer = None if stiffer is None else str(stiffer).lower() == "yes"
    if row.pain is None:
        row.settled = None
        return
    row.settled = row.pain <= row.ceiling and not row.stiffer
    if not row.settled:
        parts = [f"pain {row.pain}/10 (the ceiling is {row.ceiling})"]
        if row.stiffer:
            parts.append("stiffer than usual")
        _notify(db, patient, "Not settled the morning after a session",
                f"After {session_day.strftime('%A')}'s session: {', '.join(parts)}.")


def _week(db: Session, task: AdherenceTask, patient: Patient, answers: dict, ref: dict,
          now: datetime) -> None:
    monday = now.date() - timedelta(days=now.date().weekday())
    week_start = _day(ref.get("week_start"), monday)
    row = db.scalar(select(WeekCheckin).where(
        WeekCheckin.patient_id == patient.id, WeekCheckin.week_start == week_start))
    if row is None:
        row = WeekCheckin(patient_id=patient.id, week_start=week_start, asked_at=task.created_at)
        db.add(row)
    row.task_id = task.id
    row.answered_at = now
    went = str(answers.get("went") or "").lower()
    row.went = went if went in ("better", "same", "worse") else None
    note = str(answers.get("next_week") or "").strip()
    row.change_note = note[:600] or None


def _new_area(db: Session, task: AdherenceTask, patient: Patient, answers: dict, ref: dict,
              now: datetime) -> None:
    area = str(answers.get("area") or "").lower()
    if not area:
        return
    side = str(answers.get("side") or "").lower()
    region = regions.make(area, None if side == "middle" else side)
    note = str(answers.get("note") or "").strip()[:300] or None
    rows = db.scalars(select(PainArea).where(PainArea.patient_id == patient.id)).all()
    known = [r.region for r in rows if r.source == "evaluation" or r.seen_on is not None]
    existing = next((r for r in rows if r.region == region), None)
    if existing is not None:
        if note:
            existing.note = note
        if existing.source == "reported":
            existing.noted_on = now.date()
            existing.seen_on = None
    else:
        db.add(PainArea(patient_id=patient.id, region=region, source="reported",
                        noted_on=now.date(), note=note, created_by="patient"))
    if regions.is_new(region, known):
        _notify(db, patient, f"Reported a new area: {regions.label(region).lower()}",
                note or "Not one of the areas recorded at the evaluation.")


def _clean_goal(text: Any) -> str:
    words = " ".join(str(text or "").split())
    if words.lower().strip(" .!") in ("", "no", "none", "nothing", "n/a", "na", "skip"):
        return ""
    return words[:asks.GOAL_TEXT_LIMIT]


def active_goals(db: Session, patient_id: str) -> list[FunctionGoal]:
    return db.scalars(
        select(FunctionGoal).where(FunctionGoal.patient_id == patient_id,
                                   FunctionGoal.active.is_(True))
        .order_by(FunctionGoal.position, FunctionGoal.id)
    ).all()


def _goals(db: Session, task: AdherenceTask, patient: Patient, answers: dict, ref: dict,
           now: datetime) -> None:
    current = active_goals(db, patient.id)
    room = asks.MAX_GOALS - len(current)
    position = max((g.position for g in current), default=-1) + 1
    have = {g.text.lower() for g in current}
    for key in ("goal_1", "goal_2", "goal_3"):
        text = _clean_goal(answers.get(key))
        if not text or text.lower() in have or room <= 0:
            continue
        db.add(FunctionGoal(patient_id=patient.id, text=text, position=position,
                            created_by="patient", created_at=now))
        have.add(text.lower())
        position += 1
        room -= 1


def rate_goals(db: Session, patient_id: str, scores: dict[int, int], day: date,
               source: str = "patient") -> float | None:
    """File a rating for each goal named, and the day's patient-specific
    functional scale score (their average). Returns that average."""
    goals = {g.id: g for g in active_goals(db, patient_id)}
    filed: list[int] = []
    for goal_id, score in scores.items():
        if goal_id not in goals or not 0 <= score <= 10:
            continue
        row = db.scalar(select(FunctionRating).where(
            FunctionRating.goal_id == goal_id, FunctionRating.rated_on == day))
        if row is None:
            db.add(FunctionRating(goal_id=goal_id, patient_id=patient_id, rated_on=day,
                                  score=score, source=source))
        else:
            row.score, row.source = score, source
        filed.append(score)
    if not filed:
        return None
    average = round(sum(filed) / len(filed), 1)
    put_score(db, patient_id, "psfs", average, day, source=source, entered_by=None)
    return average


def put_score(db: Session, patient_id: str, instrument: str, total: float, day: date, *,
              source: str, entered_by: str | None) -> OutcomeScore:
    """One score per instrument and day: a second one that day replaces the
    first. Moves the instrument's schedule on, when it has one."""
    row = db.scalar(select(OutcomeScore).where(
        OutcomeScore.patient_id == patient_id, OutcomeScore.instrument == instrument,
        OutcomeScore.scored_on == day))
    if row is None:
        row = OutcomeScore(patient_id=patient_id, instrument=instrument, scored_on=day,
                           total=float(total), source=source, entered_by=entered_by)
        db.add(row)
    else:
        row.total, row.source, row.entered_by = float(total), source, entered_by
    schedule = db.scalar(select(OutcomeSchedule).where(
        OutcomeSchedule.patient_id == patient_id, OutcomeSchedule.instrument == instrument))
    if schedule is not None and schedule.active and schedule.next_due <= day:
        schedule.next_due = day + timedelta(days=schedule.every_days)
        schedule.task_id = None
    return row


def _function(db: Session, task: AdherenceTask, patient: Patient, answers: dict, ref: dict,
              now: datetime) -> None:
    scores: dict[int, int] = {}
    for key, value in answers.items():
        if key.startswith("goal_") and _int(key[5:]) is not None and _int(value) is not None:
            scores[int(key[5:])] = int(value)
    rate_goals(db, patient.id, scores, now.date())


def _outcome(db: Session, task: AdherenceTask, patient: Patient, answers: dict, ref: dict,
             now: datetime) -> None:
    instrument = str(ref.get("instrument") or "")
    if instrument not in INSTRUMENTS:
        return
    if instrument == "psfs":
        _function(db, task, patient, answers, ref, now)
        return
    value = _int(answers.get("pain" if instrument == "nprs" else "total"))
    if value is None:
        return
    put_score(db, patient.id, instrument, value, now.date(), source="patient", entered_by=None)


def _hold(db: Session, task: AdherenceTask, patient: Patient, answers: dict, ref: dict,
          now: datetime) -> None:
    kind = str(ref.get("kind") or "")
    seconds = _int(answers.get("seconds"))
    if kind not in measures.HOLDS or seconds is None:
        return
    label, unit, sided, _who = measures.KINDS[kind]
    side = str(answers.get("side") or "").lower()
    db.add(Measurement(
        patient_id=patient.id, hospital_id=patient.hospital_id, tested_on=now.date(), kind=kind,
        label=label, side=side if sided and side in ("left", "right") else "na",
        value=float(seconds), unit=unit, source="patient", entered_by=None,
    ))


def _handoff(db: Session, task: AdherenceTask, patient: Patient, answers: dict, ref: dict,
             now: datetime) -> None:
    from app.pt.service import activate_handoff

    row = db.get(Handoff, _int(ref.get("handoff_id")) or 0)
    if row is None or row.patient_id != patient.id or row.status != "awaiting":
        return
    who = row.trainer_name.strip() or "the trainer"
    if str(answers.get("share") or "").lower() == "yes":
        activate_handoff(db, row, now)
        _notify(db, patient, f"Agreed to share training limits with {who}",
                "The page is live: copy its link from the chart.")
    else:
        row.status = "declined"
        row.updated_at = now
        _notify(db, patient, f"Declined to share training limits with {who}",
                "Nothing was shared.")


_FILERS = {
    asks.MORNING: _morning, asks.WEEK: _week, asks.NEW_AREA: _new_area, asks.GOALS: _goals,
    asks.FUNCTION: _function, asks.OUTCOME: _outcome, asks.HOLD: _hold, asks.HANDOFF: _handoff,
}


def record_task_answers(db: Session, task: AdherenceTask, patient: Patient,
                        answers: dict[str, Any], now: datetime, via: str) -> None:
    payload = task.payload if isinstance(task.payload, dict) else {}
    filer = _FILERS.get(str(payload.get("qset")))
    if filer is None:
        return
    ref = payload.get("pt") if isinstance(payload.get("pt"), dict) else {}
    filer(db, task, patient, answers, ref, now)
    # Asked once, answered once: the ask is not a standing part of the plan.
    task.active = False


def after_checkin(db: Session, patient: Patient, answers: dict[str, Any]) -> None:
    """A check-in that says there is a new pain is followed by the ask that
    finds out where. Only for a person on a clinic's own program; anyone
    else's "yes" stays the alert it already was."""
    from app.engine.care.pathways import clinic_program

    if str(answers.get("new_pain") or "").lower() != "yes" or clinic_program(patient) is None:
        return
    try:
        asks.ask(
            db, patient, qset=asks.NEW_AREA, title="Where is the new pain?",
            why="You said there's a pain that wasn't there at your last visit.",
            questions=asks.new_area_questions(),
        )
    except Exception:  # noqa: BLE001 - the check-in itself must still be recorded
        logger.exception("could not ask %s where the new pain is", patient.id)
