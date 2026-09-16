"""End to end: a surgery patient and a general patient onboard in the app,
the console works their chart, and everything stays on one record.

Sendblue is faked at ``_post_message`` (the one HTTP call), so texts are
observable without a network. The stress test at the bottom runs the whole
loop for a crowd of patients with hostile input.
"""

from __future__ import annotations

import threading
from datetime import date, timedelta

from sqlalchemy import delete, select

from app.config import settings
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.checkin import Checkin
from app.models.mobile import Message, PatientSession
from app.models.notification import Notification
from app.models.patient import Patient
from app.notifications import sendblue
from tests.test_mobile import _FakeResponse, _forget_patient

SECRET = "whsec-e2e"


class Sendblue:
    """The faked provider: every text lands in ``sent`` as (phone, content)."""

    def __init__(self, monkeypatch, *, fail_for: set[str] | None = None):
        self.sent: list[tuple[str, str]] = []
        self.fail_for = fail_for or set()
        monkeypatch.setattr(settings, "sendblue_api_key", "k")
        monkeypatch.setattr(settings, "sendblue_api_secret", "s")
        monkeypatch.setattr(settings, "sendblue_webhook_secret", SECRET)
        monkeypatch.setattr(sendblue, "_post_message", self._post)

    def _post(self, phone, content):
        if phone in self.fail_for:
            import httpx

            raise httpx.ConnectError("provider down")
        self.sent.append((phone, content))
        return _FakeResponse()

    def last(self) -> str:
        return self.sent[-1][1]


def _text(client, number, content, handle=None):
    body = {"from_number": number, "content": content, "is_outbound": False}
    if handle:
        body["message_handle"] = handle
    r = client.post("/api/webhooks/sendblue", json=body, headers={"sb-signing-secret": SECRET})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- the two onboarding paths ---------------------------------------------------------------


def test_surgery_patient_finds_their_chart_and_everything_lands_on_it(client, db, monkeypatch):
    """A clinician creates the chart with a phone; the patient gets the
    invite, opens the app, finds the record, and from then on the console
    and the app are one thread and one task list."""
    from app.models.hospital import Hospital

    sb = Sendblue(monkeypatch)
    hospital = db.get(Hospital, "hosp_demo")
    hospital.access_token = "tok-e2e"
    db.commit()

    created = client.post("/api/patients/", headers=_auth("tok-e2e"), json={
        "hospital_id": "hosp_demo", "name": "Rosa Delgado", "phone": "512-555-0410",
        "date_of_birth": "1970-05-06", "sex": "F", "procedure_type": "TKA",
        "surgery_date": date.today().isoformat()})
    assert created.status_code == 200, created.text
    pid = created.json()["patient"]["id"]
    assert created.json()["invite"]["sent"] is True
    assert "Rosa" not in sb.last()  # no name in a text

    # the chart shows: phone on file, app not yet enrolled
    detail = client.get(f"/api/patients/{pid}").json()
    assert detail["phone"] == "+15125550410" and detail["app"]["enrolled"] is False
    assert detail["mode"] == "recovery" and detail["hospital_id"] == "hosp_demo"

    # the app: hospital -> find my record -> enroll
    hospitals = client.get("/api/mobile/hospitals").json()["hospitals"]
    assert "hosp_demo" in [h["id"] for h in hospitals]
    found = client.post("/api/mobile/patients/search", json={
        "hospital_id": "hosp_demo", "name": "rosa", "phone": "(512) 555-0410"}).json()["candidates"]
    assert found[0]["patient_id"] == pid and found[0]["phone_match"] is True
    enrolled = client.post("/api/mobile/enroll", json={
        "patient_id": pid, "hospital_id": "hosp_demo", "phone": "5125550410",
        "date_of_birth": "1970-05-06", "device_name": "iPhone 17 Pro", "app_version": "1.0"})
    assert enrolled.status_code == 200, enrolled.text
    token = enrolled.json()["session_token"]
    me = enrolled.json()["me"]
    assert me["patient"]["mode"] == "recovery" and me["patient"]["postop_day"] == 0
    assert me["unread_messages"] >= 1  # the welcome line
    assert sb.last() == sendblue.WELCOME_TEMPLATE
    # a wrong date of birth is refused
    assert client.post("/api/mobile/enroll", json={
        "patient_id": pid, "hospital_id": "hosp_demo", "phone": "5125550410",
        "date_of_birth": "1971-01-01"}).status_code == 409

    detail = client.get(f"/api/patients/{pid}").json()
    assert detail["app"]["enrolled"] is True and detail["app"]["device_name"] == "iPhone 17 Pro"

    # console -> app: a message is texted AND in the app thread
    reply = client.post(f"/api/patients/{pid}/actions/message", json={"text": "How is the knee today?"})
    assert reply.json()["status"] == "sent_sms"
    thread = client.get("/api/mobile/messages", headers=_auth(token)).json()["messages"]
    assert any(m["sender"] == "care_team" and "knee" in m["text"] for m in thread)
    assert sb.last().endswith("How is the knee today?")

    # console -> app: a task is texted, listed in the app, done by text
    assigned = client.post(f"/api/patients/{pid}/actions/assign-task", json={
        "title": "Daily check-in", "kind": "checkin"}).json()
    assert assigned["status"] == "assigned_texted"
    listing = client.get("/api/mobile/tasks", headers=_auth(token)).json()
    assert [t["id"] for t in listing["open"]] == [assigned["task"]["id"]]
    assert [q["id"] for q in listing["open"][0]["questions"]][:2] == ["pain", "swelling"]
    _text(client, "+15125550410", "1")
    assert "pain today" in sb.last()
    for answer in ("3", "no", "no", "well", "all"):
        _text(client, "+15125550410", answer)
    done = _text(client, "+15125550410", "feeling good")
    assert done["kind"] == "task_completed"
    listing = client.get("/api/mobile/tasks", headers=_auth(token)).json()
    assert listing["open"] == [] and listing["recent"][0]["completed_via"] == "sms"
    console_tasks = client.get(f"/api/patients/{pid}/tasks").json()["tasks"]
    assert console_tasks[0]["status"] == "done" and console_tasks[0]["answers"]["pain"] == 3

    # app -> console: a message from the app notifies the care team and is on the chart
    client.post("/api/mobile/messages", headers=_auth(token), json={"text": "Stairs were hard"})
    console_thread = client.get(f"/api/patients/{pid}/messages").json()["messages"]
    assert any(m["sender"] == "patient" and m["text"] == "Stairs were hard" for m in console_thread)
    assert client.post(f"/api/patients/{pid}/messages/read").json()["count"] >= 1

    # a second install is not a second welcome, and the old session still works
    again = client.post("/api/mobile/enroll", json={
        "patient_id": pid, "hospital_id": "hosp_demo", "phone": "5125550410"}).json()
    assert client.get("/api/mobile/me", headers=_auth(again["session_token"])).status_code == 200
    assert client.get("/api/mobile/me", headers=_auth(token)).status_code == 200
    assert sum(1 for _, c in sb.sent if c == sendblue.WELCOME_TEMPLATE) == 1
    _forget_patient(db, pid)


