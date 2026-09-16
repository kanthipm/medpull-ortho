"""Actionable next steps: a deterministic planner from a patient's current
state to a ranked list of concrete steps, each carrying an executable
payload, and the executor behind the one-click buttons.

The planner is rules-based on purpose — every button does exactly what it
says — and the AI "suggested follow-up" wording is never its source. Steps
are keyed; executing or dismissing one writes a ``CareAction`` row that
marks the step done for its cooldown, so the row goes quiet instead of
nagging. At most four open steps are shown; executed ones follow with
their state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.care.pathways import Pathway, pathway_for
from app.models.enums import CareRole, NotificationChannel, RiskLevel
from app.models.insight import RiskAssessment
from app.models.library import CareAction, MessageTemplate, TaskTemplate
from app.models.mobile import Message
from app.models.notification import Notification
from app.models.patient import CareTeamMember, Patient
from app.notifications import sendblue
from app.plan.builder import phase_for, pick_template
from app.plan.library import templates_for_pathway
from app.plan.messages import MESSAGE_BY_KEY, fill_template
from app.plan.verify_kinds import VerifyKind as V

logger = logging.getLogger(__name__)

COOLDOWN_DAYS = {
    "message": 2, "send_checkin": 2, "assign_tasks": 14, "escalate": 3, "call": 1,
    "acknowledge": 1, "open": 1,
}
URGENCY_RANK = {"today": 0, "this_week": 1, "routine": 2}
MAX_OPEN = 4
CHECKIN_STALE_DAYS = 2
CHECKIN_TITLE = "Daily check-in"
CHECKIN_WHY = "A quick check-in helps your care team follow how you feel."
_HOW_FEELING = (
    "Hi {first} — Dr. {surgeon}'s team here. How are you feeling today? Any fever, chills or "
    "new pain? A quick reply helps us keep an eye on things."
)
_PACING = (
    "Hi {first} — Dr. {surgeon}'s team here. You've been doing a lot — great effort. For the "
    "next few days keep walks a little shorter and spread them out, and put your feet up "
    "afterwards. Steady beats big."
)
_PERSONAL = (
    "Hi {first} — Dr. {surgeon}'s team here. How are you feeling about the plan? If it's a lot "
    "right now, tell us — we can make it simpler."
)
_WEIGHT_ASK = (
    "Hi {first} — Dr. {surgeon}'s team here. Your weight has moved up quickly. Could you weigh "
    "yourself now and tell us the reading, and let us know about any swelling in your legs or "
    "breathlessness lying flat?"
)
_GLUCOSE_REMIND = (
    "Hi {first} — Dr. {surgeon}'s team here. Your sugar readings have been out of range more "
    "often. Could you log a reading before breakfast and before dinner today, and tell us "
    "about any lows?"
)


@dataclass
class Step:
    key: str
    title: str
    detail: str
    urgency: str
    source: list[str]
    action: dict[str, Any]
    rank: int
    clicks: int = 1
    state: dict[str, Any] = field(default_factory=lambda: {
        "status": "open", "executed_at": None, "result": None,
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "title": self.title, "detail": self.detail,
            "urgency": self.urgency, "source": list(self.source), "clicks": self.clicks,
            "action": dict(self.action), "state": dict(self.state),
        }


# --- evidence helpers ---------------------------------------------------------------------


class _Evidence:
    def __init__(self, assessment: RiskAssessment | None) -> None:
        self.assessment = assessment
        analytics = (assessment.analytics if assessment is not None else {}) or {}
        self.reasons = {r.get("code"): r for r in (assessment.reasons if assessment else [])
                        if isinstance(r, dict)}
        care = analytics.get("care_metrics") or {}
        self.metrics = {m.get("id"): m for m in care.get("metrics", []) if isinstance(m, dict)}
        self.level = str(assessment.risk_level) if assessment is not None else "missing_data"
        self.postop_day = analytics.get("postop_day")

    def has(self, *codes: str) -> list[str]:
        return [c for c in codes if c in self.reasons]

    def status(self, metric_id: str) -> str:
        return str((self.metrics.get(metric_id) or {}).get("status") or "nodata")

    def status_text(self, metric_id: str) -> str:
        return str((self.metrics.get(metric_id) or {}).get("status_text") or "")

    def flagged(self, *ids: str, watch: bool = False) -> list[str]:
        wanted = ("flag", "watch") if watch else ("flag",)
        return [i for i in ids if self.status(i) in wanted]

    def reason_text(self, *codes: str) -> str:
        for code in codes:
            r = self.reasons.get(code)
            if r and r.get("text"):
                return str(r["text"]).rstrip(".") + "."
        return ""

    def finding(self, *ids: str) -> str:
        """The first sentence of the most relevant finding: a flagged or
        watched metric first, then any computed one."""
        for wanted in (("flag", "watch"), ("ok",)):
            for metric_id in ids:
                m = self.metrics.get(metric_id)
                if m and m.get("status") in wanted and m.get("finding"):
                    first = str(m["finding"]).split(". ")[0].rstrip(".")
                    return first + "."
        return ""


def _detail(*parts: str) -> str:
    return " ".join(p for p in parts if p).strip()


def _prefill(template_key: str | None, patient: Patient, fallback: str = "") -> str:
    spec = MESSAGE_BY_KEY.get(template_key or "")
    return fill_template(spec.body if spec else fallback, patient)


def _message(key: str, title: str, detail: str, urgency: str, source: list[str],
             patient: Patient, template_key: str | None, rank: int,
             fallback: str = "") -> Step:
    return Step(
        key, title, detail, urgency, source,
        {"type": "message", "prefill": _prefill(template_key, patient, fallback),
         "template_key": template_key}, rank, clicks=2,
    )


def _assign(key: str, title: str, detail: str, urgency: str, source: list[str],
            keys: list[str], rank: int) -> Step:
    return Step(key, title, detail, urgency, source,
                {"type": "assign_tasks", "template_keys": keys, "notify": True}, rank)


def _open(key: str, title: str, detail: str, urgency: str, source: list[str], target: str,
          rank: int) -> Step:
    return Step(key, title, detail, urgency, source, {"type": "open", "target": target}, rank)


# --- the planner ----------------------------------------------------------------------------


def _keys(templates: list[TaskTemplate], pathway: Pathway, phase: str,
          *kinds: V) -> list[str]:
    """Library keys for the kinds a step assigns. Another pathway's entry is
    the last resort — a heart-failure patient whose pressure is above target
    gets the hypertension library's AM/PM log, not nothing."""
    out: list[str] = []
    for kind in kinds:
        t = pick_template(templates, pathway, kind, phase, any_pathway=True)
        if t is not None and t.key and t.key not in out:
            out.append(t.key)
    return out


