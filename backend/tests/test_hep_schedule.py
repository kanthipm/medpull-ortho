"""The exercise schedule (docs/dev/hep-schedule.md): the week grid scoped by
clinic, the therapist's own clip, the patient's day with a pain score and a
return clip, the demo screen's session, and the five lifters' seeded
calendar.

Writes happen on a throwaway HIRT chart and are removed afterwards; the
seeded five are only read, and their calendar is pinned at the end.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.config import settings
from app.console_credentials import mint
from app.hep.models import AuditEvent, Exercise, ExerciseAssignment, ExerciseMedia
from app.models.attachment import Attachment
from app.models.enums import ProcedureType
from app.models.mobile import Message
from app.models.notification import Notification
from app.models.patient import Patient
from app.seed import hirt
from app.storage import blobs
from tests.test_attachments import _upload
from tests.test_mobile import _forget_patient

# Real ISO-BMFF headers: the server checks the brand against the declared type.
MP4 = b"\x00\x00\x00\x20ftypisom\x00\x00\x02\x00isomiso2avc1mp41" + b"\x00" * 64
MOV = b"\x00\x00\x00\x14ftypqt  \x00\x00\x00\x00qt  " + b"\x00" * 64
TODAY = date.today()
TOMORROW = TODAY + timedelta(days=1)

ASSIGNMENT_KEYS = {
    "id", "clinic_id", "patient_id", "exercise_id", "exercise_key", "title", "body_region",
    "body_region_label", "category", "category_label", "steps", "equipment", "precautions",
    "scheduled_for", "sort_order", "sets", "reps", "hold_seconds", "side", "side_label", "dose",
    "clinician_instructions", "assigned_by", "assigned_by_name", "status", "video", "completion",
    "skip_reason", "created_at", "updated_at",
}

_LEDGER = (ExerciseAssignment, ExerciseMedia, AuditEvent, Attachment, Message, Notification)


@pytest.fixture(scope="module")
def tokens(seeded_db):
    """A HIRT console and another hospital's, both narrowing the open console."""
    minted = {
        "hirt": mint(seeded_db, "hospital", "hirt", "HIRT console"),
        "demo": mint(seeded_db, "hospital", "hosp_demo", "Demo hospital console"),
    }
    yield {name: {"Authorization": f"Bearer {token}"} for name, (_row, token) in minted.items()}
    for row, _token in minted.values():
        seeded_db.delete(row)
    seeded_db.commit()


@pytest.fixture()
def ledger(db):
    """Rows a test writes are gone afterwards, their bytes with them; the
    seeded calendar (ids below the marks) is left alone."""
    marks = {model: (db.scalar(select(func.max(model.id))) or 0) for model in _LEDGER}
    yield
    db.expire_all()
    for model in (ExerciseMedia, Attachment):
        for key in db.scalars(select(model.storage_key).where(model.id > marks[model])).all():
            blobs.delete(key)
    for model, mark in marks.items():
        db.execute(delete(model).where(model.id > mark))
    db.commit()


@pytest.fixture()
def lifter(db, ledger):
    """A throwaway chart on the HIRT roster, forgotten afterwards."""
    pid = "hirt-schedule-test"
    patient = Patient(
        id=pid, name="Theo Lindqvist", initials="TL", age=33, sex="M",
        procedure_type=ProcedureType.NONE, procedure_display=hirt.PATHWAYS["hirt-cole"],
        surgery_date=TODAY - timedelta(days=14), discharge_date=TODAY - timedelta(days=14),
        surgeon_id="ct_harris", assigned_provider_id="ct_gregg", hospital_id="hirt",
        care_pathway=hirt.PATHWAYS["hirt-cole"],
    )
    db.add(patient)
    db.commit()
    yield patient
    db.execute(delete(ExerciseAssignment).where(ExerciseAssignment.patient_id == pid))
    db.commit()
    _forget_patient(db, pid)


def _exercise(client, headers, q: str) -> dict:
    rows = client.get(f"/api/hep/exercises?q={q}", headers=headers).json()["exercises"]
    assert rows, q
    return rows[0]


