"""The morning run: for every subscriber who is entitled, write today's plan,
generate the brief, put it on their thread, and text it when they asked.

Two callers. The app itself, when a subscriber opens it (``POST
/mobile/personal/day``), so a person who never opted into texts still
gets their plan; and the scheduled Lambda invoke (``{"action":
"personal_daily"}``, EventBridge, once a morning), so the text arrives
before they open anything. Both are idempotent for a day: the plan writer
skips items it already wrote, and the brief is one thread line per day.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.mobile import Message
from app.models.patient import Patient
from app.models.personal import PersonalProfile
from app.notifications import sendblue
from app.personal import archive, insights, plan, subscription
from app.personal.data import load_personal_data
from app.personal.metrics import compute_dashboard
from app.personal.scope import PERSONAL

logger = logging.getLogger(__name__)

# How many subscribers may reach the model in one scheduled run. The run
# holds the write lock; past the budget the deterministic brief is used and
# the app fills the model's version on the person's first open.
LLM_BUDGET = 6
TIME_BUDGET_S = 20.0

BRIEF_TAG = "personal_brief"


def _brief_today(db: Session, patient_id: str, today: date) -> Message | None:
    start = datetime.combine(today, datetime.min.time())
    return db.scalar(
        select(Message).where(
            Message.patient_id == patient_id, Message.sender == "copilot",
            Message.created_at >= start, Message.action_kind == BRIEF_TAG,
        ).limit(1)
    )


def start_day(db: Session, patient: Patient, profile: PersonalProfile, *,
              today: date | None = None, allow_llm: bool = True, text: bool = False) -> dict[str, Any]:
    """One subscriber's morning. Returns the dashboard, brief and plan."""
    today = today or date.today()
    data = load_personal_data(db, patient, today)
    dashboard = compute_dashboard(data, patient, profile)
    dashboard["notes"] = data.notes
    written = plan.ensure_daily_plan(db, patient, profile, dashboard, today)
    brief = insights.get_brief(db, patient, profile, dashboard, allow_llm=allow_llm)
    line = _brief_today(db, patient.id, today)
    delivery: sendblue.CheckinSendResult | None = None
    if line is None:
        from app.models.adherence import AdherenceTask

        checkin = db.get(AdherenceTask, written["checkin_id"])
        body = brief["brief"]
        line = Message(
            patient_id=patient.id, sender="copilot", channel="app", text=body,
            authored_by="ai", action_kind=BRIEF_TAG, action_task_id=checkin.id if checkin else None,
            action_label="Start check-in",
        )
        db.add(line)
        if text and profile.sms_briefs and patient.phone and sendblue.configured():
            sms = sendblue.compose(f"{body}\n\nReply 1 for your morning check-in.",
                                   patient_name=patient.name)
            delivery = sendblue.send_sms(patient.phone, sms)
            line.channel = "sms"
            line.delivery_status = "sent" if delivery.sent else "failed"
            line.delivery_detail = None if delivery.sent else delivery.detail
            line.external_handle = delivery.message_handle
            if delivery.sent and checkin is not None:
                # "1" starts the most recently texted task by text.
                checkin.status = "sent"
                checkin.sent_at = datetime.now()
        db.commit()
    # The day's record for the lake: readouts, verdict, brief, plan, the
    # log so far. Overwritten by the next call the same day.
    archive.archive_day(
        patient, today, dashboard=dashboard, brief=brief, plan=written,
        logs={key: [{"date": d.isoformat(), "value": v} for d, v in s.items()
                    if d >= today - timedelta(days=7)] for key, s in data.logs.items()},
    )
    return {"dashboard": dashboard, "brief": brief, "plan": written,
            "texted": bool(delivery and delivery.sent)}


def run(db: Session, today: date | None = None, *, text: bool = True) -> dict[str, Any]:
    """Every entitled subscriber, within a time budget."""
    today = today or date.today()
    started = time.monotonic()
    rows = db.execute(
        select(Patient, PersonalProfile)
        .join(PersonalProfile, PersonalProfile.patient_id == Patient.id)
        .where(Patient.account_kind == PERSONAL)
        .order_by(Patient.id)
    ).all()
    done: list[str] = []
    skipped: list[str] = []
    texted = 0
    llm_spent = 0
    for patient, profile in rows:
        if time.monotonic() - started > TIME_BUDGET_S:
            skipped.append(patient.id)
            continue
        if not subscription.entitled(db, patient):
            skipped.append(patient.id)
            continue
        try:
            result = start_day(db, patient, profile, today=today,
                               allow_llm=llm_spent < LLM_BUDGET, text=text)
            if result["brief"].get("provider") not in (None, "fallback"):
                llm_spent += 1
            texted += int(result["texted"])
            done.append(patient.id)
        except Exception:  # noqa: BLE001 — one subscriber must not stop the run
            logger.exception("personal daily failed for %s", patient.id)
            db.rollback()
            skipped.append(patient.id)
    return {"date": today.isoformat(), "done": done, "skipped": skipped, "texted": texted}