def _rules(
    patient: Patient, ev: _Evidence, pathway: Pathway, templates: list[TaskTemplate],
    active_keys: set[str], last_checkin_at: datetime | None, today: date,
) -> list[Step]:
    steps: dict[str, Step] = {}
    phase = phase_for(ev.postop_day)
    chronic = not pathway.uses_expected_curve
    # No operation, no incision and no expected curve to be behind.
    surgical = str(patient.procedure_type) != "NONE"
    rank = 0

    def add(step: Step) -> None:
        if step.key in steps:
            return
        if step.action["type"] == "assign_tasks":
            # Templates already on the plan are not assigned twice. A step
            # with nothing left is kept here so a recent execution can still
            # show as done; plan_next_steps drops it otherwise.
            keys = [k for k in step.action["template_keys"] if k not in active_keys]
            step.action["template_keys"] = keys
        steps[step.key] = step

    # 1. coupled deterioration
    r1 = ev.has("COMPOSITE_HIGH") + ev.flagged("M12", "M13")
    if r1:
        rank += 1
        detail = _detail(ev.reason_text("COMPOSITE_HIGH"), ev.finding("M12", "M13"))
        # The step stands whether or not a number is on file — the care team
        # can have one the chart does not. `tel` is None then, and the
        # console renders it as "no number on file" rather than a dial link.
        add(Step("call_today", "Call the patient today", detail, "today", r1,
                 {"type": "call", "tel": patient.phone}, rank))
        add(_message(
            "msg_fever_incision",
            "Ask about fever and breathing" if chronic else "Ask about fever, breathing and the incision",
            detail, "today", r1, patient,
            "msg_breathing_check" if chronic else "msg_temperature_ask", rank))
        add(Step("escalate_triage", "Escalate to nurse triage", detail, "today", r1,
                 {"type": "escalate"}, rank))

    # 2. single vitals moving
    vitals = ev.has("TEMP_RISING", "RHR_RISING", "RR_RISING", "SPO2_LOW")
    if vitals and not r1:
        rank += 1
        for code in vitals:
            detail = _detail(ev.reason_text(code), ev.finding("M12", "M13", "M10"))
            if code == "TEMP_RISING":
                # Only a surgical patient has an incision to ask about; the
                # chronic and general pathways get the same question without it.
                add(_message("msg_fever_incision",
                             "Ask about fever" if chronic or not surgical
                             else "Ask about fever and the incision",
                             detail, "today", [code, "M13"], patient,
                             "msg_temperature_ask", rank))
            elif code == "RHR_RISING":
                add(_message("msg_how_feeling", "Ask how they are feeling today", detail,
                             "today", [code, "M12"], patient, None, rank, _HOW_FEELING))
            else:
                add(_message("msg_breathing_ask", "Ask about breathing", detail, "today",
                             [code, "M12"], patient, "msg_breathing_check", rank))
        add(_open("open_m12", "Review the deterioration index",
                  _detail(ev.finding("M12"), "Open the multi-signal view to see which signals moved."),
                  "today", vitals + ["M12"], "full_stats:M12", rank))

    # 3. behind / stalled
    stalled = ev.has("TRAJECTORY_BEHIND", "STEPS_FALLING")
    if ev.status_text("M1") in ("Stalled progression", "Load collapsing"):
        stalled.append("M1")
    if ev.status("M18") == "flag":
        stalled.append("M18")
    if stalled:
        rank += 1
        detail = _detail(ev.reason_text("TRAJECTORY_BEHIND", "STEPS_FALLING"),
                         ev.finding("M1", "M17", "M18"))
        walk = V.WALK_BOUTS if phase == "early" else V.GUIDED_WALK
        add(_assign("assign_graded_activity", "Restart graded activity", detail, "this_week",
                    stalled, _keys(templates, pathway, phase, V.STEPS_BAND, walk), rank))
        add(_message("msg_walk_encourage", "Encourage walking", detail, "this_week", stalled,
                     patient, "msg_walk_encourage", rank))

    # 4. overreaching
    over = []
    if ev.status_text("M1") in ("Overreaching vs tolerance band", "Above tolerance band"):
        over.append("M1")
    over += ev.flagged("M2")
    if over:
        rank += 1
        detail = _detail(ev.finding("M1", "M2"))
        add(_assign("assign_cap_load", "Cap the load for a few days", detail, "this_week", over,
                    _keys(templates, pathway, phase, V.STEPS_BAND), rank))
        add(_message("msg_pacing", "Send a pacing note", detail, "this_week", over, patient,
                     None, rank, _PACING))

    # 5. gait
    gait = ev.has("GAIT_ASYMMETRY_HIGH") + ev.flagged("M3")
    if gait:
        rank += 1
        detail = _detail(ev.reason_text("GAIT_ASYMMETRY_HIGH"), ev.finding("M3"))
        add(_open("open_m3_gait", "Review gait with PT", detail, "this_week", gait,
                  "full_stats:M3", rank))
        add(_assign("assign_guided_walk", "Assign the guided walk", detail, "this_week", gait,
                    _keys(templates, pathway, phase, V.GUIDED_WALK), rank))

    # 6. nights
    nights = ev.has("SLEEP_DISRUPTED") + ev.flagged("M9", watch=True)
    if nights:
        rank += 1
        detail = _detail(ev.reason_text("SLEEP_DISRUPTED"), ev.finding("M9"))
        add(_message("msg_night_pain", "Check on night pain", detail, "this_week", nights,
                     patient, "msg_sleep_position", rank))
        add(_assign("assign_night_tracking", "Track nights and evening pain", detail,
                    "this_week", nights,
                    _keys(templates, pathway, phase, V.OVERNIGHT_WEAR, V.PAIN_LOG), rank))

    # 7. coverage
    coverage = ev.has("LOW_COVERAGE") + ev.flagged("M16", watch=True)
    if coverage:
        rank += 1
        detail = _detail(ev.reason_text("LOW_COVERAGE"), ev.finding("M16"))
        add(_message("msg_device_nudge", "Nudge the device sync", detail, "this_week", coverage,
                     patient, "msg_device_sync", rank))
        add(_assign("assign_overnight_wear", "Assign overnight wear", detail, "this_week",
                    coverage, _keys(templates, pathway, phase, V.OVERNIGHT_WEAR), rank))
        add(_open("open_wearables", "Check the wearable connection", detail, "this_week",
                  coverage, "wearables", rank))

    # 8. check-in overdue
    days_since = (today - last_checkin_at.date()).days if last_checkin_at else None
    if days_since is None or days_since >= CHECKIN_STALE_DAYS:
        rank += 1
        detail = (f"Last check-in {days_since} days ago." if days_since is not None
                  else "No check-in on record yet.")
        title = "Send today's check-in" if patient.phone else "Open check-in link"
        add(Step("send_checkin", title,
                 _detail(detail, "" if patient.phone else "No phone on file — the link opens "
                         "the check-in without a text."),
                 "today" if ev.level == str(RiskLevel.HIGH) else "this_week",
                 ["CHECKIN_OVERDUE"], {"type": "send_checkin", "sms": bool(patient.phone)},
                 rank))

    # 9. adherence
    adherence = ev.has("ADHERENCE_LOW") + ev.flagged("M14")
    if adherence:
        rank += 1
        detail = _detail(ev.reason_text("ADHERENCE_LOW"), ev.finding("M14"))
        add(_message("msg_exercise_nudge", "Nudge the exercise plan", detail, "this_week",
                     adherence, patient, "msg_exercise_nudge", rank))
        add(_open("open_plan", "Review the plan", detail, "this_week", adherence, "plan", rank))

    # 10. disengagement
    if ev.status("M15") == "flag":
        rank += 1
        detail = _detail(ev.finding("M15"))
        add(_message("msg_personal_checkin", "Send a personal check-in", detail, "this_week",
                     ["M15"], patient, None, rank, _PERSONAL))
        add(Step("send_checkin", "Send today's check-in" if patient.phone else "Open check-in link",
                 detail, "this_week", ["M15"],
                 {"type": "send_checkin", "sms": bool(patient.phone)}, rank))

    # 11. chronic vitals
    if ev.status("C1") == "flag":
        rank += 1
        detail = _detail(ev.finding("C1"))
        add(Step("call_today", "Call the patient today", detail, "today", ["C1"],
                 {"type": "call", "tel": patient.phone}, rank))
        add(_message("msg_weight_ask", "Ask about weight and fluid", detail, "today", ["C1"],
                     patient, None, rank, _WEIGHT_ASK))
    if ev.status("C2") == "flag":
        rank += 1
        detail = _detail(ev.finding("C2"))
        add(Step("call_today", "Call the patient today", detail, "today", ["C2"],
                 {"type": "call", "tel": patient.phone}, rank))
        add(_message("msg_breathing_ask", "Ask about breathing", detail, "today", ["C2"],
                     patient, "msg_breathing_check", rank))
    if ev.status("C3") == "flag":
        rank += 1
        detail = _detail(ev.finding("C3"))
        add(_message("msg_glucose_reminder", "Remind about glucose logs", detail, "this_week",
                     ["C3"], patient, None, rank, _GLUCOSE_REMIND))
        add(_assign("assign_glucose_log", "Assign the glucose log", detail, "this_week", ["C3"],
                    _keys(templates, pathway, phase, V.GLUCOSE_LOG), rank))
    if ev.status("C4") == "flag":
        rank += 1
        detail = _detail(ev.finding("C4"))
        add(_message("msg_bp_reminder", "Remind about blood-pressure logs", detail, "this_week",
                     ["C4"], patient, "msg_bp_reminder", rank))
        add(_assign("assign_bp_log", "Assign the blood-pressure log", detail, "this_week",
                    ["C4"], _keys(templates, pathway, phase, V.BP_LOG), rank))

    # 12. nothing else and low risk
    if not steps and ev.level == str(RiskLevel.LOW):
        add(Step("ack_on_track", "On track — no action needed",
                 _detail(ev.reason_text("ON_TRACK"), "Routine monitoring continues."),
                 "routine", ["ON_TRACK"], {"type": "acknowledge"}, 99))
    return list(steps.values())


