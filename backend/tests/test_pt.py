"""The between-visits record (app/pt; docs/dev/pt.md): the clinic's settings
and flag rules, what a person is asked and where the answers land, pain
areas and the new-area flag, function goals, the week's word, phases and
their gates, test results, outcome measures, the trainer's page, visits and
rest days on the calendar, the dose ceilings, bulk assign and the exercise
count, clip comments, question triage and the clinic's fixed red-flag words.

Writes happen on a throwaway H.I.R.T. chart and are removed afterwards.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select

from app.config import settings
from app.console_credentials import mint
from app.hep.models import AuditEvent, ExerciseAssignment
from app.models.adherence import AdherenceRecord, AdherenceTask
from app.models.attachment import Attachment
from app.models.enums import ProcedureType
from app.models.mobile import Message
from app.models.notification import Notification
from app.models.patient import Patient
from app.pt import asks, regions, triage
from app.pt import settings as pt_settings
from app.pt.models import (
    CalendarMark,
    ClinicSetting,
    ClinicVisit,
    ClipComment,
    FlagEvent,
    FunctionGoal,
    FunctionRating,
    Handoff,
    Measurement,
    MorningCheck,
    OutcomeSchedule,
    OutcomeScore,
    PainArea,
    PatientPhase,
    PatientSetting,
    Protocol,
    RedFlagText,
    WeekCheckin,
)
from app.seed import hirt
from tests.test_mobile import _forget_patient

TODAY = date.today()
YESTERDAY = TODAY - timedelta(days=1)
PID = "hirt-between-test"
_PT_PATIENT = (PainArea, MorningCheck, FunctionRating, FunctionGoal, WeekCheckin, PatientPhase,
               Measurement, Handoff, ClipComment, OutcomeSchedule, OutcomeScore, ClinicVisit,
               CalendarMark, FlagEvent)
_LEDGER = (ExerciseAssignment, AuditEvent, Attachment, Message, Notification)


@pytest.fixture(scope="module")
def console(seeded_db):
    """A H.I.R.T. console and another hospital's."""
    minted = {
        "hirt": mint(seeded_db, "hospital", "hirt", "HIRT console"),
        "demo": mint(seeded_db, "hospital", "hosp_demo", "Demo hospital console"),
    }
    yield {name: {"Authorization": f"Bearer {token}"} for name, (_row, token) in minted.items()}
    for row, _token in minted.values():
        seeded_db.delete(row)
    seeded_db.commit()


@pytest.fixture()
def lifter(db):
    """A throwaway chart on the H.I.R.T. roster; everything it grows is
    removed afterwards, the clinic's settings and red-flag entries too."""
    marks = {model: (db.scalar(select(func.max(model.id))) or 0) for model in _LEDGER}
    patient = Patient(
        id=PID, name="Noa Lindqvist", initials="NL", age=31, sex="F",
        procedure_type=ProcedureType.NONE, procedure_display=hirt.PATHWAYS["hirt-cole"],
        surgery_date=TODAY - timedelta(days=14), discharge_date=TODAY - timedelta(days=14),
        surgeon_id="ct_harris", assigned_provider_id="ct_gregg", hospital_id="hirt",
        care_pathway=hirt.PATHWAYS["hirt-cole"],
    )
    db.add(patient)
    db.commit()
    yield patient
    db.rollback()
    db.expire_all()
    for model in _PT_PATIENT:
        db.execute(delete(model).where(model.patient_id == PID))
    db.execute(delete(PatientSetting).where(PatientSetting.patient_id == PID))
    db.execute(delete(ClinicSetting).where(ClinicSetting.hospital_id.in_(["hirt", "hosp_demo"])))
    db.execute(delete(RedFlagText).where(RedFlagText.hospital_id.in_(["hirt", "hosp_demo"])))
    db.execute(delete(Protocol).where(Protocol.hospital_id == "hirt"))
    db.execute(delete(ExerciseAssignment).where(ExerciseAssignment.patient_id == PID))
    db.execute(delete(AdherenceRecord).where(AdherenceRecord.patient_id == PID))
    for model, mark in marks.items():
        db.execute(delete(model).where(model.id > mark))
    db.commit()
    _forget_patient(db, PID)


@pytest.fixture()
def phone(client, db, lifter, monkeypatch):
    """The lifter's own app session."""
    from app.api.mobile import _issue_session
    from app.database import SessionLocal

    monkeypatch.setattr(settings, "demo_mode", True)
    with SessionLocal() as session:
        token = _issue_session(session, session.get(Patient, PID), "between-visits test", None)
    return {"Authorization": f"Bearer {token}"}


def _chart(client, console) -> dict:
    resp = client.get(f"/api/pt/patients/{PID}", headers=console["hirt"])
    assert resp.status_code == 200, resp.text
    return resp.json()


def _post(client, console, path: str, body: dict | None = None, *, expect: int = 200,
          method: str = "post") -> dict:
    if method == "delete":
        resp = client.delete(f"/api/pt{path}", headers=console["hirt"])
    else:
        resp = getattr(client, method)(f"/api/pt{path}", json=body or {}, headers=console["hirt"])
    assert resp.status_code == expect, resp.text
    return resp.json()


def _open_task(client, phone, qset: str) -> dict:
    tasks_ = client.get("/api/mobile/tasks", headers=phone).json()["open"]
    from app.database import SessionLocal

    with SessionLocal() as session:
        for t in tasks_:
            row = session.get(AdherenceTask, t["id"])
            if (row.payload or {}).get("qset") == qset and t["status"] in ("pending", "sent"):
                return t
    raise AssertionError(f"no open {qset} task among {[t['title'] for t in tasks_]}")


def _answer(client, phone, task: dict, answers: dict) -> None:
    resp = client.post(f"/api/mobile/tasks/{task['id']}/complete", json={"answers": answers},
                       headers=phone)
    assert resp.status_code == 200, resp.text


def _exercise(client, console, q: str) -> dict:
    return client.get(f"/api/hep/exercises?q={q}", headers=console["hirt"]).json()["exercises"][0]


def _assign(client, console, exercise_id: int, days: list[date], *, expect: int = 201,
            **more) -> dict:
    body = {"patient_id": PID, "exercise_id": exercise_id,
            "dates": [d.isoformat() for d in days], **more}
    resp = client.post("/api/hep/schedule", json=body, headers=console["hirt"])
    assert resp.status_code == expect, resp.text
    return resp.json()


