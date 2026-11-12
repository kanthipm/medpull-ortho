"""What the clinic asks a person between visits, as tasks.

Each ask is an ordinary task (app/tasks) that carries its own questions, so
the phone, the browser app and a text conversation all put it the same way
and no app needs to know these exist. The question-set keys start with
``pt_``; ``app/pt/intake.py`` files the answers.

A question written for one person (a goal in their words, their trainer's
name) is built here from their own rows. Nothing is asked twice: an ask
that is still open for the same thing is returned as it is.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.adherence import AdherenceTask
from app.models.patient import Patient
from app.pt import measures, regions
from app.pt.instruments import INSTRUMENTS
from app.pt.models import FunctionGoal, Handoff
from app.tasks import service as tasks

MORNING = "pt_morning"
WEEK = "pt_week"
NEW_AREA = "pt_new_area"
GOALS = "pt_goals"
FUNCTION = "pt_function"
OUTCOME = "pt_outcome"
HOLD = "pt_hold"
HANDOFF = "pt_handoff"
QSETS = (MORNING, WEEK, NEW_AREA, GOALS, FUNCTION, OUTCOME, HOLD, HANDOFF)

MAX_GOALS = 3
GOAL_TEXT_LIMIT = 120


# --- the questions ---------------------------------------------------------------------


def _plain(text: str) -> str:
    """A person's words made safe to sit inside a sentence template."""
    return text.replace("{", "(").replace("}", ")").strip().rstrip(".")


def morning_questions() -> list[dict[str, Any]]:
    return [
        # "pain" is the id the care metrics read a score from, so the morning
        # number joins the pain series as that day's morning reading.
        {"id": "pain", "prompt": "The morning after yesterday's session: how is the pain "
                                 "right now, 0 to 10?", "kind": "scale"},
        {"id": "stiffer", "prompt": "Stiffer than a usual morning?", "kind": "yes_no",
         "phrases": {"yes": "I'm stiffer than a usual morning.",
                     "no": "No stiffer than a usual morning."}},
    ]


def week_questions() -> list[dict[str, Any]]:
    return [
        {"id": "went", "prompt": "How did this week's training go, next to last week?",
         "kind": "choice", "options": ["better", "same", "worse"],
         "phrases": {"better": "This week went better than last week.",
                     "same": "This week went about the same as last week.",
                     "worse": "This week went worse than last week."}},
        {"id": "next_week", "prompt": "Anything different about next week? Travel, a meet, "
                                      "a busy stretch. Say \"nothing\" if not.", "kind": "text"},
    ]


def new_area_questions() -> list[dict[str, Any]]:
    return [
        {"id": "area", "prompt": "Where is the new pain?", "kind": "choice",
         "options": list(regions.AREAS), "phrase": "The new pain is here: {value}."},
        {"id": "side", "prompt": "Which side?", "kind": "choice",
         "options": list(regions.SIDE_OPTIONS), "phrase": "Side: {value}."},
        {"id": "note", "prompt": "Anything about it the clinic should know?", "kind": "text"},
    ]


def goals_questions(room: int = MAX_GOALS) -> list[dict[str, Any]]:
    prompts = [
        "Name one thing you want to get back to doing. Be specific: \"pull 315 from the "
        "floor\", \"squat to a box without the knee talking\".",
        "A second one, if there is one.",
        "And a third.",
    ]
    return [{"id": f"goal_{n + 1}", "prompt": prompts[n], "kind": "text"}
            for n in range(max(1, min(MAX_GOALS, room)))]


def function_questions(goals: list[FunctionGoal]) -> list[dict[str, Any]]:
    return [
        # The number goes first in the person's sentence: the goal is their
        # own words and may say "pain", and nothing that reads pain scores
        # out of a transcript should find one after it.
        {"id": f"goal_{g.id}", "kind": "scale",
         "prompt": f"{g.text}: how able are you to do it today? 0 is not at all, 10 is "
                   "like before.",
         "phrase": f"{{value}} out of 10 for: {_plain(g.text)}.",
         "phrase_zero": f"0 out of 10 for: {_plain(g.text)}. I can't do it at all."}
        for g in goals
    ]