def _recent_actions(db: Session, patient_id: str, now: datetime) -> dict[str, CareAction]:
    since = now - timedelta(days=max(COOLDOWN_DAYS.values()))
    rows = db.scalars(
        select(CareAction)
        .where(CareAction.patient_id == patient_id, CareAction.executed_at >= since)
        .order_by(CareAction.executed_at.desc(), CareAction.id.desc())
    ).all()
    latest: dict[str, CareAction] = {}
    for row in rows:
        latest.setdefault(row.step_key, row)
    return latest


def _last_checkin(db: Session, patient_id: str) -> datetime | None:
    from sqlalchemy import func

    from app.models.checkin import Checkin

    return db.scalar(select(func.max(Checkin.occurred_at)).where(Checkin.patient_id == patient_id))


def plan_next_steps(
    db: Session, patient: Patient, assessment: RiskAssessment | None, *,
    today: date | None = None, now: datetime | None = None,
    last_checkin_at: datetime | None = None, templates: list[TaskTemplate] | None = None,
    include_done: bool = True,
) -> list[dict[str, Any]]:
    """The ranked steps for one patient: open ones first (urgency, then rule
    order, at most four), then executed/dismissed ones with their state."""
    from app.plan.service import active_template_keys

    now = now or datetime.now()
    today = today or now.date()
    pathway = pathway_for(patient)
    # The whole library, not the pathway's slice: pick_template ranks the
    # pathway's own entries first and crosses over only when it has none.
    if templates is None:
        templates = templates_for_pathway(db, None)
    else:
        templates = [t for t in templates if not t.archived]
    if last_checkin_at is None:
        last_checkin_at = _last_checkin(db, patient.id)
    active = active_template_keys(db, patient.id)
    steps = _rules(patient, _Evidence(assessment), pathway, templates, active, last_checkin_at,
                   today)
    recent = _recent_actions(db, patient.id, now)
    open_steps, done_steps = [], []
    for step in steps:
        action = recent.get(step.key)
        cooldown = timedelta(days=COOLDOWN_DAYS.get(action.action_type, 1)) if action else None
        exhausted = step.action["type"] == "assign_tasks" and not step.action["template_keys"]
        if exhausted and (action is None or now - action.executed_at >= cooldown):
            continue  # every template is already an active task
        if action is not None and now - action.executed_at < cooldown:
            step.state = {
                "status": "dismissed" if action.dismissed else "done",
                "executed_at": action.executed_at.isoformat(),
                "result": action.result,
            }
            done_steps.append(step)
        else:
            open_steps.append(step)
    open_steps.sort(key=lambda s: (URGENCY_RANK.get(s.urgency, 3), s.rank))
    done_steps.sort(key=lambda s: s.state["executed_at"] or "", reverse=True)
    chosen = open_steps[:MAX_OPEN] + (done_steps if include_done else [])
    return [s.to_dict() for s in chosen]