# --- settings and the rules page -------------------------------------------------------------


def test_a_clinic_reads_the_defaults_until_it_changes_one(client, console, lifter, db):
    body = client.get("/api/pt/settings", headers=console["hirt"]).json()
    assert body["settings"] == pt_settings.DEFAULTS and body["clinic"] == "hirt"
    assert db.get(ClinicSetting, "hirt") is None  # reading writes nothing

    changed = client.patch("/api/pt/settings", headers=console["hirt"], json={
        "flags": {"quiet_days": 2, "pain_rise_points": 3}, "exercise_guard": 4,
        "morning_check": {"on": True, "ceiling": 4}, "by": "ct_gregg"}).json()["settings"]
    assert changed["flags"]["quiet_days"] == 2 and changed["flags"]["pain_rise_points"] == 3
    assert changed["flags"]["load_spike_ratio"] == 1.5  # untouched ones keep the default
    assert changed["exercise_guard"] == 4 and changed["morning_check"] == {"on": True, "ceiling": 4}
    # Only what differs is stored; another clinic still reads the defaults.
    assert db.get(ClinicSetting, "hirt").data["flags"] == {"quiet_days": 2, "pain_rise_points": 3.0}
    assert client.get("/api/pt/settings", headers=console["demo"]).json()["settings"] \
        == pt_settings.DEFAULTS

    for bad in ({"flags": {"quiet_days": 0}}, {"flags": {"nope": 1}}, {"exercise_guard": 99},
                {"flags": {"load_spike_ratio": 1.2, "load_watch_ratio": 1.4}},
                {"outcome_thresholds": {"nope": 3}}, {"triage_words": ["x" * 41]}):
        resp = client.patch("/api/pt/settings", headers=console["hirt"], json=bad)
        assert resp.status_code == 422, bad
    # A threshold sent as null goes back to the default.
    back = client.patch("/api/pt/settings", headers=console["hirt"],
                        json={"flags": {"quiet_days": None}}).json()["settings"]
    assert back["flags"]["quiet_days"] == 3


def test_the_rules_page_states_each_flag_with_the_clinics_numbers(client, console, lifter, db):
    client.patch("/api/pt/settings", headers=console["hirt"],
                 json={"flags": {"quiet_days": 2, "quiet_days_high": 4}})
    for code, day in (("WENT_QUIET", TODAY), ("WENT_QUIET", YESTERDAY), ("LOAD_SPIKE", TODAY)):
        db.add(FlagEvent(hospital_id="hirt", patient_id=PID, code=code, day=day))
    db.commit()
    flags = {f["code"]: f for f in client.get("/api/pt/flags", headers=console["hirt"]).json()["flags"]}
    assert list(flags) == ["LOAD_SPIKE", "PAIN_RISING", "NEW_PAIN", "PROGRAM_SLIPPING", "WENT_QUIET"]
    quiet = flags["WENT_QUIET"]
    assert quiet["rule"] == ("Raised after 2 days with no check-in. At 4 days the chart is High.")
    assert [(t["key"], t["value"], t["default"], t["changed"]) for t in quiet["thresholds"]] == [
        ("quiet_days", 2, 3.0, True), ("quiet_days_high", 4, 5.0, True)]
    assert quiet["fired"]["today"] >= 1 and quiet["fired"]["chart_days"] >= 2
    assert "50% done" in flags["PROGRAM_SLIPPING"]["rule"]
    assert flags["NEW_PAIN"]["thresholds"] == []


def test_the_clinics_thresholds_are_the_ones_a_chart_is_scored_on(db, lifter):
    from app.engine.pipeline import compute_input_hash
    from app.engine.risk import score_reported
    from app.engine.types import ReportedSignals
    from app.models.enums import RiskLevel

    quiet = ReportedSignals(checkins_7d=4, checkins_14d=8, days_since_checkin=2)
    assert score_reported(quiet, 14).level == RiskLevel.LOW
    own = pt_settings.FlagThresholds(quiet_days=2, quiet_days_high=4)
    scored = score_reported(quiet, 14, own)
    assert scored.level == RiskLevel.MEDIUM and scored.reasons[0].code == "WENT_QUIET"
    assert score_reported(ReportedSignals(checkins_14d=8, days_since_checkin=4), 14, own).level \
        == RiskLevel.HIGH
    assert own.changed() == {"quiet_days": 2, "quiet_days_high": 4}

    # Changing a threshold rescored the clinic's charts and nobody else's.
    before, elsewhere = compute_input_hash(db, PID), compute_input_hash(db, "grace")
    pt_settings.update(db, "hirt", {"flags": {"quiet_days": 2}}, by="ct_gregg")
    assert compute_input_hash(db, PID) != before
    assert compute_input_hash(db, "grace") == elsewhere
    assert pt_settings.flag_signature(db, "hosp_demo") == ""


# --- asked, answered, filed ---------------------------------------------------------------


def test_the_morning_after_is_asked_once_and_read_against_the_ceiling(client, console, phone, db,
                                                                      lifter):
    walk = _exercise(client, console, "Step-Ups")
    made = _assign(client, console, walk["id"], [YESTERDAY], load_kg=10)["assignments"][0]
    assert _chart(client, console)["morning"]["can_ask"] is False  # not done: not a loaded day
    done = client.post(f"/api/hep/schedule/{made['id']}/complete", json={"pain_after": 3},
                       headers=console["hirt"])
    assert done.status_code == 200, done.text
    assert _chart(client, console)["morning"]["can_ask"] is True

    asked = _post(client, console, f"/patients/{PID}/morning/ask", {"by": "ct_gregg"})
    assert asked["sent"]["sent"] is False  # no phone on this chart: in the app only
    assert asked["morning"]["last"]["read"] == "waiting" and asked["morning"]["can_ask"] is False
    assert [a["qset"] for a in asked["asks"]] == [asks.MORNING]
    # Asked once: a second press is refused nowhere and adds nothing.
    again = _post(client, console, f"/patients/{PID}/morning/ask", {})
    assert again["sent"]["reused"] is True
    assert db.scalar(select(func.count(MorningCheck.id)).where(MorningCheck.patient_id == PID)) == 1

    task = _open_task(client, phone, asks.MORNING)
    assert [q["id"] for q in task["questions"]] == ["pain", "stiffer"]
    _answer(client, phone, task, {"pain": 5, "stiffer": "yes"})
    morning = _chart(client, console)["morning"]
    assert morning["last"]["pain"] == 5 and morning["last"]["stiffer"] is True
    assert morning["last"]["settled"] is False and morning["last"]["read"] == "not settled"
    assert morning["answered"] == 1 and morning["settled"] == 0
    notice = db.scalars(select(Notification).where(Notification.patient_id == PID)
                        .order_by(Notification.id.desc())).first()
    assert "Not settled the morning after" in notice.title and "pain 5/10" in notice.body
    # An answer is not a dose: no adherence record, and the plan never counts it.
    from app.engine.care.loaders import load_tasks_with_records

    assert db.scalar(select(func.count(AdherenceRecord.id))
                     .where(AdherenceRecord.patient_id == PID)) == 0
    assert load_tasks_with_records(db, PID, TODAY) == []
    assert _chart(client, console)["asks"] == []

    # Her own ceiling, where it differs from the clinic's.
    own = _post(client, console, f"/patients/{PID}/settings",
                {"morning_check": {"on": True, "ceiling": 6}}, method="patch")["settings"]
    assert own["morning_check"] == {"on": True, "ceiling": 6, "own": True}
    resp = client.post(f"/api/pt/patients/{PID}/morning/ask", headers=console["hirt"],
                       json={"session_day": TODAY.isoformat()})
    assert resp.status_code == 422 and "not come yet" in resp.json()["detail"]


