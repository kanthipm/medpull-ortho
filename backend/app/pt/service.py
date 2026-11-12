"""The between-visits record: what a chart keeps, and what changes it.

Reads return plain dicts for the API; writes take a session, do one thing,
commit, and raise ``PtError`` with a sentence for the person at the screen
when they are asked for something that cannot be. See the package docstring
for the rules that hold across all of it.
"""

from __future__ import annotations

import secrets
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.hep.models import Exercise, ExerciseAssignment
from app.hep.service import load_text, load_unit_of
from app.models.attachment import Attachment
from app.models.hospital import Hospital
from app.models.patient import CareTeamMember, Patient
from app.pt import asks, measures, regions
from app.pt import settings as pt_settings
from app.pt.instruments import INSTRUMENTS, change_read, describe
from app.pt.intake import active_goals, put_score, rate_goals
from app.pt.models import (
    CalendarMark,
    ClinicVisit,
    ClipComment,
    FunctionGoal,
    FunctionRating,
    Handoff,
    Measurement,
    MorningCheck,
    OutcomeSchedule,
    OutcomeScore,
    PainArea,
    PatientPhase,
    Protocol,
    WeekCheckin,
)

TEXT_LIMIT = 400
NAME_LIMIT = 120
MAX_PHASES = 8
MAX_CRITERIA = 10
MAX_LIMITS = 12
VISIT_KINDS = ("visit", "evaluation", "test_day")
VISIT_LABELS = {"visit": "Visit", "evaluation": "Evaluation", "test_day": "Test day"}
MARK_KINDS = ("rest",)
OUTCOME_MIN_DAYS, OUTCOME_MAX_DAYS = 1, 180


class PtError(ValueError):
    """Something asked for that cannot be; the message is for the screen."""


def _text(value: Any, limit: int = TEXT_LIMIT) -> str:
    return " ".join(str(value or "").split())[:limit]


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _member(db: Session, member_id: str | None) -> CareTeamMember | None:
    return db.get(CareTeamMember, member_id) if member_id else None


def member_name(db: Session, member_id: str | None) -> str | None:
    member = _member(db, member_id)
    return member.name if member is not None else None


def _first_name(patient: Patient) -> str:
    return (patient.name or patient.id).split()[0]


# --- pain areas ------------------------------------------------------------------------


def sync_seen(db: Session, patient_id: str, today: date) -> None:
    """An area the person named before their latest visit has been seen at
    it: it stops being new. The caller commits."""
    latest = db.scalar(
        select(ClinicVisit.visit_on).where(
            ClinicVisit.patient_id == patient_id, ClinicVisit.visit_on <= today,
        ).order_by(ClinicVisit.visit_on.desc()).limit(1)
    )
    if latest is None:
        return
    for row in db.scalars(select(PainArea).where(
        PainArea.patient_id == patient_id, PainArea.source == "reported",
        PainArea.seen_on.is_(None), PainArea.noted_on < latest,
    )):
        row.seen_on = latest


def areas_view(db: Session, patient_id: str) -> dict[str, Any]:
    rows = db.scalars(
        select(PainArea).where(PainArea.patient_id == patient_id).order_by(PainArea.noted_on, PainArea.id)
    ).all()
    known = [r.region for r in rows if r.source == "evaluation" or r.seen_on is not None]

    def view(r: PainArea) -> dict[str, Any]:
        return {
            "id": r.id, "region": r.region, "label": regions.label(r.region),
            "source": r.source, "noted_on": _iso(r.noted_on), "note": r.note or "",
            "seen_on": _iso(r.seen_on),
            "new": r.source == "reported" and r.seen_on is None and regions.is_new(r.region, known),
        }

    return {
        "evaluation": [view(r) for r in rows if r.source == "evaluation"],
        "reported": [view(r) for r in rows if r.source == "reported"],
        "areas": list(regions.AREAS), "midline": sorted(regions.MIDLINE),
    }


def add_area(db: Session, patient: Patient, *, area: str, side: str | None, source: str,
             note: str | None, by: str | None, today: date) -> PainArea:
    if source not in ("evaluation", "reported"):
        raise PtError("An area is from the evaluation, or reported since")
    try:
        region = regions.make(area, side)
    except ValueError as err:
        raise PtError(str(err)) from err
    row = db.scalar(select(PainArea).where(
        PainArea.patient_id == patient.id, PainArea.region == region))
    if row is not None:
        if row.source == "reported" and source == "evaluation":
            # The therapist is putting on file an area the person named.
            row.source, row.seen_on = "evaluation", None
        row.note = _text(note, 300) or row.note
    else:
        row = PainArea(patient_id=patient.id, region=region, source=source, noted_on=today,
                       note=_text(note, 300) or None, created_by=by)
        db.add(row)
    db.commit()
    return row


def _area(db: Session, patient: Patient, area_id: int) -> PainArea:
    row = db.get(PainArea, area_id)
    if row is None or row.patient_id != patient.id:
        raise PtError("Unknown area")
    return row


def mark_area_seen(db: Session, patient: Patient, area_id: int, today: date) -> PainArea:
    row = _area(db, patient, area_id)
    row.seen_on = today
    db.commit()
    return row


def remove_area(db: Session, patient: Patient, area_id: int) -> None:
    db.delete(_area(db, patient, area_id))
    db.commit()


# --- the morning after -----------------------------------------------------------------


def loaded_day(db: Session, patient_id: str, day: date) -> bool:
    """Whether the person did a loaded exercise that day: one the therapist
    wrote a load for, or one they reported a load on."""
    rows = db.scalars(select(ExerciseAssignment).where(
        ExerciseAssignment.patient_id == patient_id, ExerciseAssignment.scheduled_for == day,
        ExerciseAssignment.status == "done",
    )).all()
    return any((r.load_kg or 0) > 0 or (r.load_done_kg or 0) > 0 for r in rows)


def ask_morning(db: Session, patient: Patient, *, session_day: date, today: date,
                by: str | None = None, notify: bool = True, base_url: str | None = None,
                ) -> tuple[MorningCheck, dict[str, Any]]:
    """Ask how the morning after ``session_day`` is. Once per session day."""
    if session_day >= today:
        raise PtError("The morning after has not come yet")
    if (today - session_day).days > 3:
        raise PtError("That session is more than three days back: too late to ask about the morning after")
    row = db.scalar(select(MorningCheck).where(
        MorningCheck.patient_id == patient.id, MorningCheck.session_day == session_day))
    if row is not None and row.answered_at is not None:
        raise PtError(f"{_first_name(patient)} already answered for that morning")
    ceiling = pt_settings.patient_read(db, patient.id, patient.hospital_id)["morning_check"]["ceiling"]
    task, text = asks.ask(
        db, patient, qset=asks.MORNING, title="The morning after your session",
        why=f"Two questions about how {asks.session_word(session_day, today)} session has settled.",
        questions=asks.morning_questions(),
        ref={"session_day": session_day.isoformat(), "ceiling": ceiling},
        notify=notify, base_url=base_url, created_by=by,
    )
    if row is None:
        row = MorningCheck(patient_id=patient.id, session_day=session_day, ceiling=ceiling)
        db.add(row)
    row.task_id, row.asked_at, row.ceiling = task.id, datetime.now(), ceiling
    db.commit()
    return row, text


