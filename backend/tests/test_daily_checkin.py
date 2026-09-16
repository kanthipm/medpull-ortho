"""The one-press daily check-in a clinician fires from the console.

The invariant worth protecting here is that the check-in reaches the patient
whatever Sendblue does with it: a refused text, a placeholder number, no
number at all — the task and the thread row with the button still land. Most
demo patients carry numbers Sendblue will not deliver to, so the path where
the text fails is the normal path, not the edge case.

Every test works on a throwaway chart it creates and then forgets. The seeded
database is session-scoped and the rest of the suite asserts on the roster,
so a test here that enrolled or texted a roster patient would fail other
files rather than this one.
"""

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.adherence import AdherenceTask
from app.models.enums import ProcedureType
from app.models.mobile import Message, PatientSession
from app.models.patient import Patient
from tests.test_mobile import _forget_patient


@pytest.fixture()
def chart(db):
    """A fresh patient, removed afterwards along with everything that points
    at them, so the seeded roster is intact for the next file."""
    made: list[str] = []
    counter = [0]

    def create(*, phone: str | None = None, surgical: bool = True) -> Patient:
        counter[0] += 1
        pid = f"checkin-test-{counter[0]}"
        template = db.get(Patient, "linda")
        patient = Patient(
            id=pid,
            name="Dana Vaughn",
            initials="DV",
            age=57,
            sex="F",
            procedure_type=ProcedureType.TKA if surgical else ProcedureType.NONE,
            procedure_display="Total Knee Replacement (TKA)" if surgical else "General care",
            surgery_date=date.today() - timedelta(days=6),
            discharge_date=date.today() - timedelta(days=5),
            surgeon_id=template.surgeon_id,
            assigned_provider_id=template.assigned_provider_id,
            hospital_id=template.hospital_id,
            phone=phone,
        )
        db.add(patient)
        db.commit()
        made.append(pid)
        return patient

    yield create

    for pid in made:
        _forget_patient(db, pid)


def _fire(client, patient_id):
    resp = client.post(f"/api/patients/{patient_id}/actions/daily-checkin")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _rows(db, patient_id):
    db.expire_all()
    return list(db.scalars(
        select(Message).where(Message.patient_id == patient_id).order_by(Message.id)
    ).all())


def _checkins(db, patient_id):
    db.expire_all()
    return list(db.scalars(
        select(AdherenceTask).where(
            AdherenceTask.patient_id == patient_id, AdherenceTask.kind == "checkin"
        )
    ).all())


def _enroll(client, patient: Patient):
    resp = client.post(
        "/api/mobile/enroll",
        json={"patient_id": patient.id, "hospital_id": patient.hospital_id,
              "phone": patient.phone, "device_name": "iPhone (test)"},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['session_token']}"}


# --- the press ------------------------------------------------------------------


def test_unknown_patient_404(client):
    assert client.post("/api/patients/nobody/actions/daily-checkin").status_code == 404


def test_one_press_creates_the_task_and_a_thread_row_with_a_button(client, db, chart):
    patient = chart()
    body = _fire(client, patient.id)

    assert body["ok"] is True and body["in_app"] is True
    assert body["reused"] is False

    task = db.get(AdherenceTask, body["task_id"])
    assert task.kind == "checkin" and task.patient_id == patient.id
    assert task.status in ("pending", "sent")

    row = _rows(db, patient.id)[-1]
    assert row.action_kind == "open_task"
    assert row.action_task_id == task.id
    assert row.action_label == "Start check-in"
    assert "check-in" in row.text.lower()


def test_pressing_twice_reuses_the_open_check_in(client, db, chart):
    patient = chart()
    first = _fire(client, patient.id)
    second = _fire(client, patient.id)

    assert second["reused"] is True
    assert second["task_id"] == first["task_id"]
    assert len(_checkins(db, patient.id)) == 1


def test_never_carries_the_patients_name(client, db, chart):
    patient = chart()
    _fire(client, patient.id)
    text = _rows(db, patient.id)[-1].text
    for part in patient.name.split():
        assert part.lower() not in text.lower()