def test_a_new_pain_is_followed_by_where_and_a_new_area_is_named_on_the_chart(
        client, console, phone, db, lifter):
    from app.engine.reported import reported_signals
    from app.engine.risk import score_reported
    from app.tasks import service as tasks

    _post(client, console, f"/patients/{PID}/areas", {"area": "knee", "side": "right"}, expect=201)
    task, _ = tasks.create_task(db, lifter, title="Daily check-in", kind="checkin", notify=False)
    assert tasks.question_set_key(task) == "checkin_lifter"
    tasks.complete_task(db, task, {"pain": 3, "new_pain": "yes", "program": "all"}, via="app")

    follow = _open_task(client, phone, asks.NEW_AREA)
    assert follow["title"] == "Where is the new pain?"
    assert follow["questions"][0]["options"] == list(regions.AREAS)
    _answer(client, phone, follow, {"area": "hip or groin", "side": "left", "note": "Front of it."})
    areas = _chart(client, console)["areas"]
    assert [(a["label"], a["source"], a["new"]) for a in areas["evaluation"]] == [
        ("Right knee", "evaluation", False)]
    assert [(a["label"], a["new"], a["note"]) for a in areas["reported"]] == [
        ("Left hip or groin", True, "Front of it.")]
    notice = db.scalars(select(Notification).where(Notification.patient_id == PID)
                        .order_by(Notification.id.desc())).first()
    assert "Reported a new area: left hip or groin" in notice.title

    reported = reported_signals(db, lifter, TODAY, 14, {})
    assert reported.new_pain and reported.new_pain_area == "Left hip or groin"
    reported.checkins_14d = 5
    scored = score_reported(reported, 14)
    assert scored.reasons[0].code == "NEW_PAIN"
    assert scored.reasons[0].text.startswith("Reported a new area since the last visit: left hip")
    plain = score_reported(type(reported)(checkins_14d=5, new_pain=True, new_pain_day=14), 14)
    assert scored.score == plain.score + 8  # it tops the others in its tier

    # The same knee on the other side is new; the knee already on file is not.
    assert regions.is_new("knee:left", ["knee:right"]) and not regions.is_new("knee:right", ["knee"])
    # A visit after it was named: seen, no longer new, not forgotten.
    _post(client, console, f"/patients/{PID}/areas",
          {"area": "shoulder", "side": "left", "source": "reported"}, expect=201)
    db.execute(PainArea.__table__.update().where(PainArea.patient_id == PID)
               .values(noted_on=YESTERDAY))
    db.commit()
    _post(client, console, f"/patients/{PID}/visits", {"on": TODAY.isoformat()}, expect=201)
    seen = _chart(client, console)["areas"]["reported"]
    assert all(a["seen_on"] == TODAY.isoformat() and a["new"] is False for a in seen)
    assert reported_signals(db, lifter, TODAY, 14, {}).new_pain_area is None


def test_goals_are_the_persons_words_and_their_ratings_are_the_functional_scale(
        client, console, phone, db, lifter):
    asked = _post(client, console, f"/patients/{PID}/goals/ask", {})
    assert asked["sent"]["detail"]
    task = _open_task(client, phone, asks.GOALS)
    assert len(task["questions"]) == 3
    _answer(client, phone, task, {"goal_1": "Pull 315 from the floor",
                                 "goal_2": "Squat to a box without the knee talking",
                                 "goal_3": "nothing"})
    goals = _chart(client, console)["function"]["goals"]
    assert [g["text"] for g in goals] == ["Pull 315 from the floor",
                                         "Squat to a box without the knee talking"]
    # The therapist's rating at the visit, then the person's own a week on.
    ids = [g["id"] for g in goals]
    _post(client, console, f"/patients/{PID}/goals/rate",
          {"scores": {str(ids[0]): 3, str(ids[1]): 5}, "on": (TODAY - timedelta(days=7)).isoformat()})
    _post(client, console, f"/patients/{PID}/goals/ask-rating", {})
    rating = _open_task(client, phone, asks.FUNCTION)
    assert rating["questions"][0]["prompt"].startswith("Pull 315 from the floor: how able")
    _answer(client, phone, rating, {f"goal_{ids[0]}": 6, f"goal_{ids[1]}": 8})
    function = _chart(client, console)["function"]
    first, second = function["goals"]
    assert (first["first"], first["latest"], first["change"]) == (3, 6, 3)
    assert [r["source"] for r in second["ratings"]] == ["clinic", "patient"]
    score = function["score"]
    assert (score["first"], score["latest"], score["threshold"]) == (4.0, 7.0, 2)
    assert score["change"] == {"delta": 3.0, "direction": "better", "past_threshold": True}
    # The number comes first in the person's sentence, so a goal that says
    # "pain" is never read as a pain score.
    from app.models.checkin import Checkin, CheckinMessage

    said = db.scalars(select(CheckinMessage.text).join(Checkin).where(
        Checkin.patient_id == PID, CheckinMessage.who == "patient")).all()
    assert "6 out of 10 for: Pull 315 from the floor." in said

    assert _post(client, console, f"/patients/{PID}/goals", {"text": "Run a 5k"}, expect=201)
    resp = client.post(f"/api/pt/patients/{PID}/goals", headers=console["hirt"],
                       json={"text": "A fourth"})
    assert resp.status_code == 422 and "Up to 3 goals" in resp.json()["detail"]
    _post(client, console, f"/patients/{PID}/goals/{ids[0]}", method="delete")
    assert [g["active"] for g in _chart(client, console)["function"]["goals"]] == [True, True, False]


