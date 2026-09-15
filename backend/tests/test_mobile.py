"""The patient app's API: onboarding, tasks, messages, the copilot, and the
Sendblue inbound path. conftest blanks every Sendblue key, so no text can be
sent; enrollment therefore takes the unverified path and says so."""

from datetime import date

from sqlalchemy import select

from app.config import settings
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.checkin import Checkin
from app.models.mobile import Message
from app.models.notification import Notification
from app.models.patient import Patient
from app.tasks import service as tasks

STEVE_PHONE = "+15125550142"


def _forget_patient(db, patient_id: str) -> None:
    """Remove a self-enrolled patient and every row that points at them, so
    the session-scoped seeded database is the roster again afterwards."""
    from sqlalchemy import delete

    from app.models.checkin import Checkin, CheckinMessage
    from app.models.insight import EstablishedBaseline, Insight, RiskAssessment
    from app.models.mobile import PatientSession, PhoneVerification
    from app.models.observation import Observation

    checkin_ids = db.scalars(select(Checkin.id).where(Checkin.patient_id == patient_id)).all()
    if checkin_ids:
        db.execute(delete(CheckinMessage).where(CheckinMessage.checkin_id.in_(checkin_ids)))
    for model in (Checkin, RiskAssessment, Insight, EstablishedBaseline, PatientSession,
                  PhoneVerification, Message, Notification, AdherenceRecord, AdherenceTask,
                  Observation):
        db.execute(delete(model).where(model.patient_id == patient_id))
    db.execute(delete(Patient).where(Patient.id == patient_id))
    db.commit()