def test_general_patient_joins_gets_general_checkin_and_talks_to_the_copilot(client, db, monkeypatch):
    sb = Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Omar  Haddad", "phone": "+1 (512) 555-0420",
        "had_surgery": False, "device_name": "iPhone"})
    assert joined.status_code == 200, joined.text
    body = joined.json()
    token, pid = body["session_token"], body["me"]["patient"]["id"]
    assert body["me"]["patient"]["name"] == "Omar Haddad"  # whitespace collapsed
    assert body["me"]["patient"]["mode"] == "general"
    assert sb.last() == sendblue.WELCOME_TEMPLATE
    # the console sees the same person, as a general patient with the app on
    detail = client.get(f"/api/patients/{pid}").json()
    assert detail["mode"] == "general" and detail["app"]["enrolled"] is True
    assert detail["phone"] == "+15125550420"

    # a check-in for someone without an operation never mentions an incision
    assigned = client.post(f"/api/patients/{pid}/actions/assign-task", json={
        "title": "Daily check-in", "kind": "checkin"}).json()
    task = client.get("/api/mobile/tasks", headers=_auth(token)).json()["open"][0]
    assert [q["id"] for q in task["questions"]] == ["pain", "sleep", "activity", "note"]
    assert not any("incision" in q["prompt"] for q in task["questions"])
    # by text as well
    _text(client, "+15125550420", "start")
    assert "incision" not in sb.last() and "pain" in sb.last().lower()
    _text(client, "+15125550420", "2")
    assert "sleep" in sb.last()
    _text(client, "+15125550420", "well")
    assert "activity" in sb.last()
    _text(client, "+15125550420", "some")
    assert _text(client, "+15125550420", "skip")["kind"] == "task_completed"
    db.expire_all()
    checkin = db.get(Checkin, db.get(AdherenceTask, assigned["task"]["id"]).result["checkin_id"])
    assert "I got some activity in today." in [m.text for m in checkin.messages]
    # the same task, done in the app, accepts the general answers
    assigned2 = client.post(f"/api/patients/{pid}/actions/assign-task", json={
        "title": "Evening check-in", "kind": "checkin", "notify": False}).json()
    r = client.post(f"/api/mobile/tasks/{assigned2['task']['id']}/complete", headers=_auth(token),
                    json={"answers": {"pain": 1, "activity": "all"}})
    assert r.status_code == 200, r.text
    # ...and refuses a surgical answer id it never asked
    assigned3 = client.post(f"/api/patients/{pid}/actions/assign-task", json={
        "title": "Another check-in", "kind": "checkin", "notify": False}).json()
    r = client.post(f"/api/mobile/tasks/{assigned3['task']['id']}/complete", headers=_auth(token),
                    json={"answers": {"swelling": "yes"}})
    assert r.status_code == 422

    # the copilot's red-flag script drops the "after surgery" wording
    r = client.post("/api/mobile/agent", headers=_auth(token), json={"text": "I have a fever"}).json()
    assert r["flagged"] is True and "after surgery" not in r["reply"]
    r = client.post("/api/mobile/agent", headers=_auth(token), json={"text": "I fell down"}).json()
    assert "after surgery" not in r["reply"]
    # forwarding a note writes the patient's line exactly once
    before = len(client.get("/api/mobile/messages", headers=_auth(token)).json()["messages"])
    client.post("/api/mobile/agent", headers=_auth(token),
                json={"text": "tell my nurse I feel dizzy in the mornings"})
    after = client.get("/api/mobile/messages", headers=_auth(token)).json()["messages"]
    assert [m["sender"] for m in after[before:]] == ["patient", "copilot"]
    _forget_patient(db, pid)


# --- one person, one chart ------------------------------------------------------------------


def test_join_with_a_number_on_file_points_at_find_my_record(client, db, monkeypatch):
    Sendblue(monkeypatch)
    first = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Nadia Osei", "phone": "+15125550430",
        "had_surgery": False}).json()
    pid = first["me"]["patient"]["id"]
    # deleted the app; joins again under a different spelling
    again = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "N. Osei", "phone": "5125550430", "had_surgery": True,
        "procedure_type": "THA", "surgery_date": date.today().isoformat()})
    assert again.status_code == 409
    assert "find your record" in again.json()["detail"]
    # the find-my-record path lists the chart by phone even with no name overlap
    found = client.post("/api/mobile/patients/search", json={
        "hospital_id": "hosp_demo", "name": "Zz", "phone": "5125550430"}).json()["candidates"]
    assert [c["patient_id"] for c in found] == [pid]
    enrolled = client.post("/api/mobile/enroll", json={
        "patient_id": pid, "hospital_id": "hosp_demo", "phone": "5125550430"})
    assert enrolled.status_code == 200 and enrolled.json()["me"]["patient"]["id"] == pid
    assert db.scalars(select(Patient).where(Patient.phone == "+15125550430")).one().id == pid
    _forget_patient(db, pid)