def test_the_week_gets_its_word_and_the_review_shows_it(client, console, phone, db, lifter):
    monday = TODAY - timedelta(days=TODAY.weekday())
    _post(client, console, f"/patients/{PID}/week/ask", {})
    task = _open_task(client, phone, asks.WEEK)
    _answer(client, phone, task, {"went": "worse", "next_week": "Travelling Tuesday to Thursday."})
    latest = _chart(client, console)["week"]["latest"]
    assert latest["week_start"] == monday.isoformat() and latest["went"] == "worse"
    assert latest["change_note"] == "Travelling Tuesday to Thursday."
    resp = client.post(f"/api/pt/patients/{PID}/week/ask", headers=console["hirt"], json={})
    assert resp.status_code == 422 and "already answered" in resp.json()["detail"]

    review = client.get("/api/hep/week", headers=console["hirt"]).json()
    mine = next(e for e in review["patients"] if e["patient"]["id"] == PID)
    assert mine["between_visits"]["week_checkin"]["went"] == "worse"
    assert set(mine["between_visits"]) == {"week_checkin", "mornings", "next_visit", "phase"}
    assert "visits" in review and "marks" in review


# --- phases and their gates ---------------------------------------------------------------


def test_a_phase_moves_on_when_a_clinician_says_so(client, console, lifter, db):
    made = _post(client, console, "/protocols", {
        "name": "Patellar tendon, in season", "by": "ct_gregg", "phases": [
            {"name": "Isometric loading", "goal": "Calm it down.",
             "criteria": ["Pain 3/10 or less on the decline squat", "Holds 45 s wall sit"]},
            {"name": "Isotonic loading", "goal": "Build it back.", "criteria": ["Step-ups pain-free"]},
            {"name": "Energy storage", "goal": "", "criteria": []},
        ]}, expect=201)["protocols"]
    protocol = made[0]
    chart = _post(client, console, f"/patients/{PID}/phases", {"protocol_id": protocol["id"]},
                  method="put")
    phases = chart["phases"]
    assert (phases["number"], phases["count"], phases["current"]["name"]) == (1, 3, "Isometric loading")
    assert phases["protocol_name"] == "Patellar tendon, in season"
    first = phases["current"]

    ticked = _post(client, console, f"/patients/{PID}/phases/{first['id']}/criteria/0",
                   {"by": "ct_gregg", "met": True})["phases"]["current"]
    assert (ticked["met"], ticked["of"]) == (1, 2)
    assert ticked["criteria"][0]["met_by_name"] == "Dr. Ashley Gregg"
    # One criterion is still open: the software does not move her, and the
    # clinician has to mean it.
    resp = client.post(f"/api/pt/patients/{PID}/phases/advance", headers=console["hirt"],
                       json={"by": "ct_gregg"})
    assert resp.status_code == 409 and "Holds 45 s wall sit" in resp.json()["detail"]
    assert _chart(client, console)["phases"]["number"] == 1
    moved = _post(client, console, f"/patients/{PID}/phases/advance",
                  {"by": "ct_gregg", "with_unmet": True})["phases"]
    assert (moved["number"], moved["current"]["name"]) == (2, "Isotonic loading")
    assert moved["phases"][0]["status"] == "done"
    assert moved["phases"][0]["advanced_by_name"] == "Dr. Ashley Gregg"
    back = _post(client, console, f"/patients/{PID}/phases/back", {"by": "ct_gregg"})["phases"]
    assert back["number"] == 1 and back["phases"][1]["status"] == "upcoming"

    for body in ({"by": "nobody"}, {}):
        assert client.post(f"/api/pt/patients/{PID}/phases/advance", headers=console["hirt"],
                           json=body).status_code == 422
    # Another clinic neither sees the protocol nor the chart.
    assert client.get("/api/pt/protocols", headers=console["demo"]).json()["protocols"] == []
    assert client.get(f"/api/pt/patients/{PID}", headers=console["demo"]).status_code == 404


# --- numbers: tests, holds, outcome measures --------------------------------------------------


def test_test_day_numbers_sit_side_by_side_and_a_hold_is_timed_at_home(
        client, console, phone, db, lifter):
    week_ago = (TODAY - timedelta(days=7)).isoformat()
    for on, side, value in ((week_ago, "left", 320), (week_ago, "right", 400),
                            (TODAY.isoformat(), "left", 372), (TODAY.isoformat(), "right", 410)):
        _post(client, console, f"/patients/{PID}/tests",
              {"kind": "isometric_knee_extension", "side": side, "value": value,
               "tested_on": on, "by": "ct_gregg"}, expect=201)
    _post(client, console, f"/patients/{PID}/tests",
          {"kind": "custom", "label": "Decline squat pain", "value": 4, "unit": "/10"}, expect=201)
    tests = {t["label"]: t for t in _chart(client, console)["tests"]["tests"]}
    knee = tests["Isometric knee extension"]
    assert [d["left_of_right_pct"] for d in knee["days"]] == [80, 91]
    assert knee["unit"] == "N" and knee["sided"] is True
    assert tests["Decline squat pain"]["unit"] == "/10"
    # No word on what a number means: only the numbers.
    assert not any(k in str(knee).lower() for k in ("cleared", "ready", "deficit", "passed"))
    for bad in ({"kind": "nope", "value": 1}, {"kind": "custom", "value": 1},
                {"kind": "plank_hold", "value": -1},
                {"kind": "plank_hold", "value": 60,
                 "tested_on": (TODAY + timedelta(days=1)).isoformat()}):
        assert client.post(f"/api/pt/patients/{PID}/tests", headers=console["hirt"],
                           json=bad).status_code == 422, bad

    _post(client, console, f"/patients/{PID}/tests/ask-hold", {"kind": "plank_hold"})
    task = _open_task(client, phone, asks.HOLD)
    assert task["title"] == "Time your front plank hold"
    _answer(client, phone, task, {"seconds": 75})
    hold = next(t for t in _chart(client, console)["tests"]["tests"] if t["kind"] == "plank_hold")
    assert hold["hold"] is True and hold["latest"] == 75 and hold["unit"] == "s"
    assert hold["days"][0]["results"][0]["source"] == "patient"
    assert client.post(f"/api/pt/patients/{PID}/tests/ask-hold", headers=console["hirt"],
                       json={"kind": "countermovement_jump"}).status_code == 422