def morning_view(row: MorningCheck) -> dict[str, Any]:
    return {
        "id": row.id, "session_day": _iso(row.session_day),
        "morning": _iso(row.session_day + timedelta(days=1)),
        "asked_at": _iso(row.asked_at), "answered_at": _iso(row.answered_at),
        "pain": row.pain, "stiffer": row.stiffer, "ceiling": row.ceiling,
        "settled": row.settled,
        "read": ("waiting" if row.answered_at is None
                 else "settled" if row.settled else "not settled"),
    }


def mornings(db: Session, patient_id: str, *, since: date | None = None, limit: int = 14
             ) -> list[MorningCheck]:
    q = select(MorningCheck).where(MorningCheck.patient_id == patient_id)
    if since is not None:
        q = q.where(MorningCheck.session_day >= since)
    return db.scalars(q.order_by(MorningCheck.session_day.desc()).limit(limit)).all()


# --- function --------------------------------------------------------------------------


def add_goal(db: Session, patient: Patient, text: str, *, by: str) -> FunctionGoal:
    words = _text(text, asks.GOAL_TEXT_LIMIT)
    if not words:
        raise PtError("Say what the goal is, in the person's own words")
    current = active_goals(db, patient.id)
    if len(current) >= asks.MAX_GOALS:
        raise PtError(f"Up to {asks.MAX_GOALS} goals at a time: end one first")
    if any(g.text.lower() == words.lower() for g in current):
        raise PtError("That goal is already on the list")
    row = FunctionGoal(patient_id=patient.id, text=words, created_by=by,
                       position=max((g.position for g in current), default=-1) + 1)
    db.add(row)
    db.commit()
    return row


def end_goal(db: Session, patient: Patient, goal_id: int) -> None:
    row = db.get(FunctionGoal, goal_id)
    if row is None or row.patient_id != patient.id:
        raise PtError("Unknown goal")
    row.active, row.ended_at = False, datetime.now()
    db.commit()


def rate_now(db: Session, patient: Patient, scores: dict[int, int], day: date) -> float | None:
    """Ratings the therapist took down at a visit."""
    for score in scores.values():
        if not 0 <= int(score) <= 10:
            raise PtError("A rating is a whole number from 0 to 10")
    average = rate_goals(db, patient.id, {int(k): int(v) for k, v in scores.items()}, day,
                         source="clinic")
    if average is None:
        raise PtError("None of those goals are on this person's list")
    db.commit()
    return average


def ask_goals(db: Session, patient: Patient, *, by: str | None, notify: bool = True,
              base_url: str | None = None) -> dict[str, Any]:
    room = asks.MAX_GOALS - len(active_goals(db, patient.id))
    if room <= 0:
        raise PtError(f"{_first_name(patient)} already has {asks.MAX_GOALS} goals")
    _task, text = asks.ask(
        db, patient, qset=asks.GOALS, title="What do you want to get back to?",
        why="Your therapist tracks progress by what you can do, in your words.",
        questions=asks.goals_questions(room), notify=notify, base_url=base_url, created_by=by,
    )
    db.commit()
    return text


def ask_function(db: Session, patient: Patient, *, by: str | None, notify: bool = True,
                 base_url: str | None = None) -> dict[str, Any]:
    goals = active_goals(db, patient.id)
    if not goals:
        raise PtError(f"{_first_name(patient)} has no goals yet: ask for them first")
    _task, text = asks.ask(
        db, patient, qset=asks.FUNCTION, title="How are your goals going?",
        why="A quick 0 to 10 for each thing you want to get back to.",
        questions=asks.function_questions(goals), notify=notify, base_url=base_url,
        created_by=by,
    )
    db.commit()
    return text


def function_view(db: Session, patient: Patient, threshold: float | None) -> dict[str, Any]:
    goals = db.scalars(
        select(FunctionGoal).where(FunctionGoal.patient_id == patient.id)
        .order_by(FunctionGoal.active.desc(), FunctionGoal.position, FunctionGoal.id)
    ).all()
    ratings = db.scalars(
        select(FunctionRating).where(FunctionRating.patient_id == patient.id)
        .order_by(FunctionRating.rated_on, FunctionRating.id)
    ).all()
    by_goal: dict[int, list[FunctionRating]] = {}
    for r in ratings:
        by_goal.setdefault(r.goal_id, []).append(r)
    out = []
    for g in goals:
        own = by_goal.get(g.id, [])
        first, latest = (own[0], own[-1]) if own else (None, None)
        out.append({
            "id": g.id, "text": g.text, "active": g.active, "created_by": g.created_by,
            "created_at": _iso(g.created_at),
            "ratings": [{"on": _iso(r.rated_on), "score": r.score, "source": r.source} for r in own],
            "first": first.score if first else None,
            "latest": latest.score if latest else None,
            "latest_on": _iso(latest.rated_on) if latest else None,
            "change": (latest.score - first.score) if first and latest and first is not latest else None,
        })
    scores = scores_of(db, patient.id, "psfs")
    return {
        "goals": out,
        "max_goals": asks.MAX_GOALS,
        "score": _score_read("psfs", scores, threshold),
    }


# --- the week --------------------------------------------------------------------------


def week_start_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def ask_week(db: Session, patient: Patient, *, today: date, by: str | None = None,
             notify: bool = True, base_url: str | None = None,
             ) -> tuple[WeekCheckin, dict[str, Any]]:
    start = week_start_of(today)
    row = db.scalar(select(WeekCheckin).where(
        WeekCheckin.patient_id == patient.id, WeekCheckin.week_start == start))
    if row is not None and row.answered_at is not None:
        raise PtError(f"{_first_name(patient)} already answered for this week")
    task, text = asks.ask(
        db, patient, qset=asks.WEEK, title="How did the week go?",
        why="Two questions before your therapist writes next week.",
        questions=asks.week_questions(), ref={"week_start": start.isoformat()},
        notify=notify, base_url=base_url, created_by=by,
    )
    if row is None:
        row = WeekCheckin(patient_id=patient.id, week_start=start)
        db.add(row)
    row.task_id, row.asked_at = task.id, datetime.now()
    db.commit()
    return row, text


def week_view(row: WeekCheckin) -> dict[str, Any]:
    return {
        "id": row.id, "week_start": _iso(row.week_start), "asked_at": _iso(row.asked_at),
        "answered_at": _iso(row.answered_at), "went": row.went,
        "change_note": row.change_note or "",
    }


def weeks(db: Session, patient_id: str, limit: int = 6) -> list[WeekCheckin]:
    return db.scalars(
        select(WeekCheckin).where(WeekCheckin.patient_id == patient_id)
        .order_by(WeekCheckin.week_start.desc()).limit(limit)
    ).all()


# --- phases and their gates ------------------------------------------------------------