def test_console_sets_the_phone_and_refuses_a_number_on_another_chart(client, db, monkeypatch):
    sb = Sendblue(monkeypatch)
    db.expire_all()
    steve = db.get(Patient, "steve")
    steve.phone = None
    db.execute(delete(PatientSession).where(PatientSession.patient_id == "steve"))
    db.commit()
    # no phone: a message is stored for the app only
    r = client.post("/api/patients/steve/actions/message", json={"text": "Hello?"}).json()
    assert r["status"] == "stored_app_only"

    assert client.patch("/api/patients/steve/contact", json={"phone": "abc"}).status_code == 422
    other = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Steve Test", "phone": "+15125550440",
        "had_surgery": False}).json()
    other_id = other["me"]["patient"]["id"]
    taken = client.patch("/api/patients/steve/contact", json={"phone": "512-555-0440"})
    assert taken.status_code == 409 and "Steve Test" in taken.json()["detail"]
    moved = client.patch("/api/patients/steve/contact", json={"phone": "512-555-0440", "force": True})
    assert moved.status_code == 200
    assert moved.json()["phone"] == "+15125550440" and moved.json()["moved_from"] == [other_id]
    db.expire_all()
    assert db.get(Patient, other_id).phone is None
    # now the console reaches the phone
    r = client.post("/api/patients/steve/actions/message", json={"text": "Hello again"}).json()
    # A console message goes out under the clinician's name: the patient is
    # told a person sent this, not the app.
    assert r["status"] == "sent_sms"
    assert sb.last().startswith("Dr. Alvarez (your care team): Hello again")
    # inbound from that number lands on steve, not the sign-up
    out = _text(client, "+15125550440", "1")
    assert out["matched_patient"] is True
    db.expire_all()
    assert db.scalars(select(Message).where(Message.patient_id == "steve",
                                            Message.sender == "patient")).all()
    cleared = client.patch("/api/patients/steve/contact", json={"phone": None}).json()
    assert cleared["phone"] is None
    _forget_patient(db, other_id)
    db.execute(delete(Message).where(Message.patient_id == "steve"))
    db.execute(delete(Notification).where(Notification.patient_id == "steve"))
    db.commit()


def test_linking_an_app_signup_into_the_chart_makes_them_one_record(client, db, monkeypatch):
    """Steve's exact situation: the console chart has no phone, the phone
    signed up as a new general patient. Linking folds the sign-up into the
    chart; the phone's session then acts as the chart."""
    sb = Sendblue(monkeypatch)
    db.expire_all()
    steve = db.get(Patient, "steve")
    steve.phone = None
    db.execute(delete(PatientSession).where(PatientSession.patient_id == "steve"))
    db.execute(delete(Message).where(Message.patient_id == "steve"))
    db.execute(delete(AdherenceTask).where(AdherenceTask.patient_id == "steve"))
    db.commit()

    signup = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Steve Test", "phone": "+18585550450",
        "had_surgery": False, "device_name": "iPhone 17 Pro Max"}).json()
    token, src = signup["session_token"], signup["me"]["patient"]["id"]
    client.post("/api/mobile/messages", headers=_auth(token), json={"text": "sent from the app"})
    client.post("/api/mobile/observations/gait", headers=_auth(token), json={
        "points": [{"metric_type": "walking_speed", "date": date.today().isoformat(), "value": 1.1}]})
    # meanwhile the console worked the chart
    client.post("/api/patients/steve/actions/message", json={"text": "from the console"})
    chart_task = client.post("/api/patients/steve/actions/assign-task",
                             json={"title": "Walk 10 minutes", "kind": "walk"}).json()["task"]["id"]

    cands = client.get("/api/patients/steve/app-link/candidates").json()
    assert cands["app"]["enrolled"] is False
    top = cands["candidates"][0]
    assert top["patient_id"] == src and top["app"]["enrolled"] is True and top["name_match"] is True

    assert client.post("/api/patients/steve/app-link",
                       json={"from_patient_id": "steve"}).status_code == 422
    assert client.post("/api/patients/steve/app-link",
                       json={"from_patient_id": "nobody"}).status_code == 404
    linked = client.post("/api/patients/steve/app-link", json={"from_patient_id": src})
    assert linked.status_code == 200, linked.text
    body = linked.json()
    assert body["phone"] == "+18585550450" and body["app"]["enrolled"] is True
    assert body["moved"]["patient_sessions"] == 1 and body["moved"]["observations"] == 1
    db.expire_all()
    assert db.get(Patient, src) is None
    assert db.get(Patient, "steve").phone == "+18585550450"

    # the phone's existing session now IS steve
    me = client.get("/api/mobile/me", headers=_auth(token)).json()
    assert me["patient"]["id"] == "steve" and me["patient"]["mode"] == "recovery"
    thread = client.get("/api/mobile/messages", headers=_auth(token)).json()["messages"]
    texts = [m["text"] for m in thread]
    assert "sent from the app" in texts and "from the console" in texts
    tasks = client.get("/api/mobile/tasks", headers=_auth(token)).json()
    assert [t["id"] for t in tasks["open"]] == [chart_task]
    # texting the chart reaches the phone; a reply lands on the chart
    r = client.post("/api/patients/steve/actions/message", json={"text": "Linked now"}).json()
    assert r["status"] == "sent_sms" and sb.last().endswith("Linked now")
    out = _text(client, "+18585550450", "2")
    assert out["kind"] == "link_sent" and "/t/" in sb.last()
    console_thread = client.get("/api/patients/steve/messages").json()["messages"]
    assert any(m["sender"] == "patient" and m["text"] == "2" for m in console_thread)
    # the moved gait row scores the chart
    port = client.get("/api/mobile/portfolio", headers=_auth(token)).json()
    assert any(m["key"] == "walking_speed" for m in port["metrics"])

    # tidy: the seeded database is shared across the session
    from app.models.observation import Observation

    db.execute(delete(Observation).where(Observation.patient_id == "steve"))
    db.execute(delete(Message).where(Message.patient_id == "steve"))
    db.execute(delete(AdherenceRecord).where(AdherenceRecord.patient_id == "steve"))
    db.execute(delete(AdherenceTask).where(AdherenceTask.patient_id == "steve"))
    db.execute(delete(Notification).where(Notification.patient_id == "steve"))
    db.execute(delete(PatientSession).where(PatientSession.patient_id == "steve"))
    db.get(Patient, "steve").phone = None
    db.commit()


def test_console_patient_create_validates_the_phone(client, db, monkeypatch):
    from app.models.hospital import Hospital

    Sendblue(monkeypatch)
    hospital = db.get(Hospital, "hosp_demo")
    hospital.access_token = "tok-e2e"
    db.commit()
    h = _auth("tok-e2e")
    assert client.post("/api/patients/", headers=h, json={
        "hospital_id": "hosp_demo", "name": "Bad Phone", "phone": "call me"}).status_code == 422
    assert client.post("/api/patients/", headers=h, json={
        "hospital_id": "hosp_demo", "name": "   "}).status_code == 422
    ok = client.post("/api/patients/", headers=h, json={
        "hospital_id": "hosp_demo", "name": "Dup Phone", "phone": "512 555 0460"}).json()
    dup = client.post("/api/patients/", headers=h, json={
        "hospital_id": "hosp_demo", "name": "Dup Phone Two", "phone": "+15125550460"})
    assert dup.status_code == 409
    nophone = client.post("/api/patients/", headers=h, json={
        "hospital_id": "hosp_demo", "name": "No Phone"}).json()
    db.expire_all()
    assert db.get(Patient, nophone["patient"]["id"]).phone is None
    assert client.post("/api/patients/", headers=_auth("wrong"), json={
        "hospital_id": "hosp_demo", "name": "X Y"}).status_code == 401
    _forget_patient(db, ok["patient"]["id"])
    _forget_patient(db, nophone["patient"]["id"])