def test_an_outcome_measure_is_scored_on_a_rhythm_against_a_sourced_threshold(
        client, console, phone, db, lifter):
    catalog = {i["key"]: i for i in client.get("/api/pt/catalog", headers=console["hirt"])
               .json()["instruments"]}
    assert (catalog["visa_p"]["threshold"], catalog["visa_p"]["mode"]) == (13, "entered")
    assert "Hernandez-Sanchez" in catalog["visa_p"]["source"]
    assert catalog["quickdash"]["threshold"] is None  # no number we could not source

    two_weeks = (TODAY - timedelta(days=14)).isoformat()
    _post(client, console, f"/patients/{PID}/outcomes/visa_p/scores",
          {"total": 52, "on": two_weeks, "by": "ct_gregg"}, expect=201)
    _post(client, console, f"/patients/{PID}/outcomes/visa_p/schedule",
          {"every_days": 14, "start": TODAY.isoformat()}, method="put")
    _post(client, console, f"/patients/{PID}/outcomes/visa_p/ask", {})
    task = _open_task(client, phone, asks.OUTCOME)
    assert task["questions"][0]["kind"] == "number" and task["questions"][0]["max"] == 100
    _answer(client, phone, task, {"total": 61})
    visa = next(m for m in _chart(client, console)["outcomes"]["measures"] if m["key"] == "visa_p")
    assert [s["total"] for s in visa["scores"]] == [52, 61]
    assert visa["read"]["change"] == {"delta": 9.0, "direction": "better", "past_threshold": False}
    assert visa["schedule"]["next_due"] == (TODAY + timedelta(days=14)).isoformat()

    # The clinic's own threshold replaces the published one, and says so.
    client.patch("/api/pt/settings", headers=console["hirt"],
                 json={"outcome_thresholds": {"visa_p": 8}})
    visa = next(m for m in _chart(client, console)["outcomes"]["measures"] if m["key"] == "visa_p")
    assert visa["threshold"] == 8 and visa["threshold_is_clinic"] is True
    assert visa["read"]["change"]["past_threshold"] is True
    for path, body in ((f"/patients/{PID}/outcomes/visa_p/scores", {"total": 140}),
                       (f"/patients/{PID}/outcomes/psfs/scores", {"total": 5}),
                       (f"/patients/{PID}/outcomes/nope/scores", {"total": 5})):
        assert client.post(f"/api/pt{path}", headers=console["hirt"], json=body).status_code == 422


# --- the trainer's page -------------------------------------------------------------------


def test_a_trainers_page_exists_only_once_the_person_says_yes(client, console, phone, db, lifter):
    wall = _exercise(client, console, "Wall Sits")
    # 11.34 kg and 15.88 kg are 25 lb and 35 lb: the clinic reads pounds.
    _assign(client, console, wall["id"], [TODAY], load_kg=11.34, load_max_kg=15.88, rpe_max=7)
    saved = _post(client, console, f"/patients/{PID}/handoff", {
        "trainer_name": "Mara Ellis", "report_back": "Any pain past 4/10 the next morning.",
        "limits": ["No jumping or bounding", "Squat to a box, not below parallel"],
        "by": "ct_gregg"}, method="put")["handoff"]
    assert saved["status"] == "draft" and saved["url"] is None

    asked = _post(client, console, f"/patients/{PID}/handoff/request", {})["handoff"]
    assert asked["status"] == "awaiting" and asked["url"] is None
    assert db.scalar(select(Handoff.token).where(Handoff.patient_id == PID)) is None
    mine = client.get("/api/mobile/pt", headers=phone).json()
    assert mine["handoff"] == {"trainer_name": "Mara Ellis", "status": "awaiting"}
    task = _open_task(client, phone, asks.HANDOFF)
    assert "Mara Ellis" in task["questions"][0]["prompt"]
    assert "Nothing else from your record" in task["questions"][0]["prompt"]
    _answer(client, phone, task, {"share": "yes"})

    live = _chart(client, console)["handoff"]
    assert live["status"] == "active" and "/h/" in live["url"]
    token = live["url"].rsplit("/", 1)[1]
    page = client.get(f"/api/handoff/{token}")  # no credential: the link is the permission
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["person"] == "Noa L." and body["clinic"] == "H.I.R.T. Physical Therapy"
    assert body["from"] == "Dr. Ashley Gregg" and body["trainer_name"] == "Mara Ellis"
    assert body["limits"] == ["No jumping or bounding", "Squat to a box, not below parallel"]
    assert [(w["title"], w["ceiling"]) for w in body["week"]] == [
        ("Wall Sits", "Stop at RPE 7 · do not exceed 35 lb")]
    # Limits and doses, nothing from the record.
    assert set(body) == {"person", "clinic", "from", "trainer_name", "limits", "report_back",
                         "phase", "week", "week_start", "updated_at", "authorised_on"}
    assert _chart(client, console)["handoff"]["open_count"] == 1

    # The words can change under the same link; the trainer cannot.
    _post(client, console, f"/patients/{PID}/handoff", {
        "trainer_name": "Mara Ellis", "limits": ["No jumping"], "report_back": ""}, method="put")
    assert client.get(f"/api/handoff/{token}").json()["limits"] == ["No jumping"]
    resp = client.put(f"/api/pt/patients/{PID}/handoff", headers=console["hirt"],
                      json={"trainer_name": "Someone Else", "limits": ["x"]})
    assert resp.status_code == 422 and "named trainer" in resp.json()["detail"]

    _post(client, console, f"/patients/{PID}/handoff/revoke")
    assert client.get(f"/api/handoff/{token}").status_code == 404
    assert client.get("/api/handoff/nope").status_code == 404
    assert _chart(client, console)["handoff"]["status"] == "revoked"