def outcome_questions(instrument: str, goals: list[FunctionGoal]) -> list[dict[str, Any]]:
    i = INSTRUMENTS[instrument]
    if instrument == "nprs":
        return [{"id": "pain", "prompt": "How is your pain right now, 0 to 10?", "kind": "scale"}]
    if instrument == "psfs":
        return function_questions(goals)
    return [{
        "id": "total", "kind": "number", "min": int(i.low), "max": int(i.high),
        "prompt": f"Your {i.short} total, from the form the clinic gave you "
                  f"({int(i.low)} to {int(i.high)}).",
        "phrase": f"My {i.short} total is {{value}}.",
    }]


def hold_questions(kind: str) -> list[dict[str, Any]]:
    label, _unit, sided, _who = measures.KINDS[kind]
    out: list[dict[str, Any]] = [{
        "id": "seconds", "kind": "number", "min": 0, "max": 3600,
        "prompt": f"{label}: time it, then say how many seconds you held.",
        "phrase": f"{label}: {{value}} seconds.",
        "phrase_zero": f"{label}: I couldn't hold it today.",
    }]
    if sided:
        out.append({"id": "side", "prompt": "Which side?", "kind": "choice",
                    "options": ["left", "right"], "phrase": "Side: {value}."})
    return out


def handoff_questions(handoff: Handoff) -> list[dict[str, Any]]:
    who = handoff.trainer_name.strip() or "your trainer"
    return [{
        "id": "share", "kind": "yes_no",
        "prompt": f"Share your training limits with {who}? They get a page with the limits "
                  "your therapist wrote, this week's exercises and their caps, and what to "
                  "report back. Nothing else from your record.",
        "phrases": {"yes": f"Yes, share my training limits with {who}.",
                    "no": f"No, don't share my training limits with {who}."},
    }]


# --- asking ----------------------------------------------------------------------------


def open_ask(db: Session, patient_id: str, qset: str, ref: dict[str, Any] | None = None
             ) -> AdherenceTask | None:
    """The ask of this kind (about this same thing) the person has not
    answered yet, if there is one."""
    rows = db.scalars(
        select(AdherenceTask).where(
            AdherenceTask.patient_id == patient_id,
            AdherenceTask.active.is_(True),
            AdherenceTask.status.in_(tasks.OPEN_STATUSES),
        ).order_by(AdherenceTask.id.desc())
    ).all()
    for row in rows:
        payload = row.payload if isinstance(row.payload, dict) else {}
        if payload.get("qset") != qset:
            continue
        if ref is None or (payload.get("pt") or {}) == ref:
            return row
    return None


def ask(
    db: Session, patient: Patient, *, qset: str, title: str, why: str,
    questions: list[dict[str, Any]], ref: dict[str, Any] | None = None,
    notify: bool = True, base_url: str | None = None, created_by: str | None = None,
    due_at: datetime | None = None,
) -> tuple[AdherenceTask, dict[str, Any]]:
    """Put one ask in front of a person: in their app at once, and by text
    when their number can be texted. Returns the task and what came of the
    text (``{"sent", "detail", "reused"}``). The caller commits."""
    if qset not in QSETS:
        raise ValueError(f"Unknown ask: {qset}")
    if not questions:
        raise ValueError("An ask needs at least one question")
    existing = open_ask(db, patient.id, qset, ref)
    if existing is not None:
        return existing, {"sent": False, "detail": "already waiting for an answer", "reused": True}
    payload: dict[str, Any] = {"qset": qset, "questions": questions, "pt": ref or {}}
    if created_by:
        payload["created_by"] = created_by
    task = AdherenceTask(
        patient_id=patient.id, title=title[:120], why=(why or "")[:200] or "From your clinic",
        verified_by="self-report", kind="custom", status="pending",
        created_at=datetime.now(), due_at=due_at, payload=payload,
    )
    db.add(task)
    db.flush()
    text = {"sent": False, "detail": "in the app only", "reused": False}
    if notify:
        from app.hep.texts import cannot_text

        blocked = cannot_text(patient)
        if blocked is not None:
            text["detail"] = blocked[1]
        else:
            result = tasks.dispatch(db, task, patient, base_url or settings.checkin_base_url or "")
            text = {"sent": bool(result.sent), "detail": result.detail or "", "reused": False}
    return task, text


def close_ask(db: Session, task: AdherenceTask | None) -> None:
    """Withdraw an ask nobody needs answered any more (a handoff that was
    revoked before the person replied)."""
    if task is not None and task.status in tasks.OPEN_STATUSES:
        task.active = False
        task.status = "skipped"


def session_word(day: date, today: date) -> str:
    return "yesterday's" if (today - day).days == 1 else f"{day.strftime('%A')}'s"
