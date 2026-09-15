"""The next-step planner on synthetic assessments (each rule, ranking,
cooldown/dedupe), the execute endpoints, the worklist rows, the guardrail on
every string, and the golden tiers afterwards."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.llm.insights import BANNED
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.checkin import Checkin
from app.models.enums import RiskLevel
from app.models.library import CareAction, TaskVerification
from app.models.mobile import Message
from app.models.notification import Notification
from app.models.patient import Patient
from app.plan import next_steps as ns
from app.plan.library import ensure_library
from app.plan.messages import ensure_message_library
from app.plan.next_steps import COOLDOWN_DAYS, MAX_OPEN, plan_next_steps

GOLDEN = {
    "steve": RiskLevel.MISSING_DATA, "guest": RiskLevel.MISSING_DATA,
    "priya": RiskLevel.MISSING_DATA, "linda": RiskLevel.MEDIUM, "robert": RiskLevel.MEDIUM,
    "sofia": RiskLevel.MEDIUM, "aisha": RiskLevel.MEDIUM, "grace": RiskLevel.LOW,
    "david": RiskLevel.LOW, "james": RiskLevel.LOW, "elena": RiskLevel.LOW,
}
_LEDGER_MODELS = (
    AdherenceRecord, TaskVerification, AdherenceTask, Message, Notification, CareAction,
    Checkin,
)
NOW = datetime(2026, 9, 14, 9, 0)


@pytest.fixture(scope="module")
def library(seeded_db):
    ensure_library(seeded_db)
    ensure_message_library(seeded_db)
    return seeded_db


@pytest.fixture()
def ledger(db):
    marks = {model: (db.scalar(select(func.max(model.id))) or 0) for model in _LEDGER_MODELS}
    phones = {p.id: p.phone for p in db.scalars(select(Patient)).all()}
    yield
    db.expire_all()
    for model, mark in marks.items():
        for row in db.scalars(select(model).where(model.id > mark)).all():
            db.delete(row)
    for patient in db.scalars(select(Patient)).all():
        patient.phone = phones[patient.id]
    db.commit()


def _assessment(codes=(), level="medium", metrics=None, postop_day=15):
    reasons = [{"code": c, "text": f"{c.replace('_', ' ').capitalize()} vs baseline",
                "metric_type": None, "severity": 2} for c in codes]
    metric_rows = [
        {"id": mid, "status": status, "status_text": text, "finding": finding}
        for mid, (status, text, finding) in (metrics or {}).items()
    ]
    return SimpleNamespace(
        reasons=reasons, risk_level=level,
        analytics={"postop_day": postop_day, "care_metrics": {"metrics": metric_rows}},
    )


NEVER = NOW - timedelta(days=400)  # the planner reads None as "look it up"


def _plan(db, patient_id, assessment, *, last_checkin=NOW, **kw):
    return plan_next_steps(db, db.get(Patient, patient_id), assessment, now=NOW,
                           last_checkin_at=last_checkin, **kw)


def _open(steps):
    return [s for s in steps if s["state"]["status"] == "open"]


def test_rule_coupled_deterioration(db, library):
    steps = _plan(db, "aisha", _assessment(["COMPOSITE_HIGH"], "high", {
        "M12": ("flag", "Deviating from baseline — review",
                "Today's physiologic state sits 3.4σ from Aisha's own stable baseline.")}))
    keys = [s["key"] for s in steps]
    assert keys[:3] == ["call_today", "msg_fever_incision", "escalate_triage"]
    call, msg, esc = steps[:3]
    assert call["action"]["type"] == "call" and call["urgency"] == "today"
    assert "3.4σ" in call["detail"] and "COMPOSITE_HIGH" in call["source"]
    assert msg["action"]["type"] == "message" and msg["clicks"] == 2
    assert msg["action"]["prefill"].startswith("Hi Aisha — Dr. Alvarez's team")
    assert msg["action"]["template_key"] == "msg_temperature_ask"
    assert esc["action"] == {"type": "escalate"}


def test_rule_single_vital_opens_the_index(db, library):
    steps = _plan(db, "aisha", _assessment(["TEMP_RISING"]))
    keys = [s["key"] for s in steps]
    assert "msg_fever_incision" in keys and "open_m12" in keys and "call_today" not in keys
    opened = next(s for s in steps if s["key"] == "open_m12")
    assert opened["action"] == {"type": "open", "target": "full_stats:M12"}
    rhr = _plan(db, "aisha", _assessment(["RHR_RISING", "SPO2_LOW"]))
    assert {"msg_how_feeling", "msg_breathing_ask", "open_m12"} <= {s["key"] for s in rhr}


def test_rule_behind_assigns_graded_activity(db, library):
    steps = _plan(db, "aisha", _assessment(["TRAJECTORY_BEHIND"], postop_day=20))
    assign = next(s for s in steps if s["key"] == "assign_graded_activity")
    assert assign["action"]["template_keys"] == ["uc2_mid_step_band", "uc2_mid_guided_walk"]
    assert assign["action"]["notify"] is True and assign["urgency"] == "this_week"
    assert any(s["key"] == "msg_walk_encourage" for s in steps)
    early = _plan(db, "grace", _assessment(["STEPS_FALLING"], postop_day=3))
    assign = next(s for s in early if s["key"] == "assign_graded_activity")
    assert assign["action"]["template_keys"] == ["uc2_mid_step_band", "uc2_early_three_walks"]
    stalled = _plan(db, "aisha", _assessment([], metrics={
        "M1": ("watch", "Stalled progression", "The last 7 days averaged 1,200 steps/day.")}))
    assert any(s["key"] == "assign_graded_activity" for s in stalled)


def test_rules_overreach_gait_nights_coverage_adherence_disengagement(db, library):
    over = _plan(db, "aisha", _assessment([], metrics={
        "M1": ("flag", "Overreaching vs tolerance band", "Load has run past the band.")}))
    assert [s["key"] for s in _open(over)][:2] == ["assign_cap_load", "msg_pacing"]
    gait = _plan(db, "aisha", _assessment(["GAIT_ASYMMETRY_HIGH"]))
    assert {"open_m3_gait", "assign_guided_walk"} <= {s["key"] for s in gait}
    nights = _plan(db, "aisha", _assessment(["SLEEP_DISRUPTED"]))
    tracking = next(s for s in nights if s["key"] == "assign_night_tracking")
    assert tracking["action"]["template_keys"] == ["uc2_overnight_wear", "uc2_pain_precaution"]
    assert any(s["action"].get("template_key") == "msg_sleep_position" for s in nights)
    coverage = _plan(db, "aisha", _assessment(["LOW_COVERAGE"], "missing_data"))
    assert [s["key"] for s in coverage][:3] == [
        "msg_device_nudge", "assign_overnight_wear", "open_wearables"]
    adherence = _plan(db, "aisha", _assessment(["ADHERENCE_LOW"]))
    assert {"msg_exercise_nudge", "open_plan"} <= {s["key"] for s in adherence}
    disengaged = _plan(db, "aisha", _assessment([], metrics={
        "M15": ("flag", "Disengaging", "Disengagement score 70/100.")}))
    assert {"msg_personal_checkin", "send_checkin"} <= {s["key"] for s in disengaged}


def test_rule_chronic_vitals(db, library):
    patient = db.get(Patient, "priya")
    patient.care_pathway = "heart_failure"
    db.commit()
    try:
        steps = _plan(db, "priya", _assessment([], metrics={
            "C1": ("flag", "Rapid weight gain — review", "Weight is up 2.3 kg in 7 days.")}))
        assert [s["key"] for s in steps][:2] == ["call_today", "msg_weight_ask"]
        assert "2.3 kg" in steps[0]["detail"]
        bp = _plan(db, "priya", _assessment([], metrics={
            "C4": ("flag", "Above target — for review", "7-day mean 152/94.")}))
        assign = next(s for s in bp if s["key"] == "assign_bp_log")
        assert assign["action"]["template_keys"] == ["uc11_bp_am_pm"]
        glucose = _plan(db, "priya", _assessment([], metrics={
            "C3": ("flag", "Time-in-range low — review", "TIR 42%.")}))
        assert {"msg_glucose_reminder", "assign_glucose_log"} <= {s["key"] for s in glucose}
    finally:
        patient.care_pathway = None
        db.commit()


def test_rule_checkin_overdue_and_on_track(db, library, ledger):
    stale = _plan(db, "grace", _assessment([], "low"), last_checkin=NOW - timedelta(days=3))
    checkin = next(s for s in stale if s["key"] == "send_checkin")
    assert checkin["title"] == "Open check-in link" and checkin["action"]["sms"] is False
    assert "3 days ago" in checkin["detail"]
    grace = db.get(Patient, "grace")
    grace.phone = "+15125550101"
    db.commit()
    with_phone = _plan(db, "grace", _assessment([], "high"), last_checkin=NEVER)
    checkin = next(s for s in with_phone if s["key"] == "send_checkin")
    assert checkin["title"] == "Send today's check-in" and checkin["urgency"] == "today"
    fresh = _plan(db, "grace", _assessment(["ON_TRACK"], "low"))
    assert [s["key"] for s in fresh] == ["ack_on_track"]
    assert fresh[0]["action"] == {"type": "acknowledge"} and fresh[0]["urgency"] == "routine"


def test_ranking_caps_open_steps_and_orders_by_urgency(db, library):
    steps = _plan(db, "aisha", _assessment(
        ["TRAJECTORY_BEHIND", "SLEEP_DISRUPTED", "LOW_COVERAGE", "ADHERENCE_LOW", "TEMP_RISING"]),
        last_checkin=NOW - timedelta(days=5))
    assert len(steps) == MAX_OPEN
    urgencies = [s["urgency"] for s in steps]
    assert urgencies == sorted(urgencies, key=lambda u: {"today": 0, "this_week": 1}[u])
    assert steps[0]["key"] == "msg_fever_incision"


def test_cooldown_marks_executed_steps_done_and_lists_them_after(db, library, ledger):
    assessment = _assessment(["TRAJECTORY_BEHIND", "LOW_COVERAGE"])
    db.add(CareAction(patient_id="aisha", step_key="assign_graded_activity",
                      action_type="assign_tasks", executed_at=NOW - timedelta(days=3),
                      executed_by="ct_alvarez", result={"task_ids": [1]}))
    db.add(CareAction(patient_id="aisha", step_key="msg_walk_encourage", action_type="message",
                      executed_at=NOW - timedelta(days=1), executed_by="ct_alvarez",
                      result={}, dismissed=True))
    db.commit()
    steps = _plan(db, "aisha", assessment)
    states = {s["key"]: s["state"]["status"] for s in steps}
    assert states["assign_graded_activity"] == "done"
    assert states["msg_walk_encourage"] == "dismissed"
    keys = [s["key"] for s in steps]
    assert keys.index("assign_graded_activity") > max(
        i for i, s in enumerate(steps) if s["state"]["status"] == "open")
    # past the cooldown the message step is open again, the assignment is not
    later = plan_next_steps(db, db.get(Patient, "aisha"), assessment,
                            now=NOW + timedelta(days=COOLDOWN_DAYS["message"] + 1),
                            last_checkin_at=NOW)
    states = {s["key"]: s["state"]["status"] for s in later}
    assert states["msg_walk_encourage"] == "open" and states["assign_graded_activity"] == "done"


def test_executed_assign_step_stays_visible_as_done(db, library, ledger):
    """Executing an assign step makes its templates active, which would
    otherwise remove the step; the executed state wins for the cooldown."""
    from app.plan.service import PlanItem, assign_plan

    assign_plan(db, db.get(Patient, "aisha"), [
        PlanItem(template_key="uc2_mid_step_band"), PlanItem(template_key="uc2_mid_guided_walk"),
    ], notify=False)
    db.add(CareAction(patient_id="aisha", step_key="assign_graded_activity",
                      action_type="assign_tasks", executed_at=NOW - timedelta(hours=1),
                      executed_by="ct_alvarez", result={"task_ids": []}))
    db.commit()
    steps = _plan(db, "aisha", _assessment(["TRAJECTORY_BEHIND"], postop_day=20))
    step = next(s for s in steps if s["key"] == "assign_graded_activity")
    assert step["state"]["status"] == "done" and step["action"]["template_keys"] == []


def test_assign_steps_skip_templates_already_active(db, library, ledger):
    from app.plan.service import PlanItem, assign_plan

    assign_plan(db, db.get(Patient, "aisha"), [
        PlanItem(template_key="uc2_mid_step_band"), PlanItem(template_key="uc2_mid_guided_walk"),
    ], notify=False)
    steps = _plan(db, "aisha", _assessment(["TRAJECTORY_BEHIND"], postop_day=20))
    assert "assign_graded_activity" not in {s["key"] for s in steps}
    assert "msg_walk_encourage" in {s["key"] for s in steps}


# --- endpoints -----------------------------------------------------------------------------


def test_execute_assign_tasks_creates_their_tasks(client, db, library, ledger):
    steps = client.get("/api/patients/robert/next-steps").json()
    assert steps["generated_at"]
    step = next(s for s in steps["steps"] if s["action"]["type"] == "assign_tasks"
                and s["state"]["status"] == "open")
    executed = client.post(f"/api/patients/robert/next-steps/{step['key']}/execute", json={})
    assert executed.status_code == 200, executed.text
    body = executed.json()
    assert body["ok"] and body["step"]["state"]["status"] == "done"
    ids = body["result"]["task_ids"]
    assert len(ids) == len(step["action"]["template_keys"])
    db.expire_all()
    for task_id, key in zip(ids, step["action"]["template_keys"]):
        task = db.get(AdherenceTask, task_id)
        assert task.patient_id == "robert" and task.payload["care"]["template_key"] == key
    again = client.get("/api/patients/robert/next-steps").json()["steps"]
    assert next(s for s in again if s["key"] == step["key"])["state"]["status"] == "done"
    assert client.post("/api/patients/robert/next-steps/nope/execute", json={}).status_code == 404


def test_execute_send_checkin_with_and_without_phone(client, db, library, ledger):
    # priya has no recent check-in on record, so the step is offered
    priya = db.get(Patient, "priya")
    priya.phone = None
    db.commit()
    body = client.post("/api/patients/priya/next-steps/send_checkin/execute", json={})
    assert body.status_code == 200, body.text
    result = body.json()["result"]
    task = db.get(AdherenceTask, result["task_id"])
    assert task.kind == "checkin" and task.title == "Daily check-in"
    assert result["sms"] is None and result["url"].startswith("http") and "/t/" in result["url"]
    db.expire_all()
    priya = db.get(Patient, "priya")
    priya.phone = "+15125550177"
    db.commit()
    # within the cooldown the step shows as done and can still be re-run
    body = client.post("/api/patients/priya/next-steps/send_checkin/execute", json={}).json()
    assert body["result"]["sms"] == {"sent": False, "detail": "Sendblue keys not configured"}
    assert db.get(AdherenceTask, body["result"]["task_id"]).status == "pending"


def test_execute_escalate_message_acknowledge_complete_dismiss(client, db, library, ledger,
                                                                monkeypatch):
    aisha = db.get(Patient, "aisha")
    aisha.phone = None  # another suite enrolls her with a number; the ledger restores it
    db.commit()
    synthetic = {
        "escalate_triage": {"key": "escalate_triage", "title": "Escalate", "detail": "Signals moved.",
                            "action": {"type": "escalate"}},
        "msg_fever_incision": {"key": "msg_fever_incision", "title": "Ask", "detail": "",
                               "action": {"type": "message", "prefill": "Hi Aisha — how is it?",
                                          "template_key": "msg_temperature_ask"}},
        "ack_on_track": {"key": "ack_on_track", "title": "On track", "detail": "",
                         "action": {"type": "acknowledge"}},
        "call_today": {"key": "call_today", "title": "Call", "detail": "",
                       "action": {"type": "call", "tel": None}},
    }
    monkeypatch.setattr(ns, "_find_step", lambda db, patient, key: synthetic.get(key))

    esc = client.post("/api/patients/aisha/next-steps/escalate_triage/execute", json={}).json()
    ids = esc["result"]["notification_ids"]
    assert len(ids) == 2
    rows = [db.get(Notification, i) for i in ids]
    assert {r.recipient_id for r in rows} == {aisha.assigned_provider_id, "ct_torres"}
    assert all(r.kind == "escalation" and r.body == "Signals moved." for r in rows)

    msg = client.post("/api/patients/aisha/next-steps/msg_fever_incision/execute",
                      json={"payload_override": {"text": "Hi Aisha — quick question."}}).json()
    assert msg["result"]["status"] == "stored_app_only"
    message = db.get(Message, msg["result"]["message_id"])
    assert message.sender == "care_team" and message.text == "Hi Aisha — quick question."

    ack = client.post("/api/patients/aisha/next-steps/ack_on_track/execute", json={}).json()
    assert ack["result"] == {"note": "Reviewed"}
    call = client.post("/api/patients/aisha/next-steps/call_today/execute",
                       json={"payload_override": {"note": "Spoke to her son"}}).json()
    assert call["result"]["note"] == "Spoke to her son"

    done = client.post("/api/patients/aisha/next-steps/msg_fever_incision/complete",
                       json={"result": {"message_id": 1, "status": "sent_sms"}}).json()
    assert done["ok"] and done["executed_at"]
    dismissed = client.post("/api/patients/aisha/next-steps/ack_on_track/dismiss").json()
    assert dismissed == {"ok": True, "key": "ack_on_track"}
    db.expire_all()
    actions = db.scalars(select(CareAction).where(CareAction.patient_id == "aisha")
                         .order_by(CareAction.id)).all()
    assert [a.action_type for a in actions[-6:]] == [
        "escalate", "message", "acknowledge", "call", "message", "acknowledge"]
    assert actions[-1].dismissed is True and actions[-2].dismissed is False


def test_worklist_rows_carry_the_top_step(client, library):
    rows = client.get("/api/worklist").json()["patients"]
    assert rows
    for row in rows:
        assert "next_step" in row and isinstance(row["next_steps_open"], int)
        if row["next_step"] is not None:
            assert row["next_step"]["state"]["status"] == "open"
            assert {"key", "title", "action", "urgency"} <= set(row["next_step"])
    assert any(r["next_step"] is not None for r in rows)
    on_track = [r for r in rows if r["priority"] == "low"]
    assert on_track and all(r["next_step"]["key"] == "ack_on_track" for r in on_track)


def test_every_step_string_passes_the_guardrail(client, library):
    for patient_id in GOLDEN:
        for step in client.get(f"/api/patients/{patient_id}/next-steps").json()["steps"]:
            for text in (step["title"], step["detail"], step["action"].get("prefill", "")):
                assert not BANNED.search(text), (patient_id, step["key"], text)


def test_golden_tiers_unchanged_after_next_steps(db):
    from app.engine.pipeline import ensure_current

    for patient_id, tier in GOLDEN.items():
        assert ensure_current(db, patient_id).risk_level == tier, patient_id
