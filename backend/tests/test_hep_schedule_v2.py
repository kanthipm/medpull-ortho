"""The exercise schedule's second pass (docs/dev/hep-schedule.md): the
lifter's dose and the therapist's requirements, the patient's session with
its heart rate, the review and its queue, copying a week, programs, the
patient's calendar, the worklist's line, and what the seed now carries.

The fixtures are the first pass's: a HIRT console and another hospital's, a
throwaway chart on the HIRT roster, and a ledger that removes what a test
wrote. The seeded five are only read, except the one refill at the end.
"""

from __future__ import annotations

import time as clock
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from app.hep.models import AuditEvent, Exercise, ExerciseAssignment, ExerciseTemplate
from app.models.enums import Granularity, MetricType, SourceProvider
from app.models.mobile import Message
from app.models.observation import Observation
from app.seed import hirt
from tests import test_hep_schedule as first_pass
from tests.test_attachments import _upload
from tests.test_hep_schedule import MP4, TODAY, TOMORROW, _assign, _exercise, _patient_session

# The first pass's fixtures, registered here under the same names.
tokens = first_pass.tokens
ledger = first_pass.ledger
lifter = first_pass.lifter

MONDAY = TODAY - timedelta(days=TODAY.weekday())
SESSION_KEYS = {"started_at", "ended_at", "duration_s", "pain_before", "wearable_worn", "hr_avg",
                "hr_max"}
COMPLETION_KEYS = {"completed_at", "pain_after", "note", "source", "video", "effort", "sets_done",
                   "reps_done", "load_done_kg", "review", "awaiting_review"}
TEMPLATE_ITEM_KEYS = {"exercise_id", "exercise_key", "title", "weekdays", "sets", "reps",
                      "hold_seconds", "side", "load_kg", "rpe_target", "clinician_instructions",
                      "video_requirement", "wearable_requirement"}


def _hr(db, patient_id: str, at: datetime, bpm: float) -> None:
    """One heart-rate sample from a wearable, the way ingest leaves it."""
    db.add(Observation(
        patient_id=patient_id, source_provider=SourceProvider.MOCK,
        metric_type=MetricType.HR_SAMPLE, unit="bpm", value_num=bpm, start_time=at, end_time=at,
        timezone=hirt.TZ, local_date=at.date(), granularity=Granularity.INSTANT,
        dedupe_key=f"test:{patient_id}:hr:{at.isoformat()}",
    ))
    db.commit()


def _log_done(client, headers, assignment_id: int, **body) -> dict:
    done = client.post(f"/api/hep/schedule/{assignment_id}/complete", headers=headers,
                       json={"actor": "ct_gregg", **body})
    assert done.status_code == 200, done.text
    return done.json()


# --- the dose and the requirements ---------------------------------------------------------------