def _clean_phases(phases: Any) -> list[dict[str, Any]]:
    if not isinstance(phases, list) or not phases:
        raise PtError("A protocol needs at least one phase")
    if len(phases) > MAX_PHASES:
        raise PtError(f"At most {MAX_PHASES} phases")
    out = []
    for phase in phases:
        if not isinstance(phase, dict):
            raise PtError("Each phase is a name, a goal and its criteria")
        name = _text(phase.get("name"), NAME_LIMIT)
        if not name:
            raise PtError("Every phase needs a name")
        criteria = [c for c in (_text(c, 200) for c in (phase.get("criteria") or [])) if c]
        if len(criteria) > MAX_CRITERIA:
            raise PtError(f"At most {MAX_CRITERIA} criteria in a phase")
        out.append({"name": name, "goal": _text(phase.get("goal"), 240), "criteria": criteria})
    return out


def protocol_view(row: Protocol) -> dict[str, Any]:
    return {"id": row.id, "name": row.name, "description": row.description or "",
            "phases": list(row.phases or []), "created_by": row.created_by,
            "created_at": _iso(row.created_at)}


def protocols(db: Session, clinic: str) -> list[Protocol]:
    return db.scalars(
        select(Protocol).where(Protocol.hospital_id == clinic, Protocol.archived_at.is_(None))
        .order_by(Protocol.name)
    ).all()


def save_protocol(db: Session, clinic: str, *, protocol_id: int | None, name: str,
                  description: str, phases: Any, by: str) -> Protocol:
    clean_name = _text(name, NAME_LIMIT)
    if not clean_name:
        raise PtError("Name the protocol")
    cleaned = _clean_phases(phases)
    if protocol_id is None:
        row = Protocol(hospital_id=clinic, name=clean_name, created_by=by)
        db.add(row)
    else:
        row = db.get(Protocol, protocol_id)
        if row is None or row.hospital_id != clinic or row.archived_at is not None:
            raise PtError("Unknown protocol")
        row.name = clean_name
    row.description, row.phases = _text(description, 400), cleaned
    db.commit()
    return row


def archive_protocol(db: Session, clinic: str, protocol_id: int) -> None:
    row = db.get(Protocol, protocol_id)
    if row is None or row.hospital_id != clinic:
        raise PtError("Unknown protocol")
    row.archived_at = datetime.now()
    db.commit()


def patient_phases(db: Session, patient_id: str) -> list[PatientPhase]:
    return db.scalars(
        select(PatientPhase).where(PatientPhase.patient_id == patient_id)
        .order_by(PatientPhase.position, PatientPhase.id)
    ).all()


def set_phases(db: Session, patient: Patient, *, protocol_id: int | None, phases: Any,
               name: str | None, by: str, today: date) -> list[PatientPhase]:
    """Put a person on a protocol's phases (or on phases written for them).
    Replaces what they were on; the first phase starts today."""
    if protocol_id is not None:
        protocol = db.get(Protocol, protocol_id)
        if protocol is None or protocol.hospital_id != patient.hospital_id:
            raise PtError("Unknown protocol")
        cleaned, title = _clean_phases(protocol.phases), protocol.name
    else:
        cleaned, title = _clean_phases(phases), _text(name, NAME_LIMIT) or "Program"
    for row in patient_phases(db, patient.id):
        db.delete(row)
    db.flush()
    rows = []
    for position, phase in enumerate(cleaned):
        row = PatientPhase(
            patient_id=patient.id, hospital_id=patient.hospital_id, protocol_id=protocol_id,
            protocol_name=title, position=position, name=phase["name"], goal=phase["goal"],
            criteria=[{"text": c, "met": False, "met_at": None, "met_by": None}
                      for c in phase["criteria"]],
            status="current" if position == 0 else "upcoming",
            started_on=today if position == 0 else None,
        )
        db.add(row)
        rows.append(row)
    db.commit()
    return rows


def _phase(db: Session, patient: Patient, phase_id: int) -> PatientPhase:
    row = db.get(PatientPhase, phase_id)
    if row is None or row.patient_id != patient.id:
        raise PtError("Unknown phase")
    return row


def set_criterion(db: Session, patient: Patient, phase_id: int, index: int, *, met: bool,
                  by: str) -> PatientPhase:
    row = _phase(db, patient, phase_id)
    criteria = [dict(c) for c in (row.criteria or [])]
    if not 0 <= index < len(criteria):
        raise PtError("Unknown criterion")
    if _member(db, by) is None:
        raise PtError("Pick the clinician ticking this")
    criteria[index].update(met=bool(met), met_at=_iso(datetime.now()) if met else None,
                           met_by=by if met else None)
    row.criteria = criteria
    db.commit()
    return row


def advance_phase(db: Session, patient: Patient, *, by: str, today: date,
                  with_unmet: bool = False) -> list[PatientPhase]:
    """Close the current phase and start the next. A clinician's click, never
    the software's: with criteria still unticked it has to be asked for
    twice (``with_unmet``)."""
    if _member(db, by) is None:
        raise PtError("Pick the clinician moving this on")
    rows = patient_phases(db, patient.id)
    current = next((r for r in rows if r.status == "current"), None)
    if current is None:
        raise PtError("No phase is under way")
    unmet = [c["text"] for c in (current.criteria or []) if not c.get("met")]
    if unmet and not with_unmet:
        raise PtError(f"{len(unmet)} of this phase's criteria are not ticked: "
                      + "; ".join(unmet[:3]) + ("…" if len(unmet) > 3 else ""))
    current.status, current.ended_on, current.advanced_by = "done", today, by
    following = next((r for r in rows if r.position > current.position and r.status == "upcoming"), None)
    if following is not None:
        following.status, following.started_on = "current", today
    db.commit()
    return rows


def step_back_phase(db: Session, patient: Patient, *, by: str, today: date) -> list[PatientPhase]:
    """Undo a move on: the current phase goes back to upcoming and the one
    before it is under way again."""
    if _member(db, by) is None:
        raise PtError("Pick the clinician moving this back")
    rows = patient_phases(db, patient.id)
    done = [r for r in rows if r.status == "done"]
    if not done:
        raise PtError("There is no earlier phase to go back to")
    current = next((r for r in rows if r.status == "current"), None)
    if current is not None:
        current.status, current.started_on = "upcoming", None
    last = done[-1]
    last.status, last.ended_on, last.advanced_by = "current", None, None
    db.commit()
    return rows


def phases_view(db: Session, rows: list[PatientPhase]) -> dict[str, Any]:
    current = next((r for r in rows if r.status == "current"), None)

    def view(r: PatientPhase) -> dict[str, Any]:
        criteria = [
            {**c, "met_by_name": member_name(db, c.get("met_by"))} for c in (r.criteria or [])
        ]
        return {
            "id": r.id, "position": r.position, "name": r.name, "goal": r.goal or "",
            "status": r.status, "started_on": _iso(r.started_on), "ended_on": _iso(r.ended_on),
            "advanced_by_name": member_name(db, r.advanced_by),
            "criteria": criteria,
            "met": sum(1 for c in criteria if c.get("met")), "of": len(criteria),
        }

    return {
        "protocol_name": rows[0].protocol_name if rows else None,
        "phases": [view(r) for r in rows],
        "current": view(current) if current is not None else None,
        "number": (current.position + 1) if current is not None else None,
        "count": len(rows),
        "finished": bool(rows) and current is None and all(r.status == "done" for r in rows),
    }


# --- tests -----------------------------------------------------------------------------