def _enroll(client, patient_id="steve", hospital_id="hosp_medpull", phone=STEVE_PHONE):
    resp = client.post(
        "/api/mobile/enroll",
        json={"patient_id": patient_id, "hospital_id": hospital_id, "phone": phone,
              "device_name": "iPhone (test)"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "enrolled"
    return {"Authorization": f"Bearer {body['session_token']}"}, body


def test_hospitals_listed_and_searchable(client):
    body = client.get("/api/mobile/hospitals").json()
    ids = [h["id"] for h in body["hospitals"]]
    assert "hosp_medpull" in ids and "hosp_demo" in ids and len(ids) == 6
    filtered = client.get("/api/mobile/hospitals?q=methodist").json()["hospitals"]
    assert [h["id"] for h in filtered] == ["hosp_methodist"]


def test_patient_search_is_scoped_masked_and_needs_two_chars(client):
    resp = client.post("/api/mobile/patients/search",
                       json={"hospital_id": "hosp_medpull", "name": "ste"})
    assert resp.status_code == 200
    cands = resp.json()["candidates"]
    assert [c["patient_id"] for c in cands] == ["steve"]
    assert cands[0]["display_name"] == "Steve"
    assert "surgery_month" in cands[0] and "phone" not in cands[0]
    # Linda Park is at Methodist: invisible from the MedPull institute.
    empty = client.post("/api/mobile/patients/search",
                        json={"hospital_id": "hosp_medpull", "name": "Linda Park"}).json()
    assert empty["candidates"] == []
    found = client.post("/api/mobile/patients/search",
                        json={"hospital_id": "hosp_methodist", "name": "linda"}).json()
    assert found["candidates"][0]["display_name"] == "Linda P."
    short = client.post("/api/mobile/patients/search",
                        json={"hospital_id": "hosp_medpull", "name": "s"}).json()
    assert short["candidates"] == []
    assert client.post("/api/mobile/patients/search",
                       json={"hospital_id": "nope", "name": "steve"}).status_code == 404


def test_enroll_without_sendblue_is_unverified_and_issues_session(client, db):
    headers, body = _enroll(client)
    assert body["verified"] is False
    assert body["me"]["patient"]["id"] == "steve"
    assert body["me"]["patient"]["hospital"]["id"] == "hosp_medpull"
    assert body["me"]["recovery"]["label"] in {
        "On track", "Worth a check-in", "Care team reviewing", "Waiting for data",
    }
    db.expire_all()
    assert db.get(Patient, "steve").phone == STEVE_PHONE

    me = client.get("/api/mobile/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["features"]["sms"] is False
    assert client.get("/api/mobile/me").status_code == 401
    assert client.get("/api/mobile/me", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_enroll_refuses_wrong_hospital_and_bad_phone(client):
    resp = client.post("/api/mobile/enroll", json={
        "patient_id": "linda", "hospital_id": "hosp_medpull", "phone": "+15125550199"})
    assert resp.status_code == 409
    resp = client.post("/api/mobile/enroll", json={
        "patient_id": "steve", "hospital_id": "hosp_medpull", "phone": "12"})
    assert resp.status_code == 422


def test_enroll_with_sendblue_requires_a_code(client, db, monkeypatch):
    from app.api import mobile
    from app.notifications import sendblue

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "sendblue_api_key", "k")
    monkeypatch.setattr(settings, "sendblue_api_secret", "s")
    monkeypatch.setattr(
        sendblue, "_post_message",
        lambda phone, content: sent.append((phone, content)) or _FakeResponse(),
    )
    resp = client.post("/api/mobile/enroll", json={
        "patient_id": "guest", "hospital_id": "hosp_medpull", "phone": "+15125550177"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "verification_required"
    assert body["phone_masked"].endswith("0177")
    assert len(sent) == 1 and "verification code is" in sent[0][1]
    code = sent[0][1].split("is ")[1].split(".")[0]

    wrong = client.post("/api/mobile/enroll/verify",
                        json={"verification_id": body["verification_id"], "code": "000000"})
    assert wrong.status_code == 401
    ok = client.post("/api/mobile/enroll/verify",
                     json={"verification_id": body["verification_id"], "code": code})
    assert ok.status_code == 200
    assert ok.json()["verified"] is True
    assert ok.json()["me"]["features"]["sms"] is True
    # burned
    again = client.post("/api/mobile/enroll/verify",
                        json={"verification_id": body["verification_id"], "code": code})
    assert again.status_code == 404
    db.expire_all()
    assert db.get(Patient, "guest").phone == "+15125550177"
    # the fake sender is what mobile saw, not a real request
    assert mobile._verification_needed() is True


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return {"message_handle": "mh_test"}


def test_assign_task_then_complete_in_app_writes_transcript_and_record(client, db):
    headers, _ = _enroll(client)
    resp = client.post("/api/patients/steve/actions/assign-task", json={
        "title": "Ankle pumps, 20 reps", "why": "Circulation", "kind": "exercise"})
    assert resp.status_code == 200
    body = resp.json()
    # no Sendblue keys -> recorded, not texted, and the status says which
    assert body["status"] == "assigned_not_texted"
    assert body["sms"]["sent"] is False
    task_id = body["task"]["id"]

    listing = client.get("/api/mobile/tasks", headers=headers).json()
    mine = [t for t in listing["open"] if t["id"] == task_id]
    assert len(mine) == 1
    assert [q["id"] for q in mine[0]["questions"]] == ["exercises", "pain", "note"]

    bad = client.post(f"/api/mobile/tasks/{task_id}/complete", headers=headers,
                      json={"answers": {"exercises": "maybe"}})
    assert bad.status_code == 422

    done = client.post(f"/api/mobile/tasks/{task_id}/complete", headers=headers,
                       json={"answers": {"exercises": "all", "pain": 3}})
    assert done.status_code == 200
    assert done.json()["task"]["status"] == "done"
    assert done.json()["task"]["completed_via"] == "app"

    db.expire_all()
    checkin = db.get(Checkin, done.json()["checkin_id"])
    assert checkin.channel == "app"
    assert "I did all my exercises." in [m.text for m in checkin.messages]
    record = db.scalar(select(AdherenceRecord).where(AdherenceRecord.task_id == task_id))
    assert record is not None and record.date == date.today()
    assert str(record.status) == "self_attested"

    twice = client.post(f"/api/mobile/tasks/{task_id}/complete", headers=headers,
                        json={"answers": {"exercises": "all"}})
    assert twice.status_code == 409
    # the console sees the same task
    console = client.get("/api/patients/steve/tasks").json()["tasks"]
    assert any(t["id"] == task_id and t["status"] == "done" for t in console)


def test_task_cannot_be_completed_by_another_patient(client, db):
    steve_headers, _ = _enroll(client)
    kanthi_headers, _ = _enroll(client, patient_id="kanthi", phone="+15125550188")
    task_id = client.post("/api/patients/steve/actions/assign-task",
                          json={"title": "Walk 10 minutes", "kind": "walk"}).json()["task"]["id"]
    assert client.post(f"/api/mobile/tasks/{task_id}/complete", headers=kanthi_headers,
                       json={"answers": {"minutes": 10}}).status_code == 404
    assert client.post(f"/api/mobile/tasks/{task_id}/skip", headers=steve_headers).status_code == 200


def test_alerting_answers_notify_the_care_team(client, db):
    headers, _ = _enroll(client)
    task_id = client.post("/api/patients/steve/actions/assign-task",
                          json={"title": "Incision check", "kind": "wound_check"}).json()["task"]["id"]
    before = len(db.scalars(select(Notification).where(Notification.patient_id == "steve")).all())
    resp = client.post(f"/api/mobile/tasks/{task_id}/complete", headers=headers,
                       json={"answers": {"swelling": "no", "redness": "no", "drainage": "yes",
                                         "fever": "yes"}})
    assert resp.status_code == 200
    db.expire_all()
    notes = db.scalars(select(Notification).where(Notification.patient_id == "steve")).all()
    titles = [n.title for n in notes[before:]]
    assert any("drainage" in t.lower() for t in titles)
    assert any("fever" in t.lower() for t in titles)


def test_public_task_link_completes_on_the_web(client, db):
    _enroll(client)
    task_id = client.post("/api/patients/steve/actions/assign-task",
                          json={"title": "Take evening dose", "kind": "medication"}).json()["task"]["id"]
    task = db.get(AdherenceTask, task_id)
    # no text went out (no keys), so mint the link the text would have carried
    token = tasks.mint_token(task)
    db.commit()
    page = client.get(f"/api/tasks/{token}")
    assert page.status_code == 200
    assert page.json()["first_name"] == "Steve"
    assert page.json()["deep_link"] == f"medpull://tasks/{task_id}"
    assert client.get("/api/tasks/not-a-token").status_code == 404
    done = client.post(f"/api/tasks/{token}", json={"answers": {"taken": "no"}})
    assert done.status_code == 200
    db.expire_all()
    assert db.get(AdherenceTask, task_id).completed_via == "web"
    record = db.scalar(select(AdherenceRecord).where(AdherenceRecord.task_id == task_id))
    assert str(record.status) == "missed"
    assert client.post(f"/api/tasks/{token}", json={"answers": {"taken": "yes"}}).status_code == 410


def test_messages_flow_both_ways(client, db):
    headers, _ = _enroll(client)
    resp = client.post("/api/mobile/messages", headers=headers, json={"text": "Knee is stiff this morning"})
    assert resp.status_code == 200
    db.expire_all()
    assert any(n.kind == "patient_message" and n.patient_id == "steve"
               for n in db.scalars(select(Notification)).all())

    reply = client.post("/api/patients/steve/actions/message", json={"text": "Ice it for 20 minutes."})
    assert reply.status_code == 200
    assert reply.json()["status"] == "stored_sms_failed"  # has a phone, no keys

    thread = client.get("/api/mobile/messages", headers=headers).json()["messages"]
    senders = [m["sender"] for m in thread]
    assert "patient" in senders and "care_team" in senders
    assert client.post("/api/mobile/messages/read", headers=headers).json()["count"] >= 1
    console = client.get("/api/patients/steve/messages").json()["messages"]
    assert any(m["sender"] == "patient" and m["text"] == "Knee is stiff this morning" for m in console)
    assert client.post("/api/patients/steve/messages/read").status_code == 200


def test_agent_fallback_logs_pain_completes_task_and_flags_red_flags(client, db):
    headers, _ = _enroll(client)
    task_id = client.post("/api/patients/steve/actions/assign-task",
                          json={"title": "Heel slides, 2 sets", "kind": "exercise"}).json()["task"]["id"]

    r = client.post("/api/mobile/agent", headers=headers,
                    json={"text": "My pain is about 4 today and I finished my exercises", "channel": "voice"})
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "fallback"  # no LLM in tests
    kinds = {a["type"] for a in body["actions"]}
    assert kinds == {"log_pain", "complete_task"}
    assert "Logged pain 4/10" in body["reply"]
    db.expire_all()
    assert db.get(AdherenceTask, task_id).status == "done"
    assert db.get(AdherenceTask, task_id).completed_via == "voice"

    r = client.post("/api/mobile/agent", headers=headers, json={"text": "I have chest pain"})
    assert r.json()["flagged"] is True
    assert "911" in r.json()["reply"]
    assert any(n.title.endswith("Reported chest pain or trouble breathing")
               for n in db.scalars(select(Notification).where(Notification.patient_id == "steve")).all())

    r = client.post("/api/mobile/agent", headers=headers, json={"text": "what do I have to do today?"})
    assert "caught up" in r.json()["reply"] or "Today:" in r.json()["reply"]


def test_agent_reply_never_carries_diagnostic_language(client, db, monkeypatch):
    from app.agent import copilot

    headers, _ = _enroll(client)
    monkeypatch.setattr(copilot, "complete_json",
                        lambda *a, **k: {"reply": "I detect an infection.", "actions": []})
    monkeypatch.setattr(copilot, "provider_name", lambda: "groq")
    r = client.post("/api/mobile/agent", headers=headers, json={"text": "the knee is warm"})
    assert r.status_code == 200
    assert "detect" not in r.json()["reply"].lower()
    assert r.json()["provider"] == "fallback"


def test_inbound_sms_webhook_is_gated_and_runs_the_conversation(client, db, monkeypatch):
    from app.notifications import sendblue

    _enroll(client, phone="+15125550142")
    assert client.post("/api/webhooks/sendblue/anything", json={}).status_code == 503
    monkeypatch.setattr(settings, "sendblue_webhook_secret", "whsec-test")
    assert client.post("/api/webhooks/sendblue/wrong", json={"content": "1"}).status_code == 401
    assert client.post("/api/webhooks/sendblue", json={"content": "1"}).status_code == 401
    # Sendblue's own convention: the account's signing secret in a header
    assert client.post("/api/webhooks/sendblue", json={"is_outbound": True},
                       headers={"sb-signing-secret": "whsec-test"}).status_code == 200

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "sendblue_api_key", "k")
    monkeypatch.setattr(settings, "sendblue_api_secret", "s")
    monkeypatch.setattr(sendblue, "_post_message",
                        lambda phone, content: sent.append((phone, content)) or _FakeResponse())

    # A task assigned now IS texted (keys are set for this test).
    assigned = client.post("/api/patients/steve/actions/assign-task",
                           json={"title": "Daily check-in", "kind": "checkin"}).json()
    assert assigned["status"] == "assigned_texted"
    assert "/t/" in sent[-1][1] and "reply 1" in sent[-1][1]

    def text(content, number="+15125550142"):
        return client.post("/api/webhooks/sendblue/whsec-test",
                           json={"from_number": number, "content": content, "is_outbound": False})

    # status callbacks for our own sends are ignored
    assert client.post("/api/webhooks/sendblue/whsec-test",
                       json={"is_outbound": True, "status": "DELIVERED"}).json()["handled"] is False
    # unknown numbers are dropped, never stored
    unknown = text("hello", number="+15125550000").json()
    assert unknown["handled"] is False and unknown["matched_patient"] is False

    r = text("1").json()
    assert r["kind"] == "task_started" and r["replied"] is True
    assert "pain today" in sent[-1][1]
    r = text("banana").json()  # unreadable answer -> re-ask
    assert r["kind"] == "conversation_step" and "didn't catch" in sent[-1][1]
    text("6")                       # pain
    text("no")                      # swelling
    text("yes")                     # fever
    text("rough")                   # sleep
    text("some")                    # exercises
    r = text("skip").json()         # note
    assert r["kind"] == "task_completed"
    assert "sent to your care team" in sent[-1][1]

    db.expire_all()
    task = db.get(AdherenceTask, assigned["task"]["id"])
    assert task.status == "done" and task.completed_via == "sms"
    checkin = db.get(Checkin, task.result["checkin_id"])
    assert checkin.channel == "sms"
    lines = [m.text for m in checkin.messages if m.who == "patient"]
    assert "My pain is about 6 out of 10." in lines
    assert "I've felt feverish with some chills." in lines
    # the fever answer alerted the care team
    assert any("fever" in n.title.lower() for n in
               db.scalars(select(Notification).where(Notification.patient_id == "steve")).all())
    # every line of the exchange is on the thread
    thread = db.scalars(select(Message).where(Message.patient_id == "steve",
                                              Message.channel == "sms")).all()
    assert any(m.sender == "patient" and m.text == "6" for m in thread)
    assert any(m.sender == "copilot" and "pain today" in m.text for m in thread)

    # free text with nothing open goes to the care team
    r = text("Can you tell my nurse the swelling is down?").json()
    assert r["kind"] == "message"
    assert "care team" in sent[-1][1].lower()


def test_parse_free_answer_variants():
    q_scale = {"id": "pain", "kind": "scale"}
    assert tasks.parse_free_answer(q_scale, "about a 7") == 7
    assert tasks.parse_free_answer(q_scale, "11") is None
    q_yn = {"id": "fever", "kind": "yes_no"}
    assert tasks.parse_free_answer(q_yn, "Yeah a little") == "yes"
    assert tasks.parse_free_answer(q_yn, "Nope") == "no"
    assert tasks.parse_free_answer(q_yn, "maybe") is None
    q_choice = {"id": "exercises", "kind": "choice", "options": ["all", "some", "none"]}
    assert tasks.parse_free_answer(q_choice, "2") == "some"
    assert tasks.parse_free_answer(q_choice, "did them all") == "all"
    assert tasks.parse_free_answer(q_choice, "skipped") == "none"
    q_sleep = {"id": "sleep", "kind": "choice", "options": ["well", "rough"]}
    assert tasks.parse_free_answer(q_sleep, "pretty good") == "well"
    assert tasks.parse_free_answer(q_sleep, "terrible") == "rough"


def test_progress_and_wearables_answer_without_junction(client):
    headers, _ = _enroll(client)
    prog = client.get("/api/mobile/progress?days=7", headers=headers).json()
    assert len(prog["days"]) == 7 and prog["days"][-1]["date"] == date.today().isoformat()
    wear = client.get("/api/mobile/wearables", headers=headers).json()
    assert wear["summary"]["apple_health"]["connected"] is False
    assert client.post("/api/mobile/wearables/apple/session", headers=headers).status_code == 503
    assert client.post("/api/mobile/wearables/link", headers=headers).status_code == 503
    refreshed = client.post("/api/mobile/wearables/refresh", headers=headers)
    assert refreshed.status_code == 200


def test_signout_revokes_session(client):
    headers, _ = _enroll(client)
    assert client.post("/api/mobile/signout", headers=headers).status_code == 200
    assert client.get("/api/mobile/me", headers=headers).status_code == 401


def test_aasa_only_when_team_id_set(client, monkeypatch):
    assert client.get("/.well-known/apple-app-site-association").status_code == 404
    monkeypatch.setattr(settings, "ios_team_id", "TEAM123")
    body = client.get("/.well-known/apple-app-site-association").json()
    assert body["applinks"]["details"][0]["appIDs"] == ["TEAM123.com.medpull.recovery"]


def test_gait_upload_goes_through_ingest(client, db):
    from app.models.observation import Observation

    headers, _ = _enroll(client)
    today = date.today().isoformat()
    resp = client.post("/api/mobile/observations/gait", headers=headers, json={
        "device_model": "iPhone 17",
        "points": [
            {"metric_type": "walking_speed", "date": today, "value": 0.91},
            {"metric_type": "step_length", "date": today, "value": 0.58},
            {"metric_type": "walking_speed", "date": "2001-01-01", "value": 1.0},  # out of window
            {"metric_type": "steps", "date": today, "value": 100},  # not a gait metric
            {"metric_type": "walking_speed", "date": today, "value": 99.0},  # implausible
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["ingested"] == 2 and body["rejected"] == 1 and body["skipped_out_of_window"] == 1
    assert body["dropped_implausible"] == 1
    rows = db.scalars(select(Observation).where(Observation.patient_id == "steve",
                                                Observation.metric_type == "walking_speed")).all()
    assert [r.value_num for r in rows] == [0.91]
    assert str(rows[0].source_provider) == "apple"
    # same day again restates in place
    again = client.post("/api/mobile/observations/gait", headers=headers, json={
        "points": [{"metric_type": "walking_speed", "date": today, "value": 0.95}]}).json()
    assert again["updated"] == 1 and again["ingested"] == 0
    # The seeded database is shared across the session and test_seed asserts
    # gait rows exist only for the Apple-seeded patients: take these back out.
    for row in db.scalars(select(Observation).where(
            Observation.patient_id == "steve", Observation.source_device_id == "apple_health:gait")).all():
        db.delete(row)
    db.commit()


def test_join_as_general_patient_without_surgery(client, db):
    from app.engine.pipeline import latest_assessment

    resp = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Medha Rao", "phone": "+15125550301",
        "date_of_birth": "1998-04-02", "had_surgery": False})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "enrolled"
    me = body["me"]["patient"]
    assert me["mode"] == "general"
    assert me["postop_day"] is None and me["days_enrolled"] == 0
    assert me["procedure_display"] == "General care"
    assert me["hospital"]["id"] == "hosp_demo"
    assert me["care_pathway"] == "general_recovery"
    assert body["me"]["recovery"]["label"] == "Waiting for data"
    patient = db.get(Patient, me["id"])
    assert str(patient.procedure_type) == "NONE" and patient.age == 28
    # the engine scored them without a recovery curve
    assert latest_assessment(db, patient.id) is not None
    # searchable on the roster now, and the same number can't join twice
    found = client.post("/api/mobile/patients/search",
                        json={"hospital_id": "hosp_demo", "name": "medha"}).json()["candidates"]
    assert found and found[0]["display_name"] == "Medha R."
    dup = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Medha Rao", "phone": "+15125550301"})
    assert dup.status_code == 409
    headers = {"Authorization": f"Bearer {body['session_token']}"}
    port = client.get("/api/mobile/portfolio", headers=headers).json()
    assert port["metrics"] == []
    _forget_patient(db, me["id"])


def test_join_with_surgery_needs_procedure_and_date(client, db):
    bad = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Ana Lee", "phone": "+15125550302",
        "had_surgery": True})
    assert bad.status_code == 422
    ok = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Ana Lee", "phone": "+15125550302",
        "had_surgery": True, "procedure_type": "THA", "surgery_date": "2026-09-01"})
    assert ok.status_code == 200
    me = ok.json()["me"]["patient"]
    assert me["mode"] == "recovery" and me["procedure_display"].startswith("Total Hip")
    assert me["postop_day"] == (date.today() - date(2026, 9, 1)).days
    _forget_patient(db, me["id"])
    assert client.post("/api/mobile/join", json={
        "hospital_id": "nope", "name": "X Y", "phone": "+15125550303"}).status_code == 404
    procs = client.get("/api/mobile/procedures").json()["procedures"]
    assert {p["id"] for p in procs} >= {"TKA", "THA", "ACL"}


def test_portfolio_aggregates_seeded_metrics(client):
    headers, _ = _enroll(client, patient_id="aisha", hospital_id="hosp_methodist",
                         phone="+15125550304")
    port = client.get("/api/mobile/portfolio?days=14", headers=headers).json()
    keys = {m["key"] for m in port["metrics"]}
    assert "steps" in keys and "sleep_duration" in keys
    steps = next(m for m in port["metrics"] if m["key"] == "steps")
    assert steps["latest"]["value"] > 0 and len(steps["series"]) >= 7
    assert len([m for m in port["metrics"] if m["label"] == "Heart rate variability"]) <= 1


def test_first_enrollment_texts_a_welcome_once_and_writes_the_thread(client, db, monkeypatch):
    from app.models.mobile import PatientSession
    from app.notifications import sendblue

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "sendblue_api_key", "k")
    monkeypatch.setattr(settings, "sendblue_api_secret", "s")
    monkeypatch.setattr(settings, "mobile_otp_required", False)
    monkeypatch.setattr(
        sendblue, "_post_message",
        lambda phone, content: sent.append((phone, content)) or _FakeResponse(),
    )
    from sqlalchemy import delete
    db.execute(delete(PatientSession).where(PatientSession.patient_id == "steve"))
    db.execute(delete(Message).where(Message.patient_id == "steve",
                                     Message.text == sendblue.WELCOME_TEMPLATE))
    db.commit()

    headers, _ = _enroll(client)
    assert [c for _, c in sent] == [sendblue.WELCOME_TEMPLATE]
    assert sent[0][0] == STEVE_PHONE
    db.expire_all()
    welcome = db.scalars(select(Message).where(
        Message.patient_id == "steve", Message.text == sendblue.WELCOME_TEMPLATE)).all()
    assert len(welcome) == 1 and welcome[0].sender == "care_team"
    assert welcome[0].delivery_status == "sent" and welcome[0].external_handle == "mh_test"
    # the app shows it in the thread
    thread = client.get("/api/mobile/messages", headers=headers).json()
    texts = [m["text"] for m in (thread.get("messages") or thread)]
    assert sendblue.WELCOME_TEMPLATE in texts

    # a second device is not a second welcome
    _enroll(client)
    assert len(sent) == 1