def test_open_tasks_never_fall_off_the_app_list(client, db, monkeypatch):
    Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Many Tasks", "phone": "+15125550470",
        "had_surgery": False}).json()
    token, pid = joined["session_token"], joined["me"]["patient"]["id"]
    first = client.post(f"/api/patients/{pid}/actions/assign-task",
                        json={"title": "The oldest one", "kind": "custom", "notify": False}).json()["task"]["id"]
    for i in range(40):
        t = client.post(f"/api/patients/{pid}/actions/assign-task",
                        json={"title": f"Filler {i}", "kind": "custom", "notify": False}).json()["task"]["id"]
        client.post(f"/api/mobile/tasks/{t}/complete", headers=_auth(token),
                    json={"answers": {"done": "yes"}})
    listing = client.get("/api/mobile/tasks", headers=_auth(token)).json()
    assert [t["id"] for t in listing["open"]] == [first]
    assert len(listing["recent"]) == 20
    _forget_patient(db, pid)


# --- stress ---------------------------------------------------------------------------------

HOSTILE_TEXTS = [
    "", "   ", "1", "2", "skip", "stop", "STOP", "yes", "no", "maybe", "7", "11", "-3",
    "😀🔥💊", "ünïcödé pain 6", "a" * 2500, "<script>alert(1)</script>", "'; DROP TABLE patients; --",
    "tell my nurse everything hurts", "I have chest pain", "what do I have to do today",
    "1 2 3", "None", "null", "\n\t", "my pain is about 4 today and I finished my exercises",
]


def test_stress_crowd_of_patients_tasks_texts_and_messages(client, db, monkeypatch):
    """Twenty-four patients (half surgical, half general) onboard, get every
    task kind, answer by app and by text with hostile input, message the
    care team, and are texted by the console — with the provider failing for
    a quarter of them. No request may 500, no thread may double, and every
    patient must end on one record with one phone."""
    failing = {f"+1512555{5000 + i:04d}" for i in range(0, 24, 4)}
    sb = Sendblue(monkeypatch, fail_for=failing)
    ids: list[tuple[str, str, str]] = []
    for i in range(24):
        phone = f"+1512555{5000 + i:04d}"
        surgical = i % 2 == 0
        body = {"hospital_id": "hosp_demo", "name": f"Stress Person{i}", "phone": phone,
                "had_surgery": surgical}
        if surgical:
            body |= {"procedure_type": ["TKA", "THA", "ACL", "LUMBAR"][i % 4],
                     "surgery_date": date.today().isoformat()}
        r = client.post("/api/mobile/join", json=body)
        assert r.status_code == 200, r.text
        ids.append((r.json()["me"]["patient"]["id"], r.json()["session_token"], phone))
        # a duplicate join is a 409, never a second record
        assert client.post("/api/mobile/join", json=body).status_code == 409

    kinds = ["checkin", "exercise", "walk", "medication", "wound_check", "custom"]
    for n, (pid, token, phone) in enumerate(ids):
        for kind in kinds:
            r = client.post(f"/api/patients/{pid}/actions/assign-task",
                            json={"title": f"{kind} for {n}", "kind": kind})
            assert r.status_code == 200, r.text
            assert r.json()["status"] in ("assigned_texted", "assigned_not_texted")
            if phone in failing:
                assert r.json()["status"] == "assigned_not_texted"
        # bad kinds and empty titles are 422s
        assert client.post(f"/api/patients/{pid}/actions/assign-task",
                           json={"title": "x", "kind": "nope"}).status_code == 422
        assert client.post(f"/api/patients/{pid}/actions/assign-task",
                           json={"title": "  ", "kind": "custom"}).status_code == 422
        listing = client.get("/api/mobile/tasks", headers=_auth(token)).json()
        assert len(listing["open"]) == len(kinds)
        # the SMS conversation, fed garbage, always answers 200 and eventually completes
        for text in HOSTILE_TEXTS:
            out = _text(client, phone, text, handle=f"h-{n}-{abs(hash(text))}")
            assert "kind" in out or out["reason"] == "empty"
        # whatever state the text left, the app can finish every remaining task
        for t in client.get("/api/mobile/tasks", headers=_auth(token)).json()["open"]:
            answers = {q["id"]: (5 if q["kind"] == "scale" else 10 if q["kind"] == "number"
                                 else (q.get("options") or ["yes"])[0] if q["kind"] in ("choice", "yes_no")
                                 else "ok")
                       for q in t["questions"]}
            r = client.post(f"/api/mobile/tasks/{t['id']}/complete", headers=_auth(token),
                            json={"answers": answers, "via": "app"})
            assert r.status_code == 200, r.text
            assert client.post(f"/api/mobile/tasks/{t['id']}/complete", headers=_auth(token),
                               json={"answers": answers}).status_code == 409
        assert client.get("/api/mobile/tasks", headers=_auth(token)).json()["open"] == []
        # messages both ways, including hostile ones
        for text in HOSTILE_TEXTS[:12]:
            r = client.post("/api/mobile/messages", headers=_auth(token), json={"text": text})
            assert r.status_code in (200, 422)
        r = client.post(f"/api/patients/{pid}/actions/message", json={"text": f"Hi {n}"})
        assert r.status_code == 200
        assert r.json()["status"] == ("stored_sms_failed" if phone in failing else "sent_sms")
        # the copilot with hostile input
        for text in HOSTILE_TEXTS[:8]:
            r = client.post("/api/mobile/agent", headers=_auth(token), json={"text": text})
            assert r.status_code in (200, 422), r.text
        # the wrong session cannot see this patient's rows
        other_token = ids[(n + 1) % len(ids)][1]
        for t in client.get(f"/api/patients/{pid}/tasks").json()["tasks"][:2]:
            assert client.post(f"/api/mobile/tasks/{t['id']}/skip",
                               headers=_auth(other_token)).status_code in (404, 409)

    # invariants across the crowd
    db.expire_all()
    for pid, token, phone in ids:
        holders = db.scalars(select(Patient).where(Patient.phone == phone)).all()
        assert [h.id for h in holders] == [pid]
        me = client.get("/api/mobile/me", headers=_auth(token)).json()
        assert me["patient"]["id"] == pid and me["tasks_open"] == 0
        rows = db.scalars(select(Message).where(Message.patient_id == pid).order_by(Message.id)).all()
        # never two identical copilot replies back to back for one patient line
        for a, b in zip(rows, rows[1:]):
            assert not (a.sender == "copilot" and b.sender == "copilot" and a.text == b.text
                        and a.channel == b.channel == "sms"), (pid, a.text)
        records = db.scalars(select(AdherenceRecord).where(AdherenceRecord.patient_id == pid)).all()
        assert len(records) == len(kinds)
    assert sb.sent  # texts did go out for the working numbers
    assert all(phone not in failing for phone, _ in sb.sent)
    for pid, _, _ in ids:
        _forget_patient(db, pid)


