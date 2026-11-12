"""What a text can command without the assistant reading it: stopping and
resuming texts, and marking today's exercises done.

``app/tasks/service.handle_inbound_sms`` asks here before a text goes to the
assistant. ``handle`` answers with the reply to send and what it was, or
None when the text is not one of these and the normal routing carries on.

* ``STOP`` (also UNSUBSCRIBE, STOP ALL) stops every text to the number
  except the answer to this one, START and HELP, and a sign-in code the
  person asks for; ``START`` resumes; ``HELP`` says who this is and how to
  stop. The send path honours the stop for every kind of text
  (``sendblue.send_sms``).
* ``DONE`` marks today's open exercises done from a text, for the lifter who
  would rather reply than open anything. With a number ("done 3") that is
  the pain afterwards; without one the reply asks for it, and a bare 0 to 10
  inside the next two hours is the answer. An exercise the therapist asked a
  clip or a watch for cannot be closed by text: it stays open and the reply
  carries the link to it.

Nothing here judges a number. The pain score is recorded as given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import links
from app.config import settings
from app.hep.models import Exercise, ExerciseAssignment
from app.models.patient import Patient

STOP_ALWAYS = {"unsubscribe", "stop all", "stopall", "end texts"}
STOP = "stop"
START = {"start texts", "unstop", "resume"}
HELP = {"help", "info"}

# How long a "How was the pain after?" waits for its number.
PAIN_ANSWER_WINDOW = timedelta(hours=2)

_DONE = re.compile(
    r"^(?:i(?:\s+am|'m|’m)?\s+)?(?:all\s+)?(?:done|did\s+it|did\s+them|finished|complete|completed)"
    r"(?:\s+(?:it|them|today|with\s+it))?[\s,.:!-]*(?:pain\s*)?(?:(\d{1,2})(?:\s*/\s*10)?)?[\s.!]*$",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"^(\d{1,2})(?:\s*/\s*10)?[\s.!]*$")


@dataclass(frozen=True)
class Command:
    reply: str
    kind: str
    # The answer to STOP, START and HELP goes out even to a number that has
    # opted out: it is the reply the person just asked for.
    even_if_opted_out: bool = False


def is_stop(lowered: str, *, in_conversation: bool) -> bool:
    """Whether a text stops all texts. A bare "stop" in the middle of a
    question-by-text conversation ends that conversation instead (the task
    flow's own word, ``tasks.service.STOP_WORDS``); said again, or said
    outside one, it stops everything. The unmistakable forms always do."""
    if lowered in STOP_ALWAYS:
        return True
    return lowered == STOP and not in_conversation


def _clinic_name(db: Session, patient: Patient) -> str:
    from app.models.hospital import Hospital

    hospital = db.get(Hospital, patient.hospital_id) if patient.hospital_id else None
    return hospital.name if hospital is not None else "your care team"


def _stop(db: Session, patient: Patient) -> Command:
    for row in db.scalars(select(Patient).where(Patient.phone == patient.phone)).all():
        row.sms_opt_out_at = datetime.now()
        row.sms_done_asked_at = None
    db.flush()
    return Command(
        "You won't get any more texts from MedPull at this number. Reply START to turn them "
        "back on.",
        "opted_out", even_if_opted_out=True,
    )


def _start(db: Session, patient: Patient) -> Command | None:
    rows = db.scalars(select(Patient).where(Patient.phone == patient.phone)).all()
    if not any(row.sms_opt_out_at is not None for row in rows):
        return None  # nothing to resume: "start" keeps its task meaning
    for row in rows:
        row.sms_opt_out_at = None
    db.flush()
    return Command("Texts from MedPull are back on for this number. Reply STOP to turn them off.",
                   "opted_in", even_if_opted_out=True)


def _help(db: Session, patient: Patient) -> Command:
    return Command(
        f"This is MedPull, texting for {_clinic_name(db, patient)}: check-ins, your exercise "
        "plan and replies from your care team. Reply STOP to turn these texts off. For "
        "anything urgent, call the clinic.",
        "help", even_if_opted_out=True,
    )


def _open_today(db: Session, patient: Patient, today: date) -> list[ExerciseAssignment]:
    return list(db.scalars(
        select(ExerciseAssignment)
        .where(ExerciseAssignment.patient_id == patient.id,
               ExerciseAssignment.scheduled_for == today,
               ExerciseAssignment.status == "assigned")
        .order_by(ExerciseAssignment.sort_order, ExerciseAssignment.id)
    ).all())


def _title(db: Session, row: ExerciseAssignment) -> str:
    exercise = db.get(Exercise, row.exercise_id)
    return exercise.title if exercise is not None else "the exercise"


def _needs_the_app(row: ExerciseAssignment) -> str | None:
    """Why a row cannot be closed by text, in the lifter's words."""
    if row.video_requirement == "required":
        return "needs a clip of your attempt"
    if row.wearable_requirement == "required":
        return "is done with your watch on"
    return None


def _counted(n: int) -> str:
    return "1 exercise" if n == 1 else f"{n} exercises"


def _mark_done(db: Session, patient: Patient, pain: int | None, base_url: str,
               today: date) -> Command:
    """Close what a text can close among today's open rows and say what is
    left. Each row is completed through the calendar's own function, so the
    record is the same as a tap in the app with the source ``sms``."""
    from app.hep import schedule

    patient.sms_done_asked_at = None
    rows = _open_today(db, patient, today)
    if not rows:
        any_today = db.scalar(
            select(ExerciseAssignment.id)
            .where(ExerciseAssignment.patient_id == patient.id,
                   ExerciseAssignment.scheduled_for == today).limit(1)
        )
        db.flush()
        if any_today is None:
            return Command("Nothing is assigned today. Rest is part of the program.",
                           "exercise_none")
        return Command("Today's plan is already marked done.", "exercise_none")

    closable = [r for r in rows if _needs_the_app(r) is None]
    held = [r for r in rows if _needs_the_app(r) is not None]
    for row in closable:
        schedule.complete_assignment(db, row, pain_after=pain, note="", source="sms")

    parts: list[str] = []
    if closable:
        marked = f"Marked {_counted(len(closable))} done"
        marked += f", pain {pain} after." if pain is not None else "."
        parts.append(marked)
    if held:
        first = held[0]
        _link, token = links.mint_link(db, patient, "exercise", ref_id=first.id, day=today)
        url = links.text_url(token, base_url or None)
        left = f"{_title(db, first)} {_needs_the_app(first)}"
        if len(held) > 1:
            left += f" ({len(held) - 1} more like it)"
        parts.append(f"{left}. Open it here: {url}")
    db.flush()
    return Command(" ".join(parts), "exercise_done" if closable else "exercise_needs_app")


def handle(db: Session, patient: Patient, body: str, *, base_url: str = "",
           in_conversation: bool = False, now: datetime | None = None) -> Command | None:
    """The command a text is, or None. ``in_conversation`` says the person
    is answering a question-by-text task, whose own words win over DONE and
    a bare number."""
    now = now or datetime.now()
    lowered = " ".join(body.lower().split()).strip(" .!")
    if is_stop(lowered, in_conversation=in_conversation):
        return _stop(db, patient)
    if in_conversation:
        # Every other word here could be the answer to the question in hand.
        return None
    if lowered in START or (lowered == "start" and patient.sms_opt_out_at is not None):
        return _start(db, patient)
    if lowered in HELP:
        return _help(db, patient)
    if not settings.hep_enabled:
        return None

    today = now.date()
    asked = patient.sms_done_asked_at
    answer = _NUMBER.match(body.strip())
    if answer and asked is not None and now - asked <= PAIN_ANSWER_WINDOW:
        pain = int(answer.group(1))
        if 0 <= pain <= 10:
            return _mark_done(db, patient, pain, base_url, today)
    done = _DONE.match(body.strip())
    if done is None:
        return None
    if done.group(1) is not None:
        pain = int(done.group(1))
        if not 0 <= pain <= 10:
            return Command("Pain is a number from 0 to 10. Reply DONE with it, like: done 3",
                           "exercise_pain_asked")
        return _mark_done(db, patient, pain, base_url, today)
    rows = _open_today(db, patient, today)
    if rows and any(_needs_the_app(r) is None for r in rows):
        patient.sms_done_asked_at = now
        db.flush()
        return Command("Good. How was the pain after, 0 to 10?", "exercise_pain_asked")
    return _mark_done(db, patient, None, base_url, today)
