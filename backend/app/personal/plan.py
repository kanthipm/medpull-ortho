"""Today's plan for a subscriber: the morning check-in plus one or two
things to do, written from the day's verdict and the goal.

Everything is an ``AdherenceTask`` created through ``tasks.create_task``,
so the app's Tasks screen, the text conversation, completion, skipping and
the adherence engine all work unchanged. The check-in is one recurring row
(``payload.care.schedule = daily``, the care-plan convention); the day's
other items are one-shot rows tagged with the day they were written for, so
writing the plan twice on one morning adds nothing.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.adherence import AdherenceTask
from app.models.patient import Patient
from app.tasks import service as tasks

logger = logging.getLogger(__name__)

CHECKIN_KEY = "personal_checkin"
MAX_ITEMS = 2


def _personal(task: AdherenceTask) -> dict[str, Any]:
    payload = task.payload if isinstance(task.payload, dict) else {}
    tag = payload.get("personal")
    return tag if isinstance(tag, dict) else {}


def _existing(db: Session, patient_id: str) -> list[AdherenceTask]:
    return list(db.scalars(
        select(AdherenceTask).where(
            AdherenceTask.patient_id == patient_id, AdherenceTask.active.is_(True)
        ).order_by(AdherenceTask.id)
    ).all())


def ensure_checkin(db: Session, patient: Patient, profile: Any) -> AdherenceTask:
    """The one recurring morning check-in, created on first call."""
    for task in _existing(db, patient.id):
        if _personal(task).get("key") == CHECKIN_KEY:
            return task
    qset = "checkin_personal_recovery" if getattr(profile, "goal", "") == "recovery" \
        else "checkin_personal"
    task, _ = tasks.create_task(
        db, patient, title="Morning check-in",
        why="Two minutes on how you feel, read beside your wearable numbers.",
        kind="checkin", notify=False,
    )
    task.payload = {
        **(task.payload or {}),
        "qset": qset,
        "personal": {"key": CHECKIN_KEY},
        "care": {"schedule": "daily", "assigned_by": "personal_plan"},
    }
    db.commit()
    return task


def _bedtime_text(dashboard: dict[str, Any], earlier_minutes: int) -> str:
    sleep = (dashboard.get("panels") or {}).get("sleep") or {}
    usual = (sleep.get("extra") or {}).get("mean_bedtime") or "22:30"
    try:
        hh, mm = (int(x) for x in usual.split(":"))
    except ValueError:
        hh, mm = 22, 30
    total = (hh * 60 + mm - earlier_minutes) % 1440
    h, m = divmod(total, 60)
    suffix = "pm" if h >= 12 else "am"
    h12 = h - 12 if h > 12 else (12 if h == 0 else h)
    return f"{h12}:{m:02d} {suffix}"


def _items_for(dashboard: dict[str, Any], profile: Any) -> list[dict[str, Any]]:
    """(key, title, why, kind) for today, from the verdict and the goal."""
    goal = getattr(profile, "goal", None) or "everyday"
    sport = (getattr(profile, "sport", None) or "").strip()
    verdict = dashboard.get("verdict") or {}
    kind = verdict.get("kind", "steady")
    reason = verdict.get("reason") or ""
    sleep = (dashboard.get("panels") or {}).get("sleep") or {}
    debt = (sleep.get("extra") or {}).get("debt_hours") or 0.0
    items: list[dict[str, Any]] = []
    session_name = f"{sport} session" if sport else "session"

    if goal == "recovery":
        if kind == "push":
            items.append({"key": "rehab_progress", "kind": "exercise",
                          "title": "Rehab set, one step up",
                          "why": reason or "Recovery signals are above your normal."})
        elif kind == "rest":
            items.append({"key": "rehab_rom", "kind": "exercise",
                          "title": "Range of motion only today",
                          "why": reason or "Your body is asking for a lighter day."})
        elif kind == "easy":
            items.append({"key": "rehab_easy", "kind": "exercise",
                          "title": "Rehab set as written, nothing extra",
                          "why": reason})
        else:
            items.append({"key": "rehab_plan", "kind": "exercise",
                          "title": "Rehab set as written", "why": reason})
        items.append({"key": "walk", "kind": "walk", "title": "A walk at an easy pace",
                      "why": "Steady loading is what a healing joint responds to."})
    elif goal == "performance":
        if kind == "push":
            items.append({"key": "quality", "kind": "workout",
                          "title": f"Quality {session_name}",
                          "why": reason or "Green light from your recovery signals."})
        elif kind == "steady":
            items.append({"key": "planned", "kind": "workout",
                          "title": f"Train as planned: {session_name}" if sport
                          else "Train as planned", "why": reason})
        elif kind == "easy":
            items.append({"key": "easy", "kind": "workout",
                          "title": "Easy 30 to 40 min, conversational pace",
                          "why": reason})
        else:
            items.append({"key": "rest", "kind": "custom",
                          "title": "Recovery day: mobility and a walk", "why": reason})
    elif goal == "sleep":
        items.append({"key": "bedtime", "kind": "sleep",
                      "title": f"Lights out by {_bedtime_text(dashboard, 30 if debt >= 2 else 0)}",
                      "why": (f"You are carrying {debt:.1f} h of sleep debt." if debt >= 1
                              else "A fixed bedtime is the lever that regularises sleep.")})
        if kind in ("push", "steady"):
            items.append({"key": "daylight", "kind": "walk",
                          "title": "20 minutes outside before noon",
                          "why": "Morning light anchors the clock that sets tonight's bedtime."})
    else:  # everyday
        if kind == "push":
            items.append({"key": "move_hard", "kind": "workout",
                          "title": "Get a proper workout in",
                          "why": reason or "Your recovery signals are above your normal."})
        elif kind == "rest":
            items.append({"key": "move_light", "kind": "walk",
                          "title": "A gentle walk, nothing more", "why": reason})
        else:
            items.append({"key": "move", "kind": "walk", "title": "30 minutes of movement",
                          "why": reason or "Consistency beats intensity."})

    if goal != "sleep" and debt >= 2.0:
        items.append({"key": "bedtime", "kind": "sleep",
                      "title": f"Lights out by {_bedtime_text(dashboard, 30)}",
                      "why": f"You are {debt:.1f} h behind on sleep this week."})
    return items[:MAX_ITEMS]


def ensure_daily_plan(db: Session, patient: Patient, profile: Any,
                      dashboard: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Write today's plan if it is not there yet. Returns what is open today."""
    today = today or date.today()
    checkin = ensure_checkin(db, patient, profile)
    existing = _existing(db, patient.id)
    have = {(_personal(t).get("date"), _personal(t).get("key")) for t in existing}
    created: list[AdherenceTask] = []
    for item in _items_for(dashboard, profile):
        if (today.isoformat(), item["key"]) in have:
            continue
        task, _ = tasks.create_task(
            db, patient, title=item["title"], why=item["why"], kind=item["kind"],
            due_at=datetime.combine(today, time(23, 59)), notify=False,
        )
        task.payload = {
            **(task.payload or {}),
            "personal": {"key": item["key"], "date": today.isoformat(),
                         "verdict": (dashboard.get("verdict") or {}).get("kind")},
            "care": {"schedule": "once", "assigned_by": "personal_plan"},
        }
        created.append(task)
    # Yesterday's unanswered one-shot items are retired rather than left to
    # pile up: a plan is for a day.
    retired = 0
    for task in existing:
        tag = _personal(task)
        if tag.get("date") and tag["date"] < today.isoformat() and task.status in tasks.OPEN_STATUSES:
            task.active = False
            retired += 1
    db.commit()
    return {"checkin_id": checkin.id, "created": [t.id for t in created], "retired": retired}