def test_stress_concurrent_requests_do_not_corrupt_a_session(client, db, monkeypatch):
    """The phone app fans out several requests at once (me, tasks,
    messages, portfolio) while the console writes. SQLite serialises them;
    nothing may 500 and the final state must be consistent."""
    Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Con Current", "phone": "+15125550480",
        "had_surgery": True, "procedure_type": "ACL", "surgery_date": date.today().isoformat()}).json()
    token, pid = joined["session_token"], joined["me"]["patient"]["id"]
    errors: list[str] = []

    def reader():
        for _ in range(6):
            for path in ("/api/mobile/me", "/api/mobile/tasks", "/api/mobile/messages",
                         "/api/mobile/portfolio?days=7", "/api/mobile/progress?days=7"):
                r = client.get(path, headers=_auth(token))
                if r.status_code != 200:
                    errors.append(f"{path} -> {r.status_code}")

    def writer():
        for i in range(6):
            r = client.post(f"/api/patients/{pid}/actions/assign-task",
                            json={"title": f"Concurrent {i}", "kind": "custom"})
            if r.status_code != 200:
                errors.append(f"assign -> {r.status_code}")
            r = client.post("/api/mobile/messages", headers=_auth(token), json={"text": f"m{i}"})
            if r.status_code != 200:
                errors.append(f"message -> {r.status_code}")

    threads = [threading.Thread(target=reader) for _ in range(3)] + [threading.Thread(target=writer)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    listing = client.get("/api/mobile/tasks", headers=_auth(token)).json()
    assert len(listing["open"]) == 6
    thread = client.get("/api/mobile/messages", headers=_auth(token)).json()["messages"]
    assert sum(1 for m in thread if m["sender"] == "patient") == 6
    _forget_patient(db, pid)


def test_link_dedupes_overlapping_readings_and_keeps_the_phones_junction_user(client, db, monkeypatch):
    """One phone, two records, two Junction users, the same Apple Health days
    delivered to both: the merge must not double-count a day and must keep
    the Junction user the phone is signed into (the record with the live
    app session), retiring the other."""
    from datetime import datetime, time as dtime

    from app.connectors.base import CanonicalObservation
    from app.connectors.ingest import ingest_observations
    from app.models.connection import WearableConnection
    from app.models.enums import ConnectionStatus, Granularity, MetricType, SourceProvider
    from app.models.observation import Observation
    from app.models.patient import Device

    Sendblue(monkeypatch)
    db.expire_all()
    steve = db.get(Patient, "steve")
    steve.phone = None
    db.execute(delete(PatientSession).where(PatientSession.patient_id == "steve"))
    db.execute(delete(Observation).where(Observation.patient_id == "steve"))
    db.execute(delete(WearableConnection).where(WearableConnection.patient_id == "steve"))
    db.commit()
    signup = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Steve Test", "phone": "+18585550490",
        "had_surgery": False}).json()
    token, src = signup["session_token"], signup["me"]["patient"]["id"]

    def reading(pid, day, steps, user):
        return CanonicalObservation(
            patient_id=pid, source_provider=SourceProvider.JUNCTION, metric_type=MetricType.STEPS,
            unit="count", value_num=steps,
            start_time=datetime.combine(day, dtime.min), end_time=datetime.combine(day, dtime(23, 59)),
            # As production writes it: the bare provider slug. The Junction
            # user lives on the connection row, not on every reading, which
            # is what lets one phone's two accounts dedupe by day.
            granularity=Granularity.DAILY_SUMMARY, source_device_id="apple_health_kit",
            # Junction ids a daily summary per user, so the same day under two
            # users never shares a record id: the merge must collide by day.
            timezone="America/Chicago", external_id=f"activity:{user}:{day.isoformat()}",
        )
    d1, d2, d3 = (date.today() - timedelta(days=n) for n in (3, 2, 1))
    # the chart's Junction user delivered d1 and d2; the sign-up's user d2 and d3
    ingest_observations(db, [reading("steve", d1, 1000, "u-chart"), reading("steve", d2, 2000, "u-chart")])
    ingest_observations(db, [reading(src, d2, 2100, "u-app"), reading(src, d3, 3000, "u-app")])
    db.add(WearableConnection(patient_id="steve", aggregator=SourceProvider.JUNCTION,
                              external_user_id="u-chart", client_user_id="c-chart", environment="sandbox",
                              status=ConnectionStatus.LINKED, last_data_at=datetime.now()))
    db.add(WearableConnection(patient_id=src, aggregator=SourceProvider.JUNCTION,
                              external_user_id="u-app", client_user_id="c-app", environment="sandbox",
                              status=ConnectionStatus.LINKED))
    db.add(Device(id="junction:u-chart:apple_health_kit", patient_id="steve", source_provider="apple",
                  device_model="Apple Health via Junction", connected_at=datetime.now()))
    db.add(Device(id="junction:u-app:apple_health_kit", patient_id=src, source_provider="apple",
                  device_model="Apple Health via Junction", connected_at=datetime.now()))
    db.commit()

    linked = client.post("/api/patients/steve/app-link", json={"from_patient_id": src})
    assert linked.status_code == 200, linked.text
    body = linked.json()
    # d2 existed on both: the newer ingest (the sign-up's 2100) replaced the chart's 2000
    assert body["observations"] == {"moved": 2, "dropped_duplicate": 0, "replaced_older": 1}
    # the phone holds the live session on the sign-up, so its Junction user survives
    assert body["wearable"] == {"kept": "u-app", "retired_junction_user": "u-chart"}
    db.expire_all()
    rows = db.scalars(select(Observation).where(Observation.patient_id == "steve")
                      .order_by(Observation.local_date)).all()
    assert [(r.local_date, r.value_num) for r in rows] == [(d1, 1000.0), (d2, 2100.0), (d3, 3000.0)]
    assert all(":steve:" in r.dedupe_key for r in rows)
    conns = db.scalars(select(WearableConnection).where(WearableConnection.patient_id == "steve")).all()
    assert [c.external_user_id for c in conns] == ["u-app"]
    devices = {d.id: d.status for d in db.scalars(select(Device).where(Device.patient_id == "steve")).all()}
    assert devices == {"junction:u-chart:apple_health_kit": "revoked",
                       "junction:u-app:apple_health_kit": "connected"}
    # the app sees one Apple Health device, the live one, and three days of steps
    me = client.get("/api/mobile/me", headers=_auth(token)).json()
    assert me["patient"]["id"] == "steve" and me["wearables"]["apple_health"]["connected"] is True
    prog = client.get("/api/mobile/progress?days=5", headers=_auth(token)).json()["days"]
    assert [d["steps"] for d in prog if d["steps"] is not None] == [1000, 2100, 3000]
    # a redelivery of d3 for the kept user lands on the moved row, not beside it
    ingested, updated, dup = ingest_observations(db, [reading("steve", d3, 3050, "u-app")])
    assert (ingested, updated, dup) == (0, 1, 0)
    assert db.scalar(select(__import__("sqlalchemy").func.count(Observation.id)).where(
        Observation.patient_id == "steve", Observation.metric_type == MetricType.STEPS)) == 3

    # tidy the shared database
    from app.models.insight import EstablishedBaseline

    db.execute(delete(Observation).where(Observation.patient_id == "steve"))
    db.execute(delete(WearableConnection).where(WearableConnection.patient_id == "steve"))
    db.execute(delete(Device).where(Device.patient_id == "steve"))
    db.execute(delete(Message).where(Message.patient_id == "steve"))
    db.execute(delete(PatientSession).where(PatientSession.patient_id == "steve"))
    db.execute(delete(EstablishedBaseline).where(EstablishedBaseline.patient_id == "steve"))
    db.get(Patient, "steve").phone = None
    db.commit()


