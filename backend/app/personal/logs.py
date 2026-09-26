"""The subjective log: what a subscriber tells the app that no device can
measure. Written by the personal check-in (through the task completion
hook in ``tasks/service.py``) and by the coach; read by the metrics."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.adherence import AdherenceTask
from app.models.personal import PersonalLog

# Question sets whose answers land here (see tasks/service.QUESTION_SETS).
PERSONAL_QSETS = ("checkin_personal", "checkin_personal_recovery", "workout", "sleep")
LOG_KEYS = ("energy", "soreness", "mood", "sleep_quality", "rpe", "session_minutes", "note")

# Choice answers mapped onto the 0-10 scale the metrics read.
CHOICE_VALUES = {
    "sleep_quality": {"great": 9.0, "ok": 6.0, "rough": 3.0},
    "mood": {"good": 8.0, "flat": 5.0, "low": 2.0},
}


def record(db: Session, patient_id: str, day: date, key: str, value: float | None = None,
           text: str | None = None, source: str = "app") -> PersonalLog:
    """One reading for one day. A second reading the same day for the same
    key replaces the first, so a re-answered check-in does not double."""
    if key not in LOG_KEYS:
        raise ValueError(f"Unknown log key {key!r}")
    row = None
    if key != "note":
        row = db.scalar(
            select(PersonalLog).where(
                PersonalLog.patient_id == patient_id, PersonalLog.date == day,
                PersonalLog.key == key,
            )
        )
    if row is None:
        row = PersonalLog(patient_id=patient_id, date=day, key=key, source=source)
        db.add(row)
    row.value_num = value
    row.text = (text or "")[:1000] or None
    row.source = source
    db.flush()
    return row


def record_task_answers(db: Session, task: AdherenceTask, answers: dict[str, Any],
                        day: date | None = None) -> int:
    """Map a personal task's answers onto the log. Returns rows written."""
    day = day or date.today()
    written = 0
    for qid, raw in answers.items():
        if raw is None or raw == "":
            continue
        key = {"pain": "soreness", "minutes": "session_minutes"}.get(qid, qid)
        if key == "note":
            record(db, task.patient_id, day, "note", text=str(raw), source="checkin")
            written += 1
            continue
        if key not in LOG_KEYS:
            continue
        if key in CHOICE_VALUES:
            value = CHOICE_VALUES[key].get(str(raw).strip().lower())
        else:
            try:
                value = float(raw)
            except (TypeError, ValueError):
                value = None
        if value is None:
            continue
        record(db, task.patient_id, day, key, value=value, source="checkin")
        written += 1
    return written
