"""End to end: a surgery patient and a general patient onboard in the app,
the console works their chart, and everything stays on one record.

Sendblue is faked at ``_post_message`` (the one HTTP call), so texts are
observable without a network. The stress test at the bottom runs the whole
loop for a crowd of patients with hostile input.
"""

from __future__ import annotations

import threading
from datetime import date

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
    assert [h["id"] for h in hospitals] == ["hosp_demo"]
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
    assert r["status"] == "sent_sms" and sb.last().endswith("Hello again")
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