def next_step_summary(
    db: Session, patient: Patient, assessment: RiskAssessment | None, *,
    last_checkin_at: datetime | None = None, templates: list[TaskTemplate] | None = None,
) -> tuple[dict[str, Any] | None, int]:
    steps = plan_next_steps(db, patient, assessment, last_checkin_at=last_checkin_at,
                            templates=templates, include_done=False)
    return (steps[0] if steps else None), len(steps)


# --- execution ---------------------------------------------------------------------------------


def _find_step(db: Session, patient: Patient, key: str) -> dict[str, Any] | None:
    from app.engine.pipeline import ensure_current

    assessment = ensure_current(db, patient.id)
    for step in plan_next_steps(db, patient, assessment):
        if step["key"] == key:
            return step
    return None


def _log(db: Session, patient: Patient, key: str, action_type: str, result: dict[str, Any],
         executed_by: str, dismissed: bool = False) -> CareAction:
    row = CareAction(patient_id=patient.id, step_key=key, action_type=action_type,
                     executed_at=datetime.now(), executed_by=executed_by, result=result,
                     dismissed=dismissed)
    db.add(row)
    db.commit()
    return row


def _execute_message(db: Session, patient: Patient, action: dict[str, Any],
                     override: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(override.get("text") or action.get("prefill") or "").split())
    if not text:
        raise ValueError("Nothing to send")
    message = Message(patient_id=patient.id, sender="care_team",
                      sender_id=patient.assigned_provider_id, channel="console", text=text)
    db.add(message)
    delivery = None
    if patient.phone:
        delivery = sendblue.send_sms(patient.phone, f"From your MedPull care team: {text}")
        message.delivery_status = "sent" if delivery.sent else "failed"
        message.delivery_detail = None if delivery.sent else delivery.detail
        message.external_handle = delivery.message_handle
    template_key = action.get("template_key")
    if template_key:
        template = db.scalar(select(MessageTemplate).where(MessageTemplate.key == template_key))
        if template is not None:
            template.usage_count = int(template.usage_count or 0) + 1
    db.flush()
    if delivery is not None and delivery.sent:
        status = "sent_sms"
    elif patient.phone:
        status = "stored_sms_failed"
    else:
        status = "stored_app_only"
    return {"message_id": message.id, "status": status,
            "detail": delivery.detail if delivery else "patient has no phone number on file"}


