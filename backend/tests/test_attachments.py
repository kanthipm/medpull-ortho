"""Images and files on the patient <-> care team thread.

The suite runs with no object store, so every test here exercises the
direct-upload path: the API takes the bytes and the same rows, views and
authorization checks apply as when S3 is presigning.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, select

from app.models.attachment import Attachment
from app.models.hospital import Hospital
from app.models.mobile import Message, PatientSession
from app.models.patient import Patient
from app.storage import blobs
from tests.test_onboarding_e2e import Sendblue, _auth
from tests.test_mobile import _forget_patient

# Real signatures: the server checks the bytes against the declared type.
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"x" * 64


@pytest.fixture()
def joined(client, db, monkeypatch):
    """A patient with an app session, removed again afterwards."""
    Sendblue(monkeypatch)
    body = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Attach Patient", "phone": "+15125550910",
        "had_surgery": True, "procedure_type": "TKA",
        "surgery_date": date.today().isoformat()}).json()
    yield body["me"]["patient"]["id"], _auth(body["session_token"])
    _forget_patient(db, body["me"]["patient"]["id"])


def _upload(client, headers, data=JPEG, content_type="image/jpeg", name="wound.jpg"):
    return client.post(
        f"/api/mobile/attachments/direct?filename={name}",
        headers={**headers, "Content-Type": content_type},
        content=data,
    )


# --- the patient's own path -------------------------------------------------------


def test_a_patient_attaches_a_photo_to_a_message(client, db, joined):
    pid, headers = joined

    # with no object store the ticket says so, and names the cap
    ticket = client.get("/api/mobile/attachments/upload-ticket",
                        params={"content_type": "image/jpeg", "byte_size": len(JPEG)},
                        headers=headers).json()
    assert ticket["direct"] is True and ticket["upload"] is None
    assert ticket["max_bytes"] == blobs.MAX_BYTES
    assert ticket["storage_key"].startswith(f"attachments/{pid}/")

    up = _upload(client, headers)
    assert up.status_code == 200, up.text
    a = up.json()["attachment"]
    assert a["kind"] == "image" and a["content_type"] == "image/jpeg"
    assert a["byte_size"] == len(JPEG) and a["filename"] == "wound.jpg"
    assert a["withdrawn"] is False and a["sha256"]

    # a photo with no caption is a valid message
    sent = client.post("/api/mobile/messages", headers=headers,
                       json={"text": "", "attachment_ids": [a["id"]]})
    assert sent.status_code == 200, sent.text
    line = sent.json()["message"]
    assert line["text"] == ""
    assert [f["id"] for f in line["attachments"]] == [a["id"]]

    # ...and it reads back on the thread, in the app and in the console
    thread = client.get("/api/mobile/messages", headers=headers).json()["messages"]
    mine = [m for m in thread if m["attachments"]]
    assert len(mine) == 1 and mine[0]["attachments"][0]["kind"] == "image"
    console = client.get(f"/api/patients/{pid}/messages").json()["messages"]
    assert any(m["attachments"] for m in console)

    # the care team is told something arrived, not an empty message
    from app.models.notification import Notification

    db.expire_all()
    notes = db.scalars(select(Notification).where(Notification.patient_id == pid)).all()
    assert any("photo or file" in (n.body or "") for n in notes)

    # the bytes come back with headers that cannot be made to execute
    raw = client.get(f"/api/mobile/attachments/{a['id']}/raw", headers=headers)
    assert raw.status_code == 200 and raw.content == JPEG
    assert raw.headers["content-type"].startswith("image/jpeg")
    assert raw.headers["x-content-type-options"] == "nosniff"
    assert "inline" in raw.headers["content-disposition"]


def test_a_document_is_offered_as_a_download_not_a_page(client, joined):
    _pid, headers = joined
    up = _upload(client, headers, data=PDF, content_type="application/pdf", name="exercises.pdf")
    assert up.status_code == 200
    a = up.json()["attachment"]
    assert a["kind"] == "file"
    raw = client.get(f"/api/mobile/attachments/{a['id']}/raw", headers=headers)
    assert raw.headers["content-disposition"].startswith("attachment")


def test_a_message_with_neither_words_nor_a_file_is_refused(client, joined):
    _pid, headers = joined
    assert client.post("/api/mobile/messages", headers=headers,
                       json={"text": "   ", "attachment_ids": []}).status_code == 422


def test_bytes_that_are_not_what_they_claim_are_refused_and_not_stored(client, db, joined):
    pid, headers = joined
    resp = _upload(client, headers, data=b"<html><script>alert(1)</script>", name="x.jpg")
    assert resp.status_code == 422
    assert "does not look like" in resp.json()["detail"]
    db.expire_all()
    # no row, and nothing left in storage either
    assert db.scalars(select(Attachment).where(Attachment.patient_id == pid)).all() == []
    directory = blobs.local_root() / f"attachments/{pid}"
    assert not directory.is_dir() or not any(directory.rglob("*"))


def test_an_unacceptable_type_and_an_oversized_file_are_refused(client, joined):
    _pid, headers = joined
    bad_type = _upload(client, headers, data=b"MZ\x00\x00", content_type="application/x-msdownload")
    assert bad_type.status_code == 422 and "not one we accept" in bad_type.json()["detail"]
    huge = _upload(client, headers, data=JPEG + b"\x00" * (blobs.MAX_BYTES + 1))
    assert huge.status_code == 413 and "larger than" in huge.json()["detail"]


def test_one_patient_cannot_read_or_claim_another_patients_file(client, db, joined, monkeypatch):
    pid, headers = joined
    mine = _upload(client, headers).json()["attachment"]

    other = client.post("/api/mobile/join", json={
        "hospital_id": "hosp_demo", "name": "Nosy Person", "phone": "+15125550911",
        "had_surgery": False}).json()
    other_headers = _auth(other["session_token"])
    other_id = other["me"]["patient"]["id"]
    try:
        # cannot read it, cannot fetch the bytes
        assert client.get(f"/api/mobile/attachments/{mine['id']}",
                          headers=other_headers).status_code == 404
        assert client.get(f"/api/mobile/attachments/{mine['id']}/raw",
                          headers=other_headers).status_code == 404
        assert client.delete(f"/api/mobile/attachments/{mine['id']}",
                             headers=other_headers).status_code == 404
        # and cannot hang it on their own message
        sent = client.post("/api/mobile/messages", headers=other_headers,
                           json={"text": "look at this", "attachment_ids": [mine["id"]]})
        assert sent.status_code == 200
        assert sent.json()["message"]["attachments"] == []
        # no session at all reads nothing
        assert client.get(f"/api/mobile/attachments/{mine['id']}").status_code == 401
    finally:
        _forget_patient(db, other_id)
    db.expire_all()
    assert db.get(Attachment, mine["id"]).patient_id == pid


def test_a_confirm_cannot_be_pointed_at_another_patients_key(client, joined):
    _pid, headers = joined
    resp = client.post("/api/mobile/attachments", headers=headers, json={
        "storage_key": "attachments/marcus/deadbeef.jpg",
        "content_type": "image/jpeg", "byte_size": 10})
    assert resp.status_code == 403
    assert "does not belong" in resp.json()["detail"]


def test_withdrawing_a_file_deletes_the_bytes_and_keeps_the_line(client, db, joined):
    _pid, headers = joined
    a = _upload(client, headers).json()["attachment"]
    client.post("/api/mobile/messages", headers=headers,
                json={"text": "here it is", "attachment_ids": [a["id"]]})
    db.expire_all()
    key = db.get(Attachment, a["id"]).storage_key
    assert blobs.stat(key) is not None

    gone = client.delete(f"/api/mobile/attachments/{a['id']}", headers=headers)
    assert gone.status_code == 200 and gone.json()["attachment"]["withdrawn"] is True
    assert blobs.stat(key) is None, "the bytes must actually stop existing"
    db.expire_all()
    assert db.get(Attachment, a["id"]).deleted_at is not None
    # the message survives, and the line says a file was taken back rather
    # than silently losing it — a reply to nothing reads worse than this
    thread = client.get("/api/mobile/messages", headers=headers).json()["messages"]
    line = next(m for m in thread if m["text"] == "here it is")
    assert len(line["attachments"]) == 1
    withdrawn = line["attachments"][0]
    assert withdrawn["withdrawn"] is True and "url" not in withdrawn
    # and it cannot be fetched by any route
    assert client.get(f"/api/mobile/attachments/{a['id']}/raw",
                      headers=headers).status_code == 404
    assert client.get(f"/api/mobile/attachments/{a['id']}",
                      headers=headers).status_code == 404


# --- the console ------------------------------------------------------------------


def test_the_console_honours_a_hospital_token_without_requiring_one(client, db, joined):
    """The console has no sign-in: every other route here answers on origin
    verification alone. A token sent is still checked and still scopes the
    lookup, so a multi-tenant console keeps the guarantee."""
    pid, _headers = joined
    db.expire_all()
    db.get(Hospital, "hosp_demo").access_token = "tok-attach"
    db.commit()

    # no token: works, like the message route the file hangs off
    bare = client.get(f"/api/patients/{pid}/attachments/upload-ticket",
                      params={"content_type": "image/jpeg", "byte_size": 100})
    assert bare.status_code == 200

    # a token that is wrong is refused, never ignored
    assert client.get(f"/api/patients/{pid}/attachments/upload-ticket",
                      params={"content_type": "image/jpeg", "byte_size": 100},
                      headers=_auth("not-the-token")).status_code == 401

    ok = client.get(f"/api/patients/{pid}/attachments/upload-ticket",
                    params={"content_type": "application/pdf", "byte_size": 200},
                    headers=_auth("tok-attach"))
    assert ok.status_code == 200 and ok.json()["direct"] is True

    # a patient at another hospital is not this token's business
    assert client.get("/api/patients/linda/attachments/upload-ticket",
                      params={"content_type": "image/jpeg", "byte_size": 100},
                      headers=_auth("tok-attach")).status_code == 404


def test_the_console_can_send_the_bytes_when_there_is_no_object_store(client, db, joined):
    pid, _headers = joined
    r = client.post(f"/api/patients/{pid}/attachments/direct?filename=exercises.pdf",
                    headers={"Content-Type": "application/pdf"}, content=PDF)
    assert r.status_code == 200, r.text
    a = r.json()["attachment"]
    assert a["kind"] == "file" and a["uploaded_by"] == "care_team" and a["source"] == "console"

    db.expire_all()
    row = db.get(Attachment, a["id"])
    assert row.available and row.uploaded_by_id == db.get(Patient, pid).assigned_provider_id
    assert blobs.read(row.storage_key) == PDF

    # it reaches the patient's app thread as the clinician's message
    sent = client.post(f"/api/patients/{pid}/actions/message",
                       json={"text": "", "attachment_ids": [a["id"]]})
    assert sent.status_code == 200, sent.text
    assert sent.json()["message"]["attachments"][0]["id"] == a["id"]

    # and a made-up sender is refused rather than silently reassigned
    assert client.post(f"/api/patients/{pid}/attachments/direct?sender_id=ct_nobody",
                       headers={"Content-Type": "application/pdf"},
                       content=PDF).status_code == 404


def test_a_clinician_sends_a_file_and_the_text_never_carries_it(client, db, joined, monkeypatch):
    pid, headers = joined
    sb = Sendblue(monkeypatch)
    db.expire_all()
    db.get(Hospital, "hosp_demo").access_token = "tok-attach"
    db.commit()

    # the clinician's file is uploaded against the patient's chart
    key = client.get(f"/api/patients/{pid}/attachments/upload-ticket",
                     params={"content_type": "application/pdf", "byte_size": len(PDF)},
                     headers=_auth("tok-attach")).json()["storage_key"]
    blobs.put(key, PDF, "application/pdf")
    confirmed = client.post(f"/api/patients/{pid}/attachments", headers=_auth("tok-attach"),
                            json={"storage_key": key, "content_type": "application/pdf",
                                  "byte_size": len(PDF), "filename": "home exercises.pdf"})
    assert confirmed.status_code == 200, confirmed.text
    a = confirmed.json()["attachment"]
    assert a["uploaded_by"] == "care_team" and a["source"] == "console"

    sent = client.post(f"/api/patients/{pid}/actions/message",
                       json={"text": "", "attachment_ids": [a["id"]]})
    assert sent.status_code == 200, sent.text
    assert [f["id"] for f in sent.json()["message"]["attachments"]] == [a["id"]]

    # the text says a file arrived and carries neither the file nor the name
    texted = sb.last()
    assert "sent you a file" in texted
    assert "Attach" not in texted and "exercises.pdf" not in texted
    assert "http" not in texted, "an enrolled patient already has it in the app"

    # the patient sees it in their own thread
    thread = client.get("/api/mobile/messages", headers=headers).json()["messages"]
    assert any(f["filename"] == "home exercises.pdf"
               for m in thread for f in m["attachments"])


def test_a_confirm_is_refused_when_the_object_never_arrived(client, db, joined):
    pid, _headers = joined
    db.expire_all()
    db.get(Hospital, "hosp_demo").access_token = "tok-attach"
    db.commit()
    key = client.get(f"/api/patients/{pid}/attachments/upload-ticket",
                     params={"content_type": "image/png", "byte_size": len(PNG)},
                     headers=_auth("tok-attach")).json()["storage_key"]
    # nothing was uploaded against it
    resp = client.post(f"/api/patients/{pid}/attachments", headers=_auth("tok-attach"),
                       json={"storage_key": key, "content_type": "image/png"})
    assert resp.status_code == 409 and "not arrived" in resp.json()["detail"]

    # and a second confirm of a real one is refused rather than duplicated
    blobs.put(key, PNG, "image/png")
    first = client.post(f"/api/patients/{pid}/attachments", headers=_auth("tok-attach"),
                        json={"storage_key": key, "content_type": "image/png"})
    assert first.status_code == 200
    again = client.post(f"/api/patients/{pid}/attachments", headers=_auth("tok-attach"),
                        json={"storage_key": key, "content_type": "image/png"})
    assert again.status_code == 409 and "already confirmed" in again.json()["detail"]


# --- the seams ---------------------------------------------------------------------


def test_the_copilot_is_told_a_photo_arrived_rather_than_reading_a_blank_line(client, db, joined):
    """An image can be the whole message. Left as an empty string the model
    answers as if nothing was said; it must also never claim to have seen
    the picture."""
    from app.agent.copilot import _context

    pid, headers = joined
    a = _upload(client, headers).json()["attachment"]
    client.post("/api/mobile/messages", headers=headers,
                json={"text": "", "attachment_ids": [a["id"]]})
    db.expire_all()
    context = _context(db, db.get(Patient, pid), [])
    assert "sent a photo or file" in context
    assert "which you cannot see" in context


def test_attachments_follow_a_patient_through_a_link_and_die_with_a_chart(client, db, joined):
    from app.identity import delete_patient

    pid, headers = joined
    a = _upload(client, headers).json()["attachment"]
    db.expire_all()
    key = db.get(Attachment, a["id"]).storage_key
    assert blobs.stat(key) is not None

    # a chart's removal takes the bytes with it, not just the rows
    client.post("/api/mobile/signout", headers=headers)
    db.expire_all()
    result = delete_patient(db, db.get(Patient, pid))
    assert result["rows"]["attachments"] == 1
    assert result["rows"]["attachment_blobs"] >= 1
    assert blobs.stat(key) is None
    assert db.get(Attachment, a["id"]) is None
    # the fixture's own teardown must not trip over the deleted row
    db.execute(delete(PatientSession).where(PatientSession.patient_id == pid))
    db.execute(delete(Message).where(Message.patient_id == pid))
    db.commit()


# --- a picture arriving by text ---------------------------------------------------


def _mms(client, number, urls, content="", key="media_url"):
    from tests.test_onboarding_e2e import SECRET

    body = {"from_number": number, "content": content, "is_outbound": False,
            key: urls if len(urls) != 1 else urls[0]}
    r = client.post("/api/webhooks/sendblue", json=body, headers={"sb-signing-secret": SECRET})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_texted_photo_with_no_words_is_stored_acknowledged_and_escalated(
    client, db, joined, monkeypatch
):
    """The one inbound path with nobody watching. A caption-less picture used
    to be dropped as an empty message: no row, no file, nobody told."""
    from app.models.notification import Notification

    pid, _ = joined
    provider = Sendblue(monkeypatch)
    monkeypatch.setattr(blobs, "fetch_remote", lambda url: (JPEG, "image/jpeg"))

    r = _mms(client, "+15125550910", ["https://cdn.sendblue.co/m/abc.jpg"])
    assert r["handled"] is True and r["kind"] == "photo" and r["attachments"] == 1

    db.expire_all()
    rows = db.scalars(select(Attachment).where(Attachment.patient_id == pid)).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.source == "sms" and row.uploaded_by == "patient" and row.available
    assert row.content_type == "image/jpeg" and row.byte_size == len(JPEG)
    # the bytes are ours now, and the provider's public link is not kept
    assert row.source_url is None and blobs.read(row.storage_key) == JPEG
    # it hangs off the patient's own line, so the thread shows it in place
    assert db.get(Message, row.message_id).sender == "patient"

    # the patient is told a person will look, and nothing claims to have seen it
    reply = provider.last()
    assert "care team will see it" in reply
    assert "incision" not in reply.lower() and "looks" not in reply.lower()

    # and a clinician is told, because no clinician was in this loop
    note = db.scalars(
        select(Notification).where(Notification.patient_id == pid)
        .order_by(Notification.id.desc())
    ).first()
    assert note is not None and "sent a photo or file" in note.title


def test_a_texted_photo_that_cannot_be_downloaded_is_still_reported(
    client, db, joined, monkeypatch
):
    """A fetch fails inside the write lock. Losing the picture silently is
    worse than saying one arrived that we could not keep."""
    from app.models.notification import Notification

    pid, _ = joined
    Sendblue(monkeypatch)

    def refuse(url):
        raise blobs.BlobError("timed out")

    monkeypatch.setattr(blobs, "fetch_remote", refuse)
    r = _mms(client, "+15125550910", ["https://cdn.sendblue.co/m/gone.jpg"], content="see this")
    assert r["handled"] is True and r["attachments"] == 0

    db.expire_all()
    row = db.scalars(select(Attachment).where(Attachment.patient_id == pid)).one()
    assert row.available is False  # never shown: there are no bytes to show
    assert row.source_url == "https://cdn.sendblue.co/m/gone.jpg"
    # a caption also raises the copilot's own "sent a message", so look for
    # the one that says a file arrived rather than the newest
    bodies = [
        n.body for n in db.scalars(
            select(Notification).where(Notification.patient_id == pid)
        ).all()
    ]
    assert any("could not be downloaded" in b for b in bodies), bodies


def test_a_caption_still_runs_the_conversation_and_keeps_the_photo(client, db, joined, monkeypatch):
    """Words plus a picture is one message: the words are answered as they
    always were, and the file rides along."""
    pid, _ = joined
    provider = Sendblue(monkeypatch)
    monkeypatch.setattr(blobs, "fetch_remote", lambda url: (JPEG, "image/jpeg"))

    r = _mms(client, "+15125550910", ["https://cdn.sendblue.co/m/a.jpg"],
             content="is this normal?")
    assert r["kind"] == "message" and r["attachments"] == 1
    assert provider.sent  # the copilot answered the words
    db.expire_all()
    line = db.get(Message, db.scalars(
        select(Attachment.message_id).where(Attachment.patient_id == pid)).first())
    assert line.text == "is this normal?"


def test_a_link_on_a_host_we_do_not_trust_is_not_followed(client, db, joined, monkeypatch):
    """The link comes from an unauthenticated webhook body, so it is an
    attacker-chosen URL until proven otherwise."""
    pid, _ = joined
    Sendblue(monkeypatch)
    r = _mms(client, "+15125550910", ["https://sendblue.co.evil.example/x.jpg"], content="hi")
    assert r["handled"] is True
    db.expire_all()
    row = db.scalars(select(Attachment).where(Attachment.patient_id == pid)).one()
    assert row.available is False and row.storage_key.startswith("pending:")


def test_media_links_are_read_whatever_key_they_arrive_under(client, db, joined, monkeypatch):
    pid, _ = joined
    Sendblue(monkeypatch)
    monkeypatch.setattr(blobs, "fetch_remote", lambda url: (PNG, "image/png"))
    r = _mms(client, "+15125550910",
             ["https://cdn.sendblue.co/m/1.png", "https://cdn.sendblue.co/m/2.png"],
             key="mediaURLs")
    assert r["attachments"] == 2
    db.expire_all()
    assert db.scalars(select(Attachment).where(Attachment.patient_id == pid)).all().__len__() == 2


def test_a_clinician_can_take_back_a_file_they_sent(client, db, joined):
    """The wrong scan on the wrong chart, already showing in the patient's
    app. Whoever put it there has to be able to remove it."""
    pid, headers = joined
    a = client.post(f"/api/patients/{pid}/attachments/direct?filename=wrong.pdf",
                    headers={"Content-Type": "application/pdf"}, content=PDF).json()["attachment"]
    client.post(f"/api/patients/{pid}/actions/message",
                json={"text": "Here is your sheet", "attachment_ids": [a["id"]]})
    db.expire_all()
    key = db.get(Attachment, a["id"]).storage_key

    gone = client.delete(f"/api/patients/{pid}/attachments/{a['id']}")
    assert gone.status_code == 200 and gone.json()["attachment"]["withdrawn"] is True
    assert blobs.stat(key) is None  # the bytes, not just the flag

    # the line stays and says so, in both threads
    console = client.get(f"/api/patients/{pid}/messages").json()["messages"][-1]
    assert console["attachments"][0]["withdrawn"] is True
    assert "url" not in console["attachments"][0]
    app_side = client.get("/api/mobile/messages", headers=headers).json()["messages"][-1]
    assert app_side["attachments"][0]["withdrawn"] is True

    # and the patient cannot read bytes that are gone
    assert client.get(f"/api/mobile/attachments/{a['id']}/raw",
                      headers=headers).status_code == 404