def add_measurement(db: Session, patient: Patient, *, tested_on: date, kind: str,
                    label: str | None, side: str | None, value: Any, unit: str | None,
                    note: str | None, by: str | None, today: date,
                    source: str = "clinic") -> Measurement:
    if kind not in measures.KINDS:
        raise PtError("Unknown test")
    if tested_on > today:
        raise PtError("A result cannot be dated in the future")
    try:
        number = float(value)
    except (TypeError, ValueError) as err:
        raise PtError("The result is a number") from err
    if not 0 <= number <= measures.VALUE_MAX:
        raise PtError("That number is out of range")
    kind_label, kind_unit, sided, _who = measures.KINDS[kind]
    side = (side or "na").lower()
    if side not in measures.SIDES:
        raise PtError("A side is left, right, both, or none")
    if kind == "custom":
        kind_label = _text(label, 80)
        kind_unit = _text(unit, 12)
        if not kind_label:
            raise PtError("Name the test")
    elif kind == "strength_rm" and _text(label, 80):
        kind_label = _text(label, 80)
    if not sided and kind != "custom":
        side = "na"
    row = Measurement(
        patient_id=patient.id, hospital_id=patient.hospital_id, tested_on=tested_on, kind=kind,
        label=kind_label, side=side, value=number, unit=_text(unit, 12) or kind_unit,
        note=_text(note, 300) or None, source=source, entered_by=by,
    )
    db.add(row)
    db.commit()
    return row


def remove_measurement(db: Session, patient: Patient, measurement_id: int) -> None:
    row = db.get(Measurement, measurement_id)
    if row is None or row.patient_id != patient.id:
        raise PtError("Unknown result")
    db.delete(row)
    db.commit()


def ask_hold(db: Session, patient: Patient, kind: str, *, by: str | None, notify: bool = True,
             base_url: str | None = None) -> dict[str, Any]:
    if kind not in measures.HOLDS:
        raise PtError("That is not a hold a person can time at home")
    label = measures.KINDS[kind][0]
    _task, text = asks.ask(
        db, patient, qset=asks.HOLD, title=f"Time your {label.lower()}",
        why="Hold it once, as long as you can with good form, and say how long.",
        questions=asks.hold_questions(kind), ref={"kind": kind},
        notify=notify, base_url=base_url, created_by=by,
    )
    db.commit()
    return text


def measurements_view(db: Session, patient_id: str) -> dict[str, Any]:
    rows = db.scalars(
        select(Measurement).where(Measurement.patient_id == patient_id)
        .order_by(Measurement.tested_on, Measurement.id)
    ).all()
    groups: dict[tuple[str, str], list[Measurement]] = {}
    for r in rows:
        groups.setdefault((r.kind, r.label), []).append(r)
    out = []
    for (kind, label), own in groups.items():
        days: dict[date, dict[str, Any]] = {}
        for r in own:
            day = days.setdefault(r.tested_on, {"on": _iso(r.tested_on), "results": []})
            day["results"].append({
                "id": r.id, "side": r.side, "value": r.value, "unit": r.unit,
                "note": r.note or "", "source": r.source,
                "entered_by_name": member_name(db, r.entered_by),
            })
        for day in days.values():
            sides = {x["side"]: x["value"] for x in day["results"]}
            left, right = sides.get("left"), sides.get("right")
            # Two sides of one test on one day, set beside each other. A
            # ratio, with no word on what it means.
            day["left_of_right_pct"] = (
                round(left / right * 100) if left is not None and right else None
            )
        ordered = [days[d] for d in sorted(days)]
        series = [{"on": d["on"], "value": max(x["value"] for x in d["results"])} for d in ordered]
        out.append({
            "kind": kind, "label": label, "unit": own[-1].unit,
            "hold": kind in measures.HOLDS, "sided": measures.KINDS.get(kind, ("", "", False, ""))[2],
            "days": ordered, "series": series,
            "first": series[0]["value"], "latest": series[-1]["value"],
            "latest_on": series[-1]["on"],
            "change": round(series[-1]["value"] - series[0]["value"], 1) if len(series) > 1 else None,
        })
    out.sort(key=lambda g: g["latest_on"], reverse=True)
    return {"tests": out, "kinds": measures.catalog()}


# --- outcome measures ------------------------------------------------------------------


def scores_of(db: Session, patient_id: str, instrument: str) -> list[OutcomeScore]:
    return db.scalars(
        select(OutcomeScore).where(OutcomeScore.patient_id == patient_id,
                                   OutcomeScore.instrument == instrument)
        .order_by(OutcomeScore.scored_on, OutcomeScore.id)
    ).all()


def _score_read(instrument: str, scores: list[OutcomeScore], threshold: float | None
                ) -> dict[str, Any] | None:
    if not scores:
        return None
    first, latest = scores[0], scores[-1]
    out = {
        "first": first.total, "first_on": _iso(first.scored_on),
        "latest": latest.total, "latest_on": _iso(latest.scored_on),
        "count": len(scores), "threshold": threshold, "change": None,
    }
    if first is not latest:
        out["change"] = change_read(instrument, first.total, latest.total, threshold)
    return out


def set_outcome_schedule(db: Session, patient: Patient, instrument: str, *, every_days: int,
                         start: date, by: str) -> OutcomeSchedule:
    if instrument not in INSTRUMENTS:
        raise PtError("Unknown outcome measure")
    if not OUTCOME_MIN_DAYS <= int(every_days) <= OUTCOME_MAX_DAYS:
        raise PtError(f"A rhythm is between {OUTCOME_MIN_DAYS} and {OUTCOME_MAX_DAYS} days")
    row = db.scalar(select(OutcomeSchedule).where(
        OutcomeSchedule.patient_id == patient.id, OutcomeSchedule.instrument == instrument))
    if row is None:
        row = OutcomeSchedule(patient_id=patient.id, instrument=instrument, created_by=by,
                              next_due=start)
        db.add(row)
    row.every_days, row.next_due, row.active = int(every_days), start, True
    db.commit()
    return row


def stop_outcome_schedule(db: Session, patient: Patient, instrument: str) -> None:
    row = db.scalar(select(OutcomeSchedule).where(
        OutcomeSchedule.patient_id == patient.id, OutcomeSchedule.instrument == instrument))
    if row is None:
        raise PtError("That measure is not on a rhythm for this person")
    row.active = False
    db.commit()


def add_score(db: Session, patient: Patient, instrument: str, total: Any, day: date, *,
              by: str | None, today: date) -> OutcomeScore:
    if instrument not in INSTRUMENTS:
        raise PtError("Unknown outcome measure")
    if instrument == "psfs":
        raise PtError("The functional scale is scored from the goals: rate them instead")
    i = INSTRUMENTS[instrument]
    try:
        number = float(total)
    except (TypeError, ValueError) as err:
        raise PtError("The score is a number") from err
    if not i.low <= number <= i.high:
        raise PtError(f"{i.short} runs from {i.low:g} to {i.high:g}")
    if day > today:
        raise PtError("A score cannot be dated in the future")
    row = put_score(db, patient.id, instrument, number, day, source="clinic", entered_by=by)
    db.commit()
    return row