def _execute_assign(db: Session, patient: Patient, action: dict[str, Any],
                    override: dict[str, Any], base_url: str, executed_by: str) -> dict[str, Any]:
    from app.plan.service import PlanItem, assign_plan

    keys = override.get("template_keys") or action.get("template_keys") or []
    if not keys:
        raise ValueError("No tasks to assign")
    notify = bool(override.get("notify", action.get("notify", True)))
    result = assign_plan(db, patient, [PlanItem(template_key=k) for k in keys], notify=notify,
                         base_url=base_url, created_by=executed_by)
    return {"task_ids": [t["id"] for t in result["tasks"]], "delivery": result["delivery"]}


def _execute_checkin(db: Session, patient: Patient, base_url: str,
                     executed_by: str) -> dict[str, Any]:
    from app.tasks.service import create_task, mint_token, task_url

    task, sms = create_task(
        db, patient, title=CHECKIN_TITLE, why=CHECKIN_WHY, kind="checkin",
        notify=bool(patient.phone), base_url=base_url, created_by=executed_by,
    )
    result: dict[str, Any] = {"task_id": task.id,
                              "sms": {"sent": sms.sent, "detail": sms.detail} if sms else None}
    if not patient.phone:
        # No text goes out; the clinician gets the tokenized link to hand over.
        token = mint_token(task)
        db.commit()
        result["url"] = task_url(base_url, token) if base_url else None
    return result