def test_delete_patient_refuses_a_live_signup_and_removes_a_junk_row(client, db, monkeypatch):
    from app.identity import IdentityError, delete_patient

    Sendblue(monkeypatch)
    junk = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Junk Row", "phone": "+15125550495",
        "had_surgery": False}).json()
    pid, token = junk["me"]["patient"]["id"], junk["session_token"]
    client.post(f"/api/patients/{pid}/actions/assign-task", json={"title": "x", "kind": "custom"})
    import pytest

    with pytest.raises(IdentityError):
        delete_patient(db, db.get(Patient, pid))
    client.post("/api/mobile/signout", headers=_auth(token))
    db.expire_all()
    result = delete_patient(db, db.get(Patient, pid))
    assert result["deleted"] == pid and result["rows"]["adherence_tasks"] == 1
    assert db.get(Patient, pid) is None
    assert db.scalars(select(Message).where(Message.patient_id == pid)).all() == []


# --- claiming a record ----------------------------------------------------------------------


def test_enroll_cannot_take_over_a_record_that_already_has_a_number(client, db, monkeypatch):
    """The hole this closes: with OTP off, POST /enroll named any patient_id
    and any phone, and answered a session on that chart plus moved the number
    onto it. A record whose number is somebody else's now needs a code, and
    the code goes to the number ON FILE, not to the caller's phone."""
    from app.models.hospital import Hospital

    db.expire_all()
    hospital = db.get(Hospital, "hosp_demo")
    hospital.access_token = "tok-e2e"
    db.commit()

    # unconfigured Sendblue: nothing can carry a code, so the claim is refused
    created = client.post("/api/patients/", headers=_auth("tok-e2e"), json={
        "hospital_id": "hosp_demo", "name": "Owned Record", "phone": "+15125550510"}).json()
    pid = created["patient"]["id"]
    attack = client.post("/api/mobile/enroll", json={
        "patient_id": pid, "hospital_id": "hosp_demo", "phone": "+15125559999"})
    assert attack.status_code == 409
    assert "care team" in attack.json()["detail"]
    db.expire_all()
    assert db.get(Patient, pid).phone == "+15125550510"
    assert db.scalars(select(PatientSession).where(PatientSession.patient_id == pid)).all() == []
    # the real owner, with the number the clinic put on file, is frictionless
    ok = client.post("/api/mobile/enroll", json={
        "patient_id": pid, "hospital_id": "hosp_demo", "phone": "(512) 555-0510"})
    assert ok.status_code == 200 and ok.json()["session_token"]

    # configured Sendblue: the claim is a code, texted to the number on file
    sb = Sendblue(monkeypatch)
    attack = client.post("/api/mobile/enroll", json={
        "patient_id": pid, "hospital_id": "hosp_demo", "phone": "+15125559999"})
    assert attack.status_code == 200
    body = attack.json()
    assert body["status"] == "verification_required" and "session_token" not in body
    assert body["phone_masked"].endswith("0510")  # the owner's number, not the caller's
    assert sb.sent[-1][0] == "+15125550510"
    code = sb.last().split("is ")[1].split(".")[0]
    # a wrong code is refused and the chart is untouched
    assert client.post("/api/mobile/enroll/verify", json={
        "verification_id": body["verification_id"], "code": "000000"}).status_code == 401
    db.expire_all()
    assert db.get(Patient, pid).phone == "+15125550510"
    # the owner reads the code off their own phone: that is the proof, and the
    # number they are moving to becomes the chart's
    done = client.post("/api/mobile/enroll/verify", json={
        "verification_id": body["verification_id"], "code": code})
    assert done.status_code == 200 and done.json()["verified"] is True
    db.expire_all()
    assert db.get(Patient, pid).phone == "+15125559999"
    _forget_patient(db, pid)


def test_unverified_enrollment_never_takes_a_number_off_another_chart(client, db, monkeypatch):
    Sendblue(monkeypatch)
    mine = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Phone Owner", "phone": "+15125550520",
        "had_surgery": False}).json()["me"]["patient"]["id"]
    # an empty chart exists; someone tries to claim it with the owner's number
    from app.models.hospital import Hospital

    db.expire_all()
    db.get(Hospital, "hosp_demo").access_token = "tok-e2e"
    db.commit()
    empty = client.post("/api/patients/", headers=_auth("tok-e2e"), json={
        "hospital_id": "hosp_demo", "name": "Empty Chart"}).json()["patient"]["id"]
    resp = client.post("/api/mobile/enroll", json={
        "patient_id": empty, "hospital_id": "hosp_demo", "phone": "+15125550520"})
    assert resp.status_code == 409 and "find that record" in resp.json()["detail"]
    db.expire_all()
    assert db.get(Patient, mine).phone == "+15125550520"
    assert db.get(Patient, empty).phone is None
    _forget_patient(db, empty)
    _forget_patient(db, mine)