def ask_outcome(db: Session, patient: Patient, instrument: str, *, by: str | None,
                notify: bool = True, base_url: str | None = None) -> dict[str, Any]:
    if instrument not in INSTRUMENTS:
        raise PtError("Unknown outcome measure")
    goals = active_goals(db, patient.id)
    if instrument == "psfs" and not goals:
        raise PtError(f"{_first_name(patient)} has no goals yet: ask for them first")
    i = INSTRUMENTS[instrument]
    _task, text = asks.ask(
        db, patient, qset=asks.OUTCOME, title=i.name,
        why=("Your therapist tracks this score over time." if i.mode == "entered"
             else "A quick score your therapist tracks over time."),
        questions=asks.outcome_questions(instrument, goals), ref={"instrument": instrument},
        notify=notify, base_url=base_url, created_by=by,
    )
    db.commit()
    return text


def outcomes_view(db: Session, patient: Patient) -> dict[str, Any]:
    overrides = pt_settings.read(db, patient.hospital_id)["outcome_thresholds"]
    schedules = {s.instrument: s for s in db.scalars(
        select(OutcomeSchedule).where(OutcomeSchedule.patient_id == patient.id))}
    scored = set(db.scalars(
        select(OutcomeScore.instrument).where(OutcomeScore.patient_id == patient.id).distinct()))
    measures_out = []
    for key in INSTRUMENTS:
        info = describe(key, overrides.get(key))
        if key not in scored and key not in schedules:
            continue
        scores = scores_of(db, patient.id, key)
        schedule = schedules.get(key)
        measures_out.append({
            **info,
            "scores": [{"id": s.id, "on": _iso(s.scored_on), "total": s.total, "source": s.source}
                       for s in scores],
            "read": _score_read(key, scores, info["threshold"]),
            "schedule": ({"every_days": schedule.every_days, "next_due": _iso(schedule.next_due),
                          "active": schedule.active} if schedule is not None else None),
        })
    return {"measures": measures_out,
            "instruments": [describe(k, overrides.get(k)) for k in INSTRUMENTS]}


# --- visits and marks ------------------------------------------------------------------