def test_no_phone_is_not_a_failed_delivery(client, db, chart):
    """A patient with no number was never texted, which must not draw the
    thread's red "not delivered" badge — there was nothing to deliver."""
    patient = chart(phone=None)
    body = _fire(client, patient.id)

    assert body["sms"]["attempted"] is False
    row = _rows(db, patient.id)[-1]
    assert row.delivery_status is None
    assert row.channel == "app"


def test_unenrolled_patient_gets_a_link_enrolled_one_does_not(client, db, chart):
    """The link is the way in for somebody without the app. Somebody who has
    it already reaches the check-in behind their own session, so their text
    carries no public URL at all."""
    stranger = chart(phone="+15125550188")
    assert _fire(client, stranger.id)["sms"]["linked"] is True
    assert "/t/" in _rows(db, stranger.id)[-1].text

    user = chart(phone="+15125550199")
    db.add(PatientSession(
        patient_id=user.id, token_hash="test-enrolled-hash",
        created_at=datetime.now(), last_seen_at=datetime.now(),
    ))
    db.commit()

    assert _fire(client, user.id)["sms"]["linked"] is False
    text = _rows(db, user.id)[-1].text
    assert "/t/" not in text and "http" not in text


def test_a_general_patient_is_not_asked_about_an_incision(client, db, chart):
    """The question set follows the patient, not the button: somebody who
    never had surgery has no incision to report swelling around."""
    from app.tasks.service import questions_for

    task = db.get(AdherenceTask, _fire(client, chart(surgical=False).id)["task_id"])
    ids = [q["id"] for q in questions_for(task)]
    assert "swelling" not in ids and ids[0] == "pain"


# --- what the patient's app actually receives ------------------------------------


def test_the_app_receives_the_message_with_a_button_into_the_task(client, db, chart):
    """The whole point of the feature: the patient's thread carries an action
    the app can draw, pointing at the task the same press created."""
    patient = chart(phone="+15125550201")
    headers = _enroll(client, patient)
    body = _fire(client, patient.id)

    thread = client.get("/api/mobile/messages", headers=headers).json()["messages"]
    assert thread[-1]["action"] == {
        "kind": "open_task",
        "task_id": body["task_id"],
        "label": "Start check-in",
    }

    # And the task that button opens is a real check-in the app can render.
    listing = client.get("/api/mobile/tasks", headers=headers).json()
    task = next(t for t in listing["open"] if t["id"] == body["task_id"])
    assert task["kind"] == "checkin"
    assert [q["id"] for q in task["questions"]][:2] == ["pain", "swelling"]


def test_ordinary_lines_carry_no_action(client, chart):
    patient = chart(phone="+15125550202")
    headers = _enroll(client, patient)
    client.post("/api/mobile/messages", headers=headers, json={"text": "Knee feels stiff"})
    thread = client.get("/api/mobile/messages", headers=headers).json()["messages"]
    assert all(m["action"] is None for m in thread)


def test_the_console_thread_shows_the_same_action(client, chart):
    """A clinician reading the thread sees what the patient was actually
    sent, button included — otherwise the two views disagree."""
    patient = chart()
    body = _fire(client, patient.id)
    thread = client.get(f"/api/patients/{patient.id}/messages").json()["messages"]
    line = next(m for m in thread if (m.get("action") or {}).get("task_id") == body["task_id"])
    assert line["action"]["label"] == "Start check-in"


def test_completing_the_check_in_from_the_app_writes_a_transcript(client, db, chart):
    """The app's check-in posts to the same endpoint as every other surface,
    so the care team's history and digest see it unchanged."""
    from app.models.checkin import Checkin

    patient = chart(phone="+15125550203")
    headers = _enroll(client, patient)
    body = _fire(client, patient.id)

    done = client.post(
        f"/api/mobile/tasks/{body['task_id']}/complete",
        headers=headers,
        json={"answers": {"pain": 4, "swelling": "no", "sleep": "well"}},
    )
    assert done.status_code == 200, done.text
    db.expire_all()

    written = db.scalars(select(Checkin).where(Checkin.patient_id == patient.id)).all()
    assert len(written) == 1
    said = " ".join(m.text for m in written[0].messages)
    assert "4 out of 10" in said and "No new swelling." in said
