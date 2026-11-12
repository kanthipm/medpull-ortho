"""The morning run that texts each lifter today's plan.

Off unless a deployment asks for it (``EXERCISE_REMINDERS``); the console's
"Text today's plan" works either way. The schedule that calls ``run`` fires
every hour (EventBridge speaks UTC and knows nothing of the clinic's time
zone), and the run itself acts only in the hour the deployment names
(``EXERCISE_REMINDER_HOUR``, read in the functions' own time zone).

A chart is texted at most once a day: its ``exercise_reminded_on`` is
stamped before the send, so a run that is retried, or fires twice inside
the hour, finds it done. Charts with nothing open today, no real number, or
a STOP on file are passed over (``texts.cannot_text``).
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.hep import texts
from app.hep.models import ExerciseAssignment
from app.models.patient import Patient
from app.personal.scope import clinic_filter

logger = logging.getLogger(__name__)

# One run stays well inside the write lock: each send is a single bounded
# attempt, and a roster longer than this is finished by the next firing in
# the same hour (the stamp says who is left).
MAX_PER_RUN = 12


def run(db: Session, now: datetime | None = None, *, force: bool = False) -> dict:
    """Text today's plan to every clinic chart that has something open today
    and has not been texted it yet. ``force`` skips the two switches (the
    setting and the hour) for an operator's run by hand. Returns what it did."""
    now = now or datetime.now()
    if not force:
        if not settings.exercise_reminders:
            return {"ran": False, "reason": "EXERCISE_REMINDERS is off", "texted": 0}
        if now.hour != settings.exercise_reminder_hour:
            return {"ran": False, "reason": "not the reminder hour", "texted": 0}
    today = now.date()
    due = db.scalars(
        clinic_filter(select(Patient))
        .where(
            Patient.phone.is_not(None),
            or_(Patient.exercise_reminded_on.is_(None), Patient.exercise_reminded_on < today),
            Patient.id.in_(
                select(ExerciseAssignment.patient_id).where(
                    ExerciseAssignment.scheduled_for == today,
                    ExerciseAssignment.status == "assigned",
                )
            ),
        )
        .order_by(Patient.id)
    ).all()
    texted = skipped = 0
    for patient in due:
        if texted >= MAX_PER_RUN:
            break
        if texts.cannot_text(patient) is not None:
            skipped += 1
            continue
        patient.exercise_reminded_on = today
        db.commit()
        sent = texts.text_today(db, patient, day=today)
        if sent is not None and sent["sent"]:
            texted += 1
        else:
            skipped += 1
    logger.info("Exercise reminders for %s: %s texted, %s passed over", today, texted, skipped)
    return {"ran": True, "texted": texted, "skipped": skipped, "left": max(0, len(due) - texted - skipped)}
