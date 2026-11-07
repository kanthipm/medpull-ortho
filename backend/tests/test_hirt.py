"""The HIRT demo: five lifters followed by text check-in alone.

Three things are pinned here. The reported-signals rules in engine/risk.py,
one test per rule on a hand-built ``ReportedSignals``. The seeded roster's
tiers on a fresh fill — the morning the walkthrough opens on. And the paths
the check-in travels: the question set a lifter is asked, the observations
their answers write, the texted conversation, the tokenized web form, the
drafted nudges and the console's progress line.

Tests that complete a check-in do it on a throwaway chart, never on the five:
the seeded database is session-scoped and the tiers below are asserted on it.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select

from app.engine.risk import score_reported, score_risk
from app.engine.types import (
    AdherenceResult,
    CompositeResult,
    ConfidenceResult,
    ReportedSignals,
    TrajectoryResult,
)
from app.models.checkin import Checkin, CheckinInvite, CheckinMessage
from app.models.enums import ConfidenceLevel, MetricType, ProcedureType, RiskLevel, TrajectoryState
from app.models.notification import Notification
from app.models.observation import Observation
from app.models.patient import Patient
from app.seed import hirt
from app.tasks import service as tasks
from tests.test_mobile import _forget_patient

# --- the rules ------------------------------------------------------------------------


def _followed(**kw) -> ReportedSignals:
    base = dict(checkins_7d=6, checkins_14d=13, days_since_checkin=1)
    base.update(kw)
    return ReportedSignals(**base)


def _codes(result) -> list[str]:
    return [r.code for r in result.reasons]


def test_load_spike_is_high_and_the_band_is_medium():
    spike = score_reported(_followed(load_ratio=1.6), 14)
    assert spike.level == RiskLevel.HIGH
    assert _codes(spike) == ["LOAD_SPIKE"]
    assert "too much, too soon" in spike.reasons[0].text
    assert spike.reasons[0].metric_type == str(MetricType.SESSION_LOAD)

    band = score_reported(_followed(load_ratio=1.35), 14)
    assert band.level == RiskLevel.MEDIUM
    assert _codes(band) == ["LOAD_SPIKE"]
    assert "above the band" in band.reasons[0].text

    assert score_reported(_followed(load_ratio=1.29), 14).level == RiskLevel.LOW


def test_a_provisional_spike_is_an_early_read_not_a_flag():
    early = score_reported(_followed(load_ratio=1.8, load_provisional=True), 6)
    assert early.level == RiskLevel.MEDIUM
    assert early.reasons[0].text.startswith("Early read")


def test_pain_rising_and_new_pain_are_medium_and_high_with_load():
    pain = score_reported(_followed(pain_latest=6, pain_prior_mean=3.9, pain_delta=2.1), 14)
    assert pain.level == RiskLevel.MEDIUM
    assert _codes(pain) == ["PAIN_RISING"]
    assert pain.reasons[0].text == "Pain up 2 points on the week before (4 → 6)"

    assert score_reported(_followed(pain_delta=1.9), 14).level == RiskLevel.LOW

    new = score_reported(_followed(new_pain=True, new_pain_day=13), 14)
    assert new.level == RiskLevel.MEDIUM
    assert _codes(new) == ["NEW_PAIN"]
    assert new.reasons[0].text == "New pain since the last visit, reported yesterday"

    together = score_reported(_followed(load_ratio=1.35, new_pain=True, new_pain_day=14), 14)
    assert together.level == RiskLevel.HIGH
    assert set(_codes(together)) == {"LOAD_SPIKE", "NEW_PAIN"}


def test_program_slipping_is_medium():
    slipping = score_reported(_followed(program_rate_3d=0.17, program_answers_3d=3), 14)
    assert slipping.level == RiskLevel.MEDIUM
    assert _codes(slipping) == ["PROGRAM_SLIPPING"]
    assert slipping.reasons[0].text == "Program slipping — 17% done over the last 3 days"
    assert score_reported(_followed(program_rate_3d=0.5), 14).level == RiskLevel.LOW


def test_going_quiet_is_medium_at_three_days_and_high_at_five():
    quiet = score_reported(_followed(checkins_7d=4, days_since_checkin=3), 14)
    assert quiet.level == RiskLevel.MEDIUM
    assert _codes(quiet) == ["WENT_QUIET"]
    assert quiet.reasons[0].text == "Went quiet — no check-in for 3 days"

    long = score_reported(_followed(checkins_7d=2, days_since_checkin=5), 14)
    assert long.level == RiskLevel.HIGH
    assert long.reasons[0].severity == 3

    assert score_reported(_followed(days_since_checkin=2), 14).level == RiskLevel.LOW


def test_nothing_off_is_low_in_the_clinics_words():
    steady = score_reported(
        _followed(load_ratio=0.95, pain_delta=-1.2, program_rate_3d=1.0), 14
    )
    assert steady.level == RiskLevel.LOW
    assert _codes(steady) == ["ON_TRACK"]
    assert steady.reasons[0].text == "Checking in daily — load steady, pain easing, program done"


def test_reasons_sort_by_severity_for_the_worklist_line():
    both = score_reported(_followed(load_ratio=1.6, pain_delta=2.1, pain_prior_mean=4,
                                    pain_latest=6, program_rate_3d=0.0), 14)
    assert _codes(both) == ["LOAD_SPIKE", "PAIN_RISING", "PROGRAM_SLIPPING"]
    assert both.level == RiskLevel.HIGH


def _low_confidence(panel: list[str] | None = None) -> ConfidenceResult:
    return ConfidenceResult(score=0.0, level=ConfidenceLevel.LOW, days_with_data=0,
                            window_days=7, panel=panel or [])


def _score(deviations, confidence, reported):
    return score_risk(
        14, deviations, TrajectoryResult(TrajectoryState.UNKNOWN, None, None),
        CompositeResult(0.0, "normal"), confidence, AdherenceResult(0.0, 0, 0, 0),
        None, None, reported=reported,
    )


def test_the_gate_scores_from_check_ins_only_without_any_device_series():
    reported = _followed(load_ratio=1.6)
    assert _score({}, _low_confidence(), reported).level == RiskLevel.HIGH
    # A device that has reported, however thinly, keeps the device path.
    stub = SimpleNamespace(flagged=False, drifting=False, last_day=10, reference="baseline")
    device = _score({"steps": stub}, _low_confidence(panel=["steps"]), reported)
    assert device.level == RiskLevel.MISSING_DATA
    assert _codes(device) == ["LOW_COVERAGE"]
    # Nobody answering: three check-ins in two weeks is the floor.
    blank = _score({}, _low_confidence(), ReportedSignals(checkins_14d=2, days_since_checkin=9))
    assert blank.level == RiskLevel.MISSING_DATA
    assert _score({}, _low_confidence(), None).level == RiskLevel.MISSING_DATA


# --- the roster on a fresh fill ---------------------------------------------------------------


def test_the_five_land_in_the_pitched_tiers(db):
    from app.engine.pipeline import latest_assessment

    for pid, tier in hirt.EXPECTED_TIERS.items():
        assessment = latest_assessment(db, pid)
        assert assessment is not None, pid
        assert assessment.risk_level == tier, (pid, assessment.risk_level, assessment.reasons)

    cole = latest_assessment(db, "hirt-cole")
    assert [r["code"] for r in cole.reasons] == ["LOAD_SPIKE", "PAIN_RISING"]
    assert cole.reasons[0]["text"].startswith("Training load 1.6× its recent average")
    rafael = latest_assessment(db, "hirt-rafael")
    assert [r["code"] for r in rafael.reasons] == ["WENT_QUIET"]
    devon = latest_assessment(db, "hirt-devon")
    assert [r["code"] for r in devon.reasons] == ["PROGRAM_SLIPPING"]
    tessa = latest_assessment(db, "hirt-tessa")
    assert tessa.reasons[0]["text"] == "Checking in daily — load steady, program done"
    # The device-scored roster is untouched: reyes still leads the worklist.
    assert latest_assessment(db, "reyes").risk_score > cole.risk_score


def test_m1_runs_off_reported_training_load_and_agrees_with_the_tier(db):
    from app.engine.pipeline import latest_assessment

    bundle = latest_assessment(db, "hirt-cole").analytics
    m1 = next(m for m in bundle["care_metrics"]["metrics"] if m["id"] == "M1")
    assert m1["status"] == "flag"
    assert m1["inputs"] == [str(MetricType.SESSION_LOAD)]
    assert "training load" in m1["finding"] and m1["chart"]["y_label"] == "training load"
    assert m1["next_step"].startswith("Hold the training load")
    assert round(bundle["reported"]["load_ratio"], 2) == round(m1["value_num"], 2)
    steady = next(m for m in latest_assessment(db, "hirt-tessa").analytics["care_metrics"]["metrics"]
                  if m["id"] == "M1")
    assert steady["status"] == "ok"


def test_no_wearable_is_not_a_coverage_problem_for_a_lifter(db):
    """A chart followed by text has no device to nudge: data confidence reads
    "followed by check-in" instead of "cannot see this patient", and the
    attention strip and next steps carry no device-sync step."""
    from app.engine.pipeline import latest_assessment
    from app.plan.next_steps import plan_next_steps

    assessment = latest_assessment(db, "hirt-tessa")
    care = assessment.analytics["care_metrics"]
    m16 = next(m for m in care["metrics"] if m["id"] == "M16")
    assert m16["status"] == "ok" and m16["status_text"] == "Followed by check-in"
    assert "M16" not in care["attention"]
    steps = plan_next_steps(db, db.get(Patient, "hirt-tessa"), assessment)
    assert [s["key"] for s in steps if s["state"]["status"] == "open"] == ["ack_on_track"]
    # A blank chart with nothing reported keeps the honest flag.
    medha = next(m for m in latest_assessment(db, "medha").analytics["care_metrics"]["metrics"]
                 if m["id"] == "M16")
    assert medha["status"] == "flag"


def test_the_hirt_org_is_seeded_with_both_therapists(db):
    from app.models import CareTeamMember, Hospital

    hospital = db.get(Hospital, "hirt")
    assert hospital.name == "H.I.R.T. Physical Therapy" and hospital.system == "Rise Gym"
    assert hospital.city == "Tomball" and hospital.timezone == "America/Chicago"
    assert db.get(CareTeamMember, "ct_harris").role == "pt"
    assert db.get(CareTeamMember, "ct_gregg").role == "pt"
    cole = db.get(Patient, "hirt-cole")
    assert cole.procedure_type == "NONE" and cole.hospital_id == "hirt"
    assert cole.care_pathway == cole.procedure_display == "Patellar tendinopathy · progressive loading"
    assert cole.assigned_provider_id == "ct_gregg" and cole.surgeon_id == "ct_harris"
    assert 24 <= cole.age <= 48


def test_worklist_carries_the_five_with_their_tiers(client):
    body = client.get("/api/worklist").json()
    rows = {p["id"]: p for p in body["patients"]}
    for pid, tier in hirt.EXPECTED_TIERS.items():
        assert rows[pid]["priority"] == tier, pid
        assert rows[pid]["mode"] == "general"
        assert rows[pid]["procedure_display"] == hirt.PATHWAYS[pid]
    assert rows["hirt-cole"]["reason"].startswith("Training load 1.6× its recent average")
    assert rows["hirt-rafael"]["reason"].startswith("Went quiet")
    assert rows["hirt-cole"]["next_step"]["key"] == "msg_hold_load"
    # The briefing names the lifter as one to start with.
    assert "Cole Whitaker" in body["briefing"]["text"]


def test_the_progress_line_reads_load_pain_and_program(client):
    cole = client.get("/api/patients/hirt-cole").json()["progress"]
    assert cole["load_vs_prior_pct"] > 50 and round(cole["load_ratio"], 1) == 1.6
    assert cole["pain"]["latest"] == 6 and cole["pain"]["delta"] >= 2
    assert cole["program"] == {"done": 7.0, "of": 7, "rate_3d": 1.0}
    tessa = client.get("/api/patients/hirt-tessa").json()["progress"]
    assert -20 <= tessa["load_vs_prior_pct"] <= 20
    assert tessa["pain"]["delta"] < 0 and tessa["program"]["done"] == 7.0
    devon = client.get("/api/patients/hirt-devon").json()["progress"]
    assert devon["program"]["rate_3d"] < 0.5 and devon["program"]["done"] == 3.5
    # Everyone else keeps their row.
    assert client.get("/api/patients/robert").json()["progress"] is None


def test_the_summary_and_actions_speak_the_reported_reasons(client):
    body = client.get("/api/patients/hirt-cole").json()
    assert "too much, too soon" in body["summary"]["text"]
    titles = [a["title"] for a in body["actions"]]
    assert "Hold the load at last week's numbers" in titles
    assert "Ask about the pain" in titles


# --- the nudges ----------------------------------------------------------------------


def _assessment(codes, level="high"):
    reasons = [{"code": c, "text": f"{c.replace('_', ' ').capitalize()}", "metric_type": None,
                "severity": 2} for c in codes]
    return SimpleNamespace(reasons=reasons, risk_level=level,
                           analytics={"postop_day": 14, "care_metrics": {"metrics": []}})


def test_load_spike_drafts_the_hold_the_load_note(db):
    from app.plan.library import ensure_library
    from app.plan.messages import ensure_message_library
    from app.plan.next_steps import plan_next_steps

    ensure_library(db)
    ensure_message_library(db)
    cole = db.get(Patient, "hirt-cole")
    steps = plan_next_steps(db, cole, _assessment(["LOAD_SPIKE", "PAIN_RISING"]),
                            now=datetime.now(), last_checkin_at=datetime.now() - timedelta(days=1))
    by_key = {s["key"]: s for s in steps}
    hold = by_key["msg_hold_load"]
    assert hold["action"]["type"] == "message" and hold["urgency"] == "today"
    assert hold["action"]["prefill"] == (
        "Hi Cole — Dr. Harris's team here. Your training load jumped this week — hold at last "
        "week's numbers until your session with Dr. Harris. Reply with how the knee feels today."
    )
    assert "LOAD_SPIKE" in hold["source"]
    assert by_key["msg_pain_ask"]["action"]["prefill"].startswith(
        "Hi Cole — Dr. Harris's team here. You said the knee is hurting more this week."
    )


def test_went_quiet_drafts_the_one_tap_check_in(db):
    from app.plan.next_steps import plan_next_steps

    rafael = db.get(Patient, "hirt-rafael")
    steps = plan_next_steps(db, rafael, _assessment(["WENT_QUIET"], level="medium"),
                            now=datetime.now(), last_checkin_at=datetime.now() - timedelta(days=3))
    by_key = {s["key"]: s for s in steps}
    assert by_key["msg_quiet_checkin"]["action"]["prefill"] == (
        "Hi Rafael — Dr. Harris's team here. Haven't heard from you in a few days — one tap: "
        "how's it going?"
    )
    # The existing check-in step still stands beside it.
    assert "send_checkin" in by_key


def test_the_composer_draft_falls_back_to_the_clinics_words(client):
    drafted = client.post("/api/patients/hirt-cole/messages/draft", json={}).json()
    assert drafted["provider"] == "fallback"
    assert "Your training load jumped this week" in drafted["message"]
    assert "how the knee feels today" in drafted["message"]
    quiet = client.post("/api/patients/hirt-rafael/messages/draft", json={}).json()
    assert "Haven't heard from you in a few days" in quiet["message"]


def test_site_words_and_dr_surnames():
    from app.plan.messages import site_word, surname_for_dr

    assert surname_for_dr("Dr. Sean Harris") == "Harris"
    assert surname_for_dr("Dr. Alvarez") == "Alvarez"
    assert surname_for_dr("Maya Torres, RN") == "Maya Torres, RN"
    assert site_word(SimpleNamespace(care_pathway="Achilles tendinopathy · progressive loading",
                                     procedure_display="")) == "Achilles"
    assert site_word(SimpleNamespace(care_pathway="Lumbar disc · return to lifting",
                                     procedure_display="")) == "back"
    assert site_word(SimpleNamespace(care_pathway=None, procedure_display="General care")) == "it"


# --- the check-in itself --------------------------------------------------------------------


@pytest.fixture()
def lifter(db):
    """A throwaway chart on the HIRT roster, forgotten afterwards."""
    made: list[str] = []
    counter = [0]

    def create(*, phone: str | None = None, pathway: str | None = hirt.PATHWAYS["hirt-cole"],
               surgical: bool = False) -> Patient:
        counter[0] += 1
        pid = f"hirt-test-{counter[0]}"
        patient = Patient(
            id=pid, name="Theo Lindqvist", initials="TL", age=33, sex="M",
            procedure_type=ProcedureType.TKA if surgical else ProcedureType.NONE,
            procedure_display=pathway or "General care",
            surgery_date=date.today() - timedelta(days=14),
            discharge_date=date.today() - timedelta(days=14),
            surgeon_id="ct_harris", assigned_provider_id="ct_gregg", hospital_id="hirt",
            phone=phone, care_pathway=pathway,
        )
        db.add(patient)
        db.commit()
        made.append(pid)
        return patient

    yield create

    for pid in made:
        db.execute(delete(CheckinInvite).where(CheckinInvite.patient_id == pid))
        db.commit()
        _forget_patient(db, pid)


def test_a_lifter_is_asked_the_lifter_check_in(db, lifter):
    assert tasks.checkin_qset(lifter()) == "checkin_lifter"
    assert tasks.checkin_qset(lifter(pathway="general_recovery")) == "checkin_general"
    assert tasks.checkin_qset(lifter(pathway=None)) == "checkin_general"
    assert tasks.checkin_qset(lifter(pathway=hirt.PATHWAYS["hirt-june"], surgical=True)) == "checkin"
    assert [q["id"] for q in tasks.LIFTER_CHECKIN_QUESTIONS] == [
        "pain", "swelling", "new_pain", "sleep", "program", "rpe", "minutes", "note",
    ]
    minutes = next(q for q in tasks.LIFTER_CHECKIN_QUESTIONS if q["id"] == "minutes")
    assert minutes["kind"] == "number"


def _observations(db, pid: str, metric: MetricType) -> list[Observation]:
    db.expire_all()
    return list(db.scalars(
        select(Observation).where(Observation.patient_id == pid, Observation.metric_type == metric)
        .order_by(Observation.id)
    ).all())


def test_completing_the_check_in_writes_load_program_and_the_transcript(client, db, lifter):
    patient = lifter()
    task, _ = tasks.create_task(db, patient, title="Daily check-in", kind="checkin", notify=False)
    assert tasks.question_set_key(task) == "checkin_lifter"
    token = tasks.mint_token(task)
    db.commit()

    page = client.get(f"/api/tasks/{token}").json()
    assert [q["id"] for q in page["task"]["questions"]][-3:] == ["rpe", "minutes", "note"]
    resp = client.post(f"/api/tasks/{token}", json={"answers": {
        "pain": 4, "swelling": "no", "new_pain": "yes", "sleep": "well", "program": "some",
        "rpe": 7, "minutes": 65, "note": "Sharp under the kneecap on the way down.",
    }})
    assert resp.status_code == 200, resp.text

    load = _observations(db, patient.id, MetricType.SESSION_LOAD)
    assert len(load) == 1 and load[0].value_num == 455.0 and load[0].is_patient_reported
    assert load[0].source_provider == "patient_reported" and load[0].unit == "au"
    done = _observations(db, patient.id, MetricType.PROGRAM_DONE)
    assert len(done) == 1 and done[0].value_num == 0.5

    lines = db.execute(
        select(CheckinMessage.text).join(Checkin, Checkin.id == CheckinMessage.checkin_id)
        .where(Checkin.patient_id == patient.id, CheckinMessage.who == "patient")
        .order_by(CheckinMessage.seq)
    ).scalars().all()
    assert "My pain is about 4 out of 10." in lines
    assert "There's a new pain that wasn't there at my last visit." in lines
    assert "I got some of today's program in." in lines
    assert "Today's training felt like a 7 out of 10." in lines
    assert "I trained for about 65 minutes." in lines
    # A new pain reaches the care team as an alert, not just a transcript.
    alerts = db.scalars(select(Notification).where(Notification.patient_id == patient.id)).all()
    assert any("new pain" in n.title for n in alerts)

    # The engine now reads the chart from what was reported.
    from app.engine.pipeline import run_patient

    bundle = run_patient(db, patient.id, force=True).analytics
    assert bundle["reported"]["load_days"] == 1 and bundle["reported"]["new_pain"] is True
    assert client.get(f"/api/patients/{patient.id}").json()["progress"]["program"]["done"] == 0.5


def test_a_rest_day_is_a_zero_not_a_gap(db, lifter):
    patient = lifter()
    task, _ = tasks.create_task(db, patient, title="Daily check-in", kind="checkin", notify=False)
    tasks.complete_task(db, task, {"pain": 2, "program": "all", "minutes": 0}, via="app")
    load = _observations(db, patient.id, MetricType.SESSION_LOAD)
    assert len(load) == 1 and load[0].value_num == 0.0
    lines = db.execute(
        select(CheckinMessage.text).join(Checkin, Checkin.id == CheckinMessage.checkin_id)
        .where(Checkin.patient_id == patient.id, CheckinMessage.who == "patient")
    ).scalars().all()
    assert "Rest day, no training today." in lines


def test_the_texted_conversation_reads_effort_and_minutes_tolerantly(db, lifter):
    patient = lifter(phone="+12815550199")
    task, _ = tasks.create_task(db, patient, title="Daily check-in", kind="checkin", notify=False)
    first = tasks.start_conversation(task)
    assert first.startswith("Daily check-in — 8 quick questions.")
    assert "How's the pain today" in first
    replies = ["3", "no", "nope", "slept ok", "all of them", "about an 8", "70 min"]
    for body in replies:
        reply, kind = tasks.advance_conversation(db, task, body)
        assert kind == "conversation_step", (body, reply)
    reply, kind = tasks.advance_conversation(db, task, "skip")
    assert kind == "task_completed", reply
    load = _observations(db, patient.id, MetricType.SESSION_LOAD)
    assert len(load) == 1 and load[0].value_num == 560.0
    assert load[0].value_json["rpe"] == 8 and load[0].value_json["minutes"] == 70


def test_the_web_form_serves_the_lifter_set_and_takes_its_numbers(client, db, lifter):
    patient = lifter()
    invite = client.post(f"/api/patients/{patient.id}/checkin-invite",
                         json={"phone": "+12815550198"}).json()
    token = invite["url"].rsplit("/", 1)[1]
    form = client.get(f"/api/checkin/{token}").json()
    assert form["qset"] == "checkin_lifter"
    assert [q["id"] for q in form["questions"]][:2] == ["pain", "swelling"]
    assert client.post(f"/api/checkin/{token}", json={"minutes": 900}).status_code == 422
    assert client.post(f"/api/checkin/{token}", json={"program": "most"}).status_code == 422
    ok = client.post(f"/api/checkin/{token}", json={
        "pain": 3, "program": "all", "rpe": 6, "minutes": 50, "sleep": "well",
    })
    assert ok.status_code == 200, ok.text
    load = _observations(db, patient.id, MetricType.SESSION_LOAD)
    assert len(load) == 1 and load[0].value_num == 300.0
    assert _observations(db, patient.id, MetricType.PROGRAM_DONE)[0].value_num == 1.0
    # The link is single use, like before.
    assert client.post(f"/api/checkin/{token}", json={"pain": 3}).status_code == 410


def test_the_recovery_form_is_unchanged_for_a_surgical_patient(client):
    invite = client.post("/api/patients/steve/checkin-invite", json={"phone": "+15124917035"}).json()
    token = invite["url"].rsplit("/", 1)[1]
    form = client.get(f"/api/checkin/{token}").json()
    assert form["qset"] == "checkin"
    assert [q["id"] for q in form["questions"]] == [
        "pain", "swelling", "fever", "sleep", "exercises", "note",
    ]


def test_reported_observations_need_both_effort_and_minutes():
    from app.tasks.reported import program_done, reported_observations, session_load

    at = datetime(2026, 11, 6, 20, 40)
    assert session_load({"rpe": 7}) is None
    assert session_load({"minutes": 40}) is None
    assert session_load({"minutes": 0}) == 0.0
    assert session_load({"rpe": "8", "minutes": "70"}) == 560.0
    assert program_done({"program": "some"}) == 0.5 and program_done({}) is None
    rows = reported_observations("x", {"rpe": 7, "minutes": 65, "program": "all"}, at)
    assert [str(r.metric_type) for r in rows] == ["session_load", "program_done"]
    assert rows[0].local_date == date(2026, 11, 6) and rows[0].end_time == at
    assert reported_observations("x", {"pain": 3}, at) == []