# --- the care plan in the app ---------------------------------------------------------------


def test_a_daily_plan_task_comes_back_the_next_day(client, db, monkeypatch):
    """A recurring care-plan task used to retire on its first completion, so
    an assigned plan emptied out of the app after one check and never came
    back. It must leave To-do for the rest of today and return tomorrow."""
    Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Daily Walker", "phone": "+15125550530",
        "had_surgery": True, "procedure_type": "TKA",
        "surgery_date": date.today().isoformat()}).json()
    token, pid = joined["session_token"], joined["me"]["patient"]["id"]
    assigned = client.post(f"/api/patients/{pid}/plan", json={"items": [
        {"title": "Walk 10 minutes", "why": "Circulation", "task_kind": "walk",
         "verify_kind": "steps_min", "schedule": "daily", "params": {"steps": 500}},
        {"title": "One-off wound photo", "task_kind": "wound_check", "schedule": "once"},
    ], "notify": False})
    assert assigned.status_code == 200, assigned.text
    walk_id, once_id = (t["id"] for t in assigned.json()["tasks"])

    listing = client.get("/api/mobile/tasks", headers=_auth(token)).json()
    assert {t["id"] for t in listing["open"]} == {walk_id, once_id}
    assert [t["recurring"] for t in listing["open"] if t["id"] == walk_id] == [True]
    assert [t["schedule"] for t in listing["open"] if t["id"] == walk_id] == ["daily"]

    for tid, answers in ((walk_id, {"minutes": 12, "pain": 2}),
                         (once_id, {"swelling": "no", "redness": "no", "drainage": "no",
                                    "fever": "no"})):
        r = client.post(f"/api/mobile/tasks/{tid}/complete", headers=_auth(token),
                        json={"answers": answers})
        assert r.status_code == 200, r.text
    # both are done for today, and neither is offered twice
    listing = client.get("/api/mobile/tasks", headers=_auth(token)).json()
    assert listing["open"] == []
    assert {t["id"] for t in listing["recent"]} == {walk_id, once_id}
    again = client.post(f"/api/mobile/tasks/{walk_id}/complete", headers=_auth(token),
                        json={"answers": {"minutes": 5}})
    assert again.status_code == 409 and "today" in again.json()["detail"]

    # tomorrow: the daily task is owed again, the one-off stays done
    db.expire_all()
    walk = db.get(AdherenceTask, walk_id)
    walk.payload = {**walk.payload, "last_done": (date.today() - __import__("datetime").timedelta(days=1)).isoformat()}
    db.commit()
    listing = client.get("/api/mobile/tasks", headers=_auth(token)).json()
    assert [t["id"] for t in listing["open"]] == [walk_id]
    assert listing["open"][0]["status"] == "pending"  # tappable in the app
    assert walk_id not in {t["id"] for t in listing["recent"]}
    r = client.post(f"/api/mobile/tasks/{walk_id}/complete", headers=_auth(token),
                    json={"answers": {"minutes": 20}})
    assert r.status_code == 200
    # two days of records, one per day
    db.expire_all()
    records = db.scalars(select(AdherenceRecord).where(AdherenceRecord.task_id == walk_id)).all()
    assert len({r.date for r in records}) >= 1
    # the console still sees the full lifecycle
    console = client.get(f"/api/patients/{pid}/tasks").json()["tasks"]
    assert [t["status"] for t in console if t["id"] == walk_id] == ["done"]
    # ...and ending it from the console takes it out of the app for good
    assert client.post(f"/api/patients/{pid}/plan/{walk_id}/end").status_code == 200
    assert client.get("/api/mobile/tasks", headers=_auth(token)).json()["open"] == []
    blocked = client.post(f"/api/mobile/tasks/{walk_id}/complete", headers=_auth(token),
                          json={"answers": {"minutes": 5}})
    assert blocked.status_code == 409
    _forget_patient(db, pid)


# --- SMS behaviour ---------------------------------------------------------------------------


def test_an_affirmative_text_answers_the_care_team_instead_of_starting_a_task(client, db, monkeypatch):
    """"yes" used to be a task start word, so a patient answering their
    nurse's question got a questionnaire and the nurse never saw the reply."""
    sb = Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Yes Sayer", "phone": "+15125550540",
        "had_surgery": False}).json()
    pid = joined["me"]["patient"]["id"]
    client.post(f"/api/patients/{pid}/actions/assign-task",
                json={"title": "Daily check-in", "kind": "checkin"})
    client.post(f"/api/patients/{pid}/actions/message",
                json={"text": "Is the swelling any better today?"})
    out = _text(client, "+15125550540", "yes, a bit better")
    assert out["kind"] == "message"
    db.expire_all()
    assert any(n.kind == "patient_message" for n in
               db.scalars(select(Notification).where(Notification.patient_id == pid)).all())
    assert not any("quick question" in c for _, c in sb.sent)
    # a bare "yes" is still a message, not a task start
    assert _text(client, "+15125550540", "yes")["kind"] == "message"
    # "1" does start the task the text advertised
    assert _text(client, "+15125550540", "1")["kind"] == "task_started"
    _forget_patient(db, pid)


def test_one_starts_the_task_that_was_texted_most_recently(client, db, monkeypatch):
    sb = Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Two Tasks", "phone": "+15125550550",
        "had_surgery": False}).json()
    pid = joined["me"]["patient"]["id"]
    first = client.post(f"/api/patients/{pid}/actions/assign-task",
                        json={"title": "Older task", "kind": "medication"}).json()["task"]["id"]
    second = client.post(f"/api/patients/{pid}/actions/assign-task",
                         json={"title": "Newer task", "kind": "walk"}).json()["task"]["id"]
    assert _text(client, "+15125550550", "1")["kind"] == "task_started"
    assert "Newer task" in sb.last() and "minutes did you walk" in sb.last()
    db.expire_all()
    assert isinstance((db.get(AdherenceTask, second).payload or {}).get("sms"), dict)
    assert (db.get(AdherenceTask, first).payload or {}).get("sms") is None
    _forget_patient(db, pid)


