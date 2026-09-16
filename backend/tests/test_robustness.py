"""What has to keep working when something goes wrong.

One patient's failure must not empty the worklist; a plan must not half
assign; a recompute must not grow the database without bound; a narrative
must not claim an operation the patient never had; a reseed must not delete
real people. Each test here pins one of those.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.models.adherence import AdherenceTask
from app.models.insight import Insight, RiskAssessment
from app.models.mobile import Message, PatientSession
from app.models.patient import Patient


# --- the worklist ------------------------------------------------------------------


def test_one_broken_patient_does_not_empty_the_worklist(client, db, monkeypatch):
    from app.api import worklist as worklist_api

    real = worklist_api.ensure_fresh_assessment

    def explode(session, patient_id):
        if patient_id == "linda":
            raise RuntimeError("engine blew up")
        return real(session, patient_id)

    monkeypatch.setattr(worklist_api, "ensure_fresh_assessment", explode)
    body = client.get("/api/worklist").json()
    rows = {r["id"]: r for r in body["patients"]}
    # every patient is still listed, including the one that failed
    assert body["stats"]["total"] == len(rows)
    assert "steve" in rows and "linda" in rows
    broken = rows["linda"]
    assert broken["priority"] == "missing_data"
    assert "unavailable" in broken["reason"].lower()
    assert broken["next_step"] is None
    # and the healthy rows are unaffected
    assert rows["steve"]["data_confidence"]["level"] in {"low", "medium", "high"}


def test_a_failed_briefing_still_serves_the_roster(client, monkeypatch):
    from app.api import worklist as worklist_api

    monkeypatch.setattr(
        worklist_api, "get_daily_briefing", None, raising=False
    )  # attribute is imported inside the handler; patch the source instead
    from app.llm import insights

    def explode(db):
        raise RuntimeError("groq is down and the fallback broke")

    monkeypatch.setattr(insights, "get_daily_briefing", explode)
    body = client.get("/api/worklist").json()
    assert body["patients"], "the roster is the point of the screen"
    assert body["briefing"]["provider"] == "unavailable"
    assert body["briefing"]["text"] == ""


def test_the_worklist_bounds_how_many_model_calls_one_request_makes(client, db, monkeypatch):
    """A cold cache misses for every patient at once; a dozen sequential Groq
    calls behind a 30 s edge timeout is a worklist that times out."""
    from app.api import worklist as worklist_api
    from app.llm import insights

    calls: list[str] = []
    real = insights.get_patient_insight

    def counted(session, kind, patient_id, *, allow_llm=True):
        if allow_llm:
            calls.append(patient_id)
        return real(session, kind, patient_id, allow_llm=allow_llm)

    monkeypatch.setattr(worklist_api, "get_patient_insight", counted, raising=False)
    # a cold cache for every patient
    db.execute(delete(Insight))
    db.commit()
    client.get("/api/worklist")
    assert len(calls) <= worklist_api.LLM_BUDGET


# --- the engine --------------------------------------------------------------------


def test_recomputing_does_not_grow_the_assessment_table_without_bound(db):
    from app.engine.pipeline import KEEP_ASSESSMENTS, latest_assessment, run_patient

    before = latest_assessment(db, "grace")
    assert before is not None
    for _ in range(KEEP_ASSESSMENTS + 4):
        run_patient(db, "grace", force=True)
    rows = db.scalars(
        select(RiskAssessment).where(RiskAssessment.patient_id == "grace")
        .order_by(RiskAssessment.computed_at.desc())
    ).all()
    assert len(rows) == KEEP_ASSESSMENTS
    # the newest is kept, and it is the one every reader resolves to
    assert latest_assessment(db, "grace").id == rows[0].id


def test_ending_a_task_invalidates_the_stored_assessment(db):
    """Neither `active` nor `status` moves any row count, so the input hash
    used to be blind to a plan the provider had just changed."""
    from app.engine.pipeline import compute_input_hash, ensure_current
    from app.plan.service import end_task

    task = AdherenceTask(
        patient_id="grace", title="Temporary task", why="test", verified_by="self-report",
        kind="custom", status="pending", created_at=datetime.now(),
        payload={"care": {"schedule": "daily", "verify": {"kind": "custom", "params": {}}}},
    )
    db.add(task)
    db.commit()
    ensure_current(db, "grace")
    before = compute_input_hash(db, "grace")
    end_task(db, task.id)
    assert compute_input_hash(db, "grace") != before
    db.expire_all()
    assert db.get(AdherenceTask, task.id).active is False
    db.execute(delete(AdherenceTask).where(AdherenceTask.id == task.id))
    db.commit()


def test_ending_a_task_closes_its_text_conversation(db):
    from app.plan.service import end_task
    from app.tasks import service as tasks

    task = AdherenceTask(
        patient_id="grace", title="Half-answered by text", why="test",
        verified_by="self-report", kind="walk", status="sent", created_at=datetime.now(),
        sent_at=datetime.now(),
    )
    db.add(task)
    db.commit()
    tasks.start_conversation(task)
    db.commit()
    assert isinstance((task.payload or {}).get("sms"), dict)
    end_task(db, task.id)
    db.expire_all()
    task = db.get(AdherenceTask, task.id)
    # nothing is left for the patient to answer about a retired task
    assert (task.payload or {}).get("sms") is None
    assert task.active is False
    db.execute(delete(AdherenceTask).where(AdherenceTask.id == task.id))
    db.commit()


# --- the plan ----------------------------------------------------------------------


def test_a_plan_with_one_bad_item_assigns_nothing(client, db):
    """Resolution used to run inside the creation loop, so item three failing
    left items one and two committed and texted behind a 422."""
    before = db.scalar(select(func.count(AdherenceTask.id)).where(AdherenceTask.patient_id == "grace"))
    resp = client.post("/api/patients/grace/plan", json={"items": [
        {"title": "Perfectly fine task", "task_kind": "walk", "verify_kind": "steps_min",
         "params": {"steps": 500}, "schedule": "daily"},
        {"template_key": "no-such-template-key"},
    ], "notify": False})
    assert resp.status_code == 422
    db.expire_all()
    after = db.scalar(select(func.count(AdherenceTask.id)).where(AdherenceTask.patient_id == "grace"))
    assert after == before, "a rejected plan must leave no tasks behind"


# --- narratives --------------------------------------------------------------------


def test_a_patient_without_surgery_is_never_described_as_post_op(db):
    from app.llm import fallback
    from app.llm.insights import _header
    from app.models.enums import InsightKind, RiskLevel

    general = db.get(Patient, "medha")
    assert str(general.procedure_type) == "NONE"
    header = _header(general, 6)
    assert header["surgical"] is False
    for level in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.MISSING_DATA):
        analytics = {
            "postop_day": 6,
            "risk": {"level": str(level), "reasons": []},
            "trajectory": {"state": "behind", "pct": -20.0},
            "confidence": {"score": 0.2, "level": "low"},
            "adherence": {},
        }
        text = fallback.patient_summary(header, analytics)["summary"]
        assert "post-op" not in text.lower(), (level, text)
        assert "expected curve" not in text.lower(), (level, text)
    # the surgical wording is unchanged for a patient who did have surgery
    surgical_header = _header(db.get(Patient, "grace"), 6)
    assert surgical_header["surgical"] is True
    surgical_text = fallback.patient_summary(surgical_header, {
        "postop_day": 6, "risk": {"level": "low", "reasons": []},
        "trajectory": {}, "confidence": {}, "adherence": {},
    })["summary"]
    assert "post-op" in surgical_text.lower()
    # the whole path a page takes, for a real general patient
    from app.llm.insights import get_patient_insight

    served = get_patient_insight(db, InsightKind.PATIENT_SUMMARY, "medha")
    assert "post-op" not in served.content["summary"].lower()


def test_a_general_patient_is_not_asked_about_an_incision(db):
    from app.plan.next_steps import plan_next_steps

    general = db.get(Patient, "medha")
    steps = plan_next_steps(db, general, None)
    for step in steps:
        assert "incision" not in step["title"].lower()
        assert "incision" not in (step.get("detail") or "").lower()


def test_malformed_model_output_degrades_instead_of_500ing(client, db, monkeypatch):
    """{"actions": ["call them"]} parses as JSON but is not the declared
    shape: `a.get` raised AttributeError straight out of the validator."""
    from app.llm import insights

    monkeypatch.setattr(insights, "complete_json",
                        lambda *a, **k: {"actions": ["just call them", 7, None]})
    monkeypatch.setattr(insights, "provider_name", lambda: "groq")
    db.execute(delete(Insight).where(Insight.patient_id == "grace"))
    db.commit()
    resp = client.get("/api/patients/grace")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["actions"], list) and body["actions"]
    assert all(isinstance(a["title"], str) for a in body["actions"])
    assert insights._validate(insights.InsightKind.SUGGESTED_ACTIONS,
                              {"actions": ["a string, not an object"]}) is None


# --- the reseed ---------------------------------------------------------------------


def test_the_reseed_refuses_to_delete_real_patients(db):
    """`{"action": "seed"}` drops every table. On a live deployment that
    deletes the app sessions on people's phones, their threads and every
    observation Apple Health ever delivered."""
    from app.seed.seed import live_patient_ids, refuse_destructive_reseed

    # Enrolling in this suite leaves Steve with a number on file.
    steve = db.get(Patient, "steve")
    restore = steve.phone
    steve.phone = "+15125550142"
    db.commit()
    try:
        assert "steve" in live_patient_ids(db)
        refusal = refuse_destructive_reseed()
        assert refusal is not None
        assert "refusing to reseed" in refusal["error"]
        assert "steve" in refusal["live_patients"]
        # asked twice, it proceeds
        assert refuse_destructive_reseed(force=True) is None
    finally:
        db.expire_all()
        db.get(Patient, "steve").phone = restore
        db.commit()


def test_the_guard_covers_a_patient_the_seed_cannot_rebuild(db, monkeypatch):
    """Three ways to be unrebuildable, and the third is the one that bites:
    a patient the shipped roster does not contain. Clearing the phone
    numbers off a set of demo patients — a reasonable thing to do — would
    otherwise take them out from under the guard entirely."""
    from app.seed import seed as seed_module
    from app.seed.patients import PATIENTS, _spec
    from app.seed.seed import unrebuildable_patient_ids

    marker = Patient(
        id="robustness-probe", name="Probe Person", initials="PP", age=40, sex="F",
        procedure_type="NONE", procedure_display="General care",
        surgery_date=date.today(), discharge_date=date.today(),
        surgeon_id="ct_alvarez", assigned_provider_id="ct_alvarez", hospital_id="hosp_demo",
    )
    db.add(marker)
    db.commit()
    try:
        # not in the shipped roster: a reseed would delete it for good
        assert "robustness-probe" in unrebuildable_patient_ids(db)

        # pretend the seed does know how to rebuild it, with no phone and no
        # session: now it is genuinely disposable
        from app.models.enums import ProcedureType

        rebuildable = _spec("robustness-probe", "Probe Person", 40, "F", ProcedureType.NONE,
                            "General care", 0, None, "", 0, "hosp_demo")
        monkeypatch.setattr(seed_module, "PATIENTS", [*PATIENTS, rebuildable])
        assert "robustness-probe" not in unrebuildable_patient_ids(db)

        # a phone alone puts it back under the guard
        marker.phone = "+15125550699"
        db.commit()
        assert "robustness-probe" in unrebuildable_patient_ids(db)

        # so does an app session, with no phone at all
        marker.phone = None
        db.add(PatientSession(patient_id="robustness-probe", token_hash="probe-hash"))
        db.commit()
        assert "robustness-probe" in unrebuildable_patient_ids(db)
    finally:
        db.execute(delete(PatientSession).where(PatientSession.patient_id == "robustness-probe"))
        db.execute(delete(Message).where(Message.patient_id == "robustness-probe"))
        db.execute(delete(Patient).where(Patient.id == "robustness-probe"))
        db.commit()


# --- dates --------------------------------------------------------------------------


def test_a_future_surgery_date_is_refused(client, db):
    from app.models.hospital import Hospital

    db.expire_all()
    db.get(Hospital, "hosp_demo").access_token = "tok-dates"
    db.commit()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.post("/api/patients/", headers={"Authorization": "Bearer tok-dates"}, json={
        "hospital_id": "hosp_demo", "name": "Future Op", "procedure_type": "TKA",
        "surgery_date": tomorrow})
    assert resp.status_code == 422 and "future" in resp.json()["detail"]
    # the mobile join refuses it too
    assert client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Future Op", "phone": "+15125550601",
        "had_surgery": True, "procedure_type": "TKA", "surgery_date": tomorrow,
    }).status_code == 422


@pytest.mark.parametrize("phone", ["", "   ", "abc", "12", "+1", "555-010"])
def test_unusable_phone_numbers_are_refused_at_every_door(client, db, phone):
    from app.models.hospital import Hospital

    db.expire_all()
    db.get(Hospital, "hosp_demo").access_token = "tok-dates"
    db.commit()
    created = client.post("/api/patients/", headers={"Authorization": "Bearer tok-dates"}, json={
        "hospital_id": "hosp_demo", "name": "Phone Probe", "phone": phone})
    if phone.strip():
        assert created.status_code == 422, created.text
    else:
        # blank means "no number on file", which is a valid chart
        assert created.status_code == 200
        from app.identity import delete_patient

        db.expire_all()
        delete_patient(db, db.get(Patient, created.json()["patient"]["id"]))
    assert client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Phone Probe", "phone": phone,
        "had_surgery": False}).status_code == 422