def test_a_person_who_says_no_shares_nothing(client, console, phone, db, lifter):
    _post(client, console, f"/patients/{PID}/handoff",
          {"trainer_name": "Mara Ellis", "limits": ["No jumping"]}, method="put")
    _post(client, console, f"/patients/{PID}/handoff/request", {})
    _answer(client, phone, _open_task(client, phone, asks.HANDOFF), {"share": "no"})
    handoff = _chart(client, console)["handoff"]
    assert handoff["status"] == "declined" and handoff["url"] is None
    assert db.scalar(select(Handoff.token).where(Handoff.patient_id == PID)) is None
    assert client.get("/api/mobile/pt", headers=phone).json()["handoff"] is None


# --- the calendar ----------------------------------------------------------------------------


def test_visits_and_rest_days_sit_on_the_calendar_and_on_the_phone(client, console, phone, db,
                                                                   lifter):
    friday = TODAY + timedelta(days=3)
    visit = _post(client, console, f"/patients/{PID}/visits",
                  {"on": friday.isoformat(), "at": "14:30", "kind": "test_day",
                   "note": "Bring lifting shoes."}, expect=201)
    assert visit["visit"]["kind_label"] == "Test day" and visit["visits"]["days_to_next"] == 3
    mark = client.post(f"/api/pt/patients/{PID}/marks", headers=console["hirt"],
                       json={"day": TODAY.isoformat(), "note": "Deload."})
    assert mark.status_code == 201, mark.text
    grid = client.get("/api/hep/schedule", headers=console["hirt"],
                      params={"start": TODAY.isoformat(), "days": 7}).json()
    assert [(v["patient_id"], v["on"], v["at"]) for v in grid["visits"]] == [
        (PID, friday.isoformat(), "14:30")]
    assert [(m["patient_id"], m["day"], m["note"]) for m in grid["marks"]] == [
        (PID, TODAY.isoformat(), "Deload.")]
    month = client.get("/api/hep/calendar", headers=console["hirt"]).json()
    assert "visits" in month and "marks" in month

    feed = client.get("/api/mobile/exercises", headers=phone).json()
    assert feed["rest_day"] == {"note": "Deload."}
    assert feed["next_visit"] == {"on": friday.isoformat(), "at": "14:30", "kind": "test_day",
                                  "kind_label": "Test day"}
    program = client.get("/api/mobile/exercises/program", headers=phone,
                         params={"start": TODAY.isoformat(), "days": 7}).json()
    assert program["rest_days"] == [{"day": TODAY.isoformat(), "note": "Deload."}]
    assert program["visits"][0]["on"] == friday.isoformat() and "note" not in program["visits"][0]
    mine = client.get("/api/mobile/pt", headers=phone).json()
    assert mine["rest_day"] == {"note": "Deload."} and mine["next_visit"]["at"] == "14:30"

    assert client.delete(f"/api/pt/visits/{visit['visit']['id']}",
                         headers=console["demo"]).status_code == 404
    assert client.delete(f"/api/pt/marks/{mark.json()['mark']['id']}",
                         headers=console["hirt"]).status_code == 200
    assert client.get("/api/mobile/exercises", headers=phone).json()["rest_day"] is None
    resp = client.post(f"/api/pt/patients/{PID}/visits", headers=console["hirt"],
                       json={"on": friday.isoformat(), "at": "2pm", "kind": "visit"})
    assert resp.status_code == 422 and "14:30" in resp.json()["detail"]


def test_a_dose_carries_its_ceilings_and_a_day_past_one_is_over(client, console, lifter, db):
    steps = _exercise(client, console, "Step-Ups")
    made = _assign(client, console, steps["id"], [TODAY], sets=3, reps=8, load_kg=11.34,
                   rpe_target=6, load_max_kg=15.88, rpe_max=7)["assignments"][0]
    assert (made["load_max_kg"], made["rpe_max"]) == (15.88, 7)
    assert made["ceiling"] == "Stop at RPE 7 · do not exceed 35 lb"
    for body in ({"load_kg": 20, "load_max_kg": 15}, {"rpe_target": 7, "rpe_max": 5}):
        resp = client.post("/api/hep/schedule", headers=console["hirt"], json={
            "patient_id": PID, "exercise_id": steps["id"],
            "dates": [(TODAY + timedelta(days=1)).isoformat()], **body})
        assert resp.status_code == 422 and "cannot be under" in resp.json()["detail"], body
    patched = client.patch(f"/api/hep/schedule/{made['id']}", headers=console["hirt"],
                           json={"rpe_max": 5})
    assert patched.status_code == 422

    # At the target and inside the ceiling: as prescribed. One point past
    # the effort to stop at: over, whatever the margin on the target is.
    done = client.post(f"/api/hep/schedule/{made['id']}/complete", headers=console["hirt"],
                       json={"pain_after": 2, "effort": 8, "load_done_kg": 11.34,
                             "sets_done": 3, "reps_done": 8}).json()
    completion = done["completion"]
    assert completion["past_ceiling"] is True and completion["over"] is True
    assert "past the ceiling: effort 8, told to stop at 7" in completion["line"]
    assert completion["review_reason"] == "over"


def test_one_assign_reaches_several_people_and_the_count_is_asked_about(client, console, lifter,
                                                                        db):
    client.patch("/api/pt/settings", headers=console["hirt"], json={"exercise_guard": 2})
    names = ["Step-Ups", "Wall Sits", "Mini Squats"]
    first, second, third = (_exercise(client, console, n) for n in names)
    _assign(client, console, first["id"], [TODAY])
    _assign(client, console, second["id"], [TODAY])
    check = client.post("/api/hep/schedule/check", headers=console["hirt"],
                        json={"patient_ids": [PID], "dates": [TODAY.isoformat()]}).json()
    assert check == {"limit": 2, "guard": [{"day": TODAY.isoformat(), "would_be": 3, "limit": 2,
                                           "patient_id": PID, "patient_name": "Noa Lindqvist"}]}
    refused = _assign(client, console, third["id"], [TODAY], expect=409)
    assert "That would put 3 exercises on Noa Lindqvist" in refused["detail"]
    assert db.scalar(select(func.count(ExerciseAssignment.id))
                     .where(ExerciseAssignment.patient_id == PID)) == 2
    _assign(client, console, third["id"], [TODAY], allow_over_guard=True)

    # Several people in one go: each written or refused on their own.
    tomorrow = TODAY + timedelta(days=1)
    _assign(client, console, first["id"], [tomorrow])
    before = db.scalar(select(func.count(ExerciseAssignment.id))
                       .where(ExerciseAssignment.patient_id == "hirt-june"))
    many = client.post("/api/hep/schedule", headers=console["hirt"], json={
        "patient_id": PID, "patient_ids": [PID, "hirt-june"], "exercise_id": first["id"],
        "dates": [tomorrow.isoformat()], "sets": 2, "reps": 10, "allow_over_guard": True})
    assert many.status_code == 201, many.text
    by_person = {e["patient_id"]: e for e in many.json()["by_person"]}
    assert by_person[PID]["assigned"] == 0 and "already on" in by_person[PID]["error"]
    assert by_person["hirt-june"]["assigned"] == 1 and by_person["hirt-june"]["error"] is None
    assert (many.json()["people_written"], many.json()["people_refused"]) == (1, 1)
    added = db.scalars(select(ExerciseAssignment).where(
        ExerciseAssignment.patient_id == "hirt-june", ExerciseAssignment.exercise_id == first["id"],
        ExerciseAssignment.scheduled_for == tomorrow)).all()
    assert len(added) == 1 and added[0].sets == 2
    for row in added:  # the seeded lifter is put back as she was
        db.delete(row)
    db.commit()
    assert db.scalar(select(func.count(ExerciseAssignment.id))
                     .where(ExerciseAssignment.patient_id == "hirt-june")) == before