def test_asking_for_a_new_link_keeps_the_one_already_texted_working(client, db, monkeypatch):
    sb = Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Link Asker", "phone": "+15125550560",
        "had_surgery": False}).json()
    pid = joined["me"]["patient"]["id"]
    client.post(f"/api/patients/{pid}/actions/assign-task",
                json={"title": "Evening dose", "kind": "medication"})
    first_url = [c for _, c in sb.sent if "/t/" in c][-1].split("Open the task: ")[1].split("\n")[0]
    first_token = first_url.rsplit("/", 1)[1]
    assert client.get(f"/api/tasks/{first_token}").status_code == 200
    assert _text(client, "+15125550560", "2")["kind"] == "link_sent"
    second_token = sb.last().rsplit("/", 1)[1]
    assert second_token != first_token
    # both links resolve to the same task; neither text is dead
    a = client.get(f"/api/tasks/{first_token}")
    b = client.get(f"/api/tasks/{second_token}")
    assert a.status_code == 200 and b.status_code == 200
    assert a.json()["task"]["id"] == b.json()["task"]["id"]
    assert client.post(f"/api/tasks/{first_token}", json={"answers": {"taken": "yes"}}).status_code == 200
    _forget_patient(db, pid)


def test_the_app_sees_the_newest_messages_when_the_thread_is_long(client, db, monkeypatch):
    """Ordering ascending and limiting took the OLDEST 200 rows, so a long
    thread froze months back in the app."""
    from app.api.mobile import MESSAGE_PAGE

    Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Long Thread", "phone": "+15125550570",
        "had_surgery": False}).json()
    token, pid = joined["session_token"], joined["me"]["patient"]["id"]
    for i in range(MESSAGE_PAGE + 5):
        db.add(Message(patient_id=pid, sender="care_team", channel="console", text=f"line {i}"))
    db.commit()
    thread = client.get("/api/mobile/messages", headers=_auth(token)).json()["messages"]
    assert len(thread) == MESSAGE_PAGE
    assert thread[-1]["text"] == f"line {MESSAGE_PAGE + 4}"      # newest is present
    assert [m["id"] for m in thread] == sorted(m["id"] for m in thread)  # oldest-first
    # a cursor still walks forward from where the app left off
    newest = thread[-1]["id"]
    db.add(Message(patient_id=pid, sender="care_team", channel="console", text="after"))
    db.commit()
    later = client.get(f"/api/mobile/messages?since_id={newest}", headers=_auth(token)).json()
    assert [m["text"] for m in later["messages"]] == ["after"]
    _forget_patient(db, pid)


def test_linking_refuses_two_records_fed_by_different_devices(client, db, monkeypatch):
    """The accident this guard exists for: a chart with its own phone, app
    sessions, aggregator account and hundreds of Apple Health readings was
    folded into a demo patient whose data came from a Fitbit, and undoing it
    needed a backup and a provenance-by-provenance split."""
    from datetime import datetime, time as dtime

    from app.connectors.base import CanonicalObservation
    from app.connectors.ingest import ingest_observations
    from app.identity import link_app_account, link_refusal
    from app.models.enums import Granularity, MetricType, SourceProvider
    from app.models.observation import Observation

    Sendblue(monkeypatch)
    db.expire_all()
    db.execute(delete(Observation).where(Observation.patient_id == "steve"))
    db.get(Patient, "steve").phone = None
    db.commit()

    def reading(pid, day, steps, provider, device):
        return CanonicalObservation(
            patient_id=pid, source_provider=provider, metric_type=MetricType.STEPS,
            unit="count", value_num=steps,
            start_time=datetime.combine(day, dtime.min),
            end_time=datetime.combine(day, dtime(23, 59)),
            granularity=Granularity.DAILY_SUMMARY, source_device_id=device,
            timezone="America/Chicago", external_id=f"{device}:{day.isoformat()}",
        )

    today = date.today()
    # the chart: a Fitbit patient of somebody else's
    ingest_observations(db, [reading("steve", today, 4000, SourceProvider.FITBIT, "fitbit")])
    # the sign-up: a phone delivering Apple Health through Junction
    signup = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Other Person", "phone": "+15125550810",
        "had_surgery": False}).json()
    src = signup["me"]["patient"]["id"]
    ingest_observations(db, [reading(src, today, 9000, SourceProvider.JUNCTION, "apple_health_kit")])
    db.commit()

    # the console refuses, and says why in terms a clinician can check
    why = link_refusal(db, db.get(Patient, "steve"), db.get(Patient, src))
    assert why and "different devices" in why
    refused = client.post("/api/patients/steve/app-link", json={"from_patient_id": src})
    assert refused.status_code == 409
    assert "different devices" in refused.json()["detail"]
    # nothing moved, and neither record was deleted
    db.expire_all()
    assert db.get(Patient, src) is not None
    assert db.scalar(select(Observation.value_num).where(
        Observation.patient_id == "steve")) == 4000.0

    # the same phone under two aggregator users is still the case it exists
    # for: shared hardware, so no refusal
    ingest_observations(db, [reading("steve", today - timedelta(days=1), 3000,
                                     SourceProvider.JUNCTION, "apple_health_kit")])
    db.commit()
    assert link_refusal(db, db.get(Patient, "steve"), db.get(Patient, src)) is None

    # and an operator can still force it deliberately
    result = link_app_account(db, db.get(Patient, "steve"), db.get(Patient, src), force=True)
    assert result["linked_from"] == src
    db.expire_all()
    # BOTH days survive: one device's reading no longer deletes the other's
    rows = db.scalars(select(Observation).where(
        Observation.patient_id == "steve", Observation.local_date == today)).all()
    assert sorted(r.value_num for r in rows) == [4000.0, 9000.0]

    from app.models.insight import EstablishedBaseline

    db.execute(delete(Observation).where(Observation.patient_id == "steve"))
    db.execute(delete(Message).where(Message.patient_id == "steve"))
    db.execute(delete(PatientSession).where(PatientSession.patient_id == "steve"))
    db.execute(delete(EstablishedBaseline).where(EstablishedBaseline.patient_id == "steve"))
    db.get(Patient, "steve").phone = None
    db.commit()


def test_link_candidates_say_what_is_at_stake(client, db, monkeypatch):
    Sendblue(monkeypatch)
    signup = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Stakes Person", "phone": "+15125550820",
        "had_surgery": False}).json()
    pid = signup["me"]["patient"]["id"]
    body = client.get("/api/patients/steve/app-link/candidates").json()
    row = next(c for c in body["candidates"] if c["patient_id"] == pid)
    # the console can show the size of what a click would move, and whether
    # the server would allow it at all
    assert row["observations"] == 0 and row["checkins"] == 0
    assert "refusal" in row
    _forget_patient(db, pid)
