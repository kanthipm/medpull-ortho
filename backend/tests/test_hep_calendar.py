"""The calendar's wider reads and the writes that work on more than one day
(docs/dev/showcase.md, "Calendar"): where a row stands on its day, what was
done against what was written, a repeat as one thing, a copy onto other
days, the undo of a day logged in the room, the review queue's two reasons
and its count, the week in review, the month, one exercise over time, and
the unit a clinic reads loads in.

The fixtures are the schedule tests': a HIRT console and another hospital's,
a throwaway chart on the HIRT roster, and a ledger that removes what a test
wrote. The seeded five are only read.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from app.hep.models import ExerciseAssignment
from app.models.hospital import Hospital
from app.seed import hirt
from tests import test_hep_schedule as first_pass
from tests.test_hep_schedule import TODAY, TOMORROW, _assign, _exercise

tokens = first_pass.tokens
ledger = first_pass.ledger
lifter = first_pass.lifter

MONDAY = TODAY - timedelta(days=TODAY.weekday())
YESTERDAY = TODAY - timedelta(days=1)


def _step_ups(client, headers) -> dict:
    """The catalog's Step-Ups itself (a search for the words finds the
    lateral ones first)."""
    rows = client.get("/api/hep/exercises?q=step-ups", headers=headers).json()["exercises"]
    return next(r for r in rows if r["key"] == "functional_step_ups")


def _log_done(client, headers, assignment_id: int, **body) -> dict:
    done = client.post(f"/api/hep/schedule/{assignment_id}/complete", headers=headers,
                       json={"actor": "ct_gregg", **body})
    assert done.status_code == 200, done.text
    return done.json()


# --- where a row stands, and what was done against what was written ----------------------------


def test_a_row_says_where_it_stands_and_how_it_went_against_the_dose(client, tokens, lifter):
    console = tokens["hirt"]
    steps = _step_ups(client, console)
    past, today, ahead = _assign(
        client, console, lifter.id, steps["id"], [YESTERDAY, TODAY, TOMORROW],
        sets=3, reps=10, load_kg=11.34, rpe_target=7,
    )
    # open and behind today, open today, open and ahead
    assert (past["state"], today["state"], ahead["state"]) == ("missed", "due", "upcoming")
    assert past["status"] == today["status"] == ahead["status"] == "assigned"

    # heavier than written and harder than the target: over, in the clinic's own unit
    over = _log_done(client, console, today["id"], pain_after=4, effort=8, sets_done=3,
                     reps_done=10, load_done_kg=15.88)
    done = over["completion"]
    assert over["state"] == "done" and done["over"] is True and done["under"] is False
    assert done["line"] == "35 lb done, 25 lb prescribed · effort 8, target 7"
    assert done["performed"]["load_kg"] == {"done": 15.88, "prescribed": 11.34, "delta": 4.54}
    assert done["performed"]["reps"] == {"done": 10, "prescribed": 10, "delta": 0}
    # a day over the dose waits for a look although no clip came with it
    assert done["awaiting_review"] is True and done["review_reason"] == "over"

    # as written reads as that, and waits for nobody
    same = _log_done(client, console, past["id"], pain_after=2, effort=7, sets_done=3,
                     reps_done=10, load_done_kg=11.34)["completion"]
    assert same["over"] is False and same["under"] is False
    assert same["line"] == "Done as prescribed" and same["awaiting_review"] is False


def test_the_queue_says_why_each_day_waits_and_the_count_agrees(client, tokens, lifter):
    console = tokens["hirt"]
    before = client.get("/api/hep/review/count", headers=console).json()
    assert set(before["by_reason"]) == {"clip", "over"}
    assert before["count"] == sum(before["by_reason"].values())

    steps = _step_ups(client, console)
    row = _assign(client, console, lifter.id, steps["id"], [TODAY], sets=3, reps=10, load_kg=10)[0]
    _log_done(client, console, row["id"], pain_after=3, sets_done=3, reps_done=10, load_done_kg=14)

    after = client.get("/api/hep/review/count", headers=console).json()
    assert after["count"] == before["count"] + 1
    assert after["by_reason"]["over"] == before["by_reason"]["over"] + 1
    queue = client.get("/api/hep/review", headers=console).json()
    assert queue["count"] == after["count"] == len(queue["items"])
    mine = next(i for i in queue["items"] if i["id"] == row["id"])
    assert mine["reason"] == "over" and mine["patient_name"] == lifter.name
    # the grid's head carries the same number
    grid = client.get("/api/hep/schedule", headers=console,
                      params={"today": TODAY.isoformat()}).json()
    assert grid["to_review"]["count"] == after["count"]

    # looked at: it leaves the queue and the count
    reviewed = client.post(f"/api/hep/schedule/{row['id']}/review", headers=console,
                           json={"note": "", "actor": "ct_gregg"})
    assert reviewed.status_code == 200 and reviewed.json()["completion"]["awaiting_review"] is False
    assert client.get("/api/hep/review/count", headers=console).json()["count"] == before["count"]
    # another hospital's console has its own queue
    assert client.get("/api/hep/review/count", headers=tokens["demo"]).json()["count"] == 0


# --- a repeat, as one thing -------------------------------------------------------------------


def test_a_repeat_writes_its_days_and_is_edited_and_cleared_together(client, db, tokens, lifter):
    console = tokens["hirt"]
    clams = _exercise(client, console, "clamshell")
    # one of the days is already taken: the repeat lands around it and says so
    taken = MONDAY + timedelta(days=9)  # next week's Wednesday, in the repeat's first week
    _assign(client, console, lifter.id, clams["id"], [taken], sets=1, reps=5)

    start = MONDAY + timedelta(days=7)
    made = client.post("/api/hep/schedule", headers=console, json={
        "patient_id": lifter.id, "exercise_id": clams["id"],
        "repeat": {"weekdays": [0, 2, 4], "weeks": 2, "start": start.isoformat()},
        "sets": 2, "reps": 12,
    })
    assert made.status_code == 201, made.text
    body = made.json()
    series = body["series_id"]
    days = [a["scheduled_for"] for a in body["assignments"]]
    assert series and len(days) == 5 and taken.isoformat() not in days
    assert all(a["series_id"] == series and a["dose"] == "2 sets × 12 reps" for a in body["assignments"])
    assert body["skipped"] == 1 and body["skipped_days"][0]["date"] == taken.isoformat()
    assert body["text"] is None  # nobody asked for a text

    # dates and a repeat together, or neither, is not a request
    both = client.post("/api/hep/schedule", headers=console, json={
        "patient_id": lifter.id, "exercise_id": clams["id"], "dates": [TODAY.isoformat()],
        "repeat": {"weekdays": [0], "weeks": 1, "start": start.isoformat()}})
    neither = client.post("/api/hep/schedule", headers=console, json={
        "patient_id": lifter.id, "exercise_id": clams["id"]})
    assert both.status_code == neither.status_code == 422

    # "this and the following": the second week is re-dosed, the first keeps its own
    second_week = start + timedelta(days=7)
    patched = client.patch(f"/api/hep/series/{series}", headers=console,
                           params={"from": second_week.isoformat()}, json={"reps": 15})
    assert patched.status_code == 200, patched.text
    assert patched.json()["updated"] == 3
    rows = db.scalars(select(ExerciseAssignment).where(
        ExerciseAssignment.series_id == series).order_by(ExerciseAssignment.scheduled_for)).all()
    # the first week is Mon and Fri (Wed was the taken day), the second all three
    assert [r.reps for r in rows] == [12, 12, 15, 15, 15]

    # one day of it can still be changed by itself
    one = client.patch(f"/api/hep/schedule/{rows[0].id}", headers=console, json={"reps": 8})
    assert one.status_code == 200 and one.json()["reps"] == 8 and one.json()["series_id"] == series

    # cleared from the second week on: the first week stays
    cleared = client.delete(f"/api/hep/series/{series}", headers=console,
                            params={"from": second_week.isoformat()})
    assert cleared.status_code == 200
    assert (cleared.json()["deleted"], cleared.json()["kept"]) == (3, 2)
    # another hospital's console cannot see or touch the repeat
    assert client.patch(f"/api/hep/series/{series}", headers=tokens["demo"],
                        json={"reps": 1}).status_code == 404
    assert client.delete(f"/api/hep/series/{series}", headers=tokens["demo"]).status_code == 404
    assert client.patch("/api/hep/series/no-such-series", headers=console,
                        json={"reps": 1}).status_code == 404


def test_a_day_is_copied_onto_other_days_and_a_logged_day_can_be_reopened(client, tokens, lifter):
    console = tokens["hirt"]
    squats = _exercise(client, console, "mini squat")
    row = _assign(client, console, lifter.id, squats["id"], [TODAY], sets=3, reps=12,
                  clinician_instructions="Heels down.", video_requirement="required")[0]

    later = [TODAY + timedelta(days=2), TODAY + timedelta(days=4)]
    copied = client.post(f"/api/hep/schedule/{row['id']}/duplicate", headers=console,
                         json={"dates": [d.isoformat() for d in later]})
    assert copied.status_code == 201, copied.text
    copies = copied.json()["assignments"]
    assert [c["scheduled_for"] for c in copies] == [d.isoformat() for d in later]
    assert all(c["dose"] == row["dose"] and c["status"] == "assigned"
               and c["clinician_instructions"] == "Heels down."
               and c["video_requirement"] == "required" and c["completion"] is None
               for c in copies)
    # all or nothing: a day that already has it refuses the whole copy, naming the day
    again = client.post(f"/api/hep/schedule/{row['id']}/duplicate", headers=console,
                        json={"dates": [later[0].isoformat(), (TODAY + timedelta(days=6)).isoformat()]})
    assert again.status_code == 409 and later[0].isoformat() in again.json()["detail"]
    assert client.post(f"/api/hep/schedule/{row['id']}/duplicate", headers=tokens["demo"],
                       json={"dates": [TOMORROW.isoformat()]}).status_code == 404

    # logged in the room, then undone: the day is open again and can be re-dosed
    open_day = copies[0]["id"]
    assert client.post(f"/api/hep/schedule/{open_day}/reopen", headers=console).status_code == 409
    _log_done(client, console, open_day, pain_after=2)
    reopened = client.post(f"/api/hep/schedule/{open_day}/reopen", headers=console,
                           json={"actor": "ct_gregg"})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "assigned" and reopened.json()["completion"] is None
    assert client.patch(f"/api/hep/schedule/{open_day}", headers=console,
                        json={"reps": 10}).status_code == 200

    # a day the lifter logged themselves is their record: it is not the console's to undo
    cole_done = client.get("/api/hep/patients/hirt-cole/schedule", headers=console, params={
        "start": (TODAY - timedelta(days=7)).isoformat(), "days": 7,
        "today": TODAY.isoformat()}).json()["assignments"]
    theirs = next(a for a in cole_done if a["status"] == "done" and a["completion"]["source"] == "app")
    refused = client.post(f"/api/hep/schedule/{theirs['id']}/reopen", headers=console)
    assert refused.status_code == 409


# --- the week in review, the month, one exercise over time -----------------------------------------


def test_the_week_in_review_reads_each_lifter_and_puts_attention_first(client, tokens):
    console = tokens["hirt"]
    week = client.get("/api/hep/week", headers=console, params={"today": TODAY.isoformat()})
    assert week.status_code == 200, week.text
    body = week.json()
    assert body["start"] == MONDAY.isoformat() and len(body["days"]) == 7
    assert body["clinic"] == {"id": "hirt", "name": "H.I.R.T. Physical Therapy", "load_unit": "lb"}
    entries = {e["patient"]["id"]: e for e in body["patients"]}
    assert set(entries) >= hirt.HIRT_IDS

    # lifters with something to look at come first
    flags = [bool(e["attention"]) for e in body["patients"]]
    assert flags == sorted(flags, reverse=True)

    for entry in entries.values():
        week_counts = entry["week"]
        assert week_counts["assigned"] == (week_counts["done"] + week_counts["skipped"]
                                           + week_counts["missed"] + week_counts["open"])
        assert len(entry["pain"]["by_day"]) == 7
        assert set(entry["attention"]) <= {"over", "review", "missed"}
        assert entry["next_week"]["start"] == (MONDAY + timedelta(days=7)).isoformat()
        assert entry["next_week"]["set"] is (entry["next_week"]["assigned"] > 0)

    # June's therapist writes a week at a time: her next week is not set, the others' is
    assert entries["hirt-june"]["next_week"]["set"] is False
    assert entries["hirt-cole"]["next_week"]["set"] is True
    assert entries["hirt-june"]["attention"] == []  # she did it all and nothing waits

    # Cole's heavy step-ups are over the dose, each in the clinic's unit; whether any
    # fall in this week depends on the weekday the test runs on, so look a week back too
    def over(start):
        got = client.get("/api/hep/week", headers=console, params={
            "start": start.isoformat(), "today": TODAY.isoformat()}).json()
        return next(e for e in got["patients"] if e["patient"]["id"] == "hirt-cole")["over"]

    lines = over(MONDAY) + over(MONDAY - timedelta(days=7))
    assert lines and all(o["title"] == "Step-Ups" and o["line"].startswith("35 lb done, 25 lb prescribed")
                         for o in lines)

    # another hospital's week is its own
    other = client.get("/api/hep/week", headers=tokens["demo"]).json()
    assert not {e["patient"]["id"] for e in other["patients"]} & hirt.HIRT_IDS


def test_the_month_is_compact_and_counts_each_day(client, tokens):
    console = tokens["hirt"]
    month = client.get("/api/hep/calendar", headers=console, params={"today": TODAY.isoformat()})
    assert month.status_code == 200, month.text
    body = month.json()
    first = TODAY.replace(day=1)
    assert body["start"] == (first - timedelta(days=first.weekday())).isoformat()
    assert len(body["days"]) == 42 and body["today"] == TODAY.isoformat()
    cole = next(p for p in body["patients"] if p["id"] == "hirt-cole")
    assert [d["date"] for d in cole["days"]] == body["days"]
    seen = 0
    for day in cole["days"]:
        assert day["assigned"] == len(day["items"])
        assert day["assigned"] == day["done"] + day["skipped"] + day["missed"] + day["open"]
        for item in day["items"]:
            seen += 1
            # compact: where it stands and how it went, no steps and no clip URLs
            assert {"id", "title", "state", "dose", "over", "line", "review_reason"} <= set(item)
            assert "steps" not in item and "video" not in item
    assert seen > 0
    yesterday = next((d for d in cole["days"] if d["date"] == YESTERDAY.isoformat()), None)
    if yesterday is not None and yesterday["assigned"]:
        assert yesterday["done"] == yesterday["assigned"] and yesterday["missed"] == 0

    # one chart only, a shorter window, and the limits
    only = client.get("/api/hep/calendar", headers=console, params={
        "patient_id": "hirt-tessa", "days": 14, "start": MONDAY.isoformat()}).json()
    assert [p["id"] for p in only["patients"]] == ["hirt-tessa"] and len(only["days"]) == 14
    assert client.get("/api/hep/calendar", headers=console, params={"days": 43}).status_code == 422
    assert client.get("/api/hep/calendar", headers=tokens["demo"],
                      params={"patient_id": "hirt-cole"}).status_code == 404


def test_one_exercise_over_time_is_the_run_in_a_few_numbers(client, tokens):
    console = tokens["hirt"]
    steps = _step_ups(client, console)
    got = client.get(f"/api/hep/patients/hirt-cole/exercises/{steps['id']}/history",
                     headers=console, params={"today": TODAY.isoformat()})
    assert got.status_code == 200, got.text
    body = got.json()
    assert body["exercise"]["title"] == "Step-Ups" and body["clinic"]["load_unit"] == "lb"
    points = body["points"]
    assert points and [p["date"] for p in points] == sorted(p["date"] for p in points)
    assert all(p["date"] <= TODAY.isoformat() for p in points)  # nothing ahead unless asked
    done = [p for p in points if p["status"] == "done"]
    summary = body["summary"]
    assert summary["sessions_done"] == len(done) == 6  # Mon/Wed/Fri over fourteen days
    # the light week as written, the heavy week over it
    assert summary["first_load_kg"] == hirt.COLE_STEP_UP_KG
    assert summary["latest_load_kg"] == summary["best_load_kg"] == hirt.COLE_HEAVY_KG
    # the heavy days are program days 8 to 13: two or three of Mon/Wed/Fri, by the weekday today is
    assert summary["over"] == sum(p["over"] for p in done) and summary["over"] in (2, 3)
    assert summary["load_change_pct"] == 40
    heavy = done[-1]
    assert heavy["over"] and heavy["line"].startswith("35 lb done, 25 lb prescribed")
    assert heavy["tonnage"] == round(hirt.COLE_HEAVY_KG * 30, 1)

    # with the days already written ahead
    ahead = client.get(f"/api/hep/patients/hirt-cole/exercises/{steps['id']}/history",
                       headers=console, params={"today": TODAY.isoformat(), "ahead": 14}).json()
    assert len(ahead["points"]) > len(points)
    assert ahead["summary"] == summary  # the run is what has happened, not what is planned

    assert client.get("/api/hep/patients/hirt-cole/exercises/999999/history",
                      headers=console).status_code == 404
    assert client.get(f"/api/hep/patients/hirt-cole/exercises/{steps['id']}/history",
                      headers=tokens["demo"]).status_code == 404


# --- the unit a clinic reads loads in ---------------------------------------------------------------


def test_a_clinic_chooses_its_unit_and_the_rows_stay_kilograms(client, db, tokens, lifter):
    console = tokens["hirt"]
    assert client.get("/api/hep/clinic", headers=console).json() == {
        "id": "hirt", "name": "H.I.R.T. Physical Therapy", "load_unit": "lb"}
    steps = _step_ups(client, console)
    row = _assign(client, console, lifter.id, steps["id"], [TODAY], sets=3, reps=10, load_kg=11.34)[0]
    assert row["dose"] == "3 sets × 10 reps · 25 lb" and row["load_kg"] == 11.34
    try:
        changed = client.patch("/api/hep/clinic", headers=console, json={"load_unit": "kg"})
        assert changed.status_code == 200 and changed.json()["load_unit"] == "kg"
        again = client.get(f"/api/hep/patients/{lifter.id}/schedule", headers=console,
                           params={"today": TODAY.isoformat()}).json()
        assert again["clinic"]["load_unit"] == "kg"
        same = next(a for a in again["assignments"] if a["id"] == row["id"])
        # the stored number did not move; the words did
        assert same["load_kg"] == 11.34 and same["dose"] == "3 sets × 10 reps · 11.34 kg"
        assert client.patch("/api/hep/clinic", headers=console,
                            json={"load_unit": "stone"}).status_code == 422
        # each clinic's unit is its own
        assert client.get("/api/hep/clinic", headers=tokens["demo"]).json()["load_unit"] == "kg"
    finally:
        db.expire_all()
        db.get(Hospital, "hirt").load_unit = "lb"
        db.commit()
    assert client.get("/api/hep/clinic", headers=console).json()["load_unit"] == "lb"