def test_join_welcomes_on_the_stub_path_without_sending(client, db):
    from app.notifications import sendblue

    resp = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Welcome Test", "phone": "+15125550377",
        "had_surgery": False})
    assert resp.status_code == 200, resp.text
    pid = resp.json()["me"]["patient"]["id"]
    rows = db.scalars(select(Message).where(Message.patient_id == pid)).all()
    assert [r.text for r in rows] == [sendblue.WELCOME_TEMPLATE]
    assert rows[0].delivery_status == "failed"  # keys blank: nothing left the building
    _forget_patient(db, pid)


def test_creating_a_patient_texts_an_invite_with_the_app_link(client, db, monkeypatch):
    from app.models.hospital import Hospital
    from app.notifications import sendblue

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(settings, "sendblue_api_key", "k")
    monkeypatch.setattr(settings, "sendblue_api_secret", "s")
    monkeypatch.setattr(settings, "app_download_url", "https://example.test/get-app")
    monkeypatch.setattr(
        sendblue, "_post_message",
        lambda phone, content: sent.append((phone, content)) or _FakeResponse(),
    )
    hospital = db.get(Hospital, "hosp_demo")
    hospital.access_token = "tok-test"
    db.commit()

    resp = client.post("/api/patients/", headers={"Authorization": "Bearer tok-test"}, json={
        "hospital_id": "hosp_demo", "name": "Invite Test", "phone": "(512) 555-0388",
        "procedure_type": "NONE"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["invite"] == {"sent": True, "detail": "sent"}
    assert sent == [("+15125550388", sendblue.INVITE_TEMPLATE.format(
        app_url="https://example.test/get-app"))]
    assert "Invite Test" not in sent[0][1]
    pid = body["patient"]["id"]
    db.expire_all()
    assert db.get(Patient, pid).phone == "+15125550388"
    rows = db.scalars(select(Message).where(Message.patient_id == pid)).all()
    assert len(rows) == 1 and rows[0].channel == "sms" and rows[0].delivery_status == "sent"

    # no phone: created, nothing sent, and the response says why
    resp = client.post("/api/patients/", headers={"Authorization": "Bearer tok-test"}, json={
        "hospital_id": "hosp_demo", "name": "No Phone", "procedure_type": "NONE"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["invite"]["sent"] is False
    assert len(sent) == 1
    _forget_patient(db, resp.json()["patient"]["id"])
    _forget_patient(db, pid)