def test_load_effort_and_requirements_ride_on_the_day(client, db, tokens, lifter):
    hirt_console = tokens["hirt"]
    step_ups = _exercise(client, hirt_console, "functional_step_ups")
    row = _assign(client, hirt_console, lifter.id, step_ups["id"], [TODAY], sets=3, reps=10,
                  side="left", load_kg=12, rpe_target=7, video_requirement="required",
                  wearable_requirement="off")[0]
    assert row["load_kg"] == 12 and row["rpe_target"] == 7
    assert row["video_requirement"] == "required" and row["wearable_requirement"] == "off"
    assert row["dose"] == "3 sets × 10 reps · 12 kg · Left"
    assert row["session"] is None and row["completion"] is None
    # the defaults: optional both ways, no load, and the dose reads as before
    plain = _assign(client, hirt_console, lifter.id, step_ups["id"], [TOMORROW], sets=3, reps=10)[0]
    assert plain["video_requirement"] == plain["wearable_requirement"] == "optional"
    assert plain["load_kg"] is None and plain["rpe_target"] is None
    assert plain["dose"] == "3 sets × 10 reps"

    def refused(status, **body):
        resp = client.post("/api/hep/schedule", headers=hirt_console, json={
            "patient_id": lifter.id, "exercise_id": step_ups["id"],
            "dates": [(TODAY + timedelta(days=3)).isoformat()], **body})
        assert resp.status_code == status, resp.text

    refused(422, video_requirement="always")
    refused(422, wearable_requirement="sometimes")
    refused(422, load_kg=501)
    refused(422, load_kg=-1)
    refused(422, rpe_target=11)

    # re-dosing the load and the requirements on an open day
    patched = client.patch(f"/api/hep/schedule/{row['id']}", headers=hirt_console,
                           json={"load_kg": 12.5, "wearable_requirement": "required"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["load_kg"] == 12.5 and patched.json()["dose"].endswith("12.5 kg · Left")
    assert patched.json()["wearable_requirement"] == "required"
    assert client.patch(f"/api/hep/schedule/{row['id']}", headers=hirt_console,
                        json={"video_requirement": "maybe"}).status_code == 422
    cleared = client.patch(f"/api/hep/schedule/{row['id']}", headers=hirt_console,
                           json={"load_kg": None, "rpe_target": None})
    assert cleared.json()["load_kg"] is None and cleared.json()["dose"] == "3 sets × 10 reps · Left"

    # the therapist logs the day done with what the lifter told her
    done = _log_done(client, hirt_console, plain["id"], pain_after=3, effort=6, sets_done=3,
                     reps_done=8, load_done_kg=10)
    completion = done["completion"]
    assert COMPLETION_KEYS <= set(completion)
    assert completion["effort"] == 6 and completion["sets_done"] == 3
    assert completion["reps_done"] == 8 and completion["load_done_kg"] == 10
    assert completion["review"] is None and completion["awaiting_review"] is False
    assert done["session"] is None  # nobody started it from a phone
    # a done day keeps its load and target like the rest of its dose; its requirements may change
    assert client.patch(f"/api/hep/schedule/{plain['id']}", headers=hirt_console,
                        json={"load_kg": 20}).status_code == 409
    assert client.patch(f"/api/hep/schedule/{plain['id']}", headers=hirt_console,
                        json={"rpe_target": 8}).status_code == 409
    assert client.patch(f"/api/hep/schedule/{plain['id']}", headers=hirt_console,
                        json={"video_requirement": "off"}).status_code == 200


# --- the patient's session --------------------------------------------------------------------


def test_the_patient_starts_a_session_and_the_requirements_hold(client, db, tokens, lifter,
                                                                 monkeypatch):
    hirt_console = tokens["hirt"]
    step_ups = _exercise(client, hirt_console, "functional_step_ups")
    slides = _exercise(client, hirt_console, "heel slide")
    strict = _assign(client, hirt_console, lifter.id, step_ups["id"], [TODAY], sets=3, reps=10,
                     load_kg=10, video_requirement="required", wearable_requirement="required")[0]
    easy = _assign(client, hirt_console, lifter.id, slides["id"], [TODAY], sets=2, reps=10)[0]
    session = _patient_session(client, monkeypatch, hirt_console, lifter.id)
    base = f"/api/mobile/exercises/{strict['id']}"

    # the start opens the session with the pain they are in and the wearable's state
    started = client.post(f"{base}/start", headers=session,
                          json={"pain_before": 3, "wearable_worn": False})
    assert started.status_code == 200, started.text
    opened = started.json()["assignment"]["session"]
    assert SESSION_KEYS <= set(opened)
    assert opened["started_at"] and opened["ended_at"] is None and opened["duration_s"] is None
    assert opened["pain_before"] == 3 and opened["wearable_worn"] is False
    assert started.json()["assignment"]["status"] == "assigned"
    # starting again moves the start
    clock.sleep(0.01)
    again = client.post(f"{base}/start", headers=session, json={"pain_before": 2}).json()
    assert again["assignment"]["session"]["started_at"] > opened["started_at"]
    assert again["assignment"]["session"]["pain_before"] == 2
    assert client.post(f"{base}/start", headers=session, json={"pain_before": 11}).status_code == 422
    cole = _patient_session(client, monkeypatch, hirt_console, "hirt-cole")
    assert client.post(f"{base}/start", headers=cole, json={}).status_code == 404

    # what she asked for has to be there, in the words the sheet shows
    no_clip = client.post(f"{base}/complete", headers=session,
                          json={"pain_after": 4, "wearable_worn": True})
    assert no_clip.status_code == 422 and no_clip.json()["detail"] == (
        "This exercise needs a clip of your attempt")
    uploaded = _upload(client, session, data=MP4, content_type="video/mp4", name="step-ups.mp4")
    attachment_id = uploaded.json()["attachment"]["id"]
    clip = {"attachment_id": attachment_id, "content_type": "video/mp4", "byte_size": len(MP4)}
    no_watch = client.post(f"{base}/complete", headers=session,
                           json={"pain_after": 4, "video": clip})  # the start said: not worn
    assert no_watch.status_code == 422 and no_watch.json()["detail"] == (
        "This exercise is done with your wearable on")
    assert client.post(f"{base}/complete", headers=session, json={
        "pain_after": 4, "video": clip, "wearable_worn": False}).status_code == 422
    # the clip the refused completion named is still free for the one that goes through
    db.expire_all()
    assert db.get(ExerciseAssignment, strict["id"]).status == "assigned"

    # the wearable's samples inside the session, and one outside it
    now = datetime.now()
    for minutes_ago, bpm in ((8, 120), (5, 140), (2, 160), (20, 200)):
        _hr(db, lifter.id, now - timedelta(minutes=minutes_ago), bpm)
    started_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    ended_at = datetime.now(timezone.utc).isoformat()
    done = client.post(f"{base}/complete", headers=session, json={
        "pain_after": 4, "note": "Heavier than it looked", "effort": 7, "sets_done": 3,
        "reps_done": 10, "load_done_kg": 12, "wearable_worn": True, "video": clip,
        "started_at": started_at, "ended_at": ended_at})
    assert done.status_code == 200, done.text
    row = done.json()["assignment"]
    assert row["status"] == "done" and "clinic_id" not in row
    finished = row["session"]
    assert finished["duration_s"] == 600 and finished["wearable_worn"] is True
    assert finished["pain_before"] == 2  # from the start
    assert finished["hr_avg"] == 140 and finished["hr_max"] == 160
    completion = row["completion"]
    assert completion["effort"] == 7 and completion["load_done_kg"] == 12
    assert completion["sets_done"] == 3 and completion["reps_done"] == 10
    assert completion["video"]["id"] == attachment_id and completion["awaiting_review"] is True
    assert completion["review"] is None and completion["source"] == "app"
    thread = client.get("/api/mobile/messages", headers=session).json()["messages"]
    line = [m for m in thread if m["sender"] == "patient"][-1]
    assert line["text"] == "Did Step-Ups · pain 4/10 after · effort 7/10\nHeavier than it looked"
    assert [a["id"] for a in line["attachments"]] == [attachment_id]
    # a done day cannot be started
    assert client.post(f"{base}/start", headers=session, json={}).status_code == 409

    # with no start of its own, the server keeps the one it recorded and closes the session now
    easy_base = f"/api/mobile/exercises/{easy['id']}"
    assert client.post(f"{easy_base}/start", headers=session, json={}).status_code == 200
    assert client.post(f"{easy_base}/complete", headers=session, json={
        "started_at": ended_at, "ended_at": started_at}).status_code == 422  # ends before it starts
    quick = client.post(f"{easy_base}/complete", headers=session, json={"pain_after": 1}).json()
    session_view = quick["assignment"]["session"]
    assert session_view["started_at"] and session_view["ended_at"]
    assert 0 <= session_view["duration_s"] <= 5 and session_view["hr_avg"] is None
    assert quick["assignment"]["completion"]["effort"] is None
    assert db.scalar(select(Message.text).where(Message.patient_id == lifter.id)
                     .order_by(Message.id.desc())) == "Did Heel Slides · pain 1/10 after"

    # the console sees the session beside the completion
    strip = client.get(f"/api/hep/patients/{lifter.id}/schedule",
                       params={"today": TODAY.isoformat()}, headers=hirt_console).json()
    seen = next(a for a in strip["assignments"] if a["id"] == strict["id"])
    assert seen["session"]["hr_max"] == 160 and seen["completion"]["effort"] == 7
    assert strip["patient"]["awaiting_review"] == 1


# --- the review and its queue ----------------------------------------------------------------------


def test_the_review_lands_on_the_thread_and_leaves_the_queue(client, db, tokens, lifter,
                                                              monkeypatch):
    hirt_console, other = tokens["hirt"], tokens["demo"]
    step_ups = _exercise(client, hirt_console, "functional_step_ups")
    squats = _exercise(client, hirt_console, "mini squat")
    yesterday = TODAY - timedelta(days=1)
    filmed = _assign(client, hirt_console, lifter.id, step_ups["id"], [yesterday], sets=3,
                     reps=10)[0]
    plain = _assign(client, hirt_console, lifter.id, squats["id"], [yesterday], sets=3, reps=12)[0]
    open_day = _assign(client, hirt_console, lifter.id, squats["id"], [TODAY], sets=3, reps=12)[0]
    session = _patient_session(client, monkeypatch, hirt_console, lifter.id)
    attachment_id = _upload(client, session, data=MP4, content_type="video/mp4",
                            name="step-ups.mp4").json()["attachment"]["id"]
    assert client.post(f"/api/mobile/exercises/{filmed['id']}/complete", headers=session, json={
        "pain_after": 5, "effort": 8, "video": {"attachment_id": attachment_id}}).status_code == 200
    _log_done(client, hirt_console, plain["id"], pain_after=2)

    # the queue: done days with a clip and no review, newest first, the clinic's own
    queue = client.get("/api/hep/review", headers=hirt_console)
    assert queue.status_code == 200, queue.text
    items = queue.json()["items"]
    assert [i["id"] for i in items][:1] == [filmed["id"]]
    assert items[0]["patient_name"] == lifter.name and items[0]["patient_id"] == lifter.id
    assert items[0]["completion"]["awaiting_review"] is True
    assert all(i["completion"]["video"] and i["completion"]["review"] is None for i in items)
    assert plain["id"] not in {i["id"] for i in items}  # no clip, nothing to look at
    assert client.get("/api/hep/review?days=0", headers=hirt_console).status_code == 422
    assert client.get("/api/hep/review?days=91", headers=hirt_console).status_code == 422
    theirs = client.get("/api/hep/review", headers=other).json()["items"]
    assert not {i["patient_id"] for i in theirs} & (hirt.HIRT_IDS | {lifter.id})
    grid = client.get("/api/hep/schedule", params={"today": TODAY.isoformat(), "patient_id": lifter.id},
                      headers=hirt_console).json()
    assert grid["patients"][0]["awaiting_review"] == 1

    # an open day has nothing to review; another clinic cannot see the row
    assert client.post(f"/api/hep/schedule/{open_day['id']}/review", headers=hirt_console,
                       json={"note": "Looks fine"}).status_code == 409
    assert client.post(f"/api/hep/schedule/{filmed['id']}/review", headers=other,
                       json={"note": "Looks fine"}).status_code == 404
    assert client.post(f"/api/hep/schedule/{filmed['id']}/review", headers=hirt_console,
                       json={"note": "I can detect a tear here"}).status_code == 422

    # the review with a note: on the row, and one line on the thread under her name
    before = db.scalar(select(func.count(Message.id)).where(Message.patient_id == lifter.id))
    reviewed = client.post(f"/api/hep/schedule/{filmed['id']}/review", headers=hirt_console, json={
        "note": "Depth looks good. Slow the lowering a touch more.", "actor": "ct_gregg"})
    assert reviewed.status_code == 200, reviewed.text
    review = reviewed.json()["completion"]["review"]
    assert review["by"] == "ct_gregg" and review["by_name"] == "Dr. Ashley Gregg" and review["at"]
    assert review["note"] == "Depth looks good. Slow the lowering a touch more."
    assert reviewed.json()["completion"]["awaiting_review"] is False
    db.expire_all()
    note = db.scalar(select(Message).where(Message.patient_id == lifter.id)
                     .order_by(Message.id.desc()))
    assert note.sender == "care_team" and note.sender_id == "ct_gregg" and note.channel == "app"
    assert note.text == "About your Step-Ups clip: Depth looks good. Slow the lowering a touch more."
    assert note.authored_by == "care_team"
    assert db.scalar(select(func.count(Message.id)).where(Message.patient_id == lifter.id)) == before + 1
    thread = client.get("/api/mobile/messages", headers=session).json()["messages"]
    assert thread[-1]["sender"] == "care_team" and thread[-1]["author_name"] == "Dr. Ashley Gregg"
    assert thread[-1]["text"].startswith("About your Step-Ups clip:")
    # the phone reads the review under the day
    mine = client.get("/api/mobile/exercises", params={"date": yesterday.isoformat()},
                      headers=session).json()["items"]
    assert next(i for i in mine if i["id"] == filmed["id"])["completion"]["review"]["by_name"] == (
        "Dr. Ashley Gregg")
    # and it has left the queue
    assert filmed["id"] not in {i["id"] for i in client.get("/api/hep/review", headers=hirt_console)
                                .json()["items"]}
    assert client.get("/api/hep/schedule", params={"today": TODAY.isoformat(), "patient_id": lifter.id},
                      headers=hirt_console).json()["patients"][0]["awaiting_review"] == 0

    # "Mark reviewed" alone: recorded, nothing said to the patient; the generic actor
    # signs as the patient's own therapist
    marked = client.post(f"/api/hep/schedule/{plain['id']}/review", headers=hirt_console, json={})
    assert marked.status_code == 200, marked.text
    assert marked.json()["completion"]["review"]["by"] == "ct_gregg"
    assert marked.json()["completion"]["review"]["note"] == ""
    assert db.scalar(select(func.count(Message.id)).where(Message.patient_id == lifter.id)) == before + 1
    actions = db.scalars(select(AuditEvent.action).where(
        AuditEvent.subject_type == "assignment", AuditEvent.action == "assignment.review",
        AuditEvent.subject_id.in_([str(filmed["id"]), str(plain["id"])]))).all()
    assert len(actions) == 2


# --- copying a week and programs ------------------------------------------------------------------


def test_copy_week_carries_dose_note_and_requirements_and_skips_duplicates(client, db, tokens,
                                                                            lifter):
    hirt_console = tokens["hirt"]
    step_ups = _exercise(client, hirt_console, "functional_step_ups")
    slides = _exercise(client, hirt_console, "heel slide")
    week = [MONDAY + timedelta(days=i) for i in range(7)]
    _assign(client, hirt_console, lifter.id, step_ups["id"], [week[0], week[2], week[4]], sets=3,
            reps=10, side="left", load_kg=10, rpe_target=7, video_requirement="required",
            clinician_instructions="Slow on the way down.")
    _assign(client, hirt_console, lifter.id, slides["id"], week, sets=2, reps=10,
            wearable_requirement="off", assigned_by="ct_harris")
    next_monday = MONDAY + timedelta(days=7)

    def copy(**body):
        return client.post("/api/hep/schedule/copy-week", headers=hirt_console, json={
            "patient_id": lifter.id, "from_start": MONDAY.isoformat(),
            "to_start": next_monday.isoformat(), **body})

    copied = copy()
    assert copied.status_code == 201, copied.text
    rows = copied.json()["assignments"]
    assert len(rows) == 10 and copied.json()["skipped"] == 0
    assert all(r["status"] == "assigned" and r["completion"] is None for r in rows)
    assert sorted(r["scheduled_for"] for r in rows) == sorted(
        [(next_monday + timedelta(days=i)).isoformat() for i in range(7)]
        + [(next_monday + timedelta(days=i)).isoformat() for i in (0, 2, 4)])
    step = next(r for r in rows if r["exercise_id"] == step_ups["id"])
    assert step["scheduled_for"] == next_monday.isoformat()  # the same weekday
    assert step["dose"] == "3 sets × 10 reps · 10 kg · Left" and step["rpe_target"] == 7
    assert step["video_requirement"] == "required" and step["wearable_requirement"] == "optional"
    assert step["clinician_instructions"] == "Slow on the way down."
    assert step["assigned_by"] == "ct_gregg"  # whoever assigned the day being copied
    slide = next(r for r in rows if r["exercise_id"] == slides["id"])
    assert slide["wearable_requirement"] == "off" and slide["assigned_by"] == "ct_harris"
    assert slide["sort_order"] == 1 and step["sort_order"] == 0  # the week's order, kept
    # again: every day already has its exercise, so nothing is written and nothing refused
    again = copy()
    assert again.status_code == 201 and again.json() == {"assignments": [], "skipped": 10}
    # a named assigner signs every copied day
    third = copy(to_start=(MONDAY + timedelta(days=14)).isoformat(), assigned_by="ct_harris")
    assert third.status_code == 201 and {r["assigned_by"] for r in third.json()["assignments"]} == {
        "ct_harris"}
    assert copy(assigned_by="ct_nobody", to_start=(MONDAY + timedelta(days=21)).isoformat()
                ).status_code == 422
    assert copy(to_start=MONDAY.isoformat()).status_code == 422  # onto itself
    assert copy(from_start=(MONDAY - timedelta(days=28)).isoformat()).status_code == 422  # empty
    assert copy(patient_id="reyes").status_code == 404  # another hospital's chart
    assert client.post("/api/hep/schedule/copy-week", headers=tokens["demo"], json={
        "patient_id": lifter.id, "from_start": MONDAY.isoformat(),
        "to_start": next_monday.isoformat()}).status_code == 404
    db.expire_all()
    assert db.scalar(select(func.count(ExerciseAssignment.id)).where(
        ExerciseAssignment.patient_id == lifter.id)) == 30
    events = db.scalars(select(AuditEvent).where(
        AuditEvent.action == "assignment.copy_week", AuditEvent.hospital_id == "hirt")).all()
    assert len(events) == 2 and events[0].detail["skipped"] == 0 and len(events[0].detail["ids"]) == 10


def test_programs_are_the_clinics_own_and_apply_on_their_weekdays(client, db, tokens, lifter):
    hirt_console, other = tokens["hirt"], tokens["demo"]
    step_ups = _exercise(client, hirt_console, "functional_step_ups")
    items = [
        {"exercise_id": step_ups["id"], "weekdays": [0, 2, 4], "sets": 3, "reps": 10, "side": "left",
         "load_kg": 10, "rpe_target": 7, "clinician_instructions": "Slow on the way down.",
         "video_requirement": "required"},
        {"exercise_key": "knee_heel_slides", "weekdays": None, "sets": 2, "reps": 10,
         "side": "left", "wearable_requirement": "off"},
    ]
    made = client.post("/api/hep/templates", headers=hirt_console, json={
        "name": "Knee · test block", "description": "A test program.", "weeks": 2, "items": items,
        "actor": "ct_gregg"})
    assert made.status_code == 201, made.text
    template = made.json()
    assert template["clinic_id"] == "hirt" and template["weeks"] == 2
    assert template["created_by"] == "ct_gregg" and template["created_at"]
    assert [TEMPLATE_ITEM_KEYS <= set(i) for i in template["items"]] == [True, True]
    first, second = template["items"]
    assert first["exercise_key"] == "functional_step_ups" and first["title"] == "Step-Ups"
    assert first["weekdays"] == [0, 2, 4] and first["dose"] == "3 sets × 10 reps · 10 kg · Left"
    assert first["video_requirement"] == "required" and first["wearable_requirement"] == "optional"
    assert second["exercise_id"] and second["weekdays"] is None
    assert second["wearable_requirement"] == "off"

    def refused(status, **body):
        resp = client.post("/api/hep/templates", headers=hirt_console, json={
            "name": "Bad block", "items": items, **body})
        assert resp.status_code == status, resp.text

    refused(422, items=[{"exercise_key": "no_such_exercise", "sets": 1}])
    refused(422, items=[{"sets": 1}])
    refused(422, items=[{"exercise_id": step_ups["id"], "weekdays": [7]}])
    refused(422, items=[{"exercise_id": step_ups["id"], "weekdays": [0, 2]},
                        {"exercise_id": step_ups["id"], "weekdays": [2, 4]}])  # twice on Wednesday
    refused(422, items=[{"exercise_id": step_ups["id"], "video_requirement": "always"}])
    refused(422, items=[{"exercise_id": step_ups["id"],
                         "clinician_instructions": "This will detect a tear"}])
    refused(422, items=[])
    refused(422, weeks=13)
    refused(422, name="K")

    # the list is the clinic's own; another clinic sees none of it and cannot reach it
    listed = client.get("/api/hep/templates", headers=hirt_console).json()["templates"]
    assert template["id"] in {t["id"] for t in listed}
    assert {t["name"] for t in listed} >= {"Knee · test block", *(s.name for s in hirt.TEMPLATES)}
    assert template["id"] not in {t["id"] for t in client.get("/api/hep/templates", headers=other)
                                  .json()["templates"]}
    assert client.get(f"/api/hep/templates/{template['id']}", headers=other).status_code == 404
    assert client.put(f"/api/hep/templates/{template['id']}", headers=other,
                      json={"weeks": 3}).status_code == 404
    assert client.delete(f"/api/hep/templates/{template['id']}", headers=other).status_code == 404
    assert client.post(f"/api/hep/templates/{template['id']}/apply", headers=other, json={
        "patient_id": lifter.id, "start": TODAY.isoformat()}).status_code == 404

    # editing: what is sent is replaced
    edited = client.put(f"/api/hep/templates/{template['id']}", headers=hirt_console, json={
        "weeks": 3, "items": items[:1], "actor": "ct_gregg"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["weeks"] == 3 and len(edited.json()["items"]) == 1
    assert edited.json()["name"] == "Knee · test block" and edited.json()["description"] == (
        "A test program.")
    restored = client.put(f"/api/hep/templates/{template['id']}", headers=hirt_console,
                          json={"items": items, "weeks": 2})
    assert len(restored.json()["items"]) == 2

    # applying: every item on its weekdays from the start, for the weeks asked
    applied = client.post(f"/api/hep/templates/{template['id']}/apply", headers=hirt_console, json={
        "patient_id": lifter.id, "start": MONDAY.isoformat(), "weeks": 1, "actor": "ct_gregg"})
    assert applied.status_code == 201, applied.text
    rows = applied.json()["assignments"]
    assert len(rows) == 10 and applied.json()["skipped"] == 0
    steps = [r for r in rows if r["exercise_id"] == step_ups["id"]]
    assert [date.fromisoformat(r["scheduled_for"]).weekday() for r in steps] == [0, 2, 4]
    assert steps[0]["dose"] == "3 sets × 10 reps · 10 kg · Left" and steps[0]["rpe_target"] == 7
    assert steps[0]["video_requirement"] == "required"
    assert steps[0]["clinician_instructions"] == "Slow on the way down."
    assert steps[0]["assigned_by"] == "ct_gregg"  # the patient's provider, by default
    slides = [r for r in rows if r["exercise_key"] == "knee_heel_slides"]
    assert len(slides) == 7 and all(r["wearable_requirement"] == "off" for r in slides)
    # the program's own length when none is given, around what is already there
    again = client.post(f"/api/hep/templates/{template['id']}/apply", headers=hirt_console, json={
        "patient_id": lifter.id, "start": MONDAY.isoformat(), "assigned_by": "ct_harris"})
    assert again.status_code == 201 and again.json()["skipped"] == 10
    assert len(again.json()["assignments"]) == 10  # the second week only
    assert {r["assigned_by"] for r in again.json()["assignments"]} == {"ct_harris"}
    assert client.post(f"/api/hep/templates/{template['id']}/apply", headers=hirt_console, json={
        "patient_id": lifter.id, "start": (TODAY + timedelta(days=85)).isoformat(),
        "weeks": 2}).status_code == 422  # out of reach
    assert client.post(f"/api/hep/templates/{template['id']}/apply", headers=hirt_console, json={
        "patient_id": "reyes", "start": MONDAY.isoformat()}).status_code == 404
    db.expire_all()
    assert db.scalar(select(func.count(ExerciseAssignment.id)).where(
        ExerciseAssignment.patient_id == lifter.id)) == 20

    # deleting archives: gone from the list, cannot be applied, the days it made stay
    gone = client.delete(f"/api/hep/templates/{template['id']}", headers=hirt_console)
    assert gone.status_code == 200 and gone.json() == {"ok": True}
    assert template["id"] not in {t["id"] for t in client.get("/api/hep/templates",
                                                              headers=hirt_console).json()["templates"]}
    assert client.get(f"/api/hep/templates/{template['id']}", headers=hirt_console).status_code == 404
    assert client.post(f"/api/hep/templates/{template['id']}/apply", headers=hirt_console, json={
        "patient_id": lifter.id, "start": MONDAY.isoformat()}).status_code == 404
    archived = db.get(ExerciseTemplate, template["id"])
    assert archived.archived_at is not None and archived.hospital_id == "hirt"
    assert db.scalar(select(func.count(ExerciseAssignment.id)).where(
        ExerciseAssignment.patient_id == lifter.id)) == 20
    actions = db.scalars(select(AuditEvent.action).where(
        AuditEvent.subject_type == "template", AuditEvent.subject_id == str(template["id"]))).all()
    assert actions == ["template.create", "template.update", "template.update", "template.archive"]
    db.delete(archived)
    db.commit()


# --- the patient's calendar, the grid's numbers and the worklist --------------------------------


def test_the_program_counts_missed_days_and_the_cards_carry_the_week(client, db, tokens, lifter,
                                                                      monkeypatch):
    hirt_console = tokens["hirt"]
    step_ups = _exercise(client, hirt_console, "functional_step_ups")
    slides = _exercise(client, hirt_console, "heel slide")
    two_ago, yesterday, last_week = (TODAY - timedelta(days=d) for d in (2, 1, 8))
    _assign(client, hirt_console, lifter.id, slides["id"], [two_ago, yesterday, TODAY], sets=2,
            reps=10)
    heavy = _assign(client, hirt_console, lifter.id, step_ups["id"], [last_week, yesterday],
                    sets=3, reps=10, load_kg=10)
    _log_done(client, hirt_console, heavy[0]["id"], pain_after=2)  # last week, as prescribed
    _log_done(client, hirt_console, heavy[1]["id"], pain_after=3, load_done_kg=12, reps_done=10,
              sets_done=3)  # yesterday, heavier
    session = _patient_session(client, monkeypatch, hirt_console, lifter.id)

    # the calendar: a week back and ahead by default; a past open day is missed
    program = client.get("/api/mobile/exercises/program", headers=session)
    assert program.status_code == 200, program.text
    body = program.json()
    assert body["start"] == (TODAY - timedelta(days=7)).isoformat() and len(body["days"]) == 14
    assert body["clinic"] == {"id": "hirt", "name": "H.I.R.T. Physical Therapy"}
    by_date = {d["date"]: d for d in body["days"]}
    assert [d["date"] for d in body["days"]] == [
        (TODAY + timedelta(days=i)).isoformat() for i in range(-7, 7)]
    assert {k: by_date[two_ago.isoformat()][k] for k in ("assigned", "done", "skipped", "missed")} == {
        "assigned": 1, "done": 0, "skipped": 0, "missed": 1}
    assert {k: by_date[yesterday.isoformat()][k] for k in ("assigned", "done", "missed")} == {
        "assigned": 2, "done": 1, "missed": 1}
    assert {k: by_date[TODAY.isoformat()][k] for k in ("assigned", "done", "missed")} == {
        "assigned": 1, "done": 0, "missed": 0}  # today is still to do, not missed
    assert [i["title"] for i in by_date[yesterday.isoformat()]["items"]] == ["Heel Slides", "Step-Ups"]
    assert all("clinic_id" not in i for d in body["days"] for i in d["items"])
    assert last_week.isoformat() not in by_date
    wide = client.get("/api/mobile/exercises/program", headers=session,
                      params={"start": last_week.isoformat(), "days": 35}).json()
    assert wide["days"][0]["date"] == last_week.isoformat() and wide["days"][0]["done"] == 1
    assert len(wide["days"]) == 35
    assert client.get("/api/mobile/exercises/program?days=36", headers=session).status_code == 422
    assert client.get("/api/mobile/exercises/program?days=0", headers=session).status_code == 422
    assert client.get("/api/mobile/exercises/program").status_code == 401

    # the grid's row header: the seven days ending today, the load against last week
    card = client.get("/api/hep/schedule", params={"today": TODAY.isoformat(), "patient_id": lifter.id},
                      headers=hirt_console).json()["patients"][0]
    assert card["adherence"] == {"assigned": 4, "done": 1, "skipped": 0, "missed": 2, "pct": 25}
    assert card["load_week"] == {"this": 360.0, "last": 300.0, "change_pct": 20}
    assert card["awaiting_review"] == 0
    strip = client.get(f"/api/hep/patients/{lifter.id}/schedule",
                       params={"today": TODAY.isoformat()}, headers=hirt_console).json()["patient"]
    assert strip["adherence"] == card["adherence"] and strip["load_week"] == card["load_week"]
    # the seeded five carry theirs too
    grid = client.get("/api/hep/schedule", params={"today": TODAY.isoformat()},
                      headers=hirt_console).json()
    cole = next(p for p in grid["patients"] if p["id"] == "hirt-cole")
    assert cole["adherence"]["assigned"] > cole["adherence"]["done"] > 0  # today's rows are open
    assert cole["adherence"]["missed"] == 0 and 0 < cole["adherence"]["pct"] < 100
    assert cole["load_week"]["last"] > 0 and cole["load_week"]["this"] >= 0
    devon = next(p for p in grid["patients"] if p["id"] == "hirt-devon")
    assert devon["adherence"]["missed"] > 0 and devon["load_week"] == {
        "this": 0, "last": 0, "change_pct": None}

    # the worklist's line: the seven days ending today, nothing for a chart without exercises
    rows = {p["id"]: p for p in client.get("/api/worklist", headers=hirt_console).json()["patients"]}
    assert rows[lifter.id]["exercises"] == {"assigned": 4, "done": 1, "pct": 25,
                                            "awaiting_review": 0}
    for pid in hirt.HIRT_IDS:
        line = rows[pid]["exercises"]
        assert line and set(line) == {"assigned", "done", "pct", "awaiting_review"}, pid
        assert line["assigned"] >= line["done"] >= 0 and line["awaiting_review"] == 0
    everyone = {p["id"]: p for p in client.get("/api/worklist").json()["patients"]}
    assert everyone["robert"]["exercises"] is None  # a demo-hospital chart, no schedule
    assert everyone["hirt-cole"]["exercises"]["done"] > 0


# --- the seed ----------------------------------------------------------------------------------


def test_the_seed_carries_requirements_sessions_reviews_and_programs(client, db, tokens):
    start = TODAY - timedelta(days=hirt.PROGRAM_DAYS)
    keys = {e.id: e.key for e in db.scalars(select(Exercise).where(Exercise.key.is_not(None)))}
    titles = {e.key: e.title for e in db.scalars(select(Exercise).where(Exercise.key.is_not(None)))}
    for spec in hirt.HIRT_PATIENTS:
        rows = db.scalars(select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == spec.id)).all()
        expected = hirt.EXPECTED_REQUIREMENTS[spec.id]
        loads = hirt.EXPECTED_LOADS.get(spec.id, {})
        for r in rows:
            key = keys[r.exercise_id]
            assert (r.video_requirement, r.wearable_requirement) == expected.get(
                key, ("optional", "optional")), (spec.id, key)
            assert (r.load_kg, r.rpe_target) == loads.get(key, (None, None)), (spec.id, key)
        done = sorted((r for r in rows if r.status == "done"),
                      key=lambda r: (r.scheduled_for, r.sort_order))
        for r in done:
            day = (r.scheduled_for - start).days
            assert r.started_at is not None and r.ended_at == r.completed_at
            assert 8 * 60 <= r.duration_s <= 14 * 60
            assert r.duration_s == int((r.ended_at - r.started_at).total_seconds())
            assert r.effort == hirt.EFFORT[spec.id][day]
            assert r.pain_before == max(r.pain_after - 1, 0)
            assert (r.sets_done, r.reps_done) == (r.sets, r.reps)
            assert r.wearable_worn is (True if spec.id == "hirt-tessa" else None)
            assert r.hr_avg is None and r.hr_max is None  # no wearable sends samples in the seed
        # one day's sessions follow each other, never overlap
        by_day: dict[date, list[ExerciseAssignment]] = {}
        for r in done:
            by_day.setdefault(r.scheduled_for, []).append(r)
        for sessions in by_day.values():
            for earlier, later in zip(sessions, sessions[1:]):
                assert later.started_at > earlier.ended_at
        for r in rows:
            if r.status != "done":
                assert r.started_at is None and r.effort is None and r.reviewed_at is None
        # the reviews: with a note, by the lifter's own therapist, each with its thread line
        reviewed = [r for r in done if r.reviewed_at is not None]
        assert len(reviewed) == hirt.EXPECTED_REVIEWS.get(spec.id, 0), spec.id
        notes = db.scalars(select(Message).where(
            Message.patient_id == spec.id, Message.sender == "care_team",
            Message.text.like("About your %")).order_by(Message.id)).all()
        assert len(notes) == len(reviewed)
        for r in reviewed:
            assert r.reviewed_by == spec.assigned_id and r.review_note
            assert r.reviewed_at > r.completed_at
            line = next(n for n in notes if n.text.endswith(r.review_note))
            assert line.text == f"About your {titles[keys[r.exercise_id]]}: {r.review_note}"
            assert line.sender_id == spec.assigned_id and line.channel == "app"
            assert line.authored_by == "care_team" and line.created_at == r.reviewed_at

    def cole_rows(key: str) -> list[ExerciseAssignment]:
        return sorted((r for r in db.scalars(select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == "hirt-cole", ExerciseAssignment.status == "done"))
            if keys[r.exercise_id] == key), key=lambda r: r.scheduled_for)

    # Cole's effort climbs with his pain, and his step-ups went heavier than the sheet
    efforts = [r.effort for r in sorted(
        (r for r in db.scalars(select(ExerciseAssignment).where(
            ExerciseAssignment.patient_id == "hirt-cole", ExerciseAssignment.status == "done"))),
        key=lambda r: (r.scheduled_for, r.sort_order))]
    assert efforts[0] == 5 and efforts[-1] == 8 and efforts == sorted(efforts)
    step_ups = cole_rows("functional_step_ups")
    assert [r.load_done_kg for r in step_ups][:3] == [10.0, 10.0, 10.0]
    assert step_ups[-1].load_done_kg == hirt.COLE_HEAVY_KG and step_ups[-1].load_kg == 10.0
    # the latest done step-ups is left for the media script's clip, so the queue has one
    assert step_ups[-1].reviewed_at is None and step_ups[-2].reviewed_at is not None
    assert cole_rows("functional_wall_sits")[-1].reviewed_at is not None
    june_birds = sorted((r for r in db.scalars(select(ExerciseAssignment).where(
        ExerciseAssignment.patient_id == "hirt-june", ExerciseAssignment.status == "done"))
        if keys[r.exercise_id] == "back_bird_dog"), key=lambda r: r.scheduled_for)
    assert june_birds[-2].reviewed_at is not None and june_birds[-1].reviewed_at is None
    # the board reads the load trend under Cole's name
    grid = client.get("/api/hep/schedule", params={"today": TODAY.isoformat()},
                      headers=tokens["hirt"]).json()
    cole = next(p for p in grid["patients"] if p["id"] == "hirt-cole")
    assert cole["load_week"]["last"] > 0
    assert cole["awaiting_review"] == 0  # the suite has no object store, so no clips yet
    # the console's thread shows the therapist's lines to Cole, under her name
    thread = client.get("/api/patients/hirt-cole/messages", headers=tokens["hirt"])
    assert thread.status_code == 200, thread.text
    lines = [m for m in thread.json()["messages"] if m["text"].startswith("About your ")]
    assert len(lines) == 2 and all(m["sender"] == "care_team" for m in lines)

    # the clinic's two programs, as the console would have stored them
    listed = {t["name"]: t for t in client.get("/api/hep/templates", headers=tokens["hirt"])
              .json()["templates"]}
    for spec in hirt.TEMPLATES:
        template = listed[spec.name]
        assert template["weeks"] == spec.weeks and template["created_by"] == spec.created_by
        assert template["description"] == spec.description and template["clinic_id"] == "hirt"
        pattern = hirt.SCHEDULE[spec.pattern]
        assert [i["exercise_key"] for i in template["items"]] == [p.key for p in pattern]
        for item, source in zip(template["items"], pattern):
            assert item["weekdays"] == (list(source.weekdays) if source.weekdays else None)
            assert (item["sets"], item["reps"], item["hold_seconds"]) == (
                source.sets, source.reps, source.hold_seconds)
            assert (item["load_kg"], item["rpe_target"]) == (source.load_kg, source.rpe_target)
            assert item["video_requirement"] == source.video_requirement
            assert item["wearable_requirement"] == source.wearable_requirement
            assert item["clinician_instructions"] == source.note and item["title"]
    knee = listed["Patellar tendinopathy · phase 2"]["items"][0]
    assert knee["title"] == "Step-Ups" and knee["video_requirement"] == "required"
    assert knee["dose"] == "3 sets × 10 reps · 10 kg · Left"
    assert "Patellar tendinopathy · phase 2" not in {
        t["name"] for t in client.get("/api/hep/templates", headers=tokens["demo"])
        .json()["templates"]}
    assert hirt.ensure_templates(db) == 0  # idempotent
    assert hirt.ensure_org(db) == 0

    # a refill writes the same reviews once, replacing the lines of the fill before it
    lines_before = db.scalar(select(func.count(Message.id)).where(
        Message.patient_id == "hirt-cole", Message.text.like("About your %")))
    counts = hirt.write_schedule(db, "hirt-cole", TODAY)
    assert counts["reviews"] == 2 and counts["done"] == hirt.EXPECTED_SCHEDULE["hirt-cole"]["done"]
    assert db.scalar(select(func.count(Message.id)).where(
        Message.patient_id == "hirt-cole", Message.text.like("About your %"))) == lines_before == 2
    db.expire_all()
    assert db.scalar(select(func.count(ExerciseAssignment.id)).where(
        ExerciseAssignment.patient_id == "hirt-cole",
        ExerciseAssignment.reviewed_at.is_not(None))) == 2