def test_comments_on_a_clip_reach_the_person_with_the_review(client, console, lifter, db):
    steps = _exercise(client, console, "Step-Ups")
    week_ago = TODAY - timedelta(days=7)
    older = _assign(client, console, steps["id"], [week_ago])["assignments"][0]
    newer = _assign(client, console, steps["id"], [TODAY])["assignments"][0]
    noon = datetime.combine(TODAY, datetime.min.time()) + timedelta(hours=12)
    clips = []
    for n, made in enumerate((older, newer)):
        clip = Attachment(patient_id=PID, content_type="video/mp4", storage_key=f"t/between-{n}",
                          filename=f"clip-{n}.mp4", confirmed_at=noon)
        db.add(clip)
        db.flush()
        row = db.get(ExerciseAssignment, made["id"])
        row.status, row.completed_at, row.video_attachment_id = "done", noon, clip.id
        row.completion_source = "app"
        clips.append(clip)
    voice = Attachment(patient_id=PID, content_type="audio/mp4", storage_key="t/between-voice",
                       filename="note.m4a", confirmed_at=noon, uploaded_by="care_team")
    db.add(voice)
    db.commit()

    path = f"/api/pt/assignments/{newer['id']}"
    detail = client.get(f"{path}/clip", headers=console["hirt"]).json()
    assert detail["comments"] == [] and [e["day"] for e in detail["earlier"]] == [week_ago.isoformat()]
    for body in ({"by": "ct_gregg", "text": "Good depth."},
                 {"by": "ct_gregg", "at_ms": 12_000, "text": "Knee drifting in here."}):
        assert client.post(f"{path}/comments", headers=console["hirt"], json=body).status_code == 201
    spoken = client.post(f"{path}/comments", headers=console["hirt"],
                         json={"by": "ct_gregg", "at_ms": 4000, "voice_attachment_id": voice.id})
    assert spoken.status_code == 201, spoken.text
    comments = spoken.json()["comments"]
    assert [(c["at_ms"], c["text"]) for c in comments] == [
        (4000, ""), (12_000, "Knee drifting in here."), (None, "Good depth.")]
    assert comments[0]["voice"]["content_type"] == "audio/mp4"
    # The voice note is on the thread at once, under her name, as the audio.
    db.expire_all()
    line = db.get(Message, db.get(Attachment, voice.id).message_id)
    assert line.sender_id == "ct_gregg" and line.text.startswith("A voice note about your ")
    assert steps["title"] in line.text and "(at 0:04)" in line.text
    for bad in ({"by": "ct_gregg"}, {"by": "nobody", "text": "x"},
                {"by": "ct_gregg", "voice_attachment_id": clips[0].id}):
        assert client.post(f"{path}/comments", headers=console["hirt"], json=bad).status_code == 422

    # The typed comments travel with the review, as its last lines.
    reviewed = client.post(f"/api/hep/schedule/{newer['id']}/review", headers=console["hirt"],
                           json={"note": "Much better.", "actor": "ct_gregg"})
    assert reviewed.status_code == 200, reviewed.text
    note = reviewed.json()["completion"]["review"]["note"]
    assert note == "Much better.\n0:12 Knee drifting in here.\nGood depth."
    assert client.get(f"/api/pt/assignments/{newer['id']}/clip",
                      headers=console["demo"]).status_code == 404


# --- questions and the clinic's fixed words -----------------------------------------------------


def test_a_question_is_sorted_by_rule_and_moved_by_a_clinician(client, console, phone, db, lifter):
    words = pt_settings.DEFAULTS["triage_words"]
    assert triage.classify("Can I swap bird dog for dead bug this week?", words) == "weekly"
    assert triage.classify("Is it normal that my knee is swollen after stairs?", words) == "today"
    assert triage.classify("My knee swelled up after training", words) == "today"
    assert triage.classify("Thanks, see you Thursday", words) is None

    for text in ("Can I swap bird dog for dead bug this week?",
                 "Should I train tonight if it still hurts?", "Thanks!"):
        assert client.post("/api/mobile/messages", headers=phone,
                           json={"text": text}).status_code == 200
    lists = client.get("/api/pt/questions", headers=console["hirt"]).json()
    mine = lambda rows: [r["text"] for r in rows if r["patient_id"] == PID]  # noqa: E731
    assert mine(lists["today"]) == ["Should I train tonight if it still hurts?"]
    assert mine(lists["weekly"]) == ["Can I swap bird dog for dead bug this week?"]
    weekly = next(r for r in lists["weekly"] if r["patient_id"] == PID)
    assert weekly["sorted_by"] == "rule"

    moved = client.post(f"/api/pt/questions/{weekly['id']}", headers=console["hirt"],
                        json={"triage": "today", "by": "ct_gregg"})
    assert moved.status_code == 200 and moved.json()["triage"] == "today"
    lists = client.get("/api/pt/questions", headers=console["hirt"]).json()
    assert len(mine(lists["today"])) == 2 and mine(lists["weekly"]) == []
    assert next(r for r in lists["today"] if r["id"] == weekly["id"])["sorted_by_name"] \
        == "Dr. Ashley Gregg"
    client.post(f"/api/pt/questions/{weekly['id']}", headers=console["hirt"], json={"done": True})
    lists = client.get("/api/pt/questions", headers=console["hirt"]).json()
    assert len(mine(lists["today"])) == 1 and weekly["id"] in [r["id"] for r in lists["done"]]
    # Sorting never writes to the person: three lines in, three lines on the thread.
    assert db.scalar(select(func.count(Message.id)).where(Message.patient_id == PID)) == 3
    assert client.get("/api/pt/questions", headers=console["demo"]).json()["today"] == [] or all(
        r["patient_id"] != PID for r in client.get("/api/pt/questions",
                                                   headers=console["demo"]).json()["today"])


