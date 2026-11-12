"""The five lifters' between-visits record (app/pt), for the demo.

Everything here follows the five stories ``app/seed/hirt.py`` already tells
and adds no check-in to any of them, so the tiers the demo is pitched on do
not move: Cole went back to his old leg day and it shows the morning after;
Tessa is ready to move on and waits for her therapist to say so; Devon's
back program is what gets dropped on long shifts; June is steady and about
to share her limits with a trainer; Rafael came in through a free screen
and went quiet.

Two things here are examples, and are named as examples where a clinician
reads them: the protocols (a clinic writes its own phases and criteria; the
shape follows the staged loading programs in the tendinopathy literature)
and the people (the trainer is as fictional as the lifters).

``ensure_clinic`` writes what the clinic itself keeps (its settings and the
example protocols); ``write`` writes one lifter. Both are called by the
fill after the lifter's history and calendar exist, and a refill clears a
lifter's rows first (``demo_fill.PER_PATIENT_TABLES``).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.seed.hirt import HOSPITAL_ID, PROGRAM_DAYS

EXAMPLE = " (example)"

PROTOCOLS: tuple[dict[str, Any], ...] = (
    {
        "key": "tendon",
        "name": "Tendon · progressive loading" + EXAMPLE,
        "description": "An example to edit: the clinic's own phases and criteria go here.",
        "phases": [
            {"name": "Isometric loading", "goal": "Settle it: holds the tendon tolerates.",
             "criteria": ["Pain 3/10 or less during the holds",
                          "Settled by the next morning, three sessions running"]},
            {"name": "Isotonic loading", "goal": "Build strength through range, slowly.",
             "criteria": ["Pain 3/10 or less during loaded work",
                          "Settled by the next morning, three sessions running",
                          "The working load from the plan, for all sets"]},
            {"name": "Energy storage", "goal": "Bring back the spring: jumps and landings.",
             "criteria": ["Pain 3/10 or less on the test movement",
                          "Settled by the next morning after each storage session"]},
            {"name": "Back to the sport", "goal": "The sport's own loads, built back in.",
             "criteria": ["A full training week with no flare"]},
        ],
    },
    {
        "key": "back",
        "name": "Low back · return to lifting" + EXAMPLE,
        "description": "An example to edit: the clinic's own phases and criteria go here.",
        "phases": [
            {"name": "Calm and move", "goal": "Daily movement that does not provoke it.",
             "criteria": ["The home program on five days of seven",
                          "Morning stiffness under 30 minutes"]},
            {"name": "Build the hinge", "goal": "Load the pattern, light and often.",
             "criteria": ["Hinge to the knee with no symptom change",
                          "Settled by the next morning, three sessions running"]},
            {"name": "Back under the bar", "goal": "The lifts themselves, built back in.",
             "criteria": ["A full training week with no flare"]},
        ],
    },
)


@dataclass(frozen=True)
class Between:
    """One lifter's record. Days are program days (0 is the evaluation, 14
    is today); ``visits`` may run past today."""

    areas: tuple[tuple[str, str | None], ...] = ()
    visits: tuple[tuple[int, str, str | None, str], ...] = ()   # day, kind, at, note
    rest_days: tuple[int, ...] = ()                              # weekdays (Monday is 0)
    rest_note: str = ""                                          # what the day's mark says
    protocol: str | None = None
    phase: int = 0                                               # index of the current phase
    met: tuple[int, ...] = ()                                    # criteria ticked in it
    goals: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = ()   # text, (day, score)...
    mornings: tuple[tuple[int, int, bool], ...] = ()             # session day, pain, stiffer
    morning_open: int | None = None                              # a session day asked, unanswered
    week: tuple[str, str] | None = None                          # last week's word: went, note
    week_unanswered: bool = False
    tests: tuple[tuple[int, str, str, float, str | None], ...] = ()   # day, kind, side, value, label
    scores: tuple[tuple[str, tuple[tuple[int, float], ...]], ...] = ()
    schedules: tuple[tuple[str, int], ...] = ()                  # instrument, every days
    handoff: dict[str, Any] | None = None
    question: tuple[str, int] | None = None                      # a typed question, hours ago
    flags: tuple[tuple[str, int], ...] = ()                      # code, how many days up before today
    settings: dict[str, Any] = field(default_factory=dict)


TRAINER = "Mara Ellis"

RECORDS: dict[str, Between] = {
    "hirt-cole": Between(
        areas=(("knee", "left"),),
        visits=((0, "evaluation", "09:00", ""), (7, "visit", "09:00", ""),
                (16, "test_day", "09:30", "Bring lifting shoes.")),
        # Sunday carries only his heel slides: a rest from the loaded work,
        # and the mark says so.
        rest_days=(6,), rest_note="No loaded work today. Heel slides only.",
        protocol="tendon", phase=1, met=(2,),
        goals=(
            ("Squat 315 for reps without the knee talking", ((0, 4), (7, 5), (13, 4))),
            ("Take stairs down without thinking about it", ((0, 5), (7, 6), (13, 3))),
            ("Play pickup basketball on Sundays", ((0, 2), (7, 3), (13, 3))),
        ),
        # Settled while he kept to the plan; not since he went back to his
        # old leg day (program day 8 on).
        mornings=((0, 2, False), (2, 2, False), (4, 2, False), (7, 3, False), (9, 4, True),
                  (11, 5, True)),
        week=("better", "Knee felt good, so I'm going back to my normal leg day."),
        tests=((0, "isometric_knee_extension", "left", 388, None),
               (0, "isometric_knee_extension", "right", 472, None),
               (7, "isometric_knee_extension", "left", 421, None),
               (7, "isometric_knee_extension", "right", 476, None),
               (0, "custom", "na", 5, "Decline squat pain"),
               (7, "custom", "na", 3, "Decline squat pain")),
        scores=(("visa_p", ((0, 48), (7, 57))), ("nprs", ((0, 3), (7, 2), (13, 6)))),
        schedules=(("visa_p", 14), ("nprs", 7)),
        handoff={
            "status": "active", "limits": [
                "No jumping, bounding or sprint work yet",
                "Squats and leg press to a box: top half only",
                "Loads at or under what is on the calendar, not above",
            ],
            "report_back": "Any session where the knee is worse the next morning.",
        },
        question=("Knee is still talking on the stairs tonight. Do I still squat tomorrow?", 9),
        flags=(("LOAD_SPIKE", 3), ("PAIN_RISING", 2)),
    ),
    "hirt-tessa": Between(
        areas=(("achilles", "right"),),
        visits=((0, "evaluation", "07:30", ""), (7, "visit", "07:30", ""), (19, "visit", "07:30", "")),
        protocol="tendon", phase=1, met=(0, 1, 2),
        goals=(
            ("Run 5k without the heel barking the next morning", ((0, 3), (7, 5), (13, 6))),
            ("Jump rope for my warm-up", ((0, 2), (7, 4), (13, 5))),
        ),
        mornings=((1, 2, False), (3, 2, False), (5, 1, False), (8, 1, False), (10, 1, False),
                  (12, 0, False)),
        week=("better", "Nothing different."),
        tests=((0, "calf_raise_reps", "left", 24, None), (0, "calf_raise_reps", "right", 15, None),
               (7, "calf_raise_reps", "left", 25, None), (7, "calf_raise_reps", "right", 20, None)),
        scores=(("visa_a", ((0, 58), (13, 70))),),
        schedules=(("visa_a", 14),),
    ),
    "hirt-devon": Between(
        areas=(("low back", None),),
        visits=((0, "evaluation", "17:30", ""), (15, "visit", "17:30", "")),
        protocol="back", phase=0, met=(),
        goals=(
            ("Deadlift 405 again", ((0, 5), (7, 5))),
            ("Sit through a work day without stiffening up", ((0, 4), (7, 4))),
        ),
        week=("same", "Long shifts all week. The back program is what gets dropped."),
        scores=(("odi", ((0, 24), (7, 22))),),
        schedules=(("odi", 14),),
        question=("Can I swap bird dog for dead bug on the days I lift?", 20),
        flags=(("PROGRAM_SLIPPING", 4),),
    ),
    "hirt-june": Between(
        areas=(("low back", None),),
        visits=((0, "evaluation", "11:00", ""), (7, "visit", "11:00", ""), (15, "visit", "11:00", "")),
        # No rest day: her program is on every day of the week.
        protocol="back", phase=1, met=(0,),
        goals=(
            ("Deadlift my bodyweight again", ((0, 4), (7, 6), (13, 7))),
            ("Garden for an hour without paying for it", ((0, 5), (7, 7), (13, 8))),
        ),
        week=("better", "Nothing different. Same days."),
        tests=((0, "back_extension_hold", "na", 48, None), (7, "back_extension_hold", "na", 71, None),
               (13, "back_extension_hold", "na", 96, None),
               (0, "plank_hold", "na", 55, None), (13, "plank_hold", "na", 90, None)),
        scores=(("odi", ((0, 32), (13, 20))),),
        schedules=(("odi", 14),),
        handoff={
            "status": "awaiting", "limits": [
                "Hinge work from blocks: nothing from the floor yet",
                "No loaded flexion: no sit-ups, no toes-to-bar",
            ],
            "report_back": "Leg symptoms during or after a session, the same day.",
        },
        question=("Is it fine to do the bridges before work instead of after?", 30),
    ),
    "hirt-rafael": Between(
        areas=(("shoulder", "right"),),
        visits=((0, "evaluation", "12:00", "Free screen."),),
        goals=(("Press overhead without the pinch", ((0, 4),)),),
        week_unanswered=True,
        scores=(("quickdash", ((0, 30),)),),
        flags=(("WENT_QUIET", 1),),
    ),
}

# What the clinic itself has set: both asks on, on the product's defaults.
CLINIC_SETTINGS = {"morning_check": {"on": True, "ceiling": 3}, "week_checkin": {"on": True}}


def _day(today: date, program_day: int) -> date:
    return today - timedelta(days=PROGRAM_DAYS - program_day)


def ensure_clinic(db: Session) -> dict[str, int]:
    """The clinic's settings and its example protocols, written once. A
    protocol a clinician has since renamed or rewritten is left as it is."""
    from app.pt.models import ClinicSetting, Protocol

    added = {"settings": 0, "protocols": 0}
    if db.get(ClinicSetting, HOSPITAL_ID) is None:
        db.add(ClinicSetting(hospital_id=HOSPITAL_ID, data=dict(CLINIC_SETTINGS),
                             updated_by="ct_harris"))
        added["settings"] = 1
    have = set(db.scalars(select(Protocol.name).where(Protocol.hospital_id == HOSPITAL_ID)))
    for spec in PROTOCOLS:
        if spec["name"] in have:
            continue
        db.add(Protocol(hospital_id=HOSPITAL_ID, name=spec["name"], description=spec["description"],
                        phases=spec["phases"], created_by="ct_harris"))
        added["protocols"] += 1
    db.commit()
    return added


def _protocol(db: Session, key: str):
    from app.pt.models import Protocol

    name = next(p["name"] for p in PROTOCOLS if p["key"] == key)
    return db.scalar(select(Protocol).where(Protocol.hospital_id == HOSPITAL_ID,
                                            Protocol.name == name))


def write(db: Session, patient_id: str, today: date) -> dict[str, int]:
    """One lifter's between-visits record, anchored to ``today``. Expects the
    lifter's rows to have been cleared (a refill) or never written."""
    from app.models.mobile import Message
    from app.models.patient import Patient
    from app.pt import regions, triage
    from app.pt import settings as pt_settings
    from app.pt.models import (
        CalendarMark,
        ClinicVisit,
        FlagEvent,
        FunctionGoal,
        FunctionRating,
        Handoff,
        Measurement,
        MorningCheck,
        OutcomeSchedule,
        OutcomeScore,
        PainArea,
        PatientPhase,
        WeekCheckin,
    )
    from app.pt import measures

    record = RECORDS.get(patient_id)
    counts: dict[str, int] = {}
    if record is None:
        return counts
    patient = db.get(Patient, patient_id)
    by = patient.assigned_provider_id or "ct_gregg"
    monday = today - timedelta(days=today.weekday())

    for area, side in record.areas:
        db.add(PainArea(patient_id=patient_id, region=regions.make(area, side),
                        source="evaluation", noted_on=_day(today, 0), created_by=by))
    for program_day, kind, at, note in record.visits:
        db.add(ClinicVisit(hospital_id=HOSPITAL_ID, patient_id=patient_id,
                           visit_on=_day(today, program_day), at=at, kind=kind, note=note,
                           created_by=by))
    for ahead in range(-PROGRAM_DAYS, 22):
        day = today + timedelta(days=ahead)
        if day.weekday() in record.rest_days:
            db.add(CalendarMark(hospital_id=HOSPITAL_ID, patient_id=patient_id, day=day,
                                kind="rest", note=record.rest_note, created_by=by))
    counts["visits"] = len(record.visits)

    if record.protocol is not None:
        protocol = _protocol(db, record.protocol)
        if protocol is not None:
            for position, phase in enumerate(protocol.phases):
                status = ("done" if position < record.phase
                          else "current" if position == record.phase else "upcoming")
                ticked = (set(range(len(phase["criteria"]))) if status == "done"
                          else set(record.met) if status == "current" else set())
                when = datetime.combine(_day(today, 7), time(9, 40))
                db.add(PatientPhase(
                    patient_id=patient_id, hospital_id=HOSPITAL_ID, protocol_id=protocol.id,
                    protocol_name=protocol.name, position=position, name=phase["name"],
                    goal=phase["goal"], status=status,
                    criteria=[{"text": c, "met": i in ticked,
                               "met_at": when.isoformat() if i in ticked else None,
                               "met_by": by if i in ticked else None}
                              for i, c in enumerate(phase["criteria"])],
                    started_on=(_day(today, 0) if position == 0 and status != "upcoming"
                                else _day(today, 7) if status == "current" else None),
                    ended_on=_day(today, 7) if status == "done" else None,
                    advanced_by=by if status == "done" else None,
                ))
            counts["phases"] = len(protocol.phases)

    for position, (text, ratings) in enumerate(record.goals):
        goal = FunctionGoal(patient_id=patient_id, text=text, position=position,
                            created_by="patient",
                            created_at=datetime.combine(_day(today, 0), time(10, 0)))
        db.add(goal)
        db.flush()
        for program_day, score in ratings:
            db.add(FunctionRating(goal_id=goal.id, patient_id=patient_id,
                                  rated_on=_day(today, program_day), score=score,
                                  source="clinic" if program_day in (0, 7) else "patient"))
    # The functional scale's score on each day every goal was rated.
    rated_days = sorted({d for _text, ratings in record.goals for d, _s in ratings})
    for program_day in rated_days:
        scores = [s for _text, ratings in record.goals for d, s in ratings if d == program_day]
        db.add(OutcomeScore(patient_id=patient_id, instrument="psfs",
                            scored_on=_day(today, program_day),
                            total=round(sum(scores) / len(scores), 1),
                            source="clinic" if program_day in (0, 7) else "patient"))
    counts["goals"] = len(record.goals)

    ceiling = pt_settings.patient_read(db, patient_id, HOSPITAL_ID)["morning_check"]["ceiling"]
    for program_day, pain, stiffer in record.mornings:
        session_day = _day(today, program_day)
        asked = datetime.combine(session_day + timedelta(days=1), time(8, 0))
        db.add(MorningCheck(
            patient_id=patient_id, session_day=session_day, asked_at=asked,
            answered_at=asked + timedelta(minutes=35), pain=pain, stiffer=stiffer,
            ceiling=ceiling, settled=pain <= ceiling and not stiffer))
    if record.morning_open is not None:
        session_day = _day(today, record.morning_open)
        db.add(MorningCheck(patient_id=patient_id, session_day=session_day, ceiling=ceiling,
                            asked_at=datetime.combine(session_day + timedelta(days=1), time(8, 0))))
    counts["mornings"] = len(record.mornings)

    last_week = monday - timedelta(days=7)
    friday = datetime.combine(last_week + timedelta(days=4), time(16, 0))
    if record.week is not None:
        db.add(WeekCheckin(patient_id=patient_id, week_start=last_week, asked_at=friday,
                           answered_at=friday + timedelta(hours=3), went=record.week[0],
                           change_note=record.week[1]))
    elif record.week_unanswered:
        db.add(WeekCheckin(patient_id=patient_id, week_start=last_week, asked_at=friday))

    for program_day, kind, side, value, label in record.tests:
        kind_label, unit, _sided, who = measures.KINDS[kind]
        db.add(Measurement(
            patient_id=patient_id, hospital_id=HOSPITAL_ID, tested_on=_day(today, program_day),
            kind=kind, label=label or kind_label, side=side, value=float(value),
            unit="/10" if kind == "custom" else unit,
            source="patient" if who == "patient" and program_day not in (0, 7) else "clinic",
            entered_by=by if (who == "clinic" or program_day in (0, 7)) else None))
    counts["tests"] = len(record.tests)

    for instrument, scores in record.scores:
        for program_day, total in scores:
            db.add(OutcomeScore(patient_id=patient_id, instrument=instrument,
                                scored_on=_day(today, program_day), total=float(total),
                                source="clinic", entered_by=by))
    for instrument, every in record.schedules:
        last = max((d for key, scores in record.scores if key == instrument for d, _t in scores),
                   default=0)
        db.add(OutcomeSchedule(patient_id=patient_id, instrument=instrument, every_days=every,
                               next_due=_day(today, last) + timedelta(days=every), created_by=by))

    if record.handoff is not None:
        status = record.handoff["status"]
        written = datetime.combine(_day(today, 7), time(10, 15))
        handoff = Handoff(
            patient_id=patient_id, hospital_id=HOSPITAL_ID, trainer_name=TRAINER,
            limits=list(record.handoff["limits"]), report_back=record.handoff["report_back"],
            include_week=True, status=status, created_by=by, created_at=written,
            updated_at=written, requested_at=written + timedelta(minutes=5),
            authorised_at=written + timedelta(hours=2) if status == "active" else None,
            # A link for the demo that survives a refill would have to be a
            # known string; a fresh secret each morning is the honest shape.
            token=secrets.token_urlsafe(18) if status == "active" else None,
        )
        db.add(handoff)
        if status == "awaiting":
            # Waiting on the person means the question is in their tasks: the
            # same ask the console's button makes, written without a text.
            from app.pt import asks

            db.flush()
            task, _outcome = asks.ask(
                db, patient, qset=asks.HANDOFF, title="Share your training limits?",
                why="Your therapist wrote a short page for your trainer. "
                    "It goes nowhere unless you say yes.",
                questions=asks.handoff_questions(handoff), ref={"handoff_id": handoff.id},
                notify=False, created_by=by,
            )
            handoff.task_id = task.id

    if record.question is not None:
        text, hours_ago = record.question
        at = datetime.combine(today, time(7, 0)) - timedelta(hours=hours_ago)
        message = Message(patient_id=patient_id, sender="patient", channel="app", text=text,
                          created_at=at)
        where = triage.classify(text, list(pt_settings.DEFAULTS["triage_words"]))
        message.triage, message.triage_by, message.triage_at = where, "rule", at
        db.add(message)

    for code, days_up in record.flags:
        for back in range(1, days_up + 1):
            db.add(FlagEvent(hospital_id=HOSPITAL_ID, patient_id=patient_id, code=code,
                             day=today - timedelta(days=back)))
    db.commit()
    return counts