def _clock(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%H:%M").strftime("%H:%M")
    except ValueError as err:
        raise PtError("A time is written like 14:30") from err


def visit_view(db: Session, row: ClinicVisit) -> dict[str, Any]:
    return {
        "id": row.id, "patient_id": row.patient_id, "on": _iso(row.visit_on), "at": row.at,
        "kind": row.kind, "kind_label": VISIT_LABELS.get(row.kind, "Visit"),
        "note": row.note or "", "created_by_name": member_name(db, row.created_by),
    }


def phone_visit(view: dict[str, Any] | None) -> dict[str, Any] | None:
    """A visit as the person's own app gets it: the day, the time and what
    kind. The clinic's note on a visit is written for the clinic, and who
    booked it is the clinic's business, so neither travels."""
    if not view:
        return None
    return {"on": view["on"], "at": view["at"], "kind": view["kind"],
            "kind_label": view["kind_label"]}


def add_visit(db: Session, clinic: str, patient: Patient, *, visit_on: date, at: str | None,
              kind: str, note: str | None, by: str, today: date) -> ClinicVisit:
    if kind not in VISIT_KINDS:
        raise PtError("A visit is a visit, an evaluation or a test day")
    if abs((visit_on - today).days) > 366:
        raise PtError("That day is more than a year away")
    same = db.scalar(select(ClinicVisit).where(
        ClinicVisit.patient_id == patient.id, ClinicVisit.visit_on == visit_on,
        ClinicVisit.kind == kind))
    if same is not None:
        raise PtError(f"{_first_name(patient)} already has that on {visit_on.isoformat()}")
    row = ClinicVisit(hospital_id=clinic, patient_id=patient.id, visit_on=visit_on,
                      at=_clock(at), kind=kind, note=_text(note, 300), created_by=by)
    db.add(row)
    db.flush()
    sync_seen(db, patient.id, today)
    db.commit()
    return row


def remove_visit(db: Session, clinic: str, visit_id: int) -> None:
    row = db.get(ClinicVisit, visit_id)
    if row is None or row.hospital_id != clinic:
        raise PtError("Unknown visit")
    db.delete(row)
    db.commit()


def visits_of(db: Session, patient_id: str, today: date) -> dict[str, Any]:
    rows = db.scalars(
        select(ClinicVisit).where(ClinicVisit.patient_id == patient_id)
        .order_by(ClinicVisit.visit_on, ClinicVisit.id)
    ).all()
    past = [r for r in rows if r.visit_on < today]
    ahead = [r for r in rows if r.visit_on >= today]
    return {
        "last": visit_view(db, past[-1]) if past else None,
        "next": visit_view(db, ahead[0]) if ahead else None,
        "upcoming": [visit_view(db, r) for r in ahead[:6]],
        "past": [visit_view(db, r) for r in past[-6:]],
        "days_since_last": (today - past[-1].visit_on).days if past else None,
        "days_to_next": (ahead[0].visit_on - today).days if ahead else None,
    }


def set_mark(db: Session, clinic: str, patient: Patient, *, day: date, kind: str,
             note: str | None, by: str) -> CalendarMark:
    if kind not in MARK_KINDS:
        raise PtError("Unknown mark")
    row = db.scalar(select(CalendarMark).where(
        CalendarMark.patient_id == patient.id, CalendarMark.day == day, CalendarMark.kind == kind))
    if row is None:
        row = CalendarMark(hospital_id=clinic, patient_id=patient.id, day=day, kind=kind,
                           created_by=by)
        db.add(row)
    row.note = _text(note, 200)
    db.commit()
    return row


def clear_mark(db: Session, clinic: str, mark_id: int) -> None:
    row = db.get(CalendarMark, mark_id)
    if row is None or row.hospital_id != clinic:
        raise PtError("Unknown mark")
    db.delete(row)
    db.commit()


def mark_view(row: CalendarMark) -> dict[str, Any]:
    return {"id": row.id, "patient_id": row.patient_id, "day": _iso(row.day), "kind": row.kind,
            "note": row.note or ""}


def calendar_extras(db: Session, clinic: str, start: date, end: date,
                    patient_ids: list[str] | None = None) -> dict[str, Any]:
    """What the calendar draws beside the exercises on days ``start`` up to
    (not including) ``end``: the visits and the rest days."""
    visits = select(ClinicVisit).where(
        ClinicVisit.hospital_id == clinic, ClinicVisit.visit_on >= start, ClinicVisit.visit_on < end)
    marks = select(CalendarMark).where(
        CalendarMark.hospital_id == clinic, CalendarMark.day >= start, CalendarMark.day < end)
    if patient_ids is not None:
        visits = visits.where(ClinicVisit.patient_id.in_(patient_ids))
        marks = marks.where(CalendarMark.patient_id.in_(patient_ids))
    return {
        "visits": [visit_view(db, r) for r in db.scalars(visits.order_by(ClinicVisit.visit_on))],
        "marks": [mark_view(r) for r in db.scalars(marks.order_by(CalendarMark.day))],
    }


def exercise_guard(db: Session, clinic: str, patient_id: str, days: list[date], adding: int = 1
                   ) -> list[dict[str, Any]]:
    """The days on which one more exercise would take a person past the
    clinic's count (``exercise_guard``): each with what it would come to."""
    limit = int(pt_settings.read(db, clinic)["exercise_guard"])
    if not days:
        return []
    rows = db.execute(
        select(ExerciseAssignment.scheduled_for).where(
            ExerciseAssignment.patient_id == patient_id,
            ExerciseAssignment.scheduled_for.in_(days),
        )
    ).scalars().all()
    counts: dict[date, int] = {}
    for day in rows:
        counts[day] = counts.get(day, 0) + 1
    return [
        {"day": day.isoformat(), "would_be": counts.get(day, 0) + adding, "limit": limit}
        for day in sorted(set(days)) if counts.get(day, 0) + adding > limit
    ]


# --- the clip, looked at closely ---------------------------------------------------------


def _assignment(db: Session, clinic: str, assignment_id: int) -> ExerciseAssignment:
    row = db.get(ExerciseAssignment, assignment_id)
    if row is None or row.hospital_id != clinic:
        raise PtError("Unknown exercise day")
    return row


def comment_view(db: Session, row: ClipComment) -> dict[str, Any]:
    from app.api.attachments import attachment_view

    voice = db.get(Attachment, row.voice_attachment_id) if row.voice_attachment_id else None
    return {
        "id": row.id, "assignment_id": row.assignment_id, "at_ms": row.at_ms,
        "text": row.text or "", "by": row.by, "by_name": member_name(db, row.by),
        "created_at": _iso(row.created_at),
        "voice": attachment_view(voice, with_url=True) if voice is not None else None,
    }


def comments(db: Session, clinic: str, assignment_id: int) -> list[dict[str, Any]]:
    _assignment(db, clinic, assignment_id)
    rows = db.scalars(
        select(ClipComment).where(ClipComment.assignment_id == assignment_id)
        .order_by(ClipComment.at_ms.is_(None), ClipComment.at_ms, ClipComment.id)
    ).all()
    return [comment_view(db, r) for r in rows]


def add_comment(db: Session, clinic: str, assignment_id: int, *, at_ms: int | None,
                text: str | None, voice_attachment_id: int | None, by: str) -> ClipComment:
    row = _assignment(db, clinic, assignment_id)
    words = _text(text, 400)
    if _member(db, by) is None:
        raise PtError("Pick the clinician commenting")
    if at_ms is not None and not 0 <= int(at_ms) <= 3_600_000:
        raise PtError("That moment is outside the clip")
    voice = None
    if voice_attachment_id is not None:
        voice = db.get(Attachment, voice_attachment_id)
        if voice is None or voice.patient_id != row.patient_id or voice.confirmed_at is None:
            raise PtError("That voice note was not uploaded for this person")
        if not (voice.content_type or "").startswith("audio/"):
            raise PtError("A voice note is an audio file")
    if not words and voice is None:
        raise PtError("Write the comment, or record it")
    comment = ClipComment(assignment_id=row.id, patient_id=row.patient_id, hospital_id=clinic,
                          at_ms=None if at_ms is None else int(at_ms), text=words,
                          voice_attachment_id=voice.id if voice is not None else None, by=by)
    db.add(comment)
    db.commit()
    return comment


def voice_to_thread(db: Session, comment: ClipComment) -> None:
    """A spoken comment is for the person to hear: it goes onto their thread
    at once, under the therapist's name, as the audio itself. Typed
    comments wait and go with the review (``comment_lines``)."""
    from app.models.mobile import Message

    if comment.voice_attachment_id is None:
        return
    voice = db.get(Attachment, comment.voice_attachment_id)
    if voice is None or voice.message_id is not None:
        return
    row = db.get(ExerciseAssignment, comment.assignment_id)
    exercise = db.get(Exercise, row.exercise_id) if row is not None else None
    title = exercise.title if exercise is not None else "exercise"
    moment = f" (at {_mmss(comment.at_ms)})" if comment.at_ms is not None else ""
    message = Message(
        patient_id=comment.patient_id, sender="care_team", sender_id=comment.by, channel="app",
        text=f"A voice note about your {title} clip{moment}." + (
            f" {comment.text}" if comment.text else ""),
        authored_by="care_team",
    )
    db.add(message)
    db.flush()
    voice.message_id = message.id
    db.commit()


def _mmss(ms: int) -> str:
    seconds = int(ms // 1000)
    return f"{seconds // 60}:{seconds % 60:02d}"


def comment_lines(db: Session, assignment_id: int) -> list[str]:
    """The typed comments on a clip as the lines a review carries to the
    person: "0:12 knees drifting in", whole-clip remarks last."""
    rows = db.scalars(
        select(ClipComment).where(ClipComment.assignment_id == assignment_id,
                                  ClipComment.voice_attachment_id.is_(None))
        .order_by(ClipComment.at_ms.is_(None), ClipComment.at_ms, ClipComment.id)
    ).all()
    return [(f"{_mmss(r.at_ms)} {r.text}" if r.at_ms is not None else r.text)
            for r in rows if r.text]


def remove_comment(db: Session, clinic: str, comment_id: int) -> None:
    row = db.get(ClipComment, comment_id)
    if row is None or row.hospital_id != clinic:
        raise PtError("Unknown comment")
    db.delete(row)
    db.commit()


def earlier_clips(db: Session, clinic: str, assignment_id: int, limit: int = 6
                  ) -> list[dict[str, Any]]:
    """The same person's earlier clips of the same exercise, newest first:
    what a therapist sets beside today's to see what changed."""
    from app.api.attachments import attachment_view

    row = _assignment(db, clinic, assignment_id)
    rows = db.scalars(
        select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == row.patient_id,
            ExerciseAssignment.exercise_id == row.exercise_id,
            ExerciseAssignment.video_attachment_id.is_not(None),
            ExerciseAssignment.id != row.id,
            ExerciseAssignment.scheduled_for <= row.scheduled_for,
        ).order_by(ExerciseAssignment.scheduled_for.desc(), ExerciseAssignment.id.desc())
        .limit(limit)
    ).all()
    unit = load_unit_of(db.get(Hospital, clinic))
    out = []
    for earlier in rows:
        clip = db.get(Attachment, earlier.video_attachment_id)
        if clip is None or clip.deleted_at is not None:
            continue
        out.append({
            "assignment_id": earlier.id, "day": _iso(earlier.scheduled_for),
            "pain_after": earlier.pain_after, "effort": earlier.effort,
            "load": (load_text(earlier.load_done_kg or earlier.load_kg, unit)
                     if (earlier.load_done_kg or earlier.load_kg) else None),
            "review_note": earlier.review_note or "",
            "video": attachment_view(clip, with_url=True),
        })
    return out


# --- the trainer's page ------------------------------------------------------------------


def _limits(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise PtError("Limits are a list of lines")
    lines = [line for line in (_text(v, 200) for v in value) if line]
    if len(lines) > MAX_LIMITS:
        raise PtError(f"At most {MAX_LIMITS} limits")
    return lines


def handoff_of(db: Session, patient_id: str) -> Handoff | None:
    return db.scalar(
        select(Handoff).where(Handoff.patient_id == patient_id)
        .order_by(Handoff.id.desc()).limit(1)
    )


def handoff_url(row: Handoff, base_url: str | None = None) -> str | None:
    if row.status != "active" or not row.token:
        return None
    base = (base_url or settings.checkin_base_url or "").rstrip("/")
    return f"{base}/h/{row.token}"


def handoff_view(db: Session, row: Handoff | None, base_url: str | None = None
                 ) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id, "trainer_name": row.trainer_name or "", "limits": list(row.limits or []),
        "report_back": row.report_back or "", "include_week": bool(row.include_week),
        "status": row.status, "url": handoff_url(row, base_url),
        "requested_at": _iso(row.requested_at), "authorised_at": _iso(row.authorised_at),
        "revoked_at": _iso(row.revoked_at), "updated_at": _iso(row.updated_at),
        "last_opened_at": _iso(row.last_opened_at), "open_count": row.open_count or 0,
        "created_by_name": member_name(db, row.created_by),
    }


def save_handoff(db: Session, patient: Patient, *, trainer_name: str, limits: Any,
                 report_back: str, include_week: bool, by: str) -> Handoff:
    """Write (or rewrite) what the trainer is to be told. A page that is
    live keeps its link and shows the new words at once: the person agreed
    to share their limits with this trainer, and these are their limits."""
    lines = _limits(limits)
    if not lines and not _text(report_back):
        raise PtError("Write at least one limit, or what to report back")
    row = handoff_of(db, patient.id)
    if row is None or row.status in ("revoked", "declined"):
        row = Handoff(patient_id=patient.id, hospital_id=patient.hospital_id, created_by=by)
        db.add(row)
    elif row.status == "active" and _text(trainer_name, NAME_LIMIT) != (row.trainer_name or ""):
        raise PtError("This page was agreed for a named trainer. Revoke it and ask again "
                      "to share with someone else")
    row.trainer_name = _text(trainer_name, NAME_LIMIT)
    row.limits, row.report_back = lines, _text(report_back, 400)
    row.include_week, row.updated_at = bool(include_week), datetime.now()
    db.commit()
    return row


def request_handoff(db: Session, patient: Patient, *, by: str | None, notify: bool = True,
                    base_url: str | None = None) -> tuple[Handoff, dict[str, Any]]:
    """Ask the person whether these limits may be shared. Nothing is shared,
    and no link exists, until they say yes."""
    row = handoff_of(db, patient.id)
    if row is None or row.status in ("revoked", "declined"):
        raise PtError("Write the handoff first")
    if row.status == "active":
        raise PtError(f"{_first_name(patient)} has already agreed: the page is live")
    task, text = asks.ask(
        db, patient, qset=asks.HANDOFF, title="Share your training limits?",
        why="Your therapist wrote a short page for your trainer. It goes nowhere unless you say yes.",
        questions=asks.handoff_questions(row), ref={"handoff_id": row.id},
        notify=notify, base_url=base_url, created_by=by,
    )
    row.status, row.task_id, row.requested_at = "awaiting", task.id, datetime.now()
    row.updated_at = datetime.now()
    db.commit()
    return row, text


def activate_handoff(db: Session, row: Handoff, now: datetime) -> None:
    """The person said yes: the page exists from here on. The caller commits."""
    row.status, row.authorised_at, row.updated_at = "active", now, now
    row.token = row.token or secrets.token_urlsafe(18)
    row.revoked_at = None


def revoke_handoff(db: Session, patient: Patient) -> Handoff:
    from app.models.adherence import AdherenceTask

    row = handoff_of(db, patient.id)
    if row is None or row.status in ("revoked", "declined", "draft"):
        raise PtError("There is nothing shared to take back")
    if row.task_id:
        asks.close_ask(db, db.get(AdherenceTask, row.task_id))
    row.status, row.token, row.revoked_at = "revoked", None, datetime.now()
    row.updated_at = datetime.now()
    db.commit()
    return row


def handoff_page(db: Session, token: str, today: date) -> dict[str, Any] | None:
    """What the trainer's link shows, or None for a link that is not live.
    The limits, this week's exercises with their doses and ceilings, what to
    report back, and who wrote it. Nothing from the person's record: no
    pain, no notes, no scores, no messages."""
    if not token or len(token) > 80:
        return None
    row = db.scalar(select(Handoff).where(Handoff.token == token))
    if row is None or row.status != "active":
        return None
    patient = db.get(Patient, row.patient_id)
    clinic = db.get(Hospital, row.hospital_id)
    if patient is None:
        return None
    parts = (patient.name or "").split()
    shown = parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "") if parts else "Your client"
    week: list[dict[str, Any]] = []
    if row.include_week:
        from app.hep.plans import dose_text

        start = week_start_of(today)
        unit = load_unit_of(clinic)
        rows = db.scalars(
            select(ExerciseAssignment).where(
                ExerciseAssignment.patient_id == patient.id,
                ExerciseAssignment.scheduled_for >= start,
                ExerciseAssignment.scheduled_for < start + timedelta(days=7),
            ).order_by(ExerciseAssignment.scheduled_for, ExerciseAssignment.sort_order)
        ).all()
        titles = dict(db.execute(select(Exercise.id, Exercise.title).where(
            Exercise.id.in_({r.exercise_id for r in rows}))).all()) if rows else {}
        for r in rows:
            week.append({
                "day": _iso(r.scheduled_for), "title": titles.get(r.exercise_id, "Exercise"),
                "dose": dose_text(r.sets, r.reps, r.hold_seconds, r.side, load_kg=r.load_kg,
                                  load_unit=unit),
                "ceiling": ceiling_text(r, unit),
                "instructions": r.clinician_instructions or "",
            })
    phases = phases_view(db, patient_phases(db, patient.id))
    row.open_count = (row.open_count or 0) + 1
    row.last_opened_at = datetime.now()
    db.commit()
    return {
        "person": shown,
        "clinic": clinic.name if clinic is not None else "",
        "from": member_name(db, row.created_by) or member_name(db, patient.assigned_provider_id),
        "trainer_name": row.trainer_name or "",
        "limits": list(row.limits or []),
        "report_back": row.report_back or "",
        "phase": ({"name": phases["current"]["name"], "goal": phases["current"]["goal"],
                   "number": phases["number"], "count": phases["count"]}
                  if phases["current"] else None),
        "week": week,
        "week_start": _iso(week_start_of(today)),
        "updated_at": _iso(row.updated_at),
        "authorised_on": _iso(row.authorised_at.date()) if row.authorised_at else None,
    }