def test_a_red_flag_is_answered_in_the_clinics_words_and_never_by_the_assistant(
        client, console, phone, db, lifter, monkeypatch):
    entries = client.get("/api/pt/red-flags", headers=console["hirt"]).json()
    assert {e["key"] for e in entries["entries"]} >= {"saddle_numbness", "calf_swelling"}
    assert all(e["status"] == "draft" and e["sends"] == triage.STANDING_REPLY
               for e in entries["entries"])
    calf = next(e for e in entries["entries"] if e["key"] == "calf_swelling")

    # A draft listens and alerts; what goes back is the one standing line.
    sent = client.post("/api/mobile/messages", headers=phone,
                       json={"text": "My calf is swollen and warm since last night"})
    assert sent.status_code == 200
    thread = db.scalars(select(Message).where(Message.patient_id == PID).order_by(Message.id)).all()
    assert thread[-2].red_flag == "calf_swelling" and thread[-2].triage == "today"
    assert thread[-1].text == triage.STANDING_REPLY and thread[-1].sender == "copilot"
    notice = db.scalars(select(Notification).where(Notification.patient_id == PID)
                        .order_by(Notification.id.desc())).first()
    assert notice.kind == "red_flag" and "calf" in notice.title.lower()
    stuck = client.post(f"/api/pt/questions/{thread[-2].id}", headers=console["hirt"],
                        json={"triage": "weekly"})
    assert stuck.status_code == 422  # a red flag does not wait for the weekly block

    # Her words cannot be approved with the blank still in them, nor by nobody.
    path = f"/api/pt/red-flags/{calf['id']}"
    assert client.post(f"{path}/approve", headers=console["hirt"],
                       json={"by": "ct_harris"}).status_code == 422
    words = "Call the clinic now on 281-555-0100. If we do not answer, go to the nearest ER."
    client.patch(path, headers=console["hirt"], json={"text": words, "by": "ct_harris"})
    assert client.post(f"{path}/approve", headers=console["hirt"],
                       json={"by": "nobody"}).status_code == 422
    approved = client.post(f"{path}/approve", headers=console["hirt"], json={"by": "ct_harris"})
    entry = next(e for e in approved.json()["entries"] if e["id"] == calf["id"])
    assert entry["status"] == "approved" and entry["sends"] == words and entry["sends_own_words"]

    # By text: her words, word for word, under her name; the assistant is never asked.
    from app.agent import copilot
    from app.notifications import sendblue
    from app.tasks import service as tasks

    lifter.phone = "+12815550199"
    db.commit()
    monkeypatch.setattr(copilot, "respond",
                        lambda *a, **kw: pytest.fail("a red flag must not reach the assistant"))
    texts_out: list[str] = []
    monkeypatch.setattr(sendblue, "send_sms", lambda phone, text, **kw: (
        texts_out.append(text) or sendblue.CheckinSendResult(sent=True, detail="ok")))
    out = tasks.handle_inbound_sms(db, "+12815550199", "my calf is hot and swollen")
    assert out.kind == "red_flag" and texts_out == [words]
    reply = db.scalars(select(Message).where(Message.patient_id == PID)
                       .order_by(Message.id.desc())).first()
    assert (reply.sender, reply.sender_id, reply.authored_by) == ("care_team", "ct_harris", "care_team")

    # Editing the words takes the approval off: what was approved is not what would go.
    edited = client.patch(path, headers=console["hirt"], json={"text": words + " Thank you."})
    assert next(e for e in edited.json()["entries"] if e["id"] == calf["id"])["status"] == "draft"
    assert client.patch(path, headers=console["hirt"], json={"phrases": ["ab"]}).status_code == 422


# --- the morning run ---------------------------------------------------------------------------


def test_the_morning_run_asks_what_the_settings_say_and_asks_once(client, console, db, lifter):
    from app.pt import service as between

    steps = _exercise(client, console, "Step-Ups")
    made = _assign(client, console, steps["id"], [YESTERDAY], load_kg=10)["assignments"][0]
    client.post(f"/api/hep/schedule/{made['id']}/complete", json={"pain_after": 1},
                headers=console["hirt"])
    friday = TODAY + timedelta(days=(4 - TODAY.weekday()) % 7)
    asked = lambda model: db.scalar(  # noqa: E731
        select(func.count(model.id)).where(model.patient_id == PID))

    assert between.run_daily(db, TODAY)["morning"] == 0  # the clinic has not turned it on
    client.patch("/api/pt/settings", headers=console["hirt"],
                 json={"morning_check": {"on": True}, "week_checkin": {"on": True}})
    between.set_outcome_schedule(db, lifter, "nprs", every_days=7, start=TODAY, by="ct_gregg")
    counts = between.run_daily(db, TODAY)
    assert counts["morning"] >= 1 and counts["outcome"] >= 1 and asked(MorningCheck) == 1
    again = between.run_daily(db, TODAY)
    assert asked(MorningCheck) == 1 and again["outcome"] == 0
    # The week's word goes on a Friday, once.
    if friday != TODAY:
        assert asked(WeekCheckin) == 0
    between.run_daily(db, friday)
    between.run_daily(db, friday)
    assert asked(WeekCheckin) == 1
    # Someone who turned it off for herself is left alone.
    db.execute(delete(MorningCheck).where(MorningCheck.patient_id == PID))
    db.execute(delete(AdherenceTask).where(AdherenceTask.patient_id == PID))
    db.commit()
    pt_settings.patient_update(db, PID, "hirt", {"morning_check": {"on": False}}, by="ct_gregg")
    between.run_daily(db, TODAY)
    assert asked(MorningCheck) == 0
