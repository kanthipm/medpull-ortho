"""Patient check-in flow: invite, form, submit. No real SMS can be sent."""

from datetime import datetime, timedelta

from sqlalchemy import select

from app.models.checkin import Checkin, CheckinInvite


def _invite_url(client, patient_id="steve", phone="+15124917035"):
    resp = client.post(f"/api/patients/{patient_id}/checkin-invite", json={"phone": phone})
    assert resp.status_code == 200
    return resp.json()


def _token(url: str) -> str:
    return url.rsplit("/", 1)[1]


def test_invite_creates_token_and_reports_unsent_without_keys(client):
    body = _invite_url(client)
    assert body["sent"] is False  # conftest blanks the Sendblue keys
    assert "/checkin/" in body["url"]
    assert len(_token(body["url"])) > 30


def test_invite_unknown_patient_404(client):
    resp = client.post("/api/patients/nobody/checkin-invite", json={"phone": "+15551234567"})
    assert resp.status_code == 404


def test_form_returns_first_name_and_questions(client):
    token = _token(_invite_url(client)["url"])
    resp = client.get(f"/api/checkin/{token}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["patient_name"] == "Steve"
    assert [q["id"] for q in body["questions"]] == [
        "pain", "swelling", "fever", "sleep", "exercises", "note",
    ]


def test_unknown_token_404(client):
    assert client.get("/api/checkin/not-a-real-token").status_code == 404


def test_submit_stores_transcript_and_burns_token(client, db):
    token = _token(_invite_url(client)["url"])
    before = db.scalars(select(Checkin).where(Checkin.patient_id == "steve")).all()

    resp = client.post(
        f"/api/checkin/{token}",
        json={"pain": 4, "swelling": "yes", "sleep": "rough", "note": "Knee felt stiff."},
    )
    assert resp.status_code == 200

    db.expire_all()
    checkins = db.scalars(select(Checkin).where(Checkin.patient_id == "steve")).all()
    new = [c for c in checkins if c.id not in {c.id for c in before}]
    assert len(new) == 1
    assert new[0].channel == "sms"
    patient_lines = [m.text for m in new[0].messages if m.who == "patient"]
    assert "My pain is about 4 out of 10." in patient_lines
    assert "It looks more swollen than yesterday." in patient_lines
    assert "It was a rough night, I kept waking up." in patient_lines
    assert "Knee felt stiff." in patient_lines

    # token is one-time: both read and resubmit are gone
    assert client.get(f"/api/checkin/{token}").status_code == 410
    assert client.post(f"/api/checkin/{token}", json={"pain": 5}).status_code == 410


def test_submit_rejects_empty_and_invalid_answers(client):
    token = _token(_invite_url(client)["url"])
    assert client.post(f"/api/checkin/{token}", json={}).status_code == 422
    assert client.post(f"/api/checkin/{token}", json={"swelling": "maybe"}).status_code == 422
    assert client.post(f"/api/checkin/{token}", json={"pain": 11}).status_code == 422


def test_expired_token_410(client, db):
    token = _token(_invite_url(client)["url"])
    invite = db.scalars(select(CheckinInvite)).all()[-1]
    invite.expires_at = datetime.now() - timedelta(minutes=1)
    db.commit()
    assert client.get(f"/api/checkin/{token}").status_code == 410
