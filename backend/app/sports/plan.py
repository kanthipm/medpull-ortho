"""Today's plan for an athlete: the morning wellness check-in, the day's
recovery actions from the suggestion rules, a session log prompt when the
calendar has a practice or game, and the rehab block when there is an
active injury. Every item is an ``AdherenceTask`` through the same service
the clinic and personal tiers use, so completion, skipping and the thread
work unchanged.
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

CHECKIN_KEY = "sports_wellness"
MAX_ITEMS = 4

# The wellness questionnaire as a task question set, answered in the app
# (the Recovery tab's sheet writes the wellness rows directly; this task is
# the reminder and the text-channel path).
WELLNESS_QSET = "checkin_sports"
WELLNESS_QUESTIONS: list[dict[str, Any]] = [
    {"id": "sleep_quality", "prompt": "How did you sleep? 0 terrible, 10 great.", "kind": "scale"},
    {"id": "fatigue", "prompt": "How tired are you right now? 0 fresh, 10 exhausted.", "kind": "scale"},
    {"id": "soreness", "prompt": "How sore are your muscles? 0 none, 10 very sore.", "kind": "scale"},
    {"id": "stress", "prompt": "How stressed do you feel? 0 relaxed, 10 very.", "kind": "scale"},
    {"id": "mood", "prompt": "How is your mood? 0 low, 10 great.", "kind": "scale"},
    {"id": "pain", "prompt": "Any pain? Rate the worst spot, 0 to 10.", "kind": "scale"},
    {"id": "note", "prompt": "Anything your staff should know?", "kind": "text"},
]


def _tag(task: AdherenceTask) -> dict[str, Any]:
    payload = task.payload if isinstance(task.payload, dict) else {}
    t = payload.get("sports")
    return t if isinstance(t, dict) else {}


def _existing(db: Session, patient_id: str) -> list[AdherenceTask]:
    return list(db.scalars(
        select(AdherenceTask).where(AdherenceTask.patient_id == patient_id, AdherenceTask.active.is_(True))
        .order_by(AdherenceTask.id)
    ).all())


def ensure_checkin(db: Session, patient: Patient) -> AdherenceTask:
    for task in _existing(db, patient.id):
        if _tag(task).get("key") == CHECKIN_KEY:
            return task
    task, _ = tasks.create_task(
        db, patient, title="Morning wellness", why="Five questions, under a minute, read beside your overnight numbers.",
        kind="checkin", notify=False,
    )
    task.payload = {**(task.payload or {}), "qset": WELLNESS_QSET, "sports": {"key": CHECKIN_KEY},
                    "care": {"schedule": "daily", "assigned_by": "sports_plan"}}
    db.commit()
    return task


def _items_for(recovery: dict[str, Any], rehab: dict[str, Any], today: date) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    schedule = recovery.get("schedule") or {}
    verdict = recovery.get("verdict") or {}
    # Session log for what the calendar says is on today.
    for e in schedule.get("today") or []:
        if e["kind"] in ("practice", "game", "match", "lift", "shootaround", "conditioning", "training"):
            label = "Game" if e["kind"] in ("game", "match") else e["title"]
            items.append({"key": f"log_{e['kind']}_{e['date']}", "kind": "workout",
                          "title": f"Log {label.lower()}: minutes and RPE",
                          "why": "Your weekly load, monotony and the next-day readiness read all run on it."})
            break
    # The top suggestion as a task, when it has something to do.
    for s in (recovery.get("suggestions") or [])[:2]:
        if s["key"] in ("green", "saturation"):
            continue
        items.append({"key": f"tip_{s['key']}", "kind": "custom", "title": s["title"],
                      "why": s["why"][:200]})
        break
    # The rehab block.
    for board in (rehab.get("active") or [])[:1]:
        focus = [f for f in board.get("focus") or [] if f.get("kind") == "measure"]
        if focus:
            f = focus[0]
            title = f"Rehab: {f['title'].lower()}" if not f.get("missing") else f"Measure: {f['title']}"
            items.append({"key": f"rehab_{board['id']}_{f.get('measure_key', 'block')}", "kind": "exercise",
                          "title": title[:120], "why": (f.get("why") or "")[:200] or "Today's block from your plan."})
        else:
            phase = board.get("phase") or {}
            items.append({"key": f"rehab_{board['id']}_phase", "kind": "exercise",
                          "title": f"Rehab block: {phase.get('name', 'today')}"[:120],
                          "why": "; ".join((phase.get("goals") or [])[:2])[:200]})
    if verdict.get("kind") in ("rest", "modify") and not any(i["kind"] == "custom" for i in items):
        items.append({"key": "recover", "kind": "custom", "title": verdict.get("title", "Recover today"),
                      "why": (verdict.get("detail") or "")[:200]})
    return items[:MAX_ITEMS]


def ensure_daily_plan(db: Session, patient: Patient, recovery: dict[str, Any], rehab: dict[str, Any],
                      today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    checkin = ensure_checkin(db, patient)
    existing = _existing(db, patient.id)
    have = {(_tag(t).get("date"), _tag(t).get("key")) for t in existing}
    created: list[AdherenceTask] = []
    for item in _items_for(recovery, rehab, today):
        if (today.isoformat(), item["key"]) in have:
            continue
        task, _ = tasks.create_task(db, patient, title=item["title"], why=item["why"], kind=item["kind"],
                                    due_at=datetime.combine(today, time(23, 59)), notify=False)
        task.payload = {**(task.payload or {}),
                        "sports": {"key": item["key"], "date": today.isoformat(),
                                   "verdict": (recovery.get("verdict") or {}).get("kind")},
                        "care": {"schedule": "once", "assigned_by": "sports_plan"}}
        created.append(task)
    retired = 0
    for task in existing:
        tag = _tag(task)
        if tag.get("date") and tag["date"] < today.isoformat() and task.status in tasks.OPEN_STATUSES:
            task.active = False
            retired += 1
    db.commit()
    return {"checkin_id": checkin.id, "created": [t.id for t in created], "retired": retired}