def ceiling_text(row: ExerciseAssignment, unit: str = "kg") -> str:
    """"Stop at RPE 7 · do not exceed 65 lb", or "" for a day with no
    ceiling written."""
    parts = []
    if row.rpe_max is not None:
        parts.append(f"stop at RPE {row.rpe_max}")
    if row.load_max_kg is not None:
        parts.append(f"do not exceed {load_text(row.load_max_kg, unit)}")
    text = " · ".join(parts)
    return text[:1].upper() + text[1:] if text else ""


# --- the chart --------------------------------------------------------------------------


def open_asks(db: Session, patient_id: str) -> list[dict[str, Any]]:
    from app.models.adherence import AdherenceTask
    from app.tasks import service as tasks

    rows = db.scalars(select(AdherenceTask).where(
        AdherenceTask.patient_id == patient_id, AdherenceTask.active.is_(True),
        AdherenceTask.status.in_(tasks.OPEN_STATUSES),
    ).order_by(AdherenceTask.id)).all()
    out = []
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if str(payload.get("qset", "")).startswith("pt_"):
            out.append({"task_id": row.id, "qset": payload["qset"], "title": row.title,
                        "asked_at": _iso(row.created_at), "texted": row.sent_at is not None})
    return out


def chart(db: Session, patient: Patient, today: date, base_url: str | None = None) -> dict[str, Any]:
    """Everything the chart's Program card shows for one person."""
    sync_seen(db, patient.id, today)
    db.commit()
    clinic_settings = pt_settings.read(db, patient.hospital_id)
    recent = mornings(db, patient.id, since=today - timedelta(days=14))
    answered = [m for m in recent if m.answered_at is not None]
    week_rows = weeks(db, patient.id)
    return {
        "patient_id": patient.id,
        "settings": pt_settings.patient_read(db, patient.id, patient.hospital_id),
        "areas": areas_view(db, patient.id),
        "morning": {
            "recent": [morning_view(m) for m in recent],
            "answered": len(answered),
            "settled": sum(1 for m in answered if m.settled),
            "last": morning_view(recent[0]) if recent else None,
            # Yesterday was a loaded day nobody has asked about yet.
            "can_ask": (loaded_day(db, patient.id, today - timedelta(days=1))
                        and not any(m.session_day == today - timedelta(days=1) for m in recent)),
        },
        "function": function_view(db, patient, clinic_settings["outcome_thresholds"].get(
            "psfs", INSTRUMENTS["psfs"].threshold)),
        "week": {"latest": week_view(week_rows[0]) if week_rows else None,
                 "history": [week_view(w) for w in week_rows],
                 "this_week": _iso(week_start_of(today))},
        "phases": phases_view(db, patient_phases(db, patient.id)),
        "tests": measurements_view(db, patient.id),
        "outcomes": outcomes_view(db, patient),
        "handoff": handoff_view(db, handoff_of(db, patient.id), base_url),
        "visits": visits_of(db, patient.id, today),
        "asks": open_asks(db, patient.id),
    }


