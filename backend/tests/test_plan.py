"""The care plan: library content, template CRUD, assignment through the
patient-app session's tasks, the plan read-back, data verification, message
templates and drafts — and the golden tiers afterwards."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.engine.care.pathways import PATHWAYS
from app.llm.insights import BANNED
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.checkin import Checkin
from app.models.enums import AdherenceStatus, RiskLevel
from app.models.library import CareAction, MessageTemplate, TaskTemplate, TaskVerification
from app.models.mobile import Message
from app.models.notification import Notification
from app.models.patient import Patient
from app.plan.library import LIBRARY, PINNED_DEFAULTS, applies_to, ensure_library
from app.plan.messages import MESSAGE_LIBRARY, ensure_message_library
from app.plan.service import PlanError, PlanItem, assign_plan, end_task
from app.plan.verification import verify_recent
from app.plan.verify_kinds import KIND_INFO, TASK_KINDS, VerifyKind
from app.tasks.service import KINDS

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


@pytest.fixture(scope="module")
def library(seeded_db):
    ensure_library(seeded_db)
    ensure_message_library(seeded_db)
    return seeded_db


@pytest.fixture()
def ledger(db):
    """The seeded database is session-scoped with no rollback: every row a
    test writes comes back out, and patient phones go back to what they were."""
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


def _care_task(db, patient_id, key=None, *, kind="steps_min", params=None, days_ago=0,
               schedule="daily"):
    """Assign one task (no text) and backdate it so verification has days."""
    patient = db.get(Patient, patient_id)
    item = PlanItem(template_key=key) if key else PlanItem(
        title="Test task", why="Because the test says so.", verify_kind=kind,
        params=params or {}, schedule=schedule,
    )
    result = assign_plan(db, patient, [item], notify=False)
    task = db.get(AdherenceTask, result["tasks"][0]["id"])
    if days_ago:
        assigned = date.today() - timedelta(days=days_ago)
        task.created_at = datetime.combine(assigned, datetime.min.time())
        task.payload = {**task.payload, "care": {**task.payload["care"],
                                                 "assigned_on": assigned.isoformat()}}
        db.commit()
    return task


# --- library ------------------------------------------------------------------------------


def test_library_is_seeded_complete_and_patient_safe(library):
    rows = library.scalars(select(TaskTemplate).where(TaskTemplate.key.is_not(None))).all()
    keys = [t.key for t in rows]
    assert len(rows) >= 60 and len(set(keys)) == len(keys)
    assert {t.key for t in LIBRARY} <= set(keys)
    for key in PINNED_DEFAULTS:
        assert next(t for t in rows if t.key == key).pinned
    for pathway in PATHWAYS.values():
        assert sum(1 for t in rows if applies_to(t.pathways, pathway)) >= 4, pathway.key
    for t in rows:
        assert VerifyKind(t.verify_kind) in KIND_INFO
        assert t.task_kind in KINDS and t.task_kind in TASK_KINDS
        assert not re.search(r"\d", t.title + t.why), t.key
        for text in (t.title, t.why, t.clinical_target):
            assert not BANNED.search(text), t.key
    assert {"UC1", "UC7", "UC8", "UC9", "UC10", "UC11", "UC12"} <= {t.use_case for t in rows}


def test_ensure_library_keeps_the_clinicians_state(library):
    t = library.scalar(select(TaskTemplate).where(TaskTemplate.key == "uc1_mid_one_flight"))
    original = (t.pinned, t.archived, t.usage_count, t.title)
    t.pinned, t.archived, t.usage_count, t.title = True, True, 7, "changed by hand"
    library.commit()
    assert ensure_library(library) == 0
    library.expire_all()
    t = library.scalar(select(TaskTemplate).where(TaskTemplate.key == "uc1_mid_one_flight"))
    assert (t.pinned, t.archived, t.usage_count) == (True, True, 7)
    assert t.title == original[3]  # wording follows the code
    t.pinned, t.archived, t.usage_count = original[:3]
    library.commit()


def test_template_crud_pin_archive_and_filters(client, library):
    created = client.post("/api/task-templates", json={
        "title": "Practise standing on the operated leg", "why": "Balance comes back with use.",
        "clinical_target": "Single-leg stance", "verify_kind": "custom",
        "pathways": ["ortho_tka"],
    })
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["source"] == "custom" and body["key"] is None and body["task_kind"] == "custom"
    tid = body["id"]
    assert client.patch(f"/api/task-templates/{tid}", json={"pinned": True}).json()["pinned"]
    listed = client.get("/api/task-templates?pathway=ortho_tka").json()
    assert tid in [t["id"] for t in listed["templates"]]
    assert tid not in [t["id"] for t in client.get(
        "/api/task-templates?pathway=heart_failure").json()["templates"]]
    assert {k["kind"] for k in listed["kinds"]} == {str(k) for k in VerifyKind}
    assert client.patch(f"/api/task-templates/{tid}", json={"archived": True}).json()["archived"]
    assert tid not in [t["id"] for t in client.get("/api/task-templates").json()["templates"]]
    assert tid in [t["id"] for t in client.get(
        "/api/task-templates?include_archived=true").json()["templates"]]
    walks = client.get("/api/task-templates?q=walk").json()["templates"]
    assert walks and all(
        "walk" in " ".join([t["title"], t["why"], t["clinical_target"], t["key"] or "",
                            t["verified_by"]]).lower()
        for t in walks
    )
    assert client.get("/api/task-templates?q=zzzz").json()["templates"] == []
    assert client.get("/api/task-templates?pathway=nope").status_code == 400
    assert client.post("/api/task-templates", json={
        "title": "We detected a problem", "why": "x", "verify_kind": "custom"}).status_code == 422
    assert client.patch("/api/task-templates/999999", json={"pinned": True}).status_code == 404


# --- assignment + plan ----------------------------------------------------------------------


def test_assign_plan_creates_their_tasks_with_care_payload(client, db, library, ledger):
    from app.engine.pipeline import compute_input_hash

    patient = db.get(Patient, "james")
    before = compute_input_hash(db, "james")
    template = db.scalar(select(TaskTemplate).where(TaskTemplate.key == "uc1_mid_step_band"))
    used = template.usage_count
    result = assign_plan(db, patient, [
        PlanItem(template_key="uc1_mid_step_band"),
        PlanItem(title="No kneeling on the new knee", why="It protects the joint while it heals.",
                 verify_kind="precaution", schedule="ongoing", save_as_template=True),
    ], notify=False)
    assert len(result["tasks"]) == 2
    assert result["delivery"] == {"channel": "none", "sent": False, "detail": "not requested"}
    db.expire_all()
    task = db.get(AdherenceTask, result["tasks"][0]["id"])
    assert task.kind == "walk" and task.active and task.status == "pending"
    care = task.payload["care"]
    assert care["template_key"] == "uc1_mid_step_band"
    assert care["verify"] == {"kind": "steps_band", "params": template.params}
    assert care["pathway"] == "ortho_tka" and care["assigned_by"] == "provider"
    assert task.verified_by == "step data"
    custom = db.get(AdherenceTask, result["tasks"][1]["id"])
    assert custom.kind == "custom" and custom.payload["care"]["verify"]["kind"] == "precaution"
    assert custom.verified_by == "self-report"
    assert db.get(TaskTemplate, template.id).usage_count == used + 1
    saved = db.scalar(select(TaskTemplate).where(TaskTemplate.title == "No kneeling on the new knee"))
    assert saved is not None and saved.source == "custom" and saved.pathways == ["ortho_tka"]
    assert compute_input_hash(db, "james") != before

    plan = client.get("/api/patients/james/plan").json()
    ids = {t["id"] for t in plan["tasks"]}
    assert {task.id, custom.id} <= ids
    row = next(t for t in plan["tasks"] if t["id"] == task.id)
    assert row["template_key"] == "uc1_mid_step_band" and len(row["last14"]) == 14
    assert row["last14"][-1]["date"] == date.today().isoformat()
    assert {"active", "rate", "verified", "self_attested", "missed"} <= set(plan["summary"])
    theirs = client.get("/api/patients/james/tasks").json()["tasks"]
    assert {task.id, custom.id} <= {t["id"] for t in theirs}
    db.delete(saved)
    db.commit()


def test_assign_plan_sends_one_summary_text(client, db, library, ledger, monkeypatch):
    from app.notifications import sendblue

    sent: list[tuple[str, str]] = []

    class _Resp:
        def json(self):
            return {"message_handle": "mh_plan"}

    monkeypatch.setattr(settings, "sendblue_api_key", "k")
    monkeypatch.setattr(settings, "sendblue_api_secret", "s")
    monkeypatch.setattr(sendblue, "_post_message",
                        lambda phone, content: sent.append((phone, content)) or _Resp())
    patient = db.get(Patient, "grace")
    patient.phone = "+15125550101"
    db.commit()
    messages_before = db.scalar(select(func.count(Message.id)).where(Message.patient_id == "grace"))
    body = client.post("/api/patients/grace/plan", json={
        "items": [{"template_key": "uc2_early_three_walks"}, {"template_key": "uc7_pain_am_pm"}],
        "notify": True,
    }).json()
    assert body["delivery"]["channel"] == "sms" and body["delivery"]["sent"] is True
    assert len(sent) == 1
    text = sent[0][1]
    assert text.startswith("Hi Grace — your care team added 2 tasks")
    assert "Reply 1" in text and len(text) <= 900
    assert not re.search(r"\d+ ?%|σ", text)  # counts in the wording, never metric values
    db.expire_all()
    rows = db.scalars(select(Message).where(Message.patient_id == "grace")
                      .order_by(Message.id.desc())).all()
    assert len(rows) == messages_before + 1
    assert rows[0].sender == "copilot" and rows[0].channel == "sms"
    assert rows[0].delivery_status == "sent" and rows[0].external_handle == "mh_plan"
    for t in body["tasks"]:
        assert t["status"] == "sent" and t["sent_at"] is not None


def test_assign_plan_rejects_bad_items(client, db, library):
    assert client.post("/api/patients/james/plan", json={
        "items": [{"template_key": "nope"}], "notify": False}).status_code == 422
    assert client.post("/api/patients/james/plan", json={
        "items": [{"title": "", "verify_kind": "custom"}], "notify": False}).status_code == 422
    assert client.post("/api/patients/james/plan", json={
        "items": [{"title": "We detected an infection", "verify_kind": "custom"}],
        "notify": False}).status_code == 422
    with pytest.raises(PlanError):
        assign_plan(db, db.get(Patient, "james"), [], notify=False)


def test_end_task_and_provider_record(client, db, library, ledger):
    task = _care_task(db, "elena", kind="custom", params={})
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    rec = client.post(f"/api/patients/elena/plan/{task.id}/record",
                      json={"date": yesterday, "status": "verified", "count": 1})
    assert rec.status_code == 200 and rec.json()["record"]["source"] == "provider"
    plan = client.get("/api/patients/elena/plan").json()
    row = next(t for t in plan["tasks"] if t["id"] == task.id)
    assert row["last14"][-2] == {"date": yesterday, "status": "verified", "source": "provider",
                                 "count": 1.0}
    assert client.post(f"/api/patients/aisha/plan/{task.id}/record",
                       json={"date": yesterday, "status": "verified"}).status_code == 404
    assert client.post(f"/api/patients/elena/plan/{task.id}/record",
                       json={"date": yesterday, "status": "nope"}).status_code == 422
    ended = client.post(f"/api/patients/elena/plan/{task.id}/end").json()
    assert ended["ok"] is True
    db.expire_all()
    task = db.get(AdherenceTask, task.id)
    assert task.active is False and task.status == "skipped"
    assert task.payload["care"]["ended_on"] == date.today().isoformat()
    assert task.id not in [t["id"] for t in client.get("/api/patients/elena/plan").json()["tasks"]]
    assert end_task(db, task.id).active is False


# --- verification ---------------------------------------------------------------------------


def test_steps_min_is_verified_and_missed_from_step_data(db, library, ledger):
    easy = _care_task(db, "james", kind="steps_min", params={"min_steps": 1}, days_ago=9)
    hard = _care_task(db, "james", kind="steps_min", params={"min_steps": 10_000_000},
                      days_ago=9)
    written = verify_recent(db, "james", date.today())
    db.commit()
    assert written > 0
    easy_rows = db.scalars(select(AdherenceRecord).where(AdherenceRecord.task_id == easy.id)).all()
    hard_rows = db.scalars(select(AdherenceRecord).where(AdherenceRecord.task_id == hard.id)).all()
    assert easy_rows and all(r.status == AdherenceStatus.VERIFIED for r in easy_rows)
    assert hard_rows and all(r.status == AdherenceStatus.MISSED for r in hard_rows)
    assert all(r.date >= date.today() - timedelta(days=9) for r in easy_rows + hard_rows)
    # today is never missed
    assert date.today() not in {r.date for r in hard_rows}
    notes = {n.date: n for n in db.scalars(
        select(TaskVerification).where(TaskVerification.task_id == easy.id)).all()}
    assert notes and all(n.source == "data:steps" and n.count > 0 for n in notes.values())
    # idempotent
    assert verify_recent(db, "james", date.today()) == 0


def test_weight_log_on_priya_is_verified_from_the_scale(db, library, ledger):
    task = _care_task(db, "priya", key="uc8_daily_weight", days_ago=6)
    verify_recent(db, "priya", date.today())
    db.commit()
    rows = db.scalars(select(AdherenceRecord).where(AdherenceRecord.task_id == task.id)).all()
    assert len(rows) >= 5 and all(r.status == AdherenceStatus.VERIFIED for r in rows)
    notes = db.scalars(select(TaskVerification).where(TaskVerification.task_id == task.id)).all()
    assert all(n.source == "data:body_weight" and 40 < n.count < 200 for n in notes)


def test_verification_never_downgrades_and_upgrades_self_reports(db, library, ledger):
    task = _care_task(db, "james", kind="steps_min", params={"min_steps": 1}, days_ago=5)
    day = date.today() - timedelta(days=2)
    # the app said "done" (self_attested); the data confirms -> upgraded
    db.add(AdherenceRecord(patient_id="james", task_id=task.id, date=day,
                           status=AdherenceStatus.SELF_ATTESTED))
    db.commit()
    verify_recent(db, "james", date.today())
    db.commit()
    row = db.scalar(select(AdherenceRecord).where(
        AdherenceRecord.task_id == task.id, AdherenceRecord.date == day))
    assert row.status == AdherenceStatus.VERIFIED
    # now make the target unreachable: verified rows stay verified, and a
    # self-report the data contradicts stays self-attested
    task.payload = {**task.payload, "care": {**task.payload["care"], "verify": {
        "kind": "steps_min", "params": {"min_steps": 10_000_000}}}}
    other = date.today() - timedelta(days=1)
    existing = db.scalar(select(AdherenceRecord).where(
        AdherenceRecord.task_id == task.id, AdherenceRecord.date == other))
    existing.status = AdherenceStatus.SELF_ATTESTED
    db.commit()
    verify_recent(db, "james", date.today())
    db.commit()
    db.expire_all()
    statuses = {r.date: r.status for r in db.scalars(
        select(AdherenceRecord).where(AdherenceRecord.task_id == task.id)).all()}
    assert statuses[day] == AdherenceStatus.VERIFIED
    assert statuses[other] == AdherenceStatus.SELF_ATTESTED


def test_verification_leaves_seed_rows_untouched(db, library, ledger):
    seeded = db.scalars(
        select(AdherenceTask).where(AdherenceTask.patient_id == "robert")
    ).all()
    seed_ids = [t.id for t in seeded if not (t.payload or {}).get("care")]
    before = {(r.task_id, r.date): str(r.status) for r in db.scalars(
        select(AdherenceRecord).where(AdherenceRecord.task_id.in_(seed_ids))).all()}
    assert before
    _care_task(db, "robert", kind="steps_min", params={"min_steps": 10_000_000}, days_ago=7)
    verify_recent(db, "robert", date.today())
    db.commit()
    after = {(r.task_id, r.date): str(r.status) for r in db.scalars(
        select(AdherenceRecord).where(AdherenceRecord.task_id.in_(seed_ids))).all()}
    assert after == before


def test_run_patient_hooks_verification(db, library, ledger):
    from app.engine.pipeline import run_patient

    task = _care_task(db, "elena", kind="overnight_wear", days_ago=4)
    assessment = run_patient(db, "elena", force=True)
    rows = db.scalars(select(AdherenceRecord).where(AdherenceRecord.task_id == task.id)).all()
    assert rows, "the pipeline hook wrote the overnight-wear records"
    care = assessment.analytics["care_metrics"]
    m14 = next(m for m in care["metrics"] if m["id"] == "M14")
    assert any(d["task_id"] == task.id for d in m14["drivers"])


# --- messages -------------------------------------------------------------------------------


def test_message_templates_seeded_crud_and_drafts(client, db, library, ledger):
    listed = client.get("/api/message-templates").json()
    keys = {t["key"] for t in listed["templates"]}
    assert {m.key for m in MESSAGE_LIBRARY} <= keys and len(keys) >= 13
    assert [t["key"] for t in listed["templates"] if t["pinned"]][:4] == [
        "msg_checkin_nudge", "msg_temperature_ask", "msg_walk_encourage", "msg_ice_elevate"]
    for t in listed["templates"]:
        assert not BANNED.search(t["body"])
    created = client.post("/api/message-templates", json={
        "title": "Bring the walker", "body": "Hi {first} — please bring your walker to clinic.",
        "tags": ["visit"]}).json()
    assert created["source"] == "custom" and created["pinned"] is False
    patched = client.patch(f"/api/message-templates/{created['id']}", json={"pinned": True}).json()
    assert patched["pinned"] is True
    assert client.post("/api/message-templates", json={
        "title": "x", "body": "We detected something serious."}).status_code == 422

    drafted = client.post("/api/patients/aisha/messages/draft",
                          json={"intent": "remind her to ice and elevate after walks",
                                "tone": "warm"}).json()
    assert drafted["provider"] == "fallback"
    assert drafted["message"].startswith("Hi Aisha — Dr. Alvarez's team here.")
    assert "reminder to ice and elevate after walks" in drafted["message"]
    direct = client.post("/api/patients/aisha/messages/draft",
                         json={"intent": "ask her to take her temperature", "tone": "direct"}
                         ).json()["message"]
    assert direct.startswith("Aisha, Dr. Alvarez's team:") and "your temperature?" in direct
    by_template = client.post("/api/patients/aisha/messages/draft",
                              json={"template_id": created["id"]}).json()
    assert by_template["message"] == "Hi Aisha — please bring your walker to clinic."
    assert by_template["template_id"] == created["id"]
    plain = client.post("/api/patients/robert/messages/draft", json={}).json()["message"]
    assert plain.startswith("Hi Robert") and not BANNED.search(plain)
    assert client.post("/api/patients/aisha/messages/draft",
                       json={"template_id": 999999}).status_code == 404
    template = db.get(MessageTemplate, created["id"])
    db.delete(template)
    db.commit()


# --- and the tiers -----------------------------------------------------------------------


def test_golden_tiers_unchanged_after_plan_activity(db):
    from app.engine.pipeline import ensure_current

    for patient_id, tier in GOLDEN.items():
        assessment = ensure_current(db, patient_id)
        assert assessment.risk_level == tier, f"{patient_id}: {assessment.risk_level} != {tier}"