def _execute_escalate(db: Session, patient: Patient, step: dict[str, Any]) -> dict[str, Any]:
    body = step.get("detail") or "Provider requested review"
    recipients = [patient.assigned_provider_id]
    nurse = db.scalar(
        select(CareTeamMember).where(CareTeamMember.role == CareRole.NURSE)
        .order_by(CareTeamMember.id)
    )
    if nurse is not None and nurse.id not in recipients:
        recipients.append(nurse.id)
    ids: list[int] = []
    for recipient in recipients:
        notification = Notification(
            patient_id=patient.id, recipient_id=recipient, kind="escalation",
            title=f"{patient.name} — escalated by provider", body=body[:400],
            channel=NotificationChannel.IN_APP,
        )
        db.add(notification)
        db.flush()
        ids.append(notification.id)
    return {"notification_ids": ids}


def execute_step(
    db: Session, patient: Patient, key: str, *, override: dict[str, Any] | None = None,
    base_url: str = "", executed_by: str = "provider",
) -> dict[str, Any]:
    step = _find_step(db, patient, key)
    if step is None:
        raise LookupError(f"No next step {key!r} for this patient")
    override = override or {}
    action = step["action"]
    kind = action["type"]
    if kind == "message":
        result = _execute_message(db, patient, action, override)
    elif kind == "assign_tasks":
        result = _execute_assign(db, patient, action, override, base_url, executed_by)
    elif kind == "send_checkin":
        result = _execute_checkin(db, patient, base_url, executed_by)
    elif kind == "escalate":
        result = _execute_escalate(db, patient, step)
    elif kind == "call":
        result = {"note": str(override.get("note") or "Call logged")[:400],
                  "tel": action.get("tel")}
    elif kind == "open":
        result = {"target": action.get("target")}
    else:
        result = {"note": str(override.get("note") or "Reviewed")[:400]}
    row = _log(db, patient, key, kind, result, executed_by)
    step["state"] = {"status": "done", "executed_at": row.executed_at.isoformat(),
                     "result": result}
    return {"ok": True, "step": step, "result": result}


def complete_step(db: Session, patient: Patient, key: str, result: dict[str, Any] | None,
                  executed_by: str = "provider") -> dict[str, Any]:
    """Log a step the client performed itself (a message sent through the
    composer, a view opened)."""
    step = _find_step(db, patient, key)
    action_type = step["action"]["type"] if step else "message"
    row = _log(db, patient, key, action_type, dict(result or {}), executed_by)
    return {"ok": True, "key": key, "executed_at": row.executed_at.isoformat()}


def dismiss_step(db: Session, patient: Patient, key: str,
                 executed_by: str = "provider") -> dict[str, Any]:
    step = _find_step(db, patient, key)
    action_type = step["action"]["type"] if step else "acknowledge"
    _log(db, patient, key, action_type, {"note": "Not now"}, executed_by, dismissed=True)
    return {"ok": True, "key": key}


__all__ = [
    "COOLDOWN_DAYS", "MAX_OPEN", "plan_next_steps", "next_step_summary", "execute_step",
    "complete_step", "dismiss_step",
]