def _assign(client, headers, patient_id: str, exercise_id: int, dates: list[date], **dose) -> list:
    body = {"patient_id": patient_id, "exercise_id": exercise_id,
            "dates": [d.isoformat() for d in dates], **dose}
    resp = client.post("/api/hep/schedule", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["assignments"]


def _patient_session(client, monkeypatch, headers, patient_id: str) -> dict:
    """The demo screen's way in: a patient session minted by the console."""
    monkeypatch.setattr(settings, "demo_mode", True)
    resp = client.post("/api/demo/patient-session", json={"patient_id": patient_id},
                       headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["patient"]["id"] == patient_id
    return {"Authorization": f"Bearer {resp.json()['token']}"}


# --- the grid ------------------------------------------------------------------------------


def test_the_grid_is_the_clinics_own_week(client, tokens):
    grid = client.get("/api/hep/schedule", params={"today": TODAY.isoformat()},
                      headers=tokens["hirt"])
    assert grid.status_code == 200, grid.text
    body = grid.json()
    monday = TODAY - timedelta(days=TODAY.weekday())
    assert body["start"] == monday.isoformat() and body["today"] == TODAY.isoformat()
    assert body["days"] == [(monday + timedelta(days=i)).isoformat() for i in range(7)]
    assert [p["id"] for p in body["patients"]] == [
        "hirt-cole", "hirt-devon", "hirt-june", "hirt-rafael", "hirt-tessa"]  # by name
    for card in body["patients"]:
        assert card["pathway"] == hirt.PATHWAYS[card["id"]]
        assert card["risk_tier"] == hirt.EXPECTED_TIERS[card["id"]]
        assert card["initials"] and card["assigned_provider_name"].startswith("Dr. ")
        for row in card["assignments"]:
            assert ASSIGNMENT_KEYS <= set(row)
            assert row["clinic_id"] == "hirt" and row["patient_id"] == card["id"]
            assert row["scheduled_for"] in body["days"]
            assert row["video"] is None  # the suite has no object store and no clips
    assert {m["id"] for m in body["care_team"]} == {"ct_gregg", "ct_harris"}

    cole = next(p for p in body["patients"] if p["id"] == "hirt-cole")
    slides = [a for a in cole["assignments"] if a["exercise_key"] == "knee_heel_slides"]
    assert len(slides) == 7 and slides[0]["dose"] == "2 sets × 10 reps · Left"
    assert slides[0]["side_label"] == "Left" and slides[0]["assigned_by"] == "ct_gregg"
    assert slides[0]["assigned_by_name"] == "Dr. Ashley Gregg"
    assert slides[0]["clinician_instructions"] == "Every day, after your warm-up."
    today_rows = [a for a in cole["assignments"] if a["scheduled_for"] == TODAY.isoformat()]
    assert today_rows and all(a["status"] == "assigned" and a["completion"] is None
                              for a in today_rows)

    # a wider window, from a chosen Monday: last week and this one, so there
    # are done days whatever today's weekday is
    start = monday - timedelta(days=7)
    two = client.get("/api/hep/schedule", params={"start": start.isoformat(), "days": 14,
                                                  "today": TODAY.isoformat()},
                     headers=tokens["hirt"]).json()
    assert two["days"][0] == start.isoformat() and len(two["days"]) == 14
    cole_two = next(p for p in two["patients"] if p["id"] == "hirt-cole")
    done = [a for a in cole_two["assignments"] if a["status"] == "done"]
    assert done and all(a["completion"]["source"] == "app" for a in done)
    assert all(a["completion"]["pain_after"] is not None and a["completion"]["video"] is None
               for a in done)
    assert all(a["scheduled_for"] < TODAY.isoformat() for a in done)
    assert client.get("/api/hep/schedule?days=0", headers=tokens["hirt"]).status_code == 422
    assert client.get("/api/hep/schedule?days=29", headers=tokens["hirt"]).status_code == 422

    # one patient's strip, for the patient page
    strip = client.get("/api/hep/patients/hirt-cole/schedule",
                       params={"today": TODAY.isoformat()}, headers=tokens["hirt"]).json()
    assert strip["patient"]["id"] == "hirt-cole" and strip["patient"]["risk_tier"] == "high"
    assert strip["days"] == body["days"]
    assert [a["id"] for a in strip["assignments"]] == [a["id"] for a in cole["assignments"]]

    # another hospital's console sees its own charts and none of HIRT's
    other = client.get("/api/hep/schedule", headers=tokens["demo"]).json()
    assert other["patients"] and not {p["id"] for p in other["patients"]} & hirt.HIRT_IDS
    assert client.get("/api/hep/schedule?patient_id=hirt-cole",
                      headers=tokens["demo"]).status_code == 404
    assert client.get("/api/hep/patients/hirt-cole/schedule",
                      headers=tokens["demo"]).status_code == 404
    # the open console acts for the clinic with the most charts (hosp_demo), as the library does
    open_console = client.get("/api/hep/schedule").json()
    assert not {p["id"] for p in open_console["patients"]} & hirt.HIRT_IDS


def test_assign_patch_move_and_remove_scoped_by_clinic(client, db, tokens, lifter):
    hirt_console, other = tokens["hirt"], tokens["demo"]
    clams = _exercise(client, hirt_console, "clamshell")
    later = TODAY + timedelta(days=2)
    made = _assign(client, hirt_console, lifter.id, clams["id"], [later, TODAY],
                   sets=2, reps=12, side="left", clinician_instructions="Slow.")
    assert [a["scheduled_for"] for a in made] == [TODAY.isoformat(), later.isoformat()]
    first = made[0]
    assert first["title"] == "Clamshells" and first["exercise_key"] == "hip_clamshells"
    assert first["dose"] == "2 sets × 12 reps · Left" and first["status"] == "assigned"
    assert first["assigned_by"] == "ct_gregg"  # the patient's provider, by default
    assert first["assigned_by_name"] == "Dr. Ashley Gregg" and first["sort_order"] == 0
    assert first["steps"] and first["video"] is None and first["completion"] is None

    # the same exercise on a day that already has it: the whole request is refused, naming the day
    dup = client.post("/api/hep/schedule", headers=hirt_console, json={
        "patient_id": lifter.id, "exercise_id": clams["id"],
        "dates": [TOMORROW.isoformat(), TODAY.isoformat()]})
    assert dup.status_code == 409 and TODAY.isoformat() in dup.json()["detail"]
    db.expire_all()
    assert db.scalar(select(func.count(ExerciseAssignment.id)).where(
        ExerciseAssignment.patient_id == lifter.id)) == 2
    # a second exercise on the same day lands after the first
    bridges = _exercise(client, hirt_console, "bridge")
    second = _assign(client, hirt_console, lifter.id, bridges["id"], [TODAY], sets=3, reps=10,
                     assigned_by="ct_harris")
    assert second[0]["sort_order"] == 1 and second[0]["assigned_by_name"] == "Dr. Sean Harris"

    def refused(status, **body):
        resp = client.post("/api/hep/schedule", headers=hirt_console, json={
            "patient_id": lifter.id, "exercise_id": clams["id"],
            "dates": [TOMORROW.isoformat()], **body})
        assert resp.status_code == status, resp.text

    refused(422, dates=[(TODAY + timedelta(days=91)).isoformat()])
    refused(422, dates=[(TODAY - timedelta(days=61)).isoformat()])
    refused(422, side="upside")
    refused(422, assigned_by="ct_nobody")
    refused(422, clinician_instructions="This will detect a tear")
    refused(404, patient_id="reyes")  # another hospital's chart
    refused(404, exercise_id=999999)

    # another hospital's console cannot see the rows at all
    assert client.patch(f"/api/hep/schedule/{first['id']}", json={"sets": 4},
                        headers=other).status_code == 404
    assert client.delete(f"/api/hep/schedule/{first['id']}", headers=other).status_code == 404
    assert client.post(f"/api/hep/schedule/{first['id']}/complete", json={},
                       headers=other).status_code == 404

    # re-dose, clear a count, move the day
    patched = client.patch(f"/api/hep/schedule/{first['id']}", headers=hirt_console, json={
        "sets": None, "reps": 15, "scheduled_for": TOMORROW.isoformat(),
        "clinician_instructions": "Slow, and stop at the pinch."})
    assert patched.status_code == 200, patched.text
    assert patched.json()["dose"] == "15 reps · Left"
    assert patched.json()["scheduled_for"] == TOMORROW.isoformat()
    assert patched.json()["clinician_instructions"] == "Slow, and stop at the pinch."
    # moving onto a day that already has the exercise is refused
    assert client.patch(f"/api/hep/schedule/{first['id']}", headers=hirt_console,
                        json={"scheduled_for": later.isoformat()}).status_code == 409
    assert client.patch(f"/api/hep/schedule/{first['id']}", headers=hirt_console,
                        json={}).status_code == 422

    events = db.scalars(select(AuditEvent).where(
        AuditEvent.subject_type == "assignment", AuditEvent.subject_id == str(first["id"]))).all()
    assert [e.action for e in events] == ["assignment.create", "assignment.update"]
    assert all(e.hospital_id == "hirt" for e in events)

    gone = client.delete(f"/api/hep/schedule/{first['id']}", headers=hirt_console)
    assert gone.status_code == 200 and gone.json() == {"ok": True}
    assert client.delete(f"/api/hep/schedule/{first['id']}", headers=hirt_console).status_code == 404
    strip = client.get(f"/api/hep/patients/{lifter.id}/schedule",
                       params={"start": TODAY.isoformat(), "today": TODAY.isoformat()},
                       headers=hirt_console).json()
    assert {a["id"] for a in strip["assignments"]} == {made[1]["id"], second[0]["id"]}
    assert strip["patient"]["pathway"] == hirt.PATHWAYS["hirt-cole"]


def test_the_therapist_logs_a_day_done_from_the_room(client, db, tokens, lifter):
    hirt_console = tokens["hirt"]
    squats = _exercise(client, hirt_console, "mini squat")
    row = _assign(client, hirt_console, lifter.id, squats["id"], [TODAY], sets=3, reps=12)[0]
    done = client.post(f"/api/hep/schedule/{row['id']}/complete", headers=hirt_console,
                       json={"pain_after": 3, "note": "Said it was fine", "actor": "ct_gregg"})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "done" and body["completion"]["source"] == "console"
    assert body["completion"]["pain_after"] == 3 and body["completion"]["note"] == "Said it was fine"
    assert body["completion"]["video"] is None and body["completion"]["completed_at"]
    # once: the second log, a re-dose, a move and a removal are all refused; the record stays
    assert client.post(f"/api/hep/schedule/{row['id']}/complete", headers=hirt_console,
                       json={}).status_code == 409
    assert client.patch(f"/api/hep/schedule/{row['id']}", headers=hirt_console,
                        json={"reps": 8}).status_code == 409
    assert client.patch(f"/api/hep/schedule/{row['id']}", headers=hirt_console,
                        json={"scheduled_for": TOMORROW.isoformat()}).status_code == 409
    assert client.delete(f"/api/hep/schedule/{row['id']}", headers=hirt_console).status_code == 409
    # but its note may still be tidied
    tidy = client.patch(f"/api/hep/schedule/{row['id']}", headers=hirt_console,
                        json={"clinician_instructions": "Heels down."})
    assert tidy.status_code == 200 and tidy.json()["status"] == "done"
    assert client.post(f"/api/hep/schedule/{row['id']}/complete", headers=hirt_console,
                       json={"pain_after": 11}).status_code == 422
    audit = db.scalars(select(AuditEvent).where(
        AuditEvent.action == "assignment.complete", AuditEvent.subject_id == str(row["id"]))).all()
    assert len(audit) == 1 and audit[0].actor == "ct_gregg"


# --- the therapist's clip ----------------------------------------------------------------------


def test_the_therapists_clip_plays_for_her_clinic_only(client, db, tokens, lifter, monkeypatch):
    hirt_console, other = tokens["hirt"], tokens["demo"]
    step_ups = _exercise(client, hirt_console, "step-up")
    base = f"/api/hep/exercises/{step_ups['id']}/media"

    # with no object store the ticket says so, for a clinic key
    ticket = client.get(f"{base}/upload-ticket",
                        params={"content_type": "video/mp4", "byte_size": len(MP4)},
                        headers=hirt_console).json()
    assert ticket["direct"] is True and ticket["upload"] is None
    assert ticket["storage_key"].startswith("attachments/clinic/hirt/")
    assert ticket["max_bytes"] == blobs.MAX_MEDIA_BYTES
    assert client.get(f"{base}/upload-ticket",
                      params={"content_type": "application/pdf", "byte_size": 10},
                      headers=hirt_console).status_code == 422  # a clip, not a document
    assert client.get("/api/hep/exercises/999999/media/upload-ticket",
                      params={"content_type": "video/mp4", "byte_size": 10},
                      headers=hirt_console).status_code == 404

    # the direct path: the bytes as the body, confirmed in one step
    bad = client.post(f"{base}/direct?filename=demo.mp4", headers={**hirt_console,
                      "Content-Type": "video/mp4"}, content=b"<html>not a clip</html>")
    assert bad.status_code == 422 and "does not look like" in bad.json()["detail"]
    up = client.post(f"{base}/direct?filename=demo.mp4&actor=ct_gregg",
                     headers={**hirt_console, "Content-Type": "video/mp4"}, content=MP4)
    assert up.status_code == 201, up.text
    exercise = up.json()["exercise"]
    assert exercise["media"] is None  # the library clip is untouched
    clip = exercise["clinic_media"]
    assert clip["source"] == "clinic" and clip["kind"] == "video" and clip["playable"] is True
    assert clip["uploaded_by"] == "ct_gregg" and clip["approval_status"] == "approved"
    assert clip["url"] == f"/api/hep/media/{clip['id']}/raw"
    media = db.get(ExerciseMedia, clip["id"])
    assert media.hospital_id == "hirt" and media.exercise_id == step_ups["id"]
    assert media.reviewed_by == "ct_gregg" and blobs.owned_by_clinic(media.storage_key, "hirt")

    # it is the exercise's demonstration on every day this clinic assigns it...
    row = _assign(client, hirt_console, lifter.id, step_ups["id"], [TODAY], sets=3, reps=10)[0]
    assert row["video"]["id"] == clip["id"] and row["video"]["source"] == "clinic"
    assert row["video"]["uploaded_by_name"] == "Dr. Ashley Gregg"
    raw = client.get(row["video"]["url"], headers=hirt_console)
    assert raw.status_code == 200 and raw.content == MP4
    assert raw.headers["content-type"].startswith("video/mp4")
    assert raw.headers["x-content-type-options"] == "nosniff"
    listed = client.get("/api/hep/exercises?q=step-up", headers=hirt_console).json()["exercises"]
    assert listed[0]["clinic_media"]["id"] == clip["id"]
    # ...and to its patients, under their session
    session = _patient_session(client, monkeypatch, hirt_console, lifter.id)
    mine = client.get("/api/mobile/exercises", headers=session).json()["items"]
    assert mine[0]["video"]["url"] == f"/api/mobile/exercises/media/{clip['id']}/raw"
    assert client.get(mine[0]["video"]["url"], headers=session).content == MP4
    # ...while another clinic, and another clinic's patient, still see no clip
    theirs = client.get(f"/api/hep/exercises/{step_ups['id']}", headers=other).json()
    assert theirs["clinic_media"] is None and theirs["media"] is None
    assert client.get(row["video"]["url"], headers=other).status_code == 404
    medha = _patient_session(client, monkeypatch, other, "medha")
    assert client.get(mine[0]["video"]["url"], headers=medha).status_code == 404

    # the two-step path: a key from the ticket, the bytes put there, then the confirm
    key = ticket["storage_key"]
    blobs.put(key, MOV, "video/quicktime")
    confirmed = client.post(base, headers=hirt_console, json={
        "storage_key": key, "content_type": "video/quicktime", "byte_size": len(MOV),
        "filename": "IMG_0412.mov", "actor": "ct_gregg"})
    assert confirmed.status_code == 201, confirmed.text
    newest = confirmed.json()["exercise"]["clinic_media"]
    assert newest["id"] != clip["id"] and newest["content_type"] == "video/quicktime"
    # the newest clip is the one that plays
    assert client.get(f"/api/hep/patients/{lifter.id}/schedule", headers=hirt_console).json()[
        "assignments"][0]["video"]["id"] == newest["id"]
    assert client.post(base, headers=hirt_console, json={
        "storage_key": key, "content_type": "video/quicktime", "byte_size": len(MOV)},
    ).status_code == 409  # already confirmed
    foreign = blobs.new_clinic_key("hosp_demo", "video/mp4")
    assert client.post(base, headers=hirt_console, json={
        "storage_key": foreign, "content_type": "video/mp4"}).status_code == 403
    wrong = blobs.new_clinic_key("hirt", "video/mp4")
    blobs.put(wrong, b"%PDF-1.7 not a clip" + b"\x00" * 64, "video/mp4")
    assert client.post(base, headers=hirt_console, json={
        "storage_key": wrong, "content_type": "video/mp4"}).status_code == 422
    assert blobs.stat(wrong) is None  # refused and removed

    # taking a clip back: another clinic cannot, this one can, and the day falls back to no clip
    assert client.delete(f"{base}/{newest['id']}", headers=other).status_code == 404
    assert client.delete(f"{base}/{newest['id']}", headers=hirt_console).json() == {"ok": True}
    assert client.delete(f"{base}/{clip['id']}", headers=hirt_console).json() == {"ok": True}
    storage_key = media.storage_key
    db.expire_all()
    assert db.get(ExerciseMedia, clip["id"]) is None and blobs.stat(storage_key) is None
    assert client.get(row["video"]["url"], headers=hirt_console).status_code == 404
    after = client.get(f"/api/hep/patients/{lifter.id}/schedule", headers=hirt_console).json()
    assert after["assignments"][0]["video"] is None
    actions = db.scalars(select(AuditEvent.action).where(
        AuditEvent.subject_type == "media", AuditEvent.hospital_id == "hirt")).all()
    assert actions.count("media.create") == 2 and actions.count("media.delete") == 2


# --- the patient's day -------------------------------------------------------------------------


def test_the_patient_marks_a_day_done_with_pain_and_a_clip(client, db, tokens, lifter, monkeypatch):
    hirt_console = tokens["hirt"]
    slides = _exercise(client, hirt_console, "heel slide")
    sits = _exercise(client, hirt_console, "wall sit")
    today_rows = _assign(client, hirt_console, lifter.id, slides["id"], [TODAY, TOMORROW],
                         sets=2, reps=10, side="left", clinician_instructions="After your warm-up.")
    sit = _assign(client, hirt_console, lifter.id, sits["id"], [TODAY], sets=3, hold_seconds=30)[0]

    # the demo session route exists on the demo stack only, and inside the console's scope
    assert client.post("/api/demo/patient-session", json={"patient_id": lifter.id},
                       headers=hirt_console).status_code == 404
    monkeypatch.setattr(settings, "demo_mode", True)
    assert client.post("/api/demo/patient-session", json={"patient_id": lifter.id},
                       headers=tokens["demo"]).status_code == 404
    session = _patient_session(client, monkeypatch, hirt_console, lifter.id)
    assert client.get("/api/mobile/me", headers=session).json()["patient"]["id"] == lifter.id

    day = client.get("/api/mobile/exercises", headers=session).json()
    assert day["date"] == TODAY.isoformat()
    assert day["clinic"] == {"id": "hirt", "name": "H.I.R.T. Physical Therapy"}
    assert [i["title"] for i in day["items"]] == ["Heel Slides", "Wall Sits"]
    assert all("clinic_id" not in i and i["patient_id"] == lifter.id for i in day["items"])
    assert day["items"][0]["dose"] == "2 sets × 10 reps · Left"
    assert day["items"][0]["clinician_instructions"] == "After your warm-up."
    assert day["items"][1]["dose"] == "3 sets · hold 30 s"
    assert [w["date"] for w in day["week"]] == [
        (TODAY + timedelta(days=i)).isoformat() for i in range(-3, 4)]
    assert day["week"][3] == {"date": TODAY.isoformat(), "assigned": 2, "done": 0, "skipped": 0}
    assert day["week"][4]["assigned"] == 1
    assert client.get("/api/mobile/exercises", params={"date": TOMORROW.isoformat()},
                      headers=session).json()["items"][0]["id"] == today_rows[1]["id"]

    # the presigned path: a key from the ticket, the bytes there, the confirm inside the completion
    ticket = client.get("/api/mobile/attachments/upload-ticket",
                        params={"content_type": "video/quicktime", "byte_size": len(MOV)},
                        headers=session).json()
    blobs.put(ticket["storage_key"], MOV, "video/quicktime")
    done = client.post(f"/api/mobile/exercises/{today_rows[0]['id']}/complete", headers=session,
                       json={"pain_after": 4, "note": "Left knee ached on the last set",
                             "video": {"storage_key": ticket["storage_key"],
                                       "content_type": "video/quicktime",
                                       "byte_size": len(MOV), "filename": "step-ups.mov"}})
    assert done.status_code == 200, done.text
    row = done.json()["assignment"]
    assert row["status"] == "done" and row["completion"]["source"] == "app"
    assert row["completion"]["pain_after"] == 4
    assert row["completion"]["note"] == "Left knee ached on the last set"
    video = row["completion"]["video"]
    assert video["kind"] == "video" and video["filename"] == "step-ups.mov"
    assert video["content_type"] == "video/quicktime" and video["byte_size"] == len(MOV)
    assert video["uploaded_by"] == "patient" and video["source"] == "app"
    attachment = db.get(Attachment, video["id"])
    assert attachment.patient_id == lifter.id and attachment.confirmed_at is not None
    # one line on the thread, with the clip on it, and the bell for the care team
    thread = client.get("/api/mobile/messages", headers=session).json()["messages"]
    line = [m for m in thread if m["sender"] == "patient"][-1]
    assert line["text"] == "Did Heel Slides · pain 4/10 after\nLeft knee ached on the last set"
    assert [a["id"] for a in line["attachments"]] == [video["id"]]
    assert attachment.message_id == line["id"]
    db.expire_all()
    notes = db.scalars(select(Notification).where(Notification.patient_id == lifter.id)).all()
    assert any(n.recipient_id == "ct_gregg" and "pain 4/10" in n.body for n in notes)
    # the bytes come back under the session
    raw = client.get(f"/api/mobile/attachments/{video['id']}/raw", headers=session)
    assert raw.status_code == 200 and raw.content == MOV
    # a second tap is refused before anything is stored
    again = client.post(f"/api/mobile/exercises/{today_rows[0]['id']}/complete", headers=session,
                        json={"pain_after": 2})
    assert again.status_code == 409

    # the direct path: the row the upload already confirmed, by id
    uploaded = _upload(client, session, data=MP4, content_type="video/mp4", name="wall-sits.mp4")
    assert uploaded.status_code == 200, uploaded.text
    attachment_id = uploaded.json()["attachment"]["id"]
    assert client.post(f"/api/mobile/exercises/{sit['id']}/complete", headers=session,
                       json={"video": {"attachment_id": 999999}}).status_code == 404
    assert client.post(f"/api/mobile/exercises/{sit['id']}/complete", headers=session,
                       json={"video": {"content_type": "video/mp4"}}).status_code == 422
    done2 = client.post(f"/api/mobile/exercises/{sit['id']}/complete", headers=session,
                        json={"pain_after": 1, "video": {"attachment_id": attachment_id,
                                                          "content_type": "video/mp4",
                                                          "byte_size": len(MP4),
                                                          "filename": "wall-sits.mp4"}})
    assert done2.status_code == 200, done2.text
    assert done2.json()["assignment"]["completion"]["video"]["id"] == attachment_id
    assert done2.json()["assignment"]["completion"]["note"] == ""
    db.expire_all()
    linked = db.get(Attachment, attachment_id)
    assert linked.message_id is not None
    assert db.get(Message, linked.message_id).text == "Did Wall Sits · pain 1/10 after"
    # a clip is one attempt at one exercise: the same row cannot go on another day
    assert client.post(f"/api/mobile/exercises/{today_rows[1]['id']}/complete", headers=session,
                       json={"video": {"attachment_id": attachment_id}}).status_code == 409

    # skipping, with a reason
    skipped = client.post(f"/api/mobile/exercises/{today_rows[1]['id']}/skip", headers=session,
                          json={"reason": "Long shift"})
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["assignment"]["status"] == "skipped"
    assert skipped.json()["assignment"]["skip_reason"] == "Long shift"
    assert client.post(f"/api/mobile/exercises/{sit['id']}/skip", headers=session,
                       json={}).status_code == 409
    # a skipped day can still be done later
    later = client.post(f"/api/mobile/exercises/{today_rows[1]['id']}/complete", headers=session,
                        json={"pain_after": None})
    assert later.status_code == 200 and later.json()["assignment"]["skip_reason"] is None
    assert later.json()["assignment"]["completion"]["pain_after"] is None
    assert db.scalar(select(Message.text).where(Message.patient_id == lifter.id)
                     .order_by(Message.id.desc())) == "Did Heel Slides"

    week = client.get("/api/mobile/exercises", headers=session).json()["week"]
    assert week[3] == {"date": TODAY.isoformat(), "assigned": 2, "done": 2, "skipped": 0}

    # the console sees the score and the clip beside it
    strip = client.get(f"/api/hep/patients/{lifter.id}/schedule",
                       params={"today": TODAY.isoformat()}, headers=hirt_console).json()
    first = next(a for a in strip["assignments"] if a["id"] == today_rows[0]["id"])
    assert first["completion"]["pain_after"] == 4 and first["completion"]["video"]["id"] == video["id"]
    assert first["completion"]["source"] == "app"

    # another patient's session cannot reach these rows
    cole = _patient_session(client, monkeypatch, hirt_console, "hirt-cole")
    assert client.post(f"/api/mobile/exercises/{sit['id']}/skip", headers=cole,
                       json={}).status_code == 404
    assert client.post(f"/api/mobile/exercises/{sit['id']}/complete", headers=cole,
                       json={}).status_code == 404
    assert client.get("/api/mobile/exercises", headers={}).status_code == 401
    monkeypatch.setattr(settings, "hep_enabled", False)
    assert client.get("/api/mobile/exercises", headers=session).status_code == 404


# --- the seeded calendar -----------------------------------------------------------------------


def test_the_seed_lays_out_the_five_lifters_calendars(db):
    start = TODAY - timedelta(days=hirt.PROGRAM_DAYS)
    end = TODAY + timedelta(days=hirt.SCHEDULE_AHEAD)
    keys = {e.id: e.key for e in db.scalars(select(Exercise).where(Exercise.key.is_not(None)))}
    for spec in hirt.HIRT_PATIENTS:
        rows = db.scalars(select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == spec.id)).all()
        assert rows, spec.id
        assert min(r.scheduled_for for r in rows) == start
        assert max(r.scheduled_for for r in rows) == end
        assert all(r.hospital_id == "hirt" and r.assigned_by == spec.assigned_id for r in rows)
        assert all(r.video_attachment_id is None and r.plan_exercise_id is None for r in rows)
        past = [r for r in rows if r.scheduled_for < TODAY]
        assert {
            "done": sum(r.status == "done" for r in past),
            "skipped": sum(r.status == "skipped" for r in past),
            "missed": sum(r.status == "assigned" for r in past),
        } == hirt.EXPECTED_SCHEDULE[spec.id], spec.id
        assert all(r.status == "assigned" for r in rows if r.scheduled_for >= TODAY)
        for r in past:
            if r.status == "done":
                assert r.completed_at is not None and r.completion_source == "app"
                assert r.pain_after == hirt.PAIN_AFTER[spec.id][(r.scheduled_for - start).days]
            else:
                assert r.completed_at is None and r.pain_after is None
        # every exercise falls on the weekdays the therapist put it on, once per day
        for item in hirt.SCHEDULE[spec.id]:
            days = sorted(r.scheduled_for for r in rows if keys[r.exercise_id] == item.key)
            assert len(days) == len(set(days)), (spec.id, item.key)
            if item.weekdays is None:
                assert len(days) == hirt.PROGRAM_DAYS + hirt.SCHEDULE_AHEAD + 1
            else:
                assert days and all(d.weekday() in item.weekdays for d in days)
                assert all(d in days for d in (start + timedelta(days=i) for i in range(22))
                           if d.weekday() in item.weekdays)

    def done_pain(pid: str) -> list[int]:
        return [r.pain_after for r in db.scalars(
            select(ExerciseAssignment).where(ExerciseAssignment.patient_id == pid,
                                             ExerciseAssignment.status == "done")
            .order_by(ExerciseAssignment.scheduled_for, ExerciseAssignment.sort_order))]

    cole = done_pain("hirt-cole")
    assert max(cole[:20]) == 2 and cole[-1] == 6  # the climb lands on the last day

    # the lifters accepted the beta terms when they enrolled, so neither a
    # phone nor the demo screen's frame stops at the consent screen
    from app.models.patient import Patient
    from app.personal import auth

    for spec in hirt.HIRT_PATIENTS:
        consent = auth.current_consent(db, db.get(Patient, spec.id))
        assert consent is not None and consent.version == auth.CONSENT_VERSION, spec.id
    assert hirt.ensure_consent(db, "hirt-cole") == 0  # idempotent
    assert max(done_pain("hirt-tessa")) <= 2 and set(done_pain("hirt-june")) <= {1, 2}
    skips = db.scalars(select(ExerciseAssignment).where(
        ExerciseAssignment.patient_id == "hirt-devon", ExerciseAssignment.status == "skipped")).all()
    assert [s.skip_reason for s in skips] == ["Long shift", "Long shift"]
    last_done = db.scalar(select(func.max(ExerciseAssignment.scheduled_for)).where(
        ExerciseAssignment.patient_id == "hirt-rafael", ExerciseAssignment.status == "done"))
    assert last_done == TODAY - timedelta(days=3)  # and nothing since: the went-quiet story

    # a second write is a clean replacement, not a second calendar
    before = db.scalar(select(func.count(ExerciseAssignment.id)))
    counts = hirt.write_schedule(db, "hirt-june", TODAY)
    assert {k: counts[k] for k in ("assignments", "done", "skipped")} == {
        "assignments": 88, "done": 56, "skipped": 0}
    assert counts["consents"] == 0  # the first write already gave her the beta consent
    assert db.scalar(select(func.count(ExerciseAssignment.id))) == before
