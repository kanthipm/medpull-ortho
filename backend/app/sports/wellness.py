"""Writing the morning wellness answers, from the app's sheet, the task
completion hook and the coach. One row per key per day; a second answer
the same day replaces the first."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.adherence import AdherenceTask
from app.models.sports import SportsWellness
from app.sports.catalog.wellness import CYCLE_PHASES, WELLNESS


def record(db: Session, patient_id: str, day: date, key: str, value: float | None = None,
           text: str | None = None, source: str = "app") -> SportsWellness:
    spec = WELLNESS.get(key)
    if spec is None:
        raise ValueError(f"Unknown wellness key {key!r}")
    if spec.kind == "choice" and text is not None and value is None:
        value = CYCLE_PHASES.get(text.strip().lower())
    if spec.kind == "yes_no" and text is not None and value is None:
        value = 1.0 if text.strip().lower() in ("yes", "y", "true", "1") else 0.0
    if spec.kind == "scale" and value is not None:
        value = max(0.0, min(10.0, float(value)))
    row = None
    if spec.kind != "text":
        row = db.scalar(select(SportsWellness).where(SportsWellness.patient_id == patient_id,
                                                     SportsWellness.date == day, SportsWellness.key == key))
    if row is None:
        row = SportsWellness(patient_id=patient_id, date=day, key=key, source=source)
        db.add(row)
    row.value = value
    row.text = (text or "")[:1000] or None
    row.source = source
    db.flush()
    return row


def record_many(db: Session, patient_id: str, day: date, answers: dict[str, Any], source: str = "app") -> int:
    written = 0
    for key, raw in answers.items():
        if key not in WELLNESS or raw is None or raw == "":
            continue
        spec = WELLNESS[key]
        if spec.kind == "text":
            record(db, patient_id, day, key, text=str(raw), source=source)
        elif spec.kind in ("choice", "yes_no") and isinstance(raw, str):
            record(db, patient_id, day, key, text=raw, source=source)
        else:
            try:
                record(db, patient_id, day, key, value=float(raw), source=source)
            except (TypeError, ValueError):
                continue
        written += 1
    return written


def record_task_answers(db: Session, task: AdherenceTask, answers: dict[str, Any], day: date | None = None) -> int:
    return record_many(db, task.patient_id, day or date.today(), answers, source="checkin")
