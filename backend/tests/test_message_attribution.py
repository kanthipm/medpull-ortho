"""Who a message is from, and what a text is allowed to carry.

Three rules, one place each:

* the copilot speaks untagged (that is the default the patient assumes) and a
  clinician's message is signed with their name;
* no outbound text carries the patient's name, whoever typed it;
* a text that has somewhere to go in the app carries one labelled link.
"""

from __future__ import annotations

from app.models.mobile import Message
from app.models.patient import CareTeamMember
from app.notifications import sendblue
from tests.test_mobile import _forget_patient
from tests.test_onboarding_e2e import Sendblue

DR = CareTeamMember(id="ct_chen", name="Dr. Chen", role="surgeon")


# --- composition -------------------------------------------------------------


def test_a_clinicians_text_is_signed_and_the_copilots_is_not():
    assert sendblue.compose("Take it easy today.", member=DR).startswith(
        "Dr. Chen (your care team): "
    )
    # No tag at all, not an "AI" one: tagging the default would make the tag
    # that matters invisible.
    assert sendblue.compose("Take it easy today.") == "Take it easy today."


def test_the_patients_name_never_survives_into_a_text():
    out = sendblue.compose("Hi Marcus, how is the knee?", patient_name="Marcus Bennett")
    assert "Marcus" not in out
    assert out == "Hi, how is the knee?"
    # Full name, surname alone, and any casing.
    for body in ("Hello Marcus Bennett.", "Thanks BENNETT.", "hi marcus"):
        assert "marcus" not in sendblue.compose(body, patient_name="Marcus Bennett").lower()
        assert "bennett" not in sendblue.compose(body, patient_name="Marcus Bennett").lower()


def test_redaction_leaves_an_ordinary_sentence_behind():
    """A name cut out of a greeting must not leave ragged punctuation: the
    patient reads the result, and "— your walk is due" looks broken."""
    assert sendblue.redact_name("Hi Marcus, how are you?", "Marcus Bennett") == "Hi, how are you?"
    assert sendblue.redact_name("Marcus — your walk is due.", "Marcus Bennett") == (
        "Your walk is due."
    )
    assert sendblue.redact_name("Linda, your sling comes off Friday.", "Linda Park") == (
        "Your sling comes off Friday."
    )
    # Somebody else's name that happens to match nothing here is left alone.
    assert sendblue.redact_name("Dr. Bennett called.", "Marcus Wright") == "Dr. Bennett called."


def test_a_clinician_sharing_the_patients_surname_keeps_their_own_name():
    """Redaction runs before the signature, so stripping "Park" from the body
    cannot strip "Dr. Park" from the tag."""
    park = CareTeamMember(id="ct_park", name="Dr. Park", role="surgeon")
    out = sendblue.compose("Linda Park, your sling comes off Friday.",
                           patient_name="Linda Park", member=park)
    assert out == "Dr. Park (your care team): Your sling comes off Friday."


def test_the_link_is_labelled_and_on_its_own_line():
    out = sendblue.compose("A new task is ready.", link="https://x/t/tok",
                           link_label="Open the task")
    assert out.endswith("\n\nOpen the task: https://x/t/tok")


# --- the send paths ----------------------------------------------------------


def test_a_console_message_is_signed_carries_no_name_and_is_marked_care_team(
    client, db, monkeypatch
):
    sb = Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Nora Vance", "phone": "+15125550701",
        "had_surgery": False}).json()
    pid = joined["me"]["patient"]["id"]

    try:
        resp = client.post(f"/api/patients/{pid}/actions/message",
                           json={"text": "Hi Nora, how did last night go?"})
        assert resp.status_code == 200, resp.text

        _phone, content = sb.sent[-1]
        assert "(your care team): " in content
        assert "Nora" not in content

        body = resp.json()["message"]
        assert body["authored_by"]["kind"] == "care_team"
        assert body["authored_by"]["name"]
        # The stored copy keeps what the clinician actually typed; only the
        # text that leaves the building is rewritten.
        assert "Nora" in body["text"]
    finally:
        _forget_patient(db, pid)


def test_the_copilots_own_reply_is_marked_ai_and_shows_no_name(client, db, monkeypatch):
    sb = Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Owen Pike", "phone": "+15125550702",
        "had_surgery": False}).json()
    pid = joined["me"]["patient"]["id"]
    sb.sent.clear()

    try:
        client.post("/api/webhooks/sendblue", headers={"sb-signing-secret": "whsec-e2e"}, json={
            "from_number": "+15125550702", "content": "what do I have today?",
            "is_outbound": False, "message_handle": "mh-attr-1"})

        assert sb.sent, "the copilot should have answered by text"
        _phone, reply = sb.sent[-1]
        assert "(your care team)" not in reply
        assert "Owen" not in reply

        rows = client.get(f"/api/patients/{pid}/messages").json()["messages"]
        outbound = [m for m in rows if m["sender"] == "copilot"]
        assert outbound and all(m["authored_by"]["kind"] == "ai" for m in outbound)
        assert all(m["authored_by"]["name"] is None for m in outbound)
    finally:
        _forget_patient(db, pid)


def test_a_clinician_assigned_task_is_signed_and_a_system_one_is_not(client, db, monkeypatch):
    sb = Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Pia Randall", "phone": "+15125550703",
        "had_surgery": False}).json()
    pid = joined["me"]["patient"]["id"]
    sb.sent.clear()

    try:
        client.post(f"/api/patients/{pid}/actions/assign-task",
                    json={"title": "Evening dose", "kind": "medication"})
        _phone, content = sb.sent[-1]
        assert "(your care team): " in content, content
        assert "Pia" not in content
        assert "\n\nOpen the task: " in content

        # The same dispatch with nobody behind it stays unsigned.
        from app.models.patient import Patient
        from app.tasks import service as tasks

        patient = db.get(Patient, pid)
        task, _ = tasks.create_task(db, patient, title="Automatic nudge", kind="custom",
                                    notify=False)
        tasks.dispatch(db, task, patient, "https://medpull.example")
        db.commit()
        _phone, auto = sb.sent[-1]
        assert "(your care team)" not in auto
        assert "\n\nOpen the task: " in auto
    finally:
        _forget_patient(db, pid)


def test_the_patient_app_is_told_who_is_speaking(client, db, monkeypatch):
    Sendblue(monkeypatch)
    joined = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Quinn Adler", "phone": "+15125550704",
        "had_surgery": False}).json()
    pid = joined["me"]["patient"]["id"]
    token = joined["session_token"]

    try:
        client.post(f"/api/patients/{pid}/actions/message", json={"text": "Checking in on you."})

        rows = client.get("/api/mobile/messages",
                          headers={"Authorization": f"Bearer {token}"}).json()["messages"]
        clinician = [m for m in rows if m["authored_by"] == "care_team"]
        assert clinician, rows
        assert clinician[-1]["author_name"], "the app should name the clinician behind it"
    finally:
        _forget_patient(db, pid)


def test_an_old_row_without_the_column_reads_as_ai(db):
    """Rows written before attribution existed must not claim a clinician."""
    from app.api.mobile import _authored_by

    assert _authored_by(Message(sender="copilot", authored_by=None)) == "ai"
    assert _authored_by(Message(sender="care_team", authored_by=None)) == "care_team"
    assert _authored_by(Message(sender="patient", authored_by=None)) == "ai"