def week_extras(db: Session, patient_ids: list[str], start: date, today: date
                ) -> dict[str, dict[str, Any]]:
    """What the week review adds for each person: the Friday word on that
    week, how its mornings after settled, the next visit, and the phase."""
    out: dict[str, dict[str, Any]] = {}
    end = start + timedelta(days=7)
    for pid in patient_ids:
        word = db.scalar(select(WeekCheckin).where(
            WeekCheckin.patient_id == pid, WeekCheckin.week_start == start))
        checks = db.scalars(select(MorningCheck).where(
            MorningCheck.patient_id == pid, MorningCheck.session_day >= start,
            MorningCheck.session_day < end)).all()
        answered = [c for c in checks if c.answered_at is not None]
        phases = phases_view(db, patient_phases(db, pid))
        out[pid] = {
            "week_checkin": week_view(word) if word is not None else None,
            "mornings": {"asked": len(checks), "answered": len(answered),
                         "settled": sum(1 for c in answered if c.settled),
                         "not_settled": sum(1 for c in answered if c.settled is False)},
            "next_visit": visits_of(db, pid, today)["next"],
            "phase": ({"name": phases["current"]["name"], "number": phases["number"],
                       "count": phases["count"], "met": phases["current"]["met"],
                       "of": phases["current"]["of"]} if phases["current"] else None),
        }
    return out


# --- the person's own side ---------------------------------------------------------------


def patient_side(db: Session, patient: Patient, today: date) -> dict[str, Any]:
    """What the person's own app shows of this: the next visit, whether
    today is a rest day, the phase they are in and its goal, their goals
    with their own ratings, and whether a trainer page is shared. Nothing a
    clinician wrote about them that was not written for them."""
    visits = visits_of(db, patient.id, today)
    rest = db.scalar(select(CalendarMark).where(
        CalendarMark.patient_id == patient.id, CalendarMark.day == today,
        CalendarMark.kind == "rest"))
    phases = phases_view(db, patient_phases(db, patient.id))
    goals = function_view(db, patient, None)["goals"]
    handoff = handoff_of(db, patient.id)
    return {
        "next_visit": phone_visit(visits["next"]),
        "rest_day": {"note": rest.note or ""} if rest is not None else None,
        "phase": ({"name": phases["current"]["name"], "goal": phases["current"]["goal"],
                   "number": phases["number"], "count": phases["count"]}
                  if phases["current"] else None),
        "goals": [{"id": g["id"], "text": g["text"], "latest": g["latest"],
                   "first": g["first"], "ratings": g["ratings"]}
                  for g in goals if g["active"]],
        "handoff": ({"trainer_name": handoff.trainer_name or "", "status": handoff.status}
                    if handoff is not None and handoff.status in ("awaiting", "active") else None),
    }


# --- the morning run ---------------------------------------------------------------------


def run_daily(db: Session, today: date, *, base_url: str | None = None) -> dict[str, int]:
    """What goes out by itself each morning, for every person on a clinic's
    own program whose settings say so: the morning-after check for anyone
    who did a loaded session yesterday, the Friday word on the week, and any
    outcome measure that has come due. Each is asked once; a person who
    cannot be texted still gets it in their app."""
    from app.engine.care.pathways import clinic_program
    from app.personal.scope import is_clinic

    counts = {"morning": 0, "week": 0, "outcome": 0}
    yesterday = today - timedelta(days=1)
    for patient in db.scalars(select(Patient)).all():
        if not is_clinic(patient) or clinic_program(patient) is None:
            continue
        own = pt_settings.patient_read(db, patient.id, patient.hospital_id)
        try:
            if own["morning_check"]["on"] and loaded_day(db, patient.id, yesterday):
                asked = db.scalar(select(MorningCheck.id).where(
                    MorningCheck.patient_id == patient.id, MorningCheck.session_day == yesterday))
                if asked is None:
                    ask_morning(db, patient, session_day=yesterday, today=today, base_url=base_url)
                    counts["morning"] += 1
            if own["week_checkin"]["on"] and today.weekday() == 4:
                asked = db.scalar(select(WeekCheckin.id).where(
                    WeekCheckin.patient_id == patient.id,
                    WeekCheckin.week_start == week_start_of(today)))
                if asked is None:
                    ask_week(db, patient, today=today, base_url=base_url)
                    counts["week"] += 1
            for schedule in db.scalars(select(OutcomeSchedule).where(
                OutcomeSchedule.patient_id == patient.id, OutcomeSchedule.active.is_(True),
                OutcomeSchedule.next_due <= today,
            )):
                if schedule.instrument == "psfs" and not active_goals(db, patient.id):
                    continue
                if asks.open_ask(db, patient.id, asks.OUTCOME,
                                 {"instrument": schedule.instrument}) is None:
                    ask_outcome(db, patient, schedule.instrument, by=None, base_url=base_url)
                    counts["outcome"] += 1
        except PtError:
            db.rollback()
    return counts
