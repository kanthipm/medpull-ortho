"""Links a text carries into the app (app/links.py, app/api/links.py), the
texts the exercise calendar sends (app/hep/texts.py), what a text can
command (app/hep/sms_commands.py), binding a real phone to a demo persona
(app/api/demo_phone.py) and the morning reminder run (app/hep/reminders.py).

The provider is faked, as everywhere in the suite: nothing leaves the
process. Charts are throwaway rows on the H.I.R.T. roster, removed with
everything they gathered.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app import links
from app.api import applinks
from app.config import settings
from app.console_credentials import mint
from app.hep import reminders, sms_commands
from app.hep.models import AuditEvent, Exercise, ExerciseAssignment
from app.models.enums import ProcedureType
from app.models.links import AppLink
from app.models.mobile import Message, PatientSession
from app.models.patient import Patient
from app.notifications import sendblue
from app.seed import hirt
from tests.test_mobile import _forget_patient
from tests.test_onboarding_e2e import SECRET, Sendblue, _text

TODAY = date.today()
PHONE = "+15042340101"
OTHER_PHONE = "+15042340102"
BASE = "https://demo.example.test"


@pytest.fixture(scope="module")
def console(seeded_db):
    row, token = mint(seeded_db, "hospital", "hirt", "HIRT console")
    yield {"Authorization": f"Bearer {token}"}
    seeded_db.delete(row)
    seeded_db.commit()


@pytest.fixture()
def lifter(db):
    """A throwaway lifter with a real-looking phone, forgotten afterwards
    with the links, texts and calendar rows the test left on them."""
    made: list[str] = []

    def make(pid: str = "links-test-lifter", phone: str | None = PHONE) -> Patient:
        patient = Patient(
            id=pid, name="Theo Lindqvist", initials="TL", age=33, sex="M",
            procedure_type=ProcedureType.NONE, procedure_display=hirt.PATHWAYS["hirt-cole"],
            surgery_date=TODAY - timedelta(days=14), discharge_date=TODAY - timedelta(days=14),
            surgeon_id="ct_harris", assigned_provider_id="ct_gregg", hospital_id="hirt",
            care_pathway=hirt.PATHWAYS["hirt-cole"], phone=phone,
        )
        db.add(patient)
        db.commit()
        made.append(pid)
        return patient

    audit_mark = db.scalar(select(func.max(AuditEvent.id))) or 0
    yield make
    db.expire_all()
    for pid in made:
        db.execute(delete(ExerciseAssignment).where(ExerciseAssignment.patient_id == pid))
        db.execute(delete(AppLink).where(AppLink.patient_id == pid))
        db.commit()
        _forget_patient(db, pid)
    db.execute(delete(AuditEvent).where(AuditEvent.id > audit_mark))
    db.commit()


@pytest.fixture()
def public_host(monkeypatch):
    monkeypatch.setattr(settings, "checkin_base_url", BASE)


def _exercise(db, title: str) -> Exercise:
    return db.scalar(select(Exercise).where(Exercise.title == title))


def _assign(db, patient: Patient, title: str, day: date = TODAY, **fields) -> ExerciseAssignment:
    row = ExerciseAssignment(
        hospital_id="hirt", patient_id=patient.id, exercise_id=_exercise(db, title).id,
        scheduled_for=day, sort_order=fields.pop("sort_order", 0), assigned_by="ct_gregg",
        status="assigned", sets=3, reps=10, **fields,
    )
    db.add(row)
    db.commit()
    return row


def _token(url: str) -> str:
    return url.rsplit("/", 1)[1]


# --- links ---------------------------------------------------------------------------


def test_reading_a_link_changes_nothing_and_redeeming_it_is_recorded(client, db, lifter,
                                                                    public_host):
    patient = lifter()
    url = links.mint(db, patient, "exercise", ref_id=41, day=TODAY)
    db.commit()
    assert url.startswith(f"{BASE}/a/") and len(_token(url)) == 12
    token = _token(url)

    seen = client.get(f"/api/links/{token}")
    assert seen.status_code == 200
    body = seen.json()
    assert (body["kind"], body["ref_id"], body["day"]) == ("exercise", "41", TODAY.isoformat())
    assert body["patient"] == {"first_name": "Theo"}  # a first name, and nothing clinical
    assert body["clinic"] == {"name": "H.I.R.T. Physical Therapy"}
    assert body["web"] == f"/patient/#link={token}" and body["app"]["url"].endswith(f"://a/{token}")
    assert body["signin"] is False
    # Messages fetches a link to draw its preview: reading it must not count as opening it
    client.get(f"/api/links/{token}")
    db.expire_all()
    row = links.resolve(db, token)
    assert row.open_count == 0 and row.first_opened_at is None

    # off the demo stack a link names a place; it never signs anyone in
    refused = client.post(f"/api/links/{token}/session", json={"device_name": "iPhone"})
    assert refused.status_code == 403 and "sign in" in refused.json()["detail"]
    db.expire_all()
    assert links.resolve(db, token).open_count == 1  # ...but the tap is recorded

    assert client.get("/api/links/not-a-token").status_code == 404
    assert client.post("/api/links/not-a-token/session").status_code == 404
    row = links.resolve(db, token)
    row.expires_at = datetime.now() - timedelta(minutes=1)
    db.commit()
    assert client.get(f"/api/links/{token}").status_code == 404


def test_a_link_signs_a_phone_in_only_as_a_demo_persona(client, db, lifter, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    # a chart the showcase did not write: a real person, even on the demo stack
    real = lifter()
    real_token = _token(links.mint(db, real, "today", base_url=BASE))
    june = db.get(Patient, "hirt-june")
    june_token = _token(links.mint(db, june, "program", day=TODAY, base_url=BASE))
    db.commit()
    try:
        assert client.get(f"/api/links/{real_token}").json()["signin"] is False
        assert client.post(f"/api/links/{real_token}/session").status_code == 403

        seen = client.get(f"/api/links/{june_token}").json()
        assert seen["signin"] is True and seen["app"]["scheme"] == settings.demo_app_scheme
        opened = client.post(f"/api/links/{june_token}/session", json={"device_name": "iPhone"})
        assert opened.status_code == 200
        body = opened.json()
        assert body["target"] == {"kind": "program", "ref_id": None, "day": TODAY.isoformat()}
        me = client.get("/api/mobile/me",
                        headers={"Authorization": f"Bearer {body['session_token']}"}).json()
        assert me["patient"]["id"] == "hirt-june" and body["me"]["patient"]["id"] == "hirt-june"
    finally:
        db.execute(delete(PatientSession).where(PatientSession.patient_id == "hirt-june"))
        db.execute(delete(AppLink).where(AppLink.patient_id == "hirt-june"))
        db.commit()


def test_the_association_file_names_the_apps_this_host_opens(client, monkeypatch):
    monkeypatch.setattr(settings, "ios_team_id", "")
    monkeypatch.setattr(settings, "ios_link_app_ids", "")
    assert client.get("/.well-known/apple-app-site-association").status_code == 404

    # the demo stack: the demo app alone, for the task link and the texted link
    monkeypatch.setattr(settings, "ios_link_app_ids", "TEAM123.com.medpull.demo")
    body = client.get("/.well-known/apple-app-site-association").json()
    details = body["applinks"]["details"][0]
    assert details["appIDs"] == ["TEAM123.com.medpull.demo"]
    assert details["components"] == [{"/": "/t/*"}, {"/": "/a/*"}]

    # the patient app first when the deployment names its team, without repeats
    monkeypatch.setattr(settings, "ios_team_id", "TEAM123")
    monkeypatch.setattr(settings, "ios_link_app_ids",
                        "TEAM123.com.medpull.demo, TEAM123.com.medpull.recovery")
    assert applinks.app_ids() == ["TEAM123.com.medpull.recovery", "TEAM123.com.medpull.demo"]
    monkeypatch.setattr(settings, "ios_link_paths", "/a/*")
    assert applinks.link_paths() == ["/a/*"]


def test_a_send_asks_for_its_delivery_states_back_at_this_stack(monkeypatch):
    monkeypatch.setattr(settings, "checkin_base_url", "")
    monkeypatch.setattr(settings, "sendblue_webhook_secret", "s3cr3t/x")
    assert sendblue.status_callback_url() is None  # no public host to name
    monkeypatch.setattr(settings, "checkin_base_url", BASE + "/")
    assert sendblue.status_callback_url() == f"{BASE}/api/webhooks/sendblue/s3cr3t%2Fx"
    monkeypatch.setattr(settings, "sendblue_webhook_secret", "")
    assert sendblue.status_callback_url() is None


# --- the calendar's texts ------------------------------------------------------------


def test_assigning_with_text_patient_texts_a_link_to_the_day(client, db, lifter, console,
                                                             monkeypatch, public_host):
    sb = Sendblue(monkeypatch)
    patient = lifter()
    slides = _exercise(db, "Heel Slides")
    res = client.post("/api/hep/schedule", headers=console, json={
        "patient_id": patient.id, "exercise_id": slides.id, "dates": [TODAY.isoformat()],
        "sets": 2, "reps": 10, "assigned_by": "ct_gregg", "text_patient": True,
    })
    assert res.status_code == 201, res.text
    text = res.json()["text"]
    assert text["sent"] is True and text["status"] == "sent" and text["link"].startswith(f"{BASE}/a/")
    phone, words = sb.sent[-1]
    assert phone == PHONE
    assert "Dr. Ashley Gregg added 1 exercise for today: Heel Slides." in words
    assert f"Open today's plan: {text['link']}" in words
    assert "Theo" not in words and "Lindqvist" not in words and "tendinopathy" not in words.lower()

    db.expire_all()
    line = db.get(Message, text["message_id"])
    assert line.channel == "sms" and line.sender == "care_team" and line.sender_id == "ct_gregg"
    assert line.action_view() == {
        "kind": "open_today", "task_id": None, "label": "Open today's plan",
        "target": {"kind": "today", "ref_id": None, "day": TODAY.isoformat()},
        "url": text["link"],
    }
    link = links.resolve(db, _token(text["link"]))
    assert link.patient_id == patient.id and link.kind == "today" and link.message_id == line.id

    # without the flag nothing is texted, and the answer says so
    quiet = client.post("/api/hep/schedule", headers=console, json={
        "patient_id": patient.id, "exercise_id": slides.id,
        "dates": [(TODAY + timedelta(days=1)).isoformat()], "assigned_by": "ct_gregg",
    })
    assert quiet.status_code == 201 and quiet.json()["text"] is None
    assert len(sb.sent) == 1


def test_a_review_note_is_texted_with_a_link_to_that_exercise(client, db, lifter, console,
                                                              monkeypatch, public_host):
    sb = Sendblue(monkeypatch)
    patient = lifter()
    row = _assign(db, patient, "Wall Sits", TODAY - timedelta(days=1))
    done = client.post(f"/api/hep/schedule/{row.id}/complete", headers=console,
                       json={"pain_after": 3, "actor": "ct_gregg"})
    assert done.status_code == 200, done.text
    res = client.post(f"/api/hep/schedule/{row.id}/review", headers=console, json={
        "actor": "ct_gregg", "note": "Good depth. Hold the last one a little longer next time."})
    assert res.status_code == 200, res.text
    text = res.json()["text"]
    assert text["sent"] is True
    words = sb.last()
    assert "Dr. Ashley Gregg left a note on your Wall Sits. Good depth." in words
    assert f"See the reply: {text['link']}" in words
    link = links.resolve(db, _token(text["link"]))
    assert (link.kind, link.ref_id) == ("exercise", str(row.id))


def test_text_todays_plan_from_the_console_and_why_it_sometimes_cannot(client, db, lifter,
                                                                      console, monkeypatch,
                                                                      public_host):
    sb = Sendblue(monkeypatch)
    patient = lifter()
    _assign(db, patient, "Heel Slides", sort_order=0)
    _assign(db, patient, "Wall Sits", sort_order=1)
    res = client.post(f"/api/hep/patients/{patient.id}/text-today", headers=console,
                      json={"by": "ct_gregg"})
    assert res.status_code == 200, res.text
    assert "Today's plan: 2 exercises, starting with Heel Slides." in sb.last()
    assert "Dr. Ashley Gregg (your care team):" in sb.last()

    # a rest day is said as one
    rest = lifter("links-test-rest", OTHER_PHONE)
    client.post(f"/api/hep/patients/{rest.id}/text-today", headers=console)
    assert "Nothing assigned today. Rest is part of the program." in sb.last()

    # no number, a placeholder, another clinic's console: each says why, and nothing is sent
    sent = len(sb.sent)
    none = lifter("links-test-nophone", None)
    refused = client.post(f"/api/hep/patients/{none.id}/text-today", headers=console)
    assert refused.status_code == 409 and "no phone number" in refused.json()["detail"]
    fake = lifter("links-test-555", "+17135550199")
    refused = client.post(f"/api/hep/patients/{fake.id}/text-today", headers=console)
    assert refused.status_code == 409 and "placeholder" in refused.json()["detail"]
    assert client.post("/api/hep/patients/linda/text-today", headers=console).status_code == 404
    assert len(sb.sent) == sent


# --- what a text can command ----------------------------------------------------------


def test_stop_stops_every_text_until_start(client, db, lifter, console, monkeypatch, public_host):
    sb = Sendblue(monkeypatch)
    patient = lifter()
    _assign(db, patient, "Heel Slides")

    out = _text(client, PHONE, "STOP", handle="stop-1")
    assert out["kind"] == "opted_out" and out["replied"] is True
    assert "won't get any more texts" in sb.last() and "START" in sb.last()
    db.expire_all()
    assert db.get(Patient, patient.id).sms_opt_out_at is not None

    sent = len(sb.sent)
    refused = client.post(f"/api/hep/patients/{patient.id}/text-today", headers=console)
    assert refused.status_code == 409 and "replied STOP" in refused.json()["detail"]
    said = client.post(f"/api/patients/{patient.id}/actions/message", json={"text": "Checking in"})
    assert (said.json()["status"], said.json()["reason"]) == ("stored_app_only", "opted_out")
    assert len(sb.sent) == sent  # nothing reached the provider

    out = _text(client, PHONE, "start", handle="start-1")
    assert out["kind"] == "opted_in" and "back on" in sb.last()
    db.expire_all()
    assert db.get(Patient, patient.id).sms_opt_out_at is None
    assert client.post(f"/api/hep/patients/{patient.id}/text-today",
                       headers=console).status_code == 200

    out = _text(client, PHONE, "HELP", handle="help-1")
    assert out["kind"] == "help"
    assert "H.I.R.T. Physical Therapy" in sb.last() and "Reply STOP" in sb.last()


def test_done_by_text_marks_the_day_and_asks_for_the_pain(client, db, lifter, monkeypatch,
                                                         public_host):
    sb = Sendblue(monkeypatch)
    patient = lifter()
    slides = _assign(db, patient, "Heel Slides", sort_order=0)
    sits = _assign(db, patient, "Wall Sits", sort_order=1)
    clip = _assign(db, patient, "Step-Ups", sort_order=2, video_requirement="required")

    out = _text(client, PHONE, "Done", handle="done-1")
    assert out["kind"] == "exercise_pain_asked"
    assert "How was the pain after, 0 to 10?" in sb.last()
    db.expire_all()
    assert db.get(ExerciseAssignment, slides.id).status == "assigned"  # not until they say

    out = _text(client, PHONE, "3", handle="done-2")
    assert out["kind"] == "exercise_done"
    db.expire_all()
    for row_id in (slides.id, sits.id):
        row = db.get(ExerciseAssignment, row_id)
        assert (row.status, row.pain_after, row.completion_source) == ("done", 3, "sms")
    # the one she asked a clip for stays open, and the reply carries the way to it
    assert db.get(ExerciseAssignment, clip.id).status == "assigned"
    reply = sb.last()
    assert "Marked 2 exercises done, pain 3 after." in reply
    assert "Step-Ups needs a clip of your attempt" in reply and f"{BASE}/a/" in reply
    assert db.get(Patient, patient.id).sms_done_asked_at is None

    # a number with no question pending is not a pain score
    out = _text(client, PHONE, "7", handle="done-3")
    assert out["kind"] not in ("exercise_done", "exercise_pain_asked")


def test_done_with_a_number_needs_no_second_text(client, db, lifter, monkeypatch, public_host):
    sb = Sendblue(monkeypatch)
    patient = lifter()
    row = _assign(db, patient, "Heel Slides")
    assert _text(client, PHONE, "finished, pain 4", handle="d-1")["kind"] == "exercise_done"
    db.expire_all()
    assert (db.get(ExerciseAssignment, row.id).status, db.get(ExerciseAssignment, row.id).pain_after) == ("done", 4)
    assert "Marked 1 exercise done, pain 4 after." in sb.last()
    assert _text(client, PHONE, "done", handle="d-2")["kind"] == "exercise_none"
    assert "already marked done" in sb.last()
    assert _text(client, PHONE, "done 14", handle="d-3")["kind"] == "exercise_pain_asked"


def test_only_the_commands_are_commands():
    words = {"done": True, "Done!": True, "did it": True, "all done": True, "finished 2": True,
             "done 3/10": True, "I'm done": True, "done with it": True,
             "I am done waiting for a call back": False, "what is done today": False,
             "my knee is done for": False, "": False}
    for text, is_done in words.items():
        assert bool(sms_commands._DONE.match(text.strip())) is is_done, text
    assert sms_commands.is_stop("stop", in_conversation=False)
    assert not sms_commands.is_stop("stop", in_conversation=True)  # that ends the question
    assert sms_commands.is_stop("unsubscribe", in_conversation=True)


# --- the demo phone ------------------------------------------------------------------


def _as_persona(client, persona_id: str) -> dict:
    res = client.post("/api/demo/session", json={"persona_id": persona_id, "device_name": "pytest"})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['session_token']}"}


def test_a_presenter_binds_their_own_phone_to_a_persona(client, db, lifter, monkeypatch,
                                                       public_host):
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "sendblue_from_number", "+15049081262")
    sb = Sendblue(monkeypatch)
    # the presenter's number is already on their own real chart
    own = lifter("links-test-own-chart", PHONE)
    june = _as_persona(client, "hirt-june")
    cole = _as_persona(client, "hirt-cole")
    try:
        assert client.get("/api/demo/phone", headers=june).json()["phone"] is None
        assert client.post("/api/demo/phone", headers=june,
                           json={"phone": "nope"}).status_code == 422
        assert client.post("/api/demo/phone", headers=june,
                           json={"phone": "+17135550100"}).status_code == 422

        bound = client.post("/api/demo/phone", headers=june, json={"phone": "(504) 234-0101"})
        assert bound.status_code == 200, bound.text
        state = bound.json()
        assert state["phone"] == PHONE and state["reachable"] is True and state["sent"] is True
        assert state["text_to"] == "+15049081262" and state["text_body"] == "Hi MedPull"
        phone, words = sb.sent[-1]
        assert phone == PHONE and "connected to the MedPull demo" in words
        assert f"Open the app: {BASE}/a/" in words
        assert sb.media[-1] == f"{BASE}/api/contact/hirt.vcf"  # the line's contact card

        db.expire_all()
        # the real chart keeps its number; a text from it is now the persona's
        assert db.get(Patient, own.id).phone == PHONE
        row = _assign(db, db.get(Patient, "hirt-june"), "Heel Slides")
        try:
            out = _text(client, PHONE, "done 2", handle="demo-done")
            assert out["kind"] == "exercise_done"
            db.expire_all()
            assert db.get(ExerciseAssignment, row.id).status == "done"
        finally:
            db.execute(delete(ExerciseAssignment).where(ExerciseAssignment.id == row.id))
            db.commit()

        # one number, one persona: binding it to a second takes it off the first
        client.post("/api/demo/phone", headers=cole, json={"phone": PHONE})
        db.expire_all()
        assert db.get(Patient, "hirt-june").phone is None
        assert db.get(Patient, "hirt-cole").phone == PHONE

        gone = client.delete("/api/demo/phone", headers=cole).json()
        assert gone["phone"] is None and gone["sent"] is False
        db.expire_all()
        assert db.get(Patient, "hirt-cole").demo_phone_bound_at is None
        assert db.get(Patient, own.id).phone == PHONE

        # the contact card itself
        card = client.get("/api/contact/hirt.vcf")
        assert card.status_code == 200 and card.headers["content-type"].startswith("text/vcard")
        assert "FN:H.I.R.T. Physical Therapy via MedPull" in card.text
        assert "TEL;TYPE=CELL:+15049081262" in card.text
        assert client.get("/api/contact/nowhere.vcf").status_code == 404
    finally:
        db.expire_all()
        for pid in ("hirt-june", "hirt-cole"):
            row = db.get(Patient, pid)
            row.phone = row.demo_phone_bound_at = row.sms_welcome_owed_at = None
            row.sms_opt_out_at = row.sms_done_asked_at = None
            db.execute(delete(PatientSession).where(PatientSession.patient_id == pid,
                                                    PatientSession.device_name == "pytest"))
            db.execute(delete(AppLink).where(AppLink.patient_id == pid))
            db.execute(delete(Message).where(Message.patient_id == pid, Message.channel == "sms"))
        db.commit()


def test_the_welcome_waits_for_a_number_that_has_not_texted_the_line(client, db, monkeypatch,
                                                                    public_host):
    from app.notifications import reachability

    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "sendblue_from_number", "+15049081262")
    sb = Sendblue(monkeypatch)
    monkeypatch.setattr(reachability, "lookup", lambda db, phone, fresh=False: "unverified")
    tessa = _as_persona(client, "hirt-tessa")
    try:
        state = client.post("/api/demo/phone", headers=tessa, json={"phone": OTHER_PHONE}).json()
        assert state["phone"] == OTHER_PHONE and state["reachable"] is False
        assert state["sent"] is False and sb.sent == []  # nothing tried: it would be refused
        assert client.get("/api/demo/phone", headers=tessa).json()["reachable"] is False

        # the person texts the line once: that is the proof, and the welcome goes now
        out = _text(client, OTHER_PHONE, "Hi MedPull", handle="first-text")
        assert out["kind"] == "demo_welcome"
        assert "connected to the MedPull demo" in sb.last()
        after = client.get("/api/demo/phone", headers=tessa).json()
        assert after["reachable"] is True and after["sent"] is True
    finally:
        from app.models.mobile import VerifiedContact

        db.expire_all()
        row = db.get(Patient, "hirt-tessa")
        row.phone = row.demo_phone_bound_at = row.sms_welcome_owed_at = None
        db.execute(delete(PatientSession).where(PatientSession.patient_id == "hirt-tessa",
                                                PatientSession.device_name == "pytest"))
        db.execute(delete(AppLink).where(AppLink.patient_id == "hirt-tessa"))
        db.execute(delete(Message).where(Message.patient_id == "hirt-tessa",
                                         Message.channel == "sms"))
        db.execute(delete(VerifiedContact).where(VerifiedContact.phone == OTHER_PHONE))
        db.commit()


def test_the_demo_phone_is_for_a_persona_on_the_demo_stack(client, db, lifter, monkeypatch):
    from app.api.mobile import _issue_session

    real = lifter()
    session = {"Authorization": f"Bearer {_issue_session(db, real, 'pytest', None)}"}
    # the real app: not there at all
    assert client.get("/api/demo/phone", headers=session).status_code == 404
    monkeypatch.setattr(settings, "demo_mode", True)
    # the demo stack, but a session that is a real person's
    assert client.get("/api/demo/phone", headers=session).status_code == 404
    assert client.post("/api/demo/phone", headers=session,
                       json={"phone": OTHER_PHONE}).status_code == 404
    assert client.get("/api/demo/phone").status_code == 401


# --- the morning run -----------------------------------------------------------------


def test_the_morning_run_texts_each_chart_once(client, db, lifter, monkeypatch, public_host):
    sb = Sendblue(monkeypatch)
    due = lifter("links-test-due", PHONE)
    _assign(db, due, "Heel Slides")
    rest = lifter("links-test-resting", OTHER_PHONE)  # nothing on today
    stopped = lifter("links-test-stopped", "+15042340103")
    _assign(db, stopped, "Heel Slides")
    stopped.sms_opt_out_at = datetime.now()
    db.commit()

    # off unless the deployment asks, and only in its hour
    assert reminders.run(db) == {"ran": False, "reason": "EXERCISE_REMINDERS is off", "texted": 0}
    monkeypatch.setattr(settings, "exercise_reminders", True)
    monkeypatch.setattr(settings, "exercise_reminder_hour", 8)
    assert reminders.run(db, datetime.combine(TODAY, datetime.min.time()).replace(hour=7))["ran"] is False
    assert sb.sent == []

    at_eight = datetime.combine(TODAY, datetime.min.time()).replace(hour=8, minute=5)
    report = reminders.run(db, at_eight)
    assert report["ran"] is True and report["texted"] == 1
    assert [phone for phone, _ in sb.sent] == [PHONE]
    assert "Today's plan: 1 exercise, Heel Slides." in sb.last()
    db.expire_all()
    assert db.get(Patient, due.id).exercise_reminded_on == TODAY
    assert db.get(Patient, rest.id).exercise_reminded_on is None

    # the schedule fires again inside the hour: nobody is texted twice
    assert reminders.run(db, at_eight.replace(minute=40))["texted"] == 0
    assert len(sb.sent) == 1


def test_secret_is_the_suites(monkeypatch):
    # the webhook helper above signs with the e2e module's secret
    assert SECRET
